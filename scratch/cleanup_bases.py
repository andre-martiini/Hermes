import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore

try:
    cred = credentials.Certificate('firebase_service_account_key.json')
    firebase_admin.initialize_app(cred)
except Exception as e:
    pass

db = firestore.client()

docs = list(db.collection('knowledge_bases').stream())
bases_by_name = {}

for d in docs:
    data = d.to_dict()
    name = data.get('nome')
    if not name:
        continue
    name_lower = name.lower()
    if name_lower not in bases_by_name:
        bases_by_name[name_lower] = []
    bases_by_name[name_lower].append(d)

target_names = ["financeira", "saúde", "serviços"]

print("--- CLEANING UP DUPLICATE BASES ---")
for name_lower in target_names:
    if name_lower in bases_by_name:
        bases = bases_by_name[name_lower]
        if len(bases) > 1:
            print(f"Found {len(bases)} bases for '{name_lower}'. Keeping the first one and deleting the rest.")
            # Keep the first one
            keep_doc = bases[0]
            print(f"  Keeping: ID={keep_doc.id}")
            for delete_doc in bases[1:]:
                print(f"  Deleting: ID={delete_doc.id}")
                db.collection('knowledge_bases').document(delete_doc.id).delete()
        else:
            print(f"Only 1 base found for '{name_lower}'. No action needed.")
print("Cleanup complete!")
