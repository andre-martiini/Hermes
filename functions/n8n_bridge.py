
import requests
import os
import json
from datetime import datetime

# --- CONFIGURAÇÕES ---
# O ideal é colocar estas URLs nas variáveis de ambiente do Firebase (firebase functions:config:set)
N8N_ETL_WEBHOOK_URL = os.environ.get("N8N_ETL_WEBHOOK_URL", "https://seu-n8n.webhook.com/ingestion-bridge")
N8N_API_KEY = os.environ.get("N8N_API_KEY", "")

class N8NBridge:
    """
    Módulo de integração com o Sistema Digestivo (n8n).
    Responsável por delegar limpeza, transcrição (Whisper) e conversão de PDFs complexos.
    """

    @staticmethod
    def delegate_ingestion(file_data, metadata):
        """
        Envia um arquivo para o n8n processar.
        - file_data: bytes ou URL do arquivo (Google Drive)
        - metadata: dicionário com filename, mime_type, extension, source
        """
        
        # Modo de Segurança: Se não houver URL, não falha, apenas avisa.
        if "seu-n8n.webhook.com" in N8N_ETL_WEBHOOK_URL:
            print("⚠️ n8n Bridge: URL de produção não configurada em N8N_ETL_WEBHOOK_URL.")
            return {
                "status": "not_configured",
                "message": "Delegação n8n desativada (URL padrão detectada).",
                "fallback_needed": True
            }

        payload = {
            "source": "hermes_ingestion_gate",
            "origin_system": "Hermes-V2",
            "timestamp": datetime.now().isoformat(),
            "metadata": json.dumps(metadata)
        }

        # Preparar envio
        try:
            # Se for bytes (upload direto no app)
            if isinstance(file_data, bytes):
                files = {'file': (metadata.get('filename', 'upload'), file_data)}
                response = requests.post(
                    N8N_ETL_WEBHOOK_URL,
                    data=payload,
                    files=files,
                    headers={"X-N8N-API-KEY": N8N_API_KEY} if N8N_API_KEY else {},
                    timeout=120 # Digestão (Whisper/OCR) pode levar tempo
                )
            # Se for uma URL (Google Drive)
            else:
                payload['file_url'] = file_data
                response = requests.post(
                    N8N_ETL_WEBHOOK_URL,
                    json=payload,
                    headers={"X-N8N-API-KEY": N8N_API_KEY} if N8N_API_KEY else {},
                    timeout=120
                )
            
            response.raise_for_status()
            print(f"✅ n8n Bridge: Arquivo {metadata.get('filename')} enviado com sucesso.")
            return response.json()

        except Exception as e:
            print(f"❌ n8n Bridge Error: Falha ao delegar para n8n: {str(e)}")
            return {
                "status": "error",
                "error": str(e),
                "fallback_needed": True
            }

    @staticmethod
    def handle_n8n_callback(processed_payload):
        """
        Processa o retorno do n8n após a limpeza.
        """
        # Aqui o Hermes recebe o texto limpo, tags sugeridas e localização sugerida
        return {
            "status": "received",
            "content_verified": "text_logic_markdown" in processed_payload
        }
