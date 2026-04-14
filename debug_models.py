from google import genai
import firebase_admin
from firebase_admin import firestore

def list_all():
    db = firestore.client()
    keys_doc = db.collection('system').document('api_keys').get()
    api_key = keys_doc.to_dict().get('gemini_api_key')
    client = genai.Client(api_key=api_key)
    for m in client.models.list():
        print(f"Name: {m.name}, Methods: {m.supported_methods}")

if __name__ == "__main__":
    firebase_admin.initialize_app()
    list_all()
