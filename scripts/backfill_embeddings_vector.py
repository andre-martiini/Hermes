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

    total_converted = 0
    for coll in COLLECTIONS:
        converted = 0
        already_vector = 0
        missing = 0
        for snap in db.collection(coll).stream():
            data = snap.to_dict() or {}
            emb = data.get("embedding")
            if emb is None or emb == []:
                missing += 1
                continue
            if isinstance(emb, Vector):
                already_vector += 1
                continue
            try:
                vec = Vector(list(map(float, emb)))
            except Exception as exc:
                print(f"  [SKIP] {coll}/{snap.id}: embedding invalido ({exc})")
                continue
            snap.reference.update({"embedding": vec})
            converted += 1
        print(
            f"[{coll}] convertidos={converted} ja_vector={already_vector} sem_embedding={missing}"
        )
        total_converted += converted

    print(f"Backfill concluido. Total convertido: {total_converted}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
