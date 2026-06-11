"""Backfill: converte embeddings gravados como lista simples para o tipo Vector.

Documentos com embedding em formato lista NAO entram no indice vetorial do
Firestore e ficam invisiveis ao find_nearest. Este script corrige o legado em:
  - knowledge_nodes  (memorias globais + nos conceituais do grafo)
  - indice_artefatos (RAG de artefatos)

Uso (na raiz do projeto):
    python scripts/backfill_embeddings_vector.py
"""

import os
import sys

import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore_v1.vector import Vector

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KEY_PATH = os.path.join(ROOT, "firebase_service_account_key.json")

COLLECTIONS = ["knowledge_nodes", "indice_artefatos"]


def main() -> int:
    cred = credentials.Certificate(KEY_PATH)
    firebase_admin.initialize_app(cred)
    db = firestore.client()

    # Carregar a API key do Gemini a partir de system/api_keys
    print("Obtendo chave do Gemini a partir do Firestore...")
    api_key_doc = db.collection("system").document("api_keys").get()
    api_key = api_key_doc.to_dict().get("gemini_api_key") if api_key_doc.exists else None
    if not api_key:
        print("[AVISO] Chave 'gemini_api_key' nao encontrada em system/api_keys. Re-embeddings serao pulados.")

    total_converted = 0
    for coll in COLLECTIONS:
        converted = 0
        already_vector = 0
        missing = 0
        re_embedded = 0
        for snap in db.collection(coll).stream():
            data = snap.to_dict() or {}
            emb = data.get("embedding")
            if emb is None or emb == []:
                missing += 1
                continue
            if isinstance(emb, Vector):
                already_vector += 1
                continue
            
            # Se for uma lista comum de floats/ints
            if isinstance(emb, list):
                if len(emb) == 768:
                    try:
                        vec = Vector(list(map(float, emb)))
                    except Exception as exc:
                        print(f"  [SKIP] {coll}/{snap.id}: embedding invalido ({exc})")
                        continue
                else:
                    # Dimensão incorreta, necessita re-embedar
                    print(f"  [RE-EMBED] {coll}/{snap.id}: dim={len(emb)} (esperado 768). Re-embedando...")
                    if not api_key:
                        print(f"  [SKIP] {coll}/{snap.id}: sem chave do Gemini para re-embedar.")
                        continue
                    
                    text_to_embed = data.get("resumo") or data.get("titulo") or data.get("nome")
                    if not text_to_embed:
                        print(f"  [SKIP] {coll}/{snap.id}: nenhum campo de texto valido ('resumo', 'titulo', 'nome') encontrado.")
                        continue
                    
                    try:
                        from google import genai
                        from google.genai import types
                        import time
                        
                        client = genai.Client(api_key=api_key)
                        response = client.models.embed_content(
                            model="gemini-embedding-001",
                            contents=text_to_embed[:8000],
                            config=types.EmbedContentConfig(
                                task_type="RETRIEVAL_DOCUMENT",
                                output_dimensionality=768
                            )
                        )
                        new_emb = response.embeddings[0].values
                        vec = Vector(list(map(float, new_emb)))
                        re_embedded += 1
                        time.sleep(0.1)  # Delay leve
                    except Exception as exc:
                        print(f"  [ERROR-EMBED] {coll}/{snap.id}: falha na API Gemini ({exc})")
                        continue
            else:
                print(f"  [SKIP] {coll}/{snap.id}: tipo de embedding desconhecido ({type(emb)})")
                continue
            
            # Atualiza no Firestore
            snap.reference.update({"embedding": vec})
            converted += 1
            
        print(
            f"[{coll}] convertidos_total={converted} (re_embedded={re_embedded}) ja_vector={already_vector} sem_embedding={missing}"
        )
        total_converted += converted

    print(f"Backfill concluido. Total convertido: {total_converted}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
