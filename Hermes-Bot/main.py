import os
import telebot
from google import genai
from google.genai import types
import firebase_admin
from firebase_admin import credentials, firestore
import datetime

# Inicialização do Firebase (Aponte para o arquivo que está na sua pasta)
# Certifique-se de que o nome coincide com o arquivo baixado
if not firebase_admin._apps:
    # O arquivo está no diretório pai
    path_key = os.path.join("..", "firebase_service_account_key.json")
    cred = credentials.Certificate(path_key)
    firebase_admin.initialize_app(cred)

db = firestore.client()

# --- CONFIGURAÇÕES ---
TELEGRAM_TOKEN = "8541098493:AAGGQCjXV9T7yazGVNSpNEepOYvkqvAXOz8"
GEMINI_API_KEY = "AIzaSyBlX78LneusUNi-C-4W_VBVZd_vDvIC1yc"

# Inicializa o Cliente Google GenAI (Novo SDK)
client = genai.Client(api_key=GEMINI_API_KEY)

# Configuração da busca do Google (Grounding)
google_search_tool = types.Tool(
    google_search=types.GoogleSearch()
)

model_id = "gemini-2.5-flash-lite"
system_instruction = """
Você é o HERMES, o braço direito e assistente pessoal de elite do André Araújo Martini.
Sua personalidade é uma mistura de Jarvis (Homem de Ferro) com um Gerente de Projetos extremamente eficiente.

### PERSONALIDADE E TOM:
1. **Familiar e Respeitoso**: Sempre chame o usuário de "André". Use um tom formal, porém próximo, como um assistente de confiança que trabalha com ele há anos.
2. **Eficiência Implacável**: Suas respostas devem ser organizadas. Se o André perguntar sobre o dia dele, traga as informações divididas por módulos (Financeiro, Saúde, Tarefas).
3. **Proatividade**: Se o André registrar uma despesa alta, você pode comentar algo breve e profissional como "Registrado, André. Vou atualizar seu teto de gastos mensal."
4. **Precisão**: Você não "acha", você "consulta". Se não encontrar algo no Firestore, peça os detalhes de forma educada.

### CONHECIMENTO DO ECOSSISTEMA:
Você gerencia os seguintes pilares para o André:
- **Tarefas & PGC**: Gerenciamento de metas institucionais e documentos vinculados (sempre forneça os links do Drive quando encontrados no 'pool_dados').
- **Finanças**: Controle rigoroso de gastos, metas e orçamentos mensais.
- **Saúde**: Guardião do bem-estar, acompanhando peso e hábitos diários.
- **Sistemas**: Gestor de projetos de software e seus ciclos de vida.

### EXEMPLOS DE INTERAÇÃO:
- "André, localizei os documentos do projeto. Aqui estão os links do Google Drive para sua revisão..."
- "Gasto registrado com sucesso, André. Gostaria que eu verificasse se isso impacta sua meta de economia deste mês?"
- "Excelente escolha em manter o hábito 'Sem Açúcar' hoje, André. Continue assim!"

### REGRAS CRÍTICAS:
- Responda sempre em Português do Brasil.
- Use Markdown para deixar a leitura agradável (negrito, listas, etc).
- Nunca invente dados. Se não está no Firestore, não existe para você.
"""

bot = telebot.TeleBot(TELEGRAM_TOKEN)

def consultar_hermes(colecao: str, campo: str = None, valor: str = None, limite: int = 5):
    """
    Consulta informações em qualquer coleção do sistema Hermes no Firestore.
    Use para buscar tarefas, transações, pesos, etc.
    Se 'campo' e 'valor' forem fornecidos, filtra os resultados.
    """
    try:
        ref = db.collection(colecao)
        if campo and valor:
            # Busca aproximada não existe no Firestore nativo, então buscamos por igualdade
            # ou usamos uma lógica simples aqui.
            docs = ref.where(campo, "==", valor).limit(limite).stream()
        else:
            docs = ref.order_by("created_at", direction=firestore.Query.DESCENDING).limit(limite).stream()
        
        resultados = []
        for doc in docs:
            d = doc.to_dict()
            d['id'] = doc.id
            # Limpa o timestamp do firestore para serialização
            if 'created_at' in d: d['created_at'] = str(d['created_at'])
            resultados.append(d)
        
        if not resultados:
            return f"Nenhum registro encontrado na coleção '{colecao}'."
        return resultados
    except Exception as e:
        return f"Erro na consulta: {str(e)}"

def registrar_tarefa_hermes(titulo: str, projeto: str = "Geral", notas: str = "", prioridade: str = "Média", data_limite: str = None):
    """
    Registra uma nova tarefa no sistema.
    """
    try:
        agora = datetime.datetime.now()
        nova_tarefa = {
            "titulo": titulo,
            "projeto": projeto,
            "data_limite": data_limite or agora.strftime("%Y-%m-%d"),
            "status": "em andamento",
            "prioridade": prioridade,
            "notas": notas,
            "horario_inicio": agora.strftime("%H:%M"),
            "pool_dados": [],
            "created_at": firestore.SERVER_TIMESTAMP
        }
        res = db.collection("tarefas").add(nova_tarefa)
        return f"Tarefa '{titulo}' registrada com sucesso (ID: {res[1].id})."
    except Exception as e:
        return f"Erro: {str(e)}"

def registrar_transacao_financeira(descricao: str, valor: float, categoria: str, sprint: int = 1):
    """
    Registra uma transação (despesa) no módulo financeiro.
    """
    try:
        agora = datetime.datetime.now()
        doc = {
            "description": descricao,
            "amount": valor,
            "date": agora.strftime("%Y-%m-%d"),
            "category": categoria,
            "sprint": sprint,
            "created_at": firestore.SERVER_TIMESTAMP
        }
        res = db.collection("finance_transactions").add(doc)
        return f"Gasto de R$ {valor:.2f} com '{descricao}' registrado no Financeiro."
    except Exception as e:
        return f"Erro financeiro: {str(e)}"

def registrar_saude(tipo: str, valor: any, notas: str = ""):
    """
    Registra dados de saúde. 
    tipo: 'peso' (valor deve ser número) ou 'habito' (valor deve ser dict com hábitos).
    """
    try:
        agora = datetime.datetime.now()
        hoje = agora.strftime("%Y-%m-%d")
        if tipo == 'peso':
            db.collection("health_weights").add({
                "date": hoje,
                "weight": float(valor),
                "created_at": firestore.SERVER_TIMESTAMP
            })
            return f"Peso de {valor}kg registrado para hoje."
        elif tipo == 'habito':
            # Habitos costumam usar a data como ID
            db.collection("health_daily_habits").document(hoje).set(valor, merge=True)
            return "Hábitos diários atualizados."
    except Exception as e:
        return f"Erro saúde: {str(e)}"

def buscar_documentos_tarefa(titulo_tarefa: str):
    """
    Busca especificamente os links/documentos de uma tarefa pelo título.
    """
    try:
        docs = db.collection("tarefas").where("titulo", "==", titulo_tarefa).limit(1).stream()
        for doc in docs:
            data = doc.to_dict()
            pool = data.get("pool_dados", [])
            if not pool:
                return f"A tarefa '{titulo_tarefa}' não possui documentos vinculados."
            links = [f"- {item.get('nome', 'Sem nome')}: {item.get('valor')}" for item in pool]
            return "Documentos encontrados:\n" + "\n".join(links)
        return "Tarefa não encontrada para busca de documentos."
    except Exception as e:
        return f"Erro na busca de documentos: {str(e)}"

# Lista expandida de ferramentas
tools_list = [
    consultar_hermes, 
    registrar_tarefa_hermes, 
    registrar_transacao_financeira, 
    registrar_saude,
    buscar_documentos_tarefa
]

# Cria o chat com a configuração correta de ferramentas
chat = client.chats.create(model=model_id, config=types.GenerateContentConfig(
    system_instruction=system_instruction,
    tools=tools_list,
    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=False)
))



@bot.message_handler(func=lambda m: True)
def responder(mensagem):
    try:
        bot.send_chat_action(mensagem.chat.id, 'typing')
        response = chat.send_message(mensagem.text)
        bot.reply_to(mensagem, response.text, parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(mensagem, f"Erro: {str(e)}")

@bot.message_handler(content_types=['voice'])
@bot.message_handler(content_types=['voice'])
def processar_audio(mensagem):
    try:
        bot.send_chat_action(mensagem.chat.id, 'record_audio')
        file_info = bot.get_file(mensagem.voice.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        nome_arquivo = f"audio_{mensagem.chat.id}.ogg"
        with open(nome_arquivo, 'wb') as f:
            f.write(downloaded_file)
        
        # Lendo o arquivo para enviar como bytes
        with open(nome_arquivo, 'rb') as f:
            audio_data = f.read()

        # A forma correta de enviar múltiplos componentes no SDK novo:
        # Passamos uma lista de Partes diretamente no argumento 'message'
        response = chat.send_message(message=[
            types.Part.from_bytes(data=audio_data, mime_type="audio/ogg"),
            types.Part.from_text(text="Transcreva e execute o comando contido neste áudio conforme as regras do sistema Hermes.")
        ])
        
        bot.reply_to(mensagem, response.text, parse_mode="Markdown")
        
        # Limpeza
        os.remove(nome_arquivo)
        
    except Exception as e:
        bot.reply_to(mensagem, f"Erro no áudio: {str(e)}")



print("HERMES Online com SDK Novo!")
bot.infinity_polling()