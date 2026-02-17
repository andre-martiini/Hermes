
import firebase_admin
from firebase_admin import credentials, firestore

def cleanup():
    if not firebase_admin._apps:
        cred = credentials.Certificate('firebase_service_account_key.json')
        firebase_admin.initialize_app(cred)
    
    db = firestore.client()
    
    print("--- INICIANDO LIMPEZA DE DUPLICATAS DE PIX ---")
    
    collections = ['finance_transactions', 'finance_income']
    for coll_name in collections:
        print(f"\nAnalisando {coll_name}...")
        docs = db.collection(coll_name).get()
        seen = set()
        deleted_count = 0
        
        for doc in docs:
            data = doc.to_dict()
            desc = data.get('description', '')
            # Apenas processamos itens de Pix
            if not desc.startswith('Pix:'):
                continue
                
            amount = data.get('amount')
            date = data.get('date', '')
            
            # Identificador único para a transação
            # Se tiver o mesmo título, valor e data (mesmo que seja a data genérica de hoje), é duplicata.
            key = (desc, amount, date)
            
            if key in seen:
                print(f"Limpando duplicata: {desc} (R$ {amount})")
                doc.reference.delete()
                deleted_count += 1
            else:
                seen.add(key)
        
        print(f"Concluído. {deleted_count} duplicatas removidas de {coll_name}.")

    # Resetar os IDs processados para garantir que a próxima sincronização (com as novas regras) 
    # pegue tudo com as datas corretas e os IDs de e-mail salvos.
    print("\nLimpando lista de e-mails processados para re-sincronização limpa...")
    db.collection('system').document('processed_emails').delete()
    print("Pronto! Agora você pode rodar 'python3.13 hermes_cli.py sync-pix' para ter os dados perfeitos.")

if __name__ == "__main__":
    cleanup()
