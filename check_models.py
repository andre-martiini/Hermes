from google import genai
import firebase_admin
from firebase_admin import firestore

def list_models():
    try:
        if not firebase_admin._apps:
            firebase_admin.initialize_app()
        db = firestore.client()
        keys_doc = db.collection('system').document('api_keys').get()
        api_key = keys_doc.to_dict().get('gemini_api_key') if keys_doc.exists else None
        
        client = genai.Client(api_key=api_key)
        print("Modelos disponíveis para embedding:")
        for m in client.models.list():
            if 'embedContent' in m.supported_methods:
                print(f"- {m.name}")
    except Exception as e:
        print(f"Erro: {e}")

if __name__ == "__main__":
    list_models()
