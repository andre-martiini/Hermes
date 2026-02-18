
import firebase_admin
from firebase_admin import credentials, firestore

def check_notifications():
    try:
        cred = credentials.Certificate('firebase_service_account_key.json')
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)
        db = firestore.client()
        
        # Check fcm_tokens
        tokens = db.collection('fcm_tokens').get()
        print(f"Tokens FCM encontrados: {len(tokens)}")
        for t in tokens:
            data = t.to_dict()
            print(f"- Token ID: {t.id} | Plataforma: {data.get('platform')} | Ultima atualizacao: {data.get('last_updated')}")
            
        # Check notifications
        notifs = db.collection('notificacoes').order_by('timestamp', direction='DESCENDING').limit(5).get()
        print(f"\nUltimas 5 notificacoes:")
        for n in notifs:
            data = n.to_dict()
            print(f"- {data.get('timestamp')} | {data.get('title')} | Sent to Push: {data.get('sent_to_push')}")
            
    except Exception as e:
        print(f"Erro: {e}")

if __name__ == "__main__":
    check_notifications()
