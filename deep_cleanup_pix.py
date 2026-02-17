
import firebase_admin
from firebase_admin import credentials, firestore

def deep_cleanup():
    if not firebase_admin._apps:
        cred = credentials.Certificate('firebase_service_account_key.json')
        firebase_admin.initialize_app(cred)
    
    db = firestore.client()
    
    print("--- LIMPANDO LANÇAMENTOS PIX ANTIGOS/DUPLICADOS ---")
    
    colls = ['finance_transactions', 'finance_income']
    for c in colls:
        docs = db.collection(c).get()
        for doc in docs:
            desc = doc.to_dict().get('description', '')
            if desc.startswith('Pix:'):
                # Se a data for de hoje (2026-02-16) e tiver o formato TXX:XX:XX (gerado pelo now())
                # nós removemos para reconstruir com a data real do e-mail.
                date = doc.to_dict().get('date', '')
                if '2026-02-16T' in date:
                    print(f"Removendo item temporário: {desc} ({date})")
                    doc.reference.delete()
                    
    # Limpa o cache de IDs para re-sincronizar tudo com datas reais
    db.collection('system').document('processed_emails').delete()
    print("\nBanco de Pix limpo. Iniciando sincronização limpa...")

if __name__ == "__main__":
    deep_cleanup()
