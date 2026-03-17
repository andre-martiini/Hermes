
import firebase_admin
from firebase_admin import credentials, firestore
import json
import os

def check_rag():
    if not os.path.exists('firebase_service_account_key.json'):
        print("Error: firebase_service_account_key.json not found.")
        return

    if not firebase_admin._apps:
        cred = credentials.Certificate('firebase_service_account_key.json')
        firebase_admin.initialize_app(cred)
    
    db = firestore.client()
    
    print("--- CHECKING SYSTEMS RAG ---")
    
    # 1. Get Systems
    sistemas_ref = db.collection('sistemas_detalhes').stream()
    sistemas = []
    for doc in sistemas_ref:
        data = doc.to_dict()
        data['id'] = doc.id
        sistemas.append(data)
    
    print(f"Found {len(sistemas)} systems registered.")
    
    results = []
    
    for sys in sistemas:
        sys_id = sys['id']
        sys_nome = sys.get('nome', 'N/A')
        repo_url = sys.get('repositorio_principal', '')
        synced_at = sys.get('github_rag_synced_at', 'Never')
        
        status = {
            'nome': sys_nome,
            'repo': repo_url,
            'github_rag_synced_at': synced_at,
            'has_kb': False,
            'kb_id': f"github_{sys_id}",
            'chunk_count': 0,
            'vectorized_count': 0
        }
        
        if repo_url:
            # Check for KB
            kb_doc = db.collection('knowledge_bases').document(status['kb_id']).get()
            if kb_doc.exists:
                status['has_kb'] = True
                
            # Check for Chunks
            chunks = db.collection('conhecimento').where('base_id', '==', status['kb_id']).stream()
            for chunk in chunks:
                status['chunk_count'] += 1
                c_data = chunk.to_dict()
                if 'embedding' in c_data and c_data['embedding']:
                    status['vectorized_count'] += 1
        
        results.append(status)
    
    print("\nSummary of Systems RAG:")
    for r in results:
        print(f"\nSystem: {r['nome']}")
        print(f"  Repo: {r['repo'] or 'None'}")
        print(f"  Last Sync: {r['github_rag_synced_at']}")
        if r['repo']:
            print(f"  Knowledge Base: {'YES' if r['has_kb'] else 'NO'}")
            print(f"  Chunks found: {r['chunk_count']}")
            print(f"  Vectorized: {r['vectorized_count']} / {r['chunk_count']}")
    
    # Save to file for assistant to read
    with open('rag_status_report.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print("\nFull report saved to rag_status_report.json")

if __name__ == "__main__":
    check_rag()
