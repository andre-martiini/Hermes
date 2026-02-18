
import firebase_admin
from firebase_admin import credentials, messaging, firestore

def send_to_last_token():
    try:
        cred = credentials.Certificate('firebase_service_account_key.json')
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)
        
        db = firestore.client()
        # Pega o token mais recente (provavelmente o do seu celular pós-reset)
        tokens = db.collection('fcm_tokens').order_by('last_updated', direction='DESCENDING').limit(1).get()
        
        if not tokens:
            print("Nenhum token encontrado.")
            return

        token_doc = tokens[0]
        token_id = token_doc.id
        print(f"Enviando para o token mais recente: {token_id[:20]}...")
        
        message = messaging.Message(
            notification=messaging.Notification(
                title='Teste Final (Script)',
                body='Se chegou, o token é válido!',
            ),
            token=token_id,
        )

        response = messaging.send(message)
        print('Sucesso! ID da mensagem:', response)
    except Exception as e:
        print('Erro:', e)

if __name__ == "__main__":
    send_to_last_token()
