import os
import io
import base64
import tempfile
import html2text
from bs4 import BeautifulSoup
from typing import Dict, Any

def buscar_e_analisar_email(query: str, max_results: int = 5) -> str:
    """
    Busca e analisa e-mails no Gmail usando uma query estruturada.
    Retorna o texto higienizado e o conteúdo de anexos (PDF, CSV).
    Não baixe anexos se não for necessário.

    Args:
        query: Query de busca padrão do Gmail (ex: 'from:nome@empresa.com newer_than:2d').
        max_results: Número máximo de e-mails a processar (limite: 5).
    """
    try:
        from main import get_gmail_service, get_db
        service = get_gmail_service()
    except Exception as e:
        return f"⚠️ Erro ao inicializar serviço do Gmail: {e}"

    try:
        results = service.users().messages().list(userId='me', q=query, maxResults=max_results).execute()
        messages = results.get('messages', [])

        if not messages:
            return "Nenhum e-mail encontrado para a query informada."

        output = []
        for msg in messages:
            msg_id = msg['id']
            full_msg = service.users().messages().get(userId='me', id=msg_id, format='full').execute()

            payload = full_msg.get('payload', {})
            headers = payload.get('headers', [])

            subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), 'Sem Assunto')
            sender = next((h['value'] for h in headers if h['name'].lower() == 'from'), 'Desconhecido')
            date_str = next((h['value'] for h in headers if h['name'].lower() == 'date'), '')

            # Extrair texto principal
            text_parts = []
            html_parts = []
            attachments = []

            def walk_parts(part):
                mime_type = part.get('mimeType')
                body = part.get('body', {})
                data = body.get('data')
                part_id = part.get('partId')
                filename = part.get('filename', '')

                if filename and body.get('attachmentId'):
                    # Pular imagens pequenas (<50kb) ou anexos irrelevantes
                    size = body.get('size', 0)
                    if size < 50000 and mime_type.startswith('image/'):
                        pass
                    elif mime_type in ['application/pdf', 'text/csv']:
                        attachments.append({
                            'id': body['attachmentId'],
                            'filename': filename,
                            'mime_type': mime_type,
                            'size': size
                        })
                elif data:
                    if mime_type == 'text/plain':
                        text_parts.append(base64.urlsafe_b64decode(data + '=' * (-len(data) % 4)).decode('utf-8', errors='replace'))
                    elif mime_type == 'text/html':
                        html_parts.append(base64.urlsafe_b64decode(data + '=' * (-len(data) % 4)).decode('utf-8', errors='replace'))

                if 'parts' in part:
                    for subpart in part['parts']:
                        walk_parts(subpart)

            walk_parts(payload)

            clean_text = ""
            if text_parts:
                clean_text = "\n".join(text_parts)
            elif html_parts:
                h = html2text.HTML2Text()
                h.ignore_links = False
                h.ignore_images = True
                h.body_width = 0
                clean_text = "\n".join([h.handle(html) for html in html_parts])

            # Limpar whitespace em excesso
            clean_text = "\n".join([line for line in clean_text.split("\n") if line.strip()])

            msg_str = f"--- E-MAIL ---\nID: {msg_id}\nDe: {sender}\nAssunto: {subject}\nData: {date_str}\n\n[Corpo do E-mail]\n{clean_text}\n"

            # Processar anexos (apenas PDF e CSV relevantes)
            for att in attachments:
                att_id = att['id']
                att_name = att['filename']
                msg_str += f"\n[Anexo: {att_name}]\n"

                try:
                    att_obj = service.users().messages().attachments().get(userId='me', messageId=msg_id, id=att_id).execute()
                    file_data = base64.urlsafe_b64decode(att_obj['data'])

                    with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(att_name)[1]) as temp_file:
                        temp_file.write(file_data)
                        temp_path = temp_file.name

                    try:
                        if att['mime_type'] == 'application/pdf':
                            import pdfplumber
                            with pdfplumber.open(temp_path) as pdf:
                                extracted_text = ""
                                for page in pdf.pages[:10]: # Limite 10 páginas
                                    text = page.extract_text()
                                    if text: extracted_text += text + "\n"
                            msg_str += f"Conteúdo do PDF (Extração):\n{extracted_text[:3000]}\n"
                        elif att['mime_type'] == 'text/csv':
                            import csv
                            with open(temp_path, 'r', encoding='utf-8', errors='replace') as f:
                                reader = csv.reader(f)
                                lines = [",".join(row) for i, row in enumerate(reader) if i < 50]
                                msg_str += f"Conteúdo do CSV (Primeiras 50 linhas):\n" + "\n".join(lines) + "\n"
                    finally:
                        # OBRIGATORIAMENTE REMOVER ARQUIVO
                        if os.path.exists(temp_path):
                            os.remove(temp_path)
                except Exception as e_att:
                    msg_str += f"(Erro ao processar anexo {att_name}: {e_att})\n"

            output.append(msg_str)

        return "\n\n==========================\n\n".join(output)
    except Exception as e:
        return f"⚠️ Erro ao processar e-mails: {str(e)}"
