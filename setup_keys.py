import firebase_admin
from firebase_admin import credentials, firestore
import os

try:
    firebase_admin.initialize_app()
    print("Firebase Admin inicializado.")
except ValueError:
    print("Firebase Admin já inicializado.")
    # Suponho que use Application Default Credentials (gcloud auth application-default login)
    pass
except Exception as e:
    print(f"Erro ao inicializar Firebase Admin: {e}")
    # Tentar com credencial de serviço se existir arquivo
    cred_path = "firebase_service_account_key.json"
    if os.path.exists(cred_path):
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)
        print(f"Usando chave de serviço: {cred_path}")
    else:
        print("Nenhuma credencial encontrada. Execute 'gcloud auth application-default login' se local.")

try:
    db = firestore.client()
    
    print("\n--- Configuração de Chaves de API (system/api_keys) ---")
    print("Mantenha o campo vazio para não alterar o valor existente.\n")

    groq = input("Digite a nova GROQ_API_KEY: ").strip()
    gemini = input("Digite a nova GEMINI_API_KEY: ").strip()

    doc_ref = db.collection('system').document('api_keys')
    
    # Busca dados atuais para merge
    doc = doc_ref.get()
    current_data = doc.to_dict() if doc.exists else {}

    updates = {}
    if groq:
        updates['groq_api_key'] = groq
    elif 'groq_api_key' not in current_data:
        print("AVISO: Chave GROQ não definida!")

    if gemini:
        updates['gemini_api_key'] = gemini
    elif 'gemini_api_key' not in current_data:
        print("AVISO: Chave Gemini não definida!")

    if updates:
        doc_ref.set(updates, merge=True)
        print("\nSucesso! Chaves atualizadas no Firestore.")
    else:
        print("\nNenhuma alteração realizada.")

except Exception as e:
    print(f"\nErro crítico: {e}")
    print("Verifique se você tem permissão ou execute 'gcloud auth application-default login'.")
