import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore_v1.vector import Vector
from google.cloud.firestore_v1.base_vector_query import DistanceMeasure
import os
from google import genai
from google.genai import types

def test_search():
    cred = credentials.Certificate('firebase_service_account_key.json')
    firebase_admin.initialize_app(cred)
    db = firestore.client()
    
    api_key = db.collection('system').document('api_keys').get().to_dict().get('gemini_api_key')
    client = genai.Client(api_key=api_key)
    
    print("Gerando embedding...")
    res = client.models.embed_content(
        model='gemini-embedding-001', 
        contents='Allcare', 
        config=types.EmbedContentConfig(task_type='RETRIEVAL_QUERY', output_dimensionality=768)
    )
    emb = res.embeddings[0].values
    
    print("Buscando no Firestore...")
    try:
        results = db.collection('indice_artefatos').find_nearest(
            vector_field='embedding', 
            query_vector=Vector(emb), 
            distance_measure=DistanceMeasure.COSINE, 
            limit=5
        ).get()
        
        docs = list(results)
        print(f"Sucesso: {len(docs)} resultados encontrados.")
        for d in docs:
            print(f"- {d.to_dict().get('nome')}")
            
    except Exception as e:
        print(f"Erro na busca: {e}")

if __name__ == "__main__":
    test_search()
