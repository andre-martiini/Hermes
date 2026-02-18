
import os

file_path = 'functions/main.py'

# Read potentially corrupted file
with open(file_path, 'rb') as f:
    content = f.read()

# Try to decode
try:
    # First try utf-8
    text = content.decode('utf-8')
except UnicodeDecodeError:
    try:
        # Try UTF-16 (little endian is common on windows)
        text = content.decode('utf-16')
    except UnicodeDecodeError:
        # Fallback to latin-1
        text = content.decode('latin-1')

# Trim corrupted part if present
marker = "@https_fn.on_call()"
# We know the original file ended around line 433 with proper code.
# The corrupted part starts after the last valid function `upload_to_drive`.
# `upload_to_drive` ends... let's check.
# We can search for `def transcrever_audio` or similar from the bad append.
# Or better, just strip trailing whitespace and find the last `upload_to_drive` block end.
# But simply searching for the new function name and cutting before it is safer.

split_marker = "def transcrever_audio"
if split_marker in text:
    # Find the decorator before it
    # We'll just cut at global scope level
    idx = text.rfind("@https_fn.on_call", 0, text.find(split_marker))
    if idx != -1:
        text = text[:idx]

text = text.rstrip() + "\n\n"

# New function code
new_code = r'''
@https_fn.on_call()
def transcrever_audio(req: https_fn.CallableRequest):
    """
    Recebe áudio em Base64, transcreve com Groq (Whisper-Large-V3-Turbo) e refina com Gemini.
    """
    import base64
    import tempfile
    import os
    # Instale: pip install groq google-generativeai
    from groq import Groq
    import google.generativeai as genai

    data = req.data
    audio_base64 = data.get('audioBase64')

    if not audio_base64:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
            message="Áudio não fornecido."
        )

    # Buscar chaves de API no Firestore
    try:
        # Import local (dentro da função ou escopo global se preferir, mas aqui segue o padrão do fix)
        # Assumindo que get_db já existe no main.py. Mas o fix_main.py injeta apenas ESTA função?
        # Sim, ele injeta `transcrever_audio`.
        # Precisamos garantir que `get_db` esteja disponível ou usar firestore.client() direto?
        # O arquivo main.py tem `from firebase_admin import firestore` e `initialize_app`.
        # Melhor usar `firestore.client()` diretamente para garantir, já que `get_db` é custom.
        # Mas `main.py` tem `get_db` definido no topo. Vamos usar `get_db()` para consistência,
        # assumindo que o `fix_main.py` insere isso num arquivo que tem `get_db`.
        
        # Como não temos certeza se `get_db` está acessível no escopo (python é permissivo),
        # vamos usar o padrão seguro: importar firestore.
        from firebase_admin import firestore
        db = firestore.client()
        keys_doc = db.collection('system').document('api_keys').get()
        
        if not keys_doc.exists:
             raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.FAILED_PRECONDITION, 
                message="Chaves de API não configuradas (system/api_keys)."
            )
            
        keys = keys_doc.to_dict()
        GROQ_API_KEY = keys.get('groq_api_key')
        GEMINI_API_KEY = keys.get('gemini_api_key')
        
    except Exception as e:
        print(f"Erro ao buscar chaves: {e}")
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INTERNAL,
            message="Erro interno de configuração."
        )

    temp_path = None
    try:
        # 1. Converter Base64 para arquivo temporário
        # b64decode retorna bytes
        try:
            audio_bytes = base64.b64decode(audio_base64)
        except Exception:
             raise https_fn.HttpsError(
                code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
                message="Base64 inválido."
            )
        
        # Cria um arquivo temporário físico para o Groq poder ler
        # O sufixo .m4a é importante para o ffmpeg interno do whisper identificar o formato se necessário
        with tempfile.NamedTemporaryFile(suffix=".m4a", delete=False) as temp_file:
            temp_file.write(audio_bytes)
            temp_path = temp_file.name

        # 2. Transcrição via Groq
        client = Groq(api_key=GROQ_API_KEY)
        
        with open(temp_path, "rb") as file_stream:
            transcription = client.audio.transcriptions.create(
                file=(os.path.basename(temp_path), file_stream), 
                model="whisper-large-v3-turbo",
                response_format="json",
                language="pt",
                temperature=0.0
            )

        texto_bruto = transcription.text

        # 3. Refinamento via Gemini Flash
        genai.configure(api_key=GEMINI_API_KEY)
        # Usando o modelo solicitado (2.5-flash)
        model = genai.GenerativeModel("gemini-2.5-flash")

        prompt = f"""
        Atue como um redator especialista. O texto a seguir é uma transcrição de voz bruta.
        Sua tarefa:
        1. Corrigir pontuação e gramática (pt-BR).
        2. Remover vícios de linguagem (né, tipo, ahn).
        3. Manter o tom original e termos técnicos.
        4. Retorne APENAS o texto corrigido, sem introduções.
        
        Texto: "{texto_bruto}"
        """
        
        response = model.generate_content(prompt)
        texto_refinado = response.text

        return {
            "raw": texto_bruto,
            "refined": texto_refinado
        }

    except Exception as e:
        print(f"Erro na transcrição: {e}")
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INTERNAL,
            message=f"Falha ao processar áudio: {str(e)}"
        )
    finally:
        # Limpeza
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
'''

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(text + new_code)

print("File fixed and updated.")
