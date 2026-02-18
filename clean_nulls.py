
import re

file_path = "functions/main.py"
try:
    with open(file_path, "rb") as f:
        content = f.read()

    # Remover bytes nulos e caracteres estranhos espaçados
    cleaned_content = content.replace(b'\x00', b'')
    
    # Decodificar para string (tentando utf-8, fallback para latin-1 se precisar)
    try:
        text_content = cleaned_content.decode('utf-8')
    except UnicodeDecodeError:
        text_content = cleaned_content.decode('latin-1')
        
    # Salvar de volta
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(text_content)
        
    print(f"Limpeza concluída em {file_path}")

except Exception as e:
    print(f"Erro na limpeza: {e}")
