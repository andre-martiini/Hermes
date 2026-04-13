"""
Migração — Cristalização em Lote do Grafo de Conhecimento
==========================================================
Este script percorre todas as tarefas com status 'concluído' que ainda não
foram cristalizadas (kg_crystallized != True) e executa _crystallize_task
para cada uma, populando as coleções knowledge_nodes e knowledge_edges.

Uso:
    python migrate_kg_crystallize.py [--dry-run] [--limit N] [--area AREA] [--force]

Flags:
  --dry-run      Lista as tarefas elegíveis sem cristalizar.
  --limit N      Processa no máximo N tarefas (útil para testes parciais).
  --area AREA    Filtra por area_tematica específica.
  --force        Re-cristaliza tarefas que já têm kg_crystallized=True.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import types

# ── Stub mínimo de firebase_functions ────────────────────────────────────────
# knowledge_graph.py importa firebase_functions apenas para os decorators
# das Cloud Functions. Aqui criamos stubs que não fazem nada, permitindo
# importar as funções internas (_crystallize_task, etc.) sem o runtime Firebase.

def _make_noop_decorator(*_a, **_kw):
    def decorator(fn):
        return fn
    return decorator

_ff_stub = types.ModuleType("firebase_functions")
_ff_stub.firestore_fn = types.SimpleNamespace(
    on_document_created=_make_noop_decorator,
    on_document_updated=_make_noop_decorator,
    Event=object,
    DocumentSnapshot=object,
    Change=object,
)
_ff_stub.https_fn = types.SimpleNamespace(
    on_call=_make_noop_decorator,
    CallableRequest=object,
    HttpsError=Exception,
    FunctionsErrorCode=types.SimpleNamespace(INVALID_ARGUMENT="invalid-argument", NOT_FOUND="not-found"),
)
_ff_stub.options = types.SimpleNamespace(
    MemoryOption=types.SimpleNamespace(MB_512="512MB", GB_1="1GB"),
)
_ff_stub.pubsub_fn = types.SimpleNamespace(on_message_published=_make_noop_decorator)
_ff_stub.scheduler_fn = types.SimpleNamespace(on_schedule=_make_noop_decorator)
sys.modules.setdefault("firebase_functions", _ff_stub)
sys.modules.setdefault("firebase_functions.firestore_fn", types.ModuleType("firebase_functions.firestore_fn"))
sys.modules.setdefault("firebase_functions.https_fn", types.ModuleType("firebase_functions.https_fn"))
sys.modules.setdefault("firebase_functions.options", types.ModuleType("firebase_functions.options"))

# ── Adiciona functions/ ao path e importa as funções necessárias ─────────────
FUNCTIONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "functions")
if FUNCTIONS_DIR not in sys.path:
    sys.path.insert(0, FUNCTIONS_DIR)

import firebase_admin  # noqa: E402
from firebase_admin import credentials, firestore  # noqa: E402

from knowledge_graph import (  # noqa: E402
    _crystallize_task,
    _generate_kg_tags,
    _fetch_all_existing_tags,
)

# ── Firebase ──────────────────────────────────────────────────────────────────
KEY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "firebase_service_account_key.json")


def init_firebase():
    if not os.path.exists(KEY_FILE):
        print(f"[ERRO] Arquivo de credenciais não encontrado: {KEY_FILE}")
        sys.exit(1)
    if not firebase_admin._apps:
        cred = credentials.Certificate(KEY_FILE)
        firebase_admin.initialize_app(cred)
    return firestore.client()


def get_api_key(db) -> str:
    doc = db.collection("system").document("api_keys").get()
    if not doc.exists:
        print("[ERRO] Documento system/api_keys não encontrado no Firestore.")
        sys.exit(1)
    key = (doc.to_dict() or {}).get("gemini_api_key")
    if not key:
        print("[ERRO] Campo gemini_api_key ausente em system/api_keys.")
        sys.exit(1)
    return key


# ── Consulta tarefas elegíveis ────────────────────────────────────────────────

SKIP_AREAS = {
    None, "", "SISTEMAS", "NÃO CLASSIFICADA",
}


def _is_skip_area(area: str | None) -> bool:
    """Descarta áreas sem valor semântico para o grafo."""
    if area in SKIP_AREAS:
        return True
    # Áreas de sistemas de desenvolvimento (SISTEMA: X)
    if area and area.upper().startswith("SISTEMA"):
        return True
    return False


def fetch_eligible_tasks(db, area: str | None, force: bool) -> list[tuple[str, dict]]:
    """
    Retorna lista de (task_id, task_data) das tarefas concluídas não cristalizadas.
    Se force=True, inclui também as já cristalizadas.
    Exclui automaticamente áreas sem valor semântico (NÃO CLASSIFICADA, SISTEMAS, etc.).
    """
    query = db.collection("tarefas").where("status", "==", "concluído")
    if area:
        query = query.where("area_tematica", "==", area)

    results = []
    for doc in query.stream():
        data = doc.to_dict() or {}
        if not force and data.get("kg_crystallized"):
            continue
        if _is_skip_area(data.get("area_tematica")):
            continue
        results.append((doc.id, data))

    return results


# ── Cristalização em lote ─────────────────────────────────────────────────────

def run_migration(args):
    print("=" * 62)
    print("  Migração KG — Cristalização em Lote")
    print("=" * 62)

    db = init_firebase()
    api_key = get_api_key(db)

    print("Consultando tarefas elegíveis...", end=" ", flush=True)
    tasks = fetch_eligible_tasks(db, args.area, args.force)
    print(f"{len(tasks)} encontradas.")

    if args.limit:
        tasks = tasks[: args.limit]
        print(f"Limitando a {args.limit} tarefas conforme --limit.")

    if not tasks:
        print("Nenhuma tarefa para processar. Encerrando.")
        return

    if args.dry_run:
        print("\n[DRY-RUN] Tarefas que seriam cristalizadas:")
        for tid, data in tasks:
            tags_info = f"  tags={'sim' if data.get('kg_tags') else 'não'}"
            print(f"  • {tid}  [{data.get('area_tematica', '?'):20s}]  {data.get('titulo', '(sem título)')[:55]}{tags_info}")
        print(f"\nTotal: {len(tasks)} tarefas.")
        return

    print()
    ok = 0
    erros = 0

    for i, (task_id, task_data) in enumerate(tasks, 1):
        titulo = task_data.get("titulo", "(sem título)")
        area = task_data.get("area_tematica", "?")
        has_tags = bool(task_data.get("kg_tags"))
        print(f"[{i:3d}/{len(tasks)}] {task_id}  [{area}]")
        print(f"         Título: {titulo[:65]}")

        # ── Fase 1 retroativa: gera kg_tags se ausentes ───────────────────
        if not has_tags:
            try:
                existing_tags = _fetch_all_existing_tags(db)
                tags = _generate_kg_tags(task_data, existing_tags, api_key)
                if tags:
                    db.collection("tarefas").document(task_id).update({"kg_tags": tags})
                    task_data["kg_tags"] = tags
                    print(f"         Tags geradas: {tags}")
                else:
                    print("         AVISO: nenhuma tag gerada.")
            except Exception as e:
                print(f"         AVISO: falha ao gerar tags: {e}")

        # ── Fase 2: cristalização ─────────────────────────────────────────
        try:
            _crystallize_task(task_id, task_data, db, api_key)
            print(f"         OK — cristalizada com sucesso.")
            ok += 1
        except Exception as e:
            print(f"         ERRO: {e}")
            erros += 1

        # Pausa para não saturar a API Gemini (ajuste conforme cota disponível)
        if i < len(tasks):
            time.sleep(1.5)

    print()
    print("=" * 62)
    print(f"  Resultado: {ok} cristalizadas  |  {erros} erros  |  {len(tasks)} processadas")
    print("=" * 62)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Cristalização em lote do Grafo de Conhecimento Hermes.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--dry-run", action="store_true", help="Lista tarefas sem cristalizar")
    parser.add_argument("--limit", type=int, default=0, metavar="N", help="Máximo de tarefas a processar")
    parser.add_argument("--area", type=str, default="", metavar="AREA", help="Filtrar por area_tematica")
    parser.add_argument("--force", action="store_true", help="Re-cristalizar tarefas já processadas")
    args = parser.parse_args()

    if not args.limit:
        args.limit = None
    if not args.area:
        args.area = None

    run_migration(args)
