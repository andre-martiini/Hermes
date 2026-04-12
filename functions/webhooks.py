
from firebase_functions import https_fn
from firebase_admin import firestore
import json
from datetime import datetime

@https_fn.on_request()
def n8n_callback_handler(req: https_fn.Request) -> https_fn.Response:
    """
    Endpoint que recebe os dados 'digeridos' pelo n8n.
    Implementa a fase final da Metodologia SIPOC (Output para o Cliente/Memória).
    """
    # 1. Segurança e Método
    if req.method != "POST":
        return https_fn.Response("Permitido apenas POST", status=405)

    try:
        # Tenta extrair o JSON
        try:
            data = req.get_json()
        except:
            return https_fn.Response("JSON inválido", status=400)

        db = firestore.client()

        # Extração de Campos Estruturados (Paradigma V2)
        ref_id = data.get('ref_id', 'manual_upload')
        content = data.get('text_logic_markdown', '')
        
        if not content:
            return https_fn.Response("Conteúdo vazio não permitido", status=400)

        # Análise Sugerida pelo n8n (AI)
        analysis = data.get('analysis', {})
        
        # Mapeamento Espacial (MemPalace)
        wing = analysis.get('wing', 'captura')
        room = analysis.get('room', 'biblioteca')
        drawer = analysis.get('drawer', 'entrada_automática')

        # 2. Construção do Artefacto de Conhecimento
        knowledge_item = {
            'titulo': data.get('title', f"Processado: {datetime.now().strftime('%Y-%m-%d %H:%M')}"),
            'texto_bruto': content,
            'tipo_arquivo': 'md',
            'data_criacao': firestore.SERVER_TIMESTAMP,
            'fonte_origem': 'n8n_sensory_pipeline',
            'paradigm_version': "2.0",
            'memory_location': {
                'wing': wing,
                'room': room,
                'drawer': drawer,
                'path_label': f"{wing} / {room} / {drawer}".lower().replace(' ', '_')
            },
            'tags': analysis.get('tags', ['n8n', 'reflex_ingestion']),
            'last_sync_date': datetime.now().isoformat()
        }

        # 3. Gravação no Firestore (Base de Conhecimento RAG)
        doc_ref = db.collection('conhecimento').document()
        doc_ref.set(knowledge_item)

        print(f"✅ n8n Callback: Novo documento gerado [{doc_ref.id}]")

        return https_fn.Response(
            json.dumps({
                "status": "success", 
                "doc_id": doc_ref.id,
                "paradigm": "v2.0"
            }), 
            status=200,
            mimetype="application/json"
        )

    except Exception as e:
        print(f"❌ Erro Crítico no Webhook n8n: {str(e)}")
        return https_fn.Response(
            json.dumps({"status": "error", "message": str(e)}),
            status=500,
            mimetype="application/json"
        )
