
import firebase_admin
from firebase_admin import credentials, firestore

def check_fluxo():
    cred = credentials.Certificate('firebase_service_account_key.json')
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
    
    db = firestore.client()
    
    print("\n--- TOKENS RECENTES (Últimos 5) ---")
    tokens = db.collection('fcm_tokens').order_by('last_updated', direction='DESCENDING').limit(5).get()
    for t in tokens:
        d = t.to_dict()
        print(f"Token: {t.id[:30]}... | UserAgent: {d.get('userAgent', 'N/A')[:30]}... | Atualizado: {d.get('last_updated')}")

    print("\n--- NOTIFICAÇÕES RECENTES (Últimas 5) ---")
    notifs = db.collection('notificacoes').order_by('timestamp', direction='DESCENDING').limit(5).get()
    for n in notifs:
        d = n.to_dict()
        print(f"Título: {d.get('title')} | Mensagem: {d.get('message')[:40]}... | Criado: {d.get('timestamp')} | Push Enviado? {d.get('sent_to_push')}")

if __name__ == "__main__":
    check_fluxo()
