from google import genai
import firebase_admin
from firebase_admin import firestore, credentials

def list_models():
    try:
        # Tenta inicializar com a chave de serviço se disponível
        if not firebase_admin._apps:
            try:
                cred = credentials.Certificate('firebase_service_account_key.json')
                firebase_admin.initialize_app(cred)
            except:
                firebase_admin.initialize_app()
        
        db = firestore.client()
        keys_doc = db.collection('system').document('api_keys').get()
        api_key = keys_doc.to_dict().get('gemini_api_key') if keys_doc.exists else None
        
        if not api_key:
            print("API Key não encontrada.")
            return

        client = genai.Client(api_key=api_key)
        print("Modelos disponíveis:")
        for m in client.models.list():
            methods = m.supported_methods if hasattr(m, 'supported_methods') else []
            if 'embedContent' in methods:
                print(f"- {m.name} (Methods: {methods})")
            elif 'generateContent' in methods:
                 # print(f"- {m.name} (Generate)")
                 pass
    except Exception as e:
        print(f"Erro: {e}")

if __name__ == "__main__":
    list_models()
