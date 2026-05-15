"""
Hermes Queue Processor

Substitui o server.py (HTTP) por um listener Firestore para as automações
ponto_eletronico e executar_pgd. Tarefas são enfileiradas pelo frontend
escrevendo em `fila_automacoes` e processadas aqui com retry automático.

Retry schedule: tentativa 1 → aguarda 30s → tentativa 2 → 60s → tentativa 3 (permanente).
"""

import os
import sys
import time
import threading
from datetime import datetime, timezone

import firebase_admin
from firebase_admin import credentials, firestore

KEY_FILE = os.path.join(os.path.dirname(__file__), '..', 'firebase_service_account_key.json')

MAX_TENTATIVAS = 3
BACKOFF_BASE_S = 30   # 30 s, 60 s, 120 s

_active_tasks: set[str] = set()
_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Firebase
# ---------------------------------------------------------------------------

def init_db():
    if not os.path.exists(KEY_FILE):
        print(f"❌ Chave de serviço não encontrada: {KEY_FILE}")
        sys.exit(1)
    cred = credentials.Certificate(KEY_FILE)
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
    return firestore.client()


# ---------------------------------------------------------------------------
# Logging helpers
# ---------------------------------------------------------------------------

def _log(doc_ref, mensagem: str):
    ts = datetime.now(timezone.utc).strftime('%H:%M:%S')
    linha = f"[{ts}] {mensagem}"
    doc_ref.update({
        'logs': firestore.ArrayUnion([linha]),
        'atualizado_em': firestore.SERVER_TIMESTAMP,
    })
    print(linha)


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

def _run_ponto_eletronico(payload: dict, doc_ref) -> bool:
    import subprocess
    _log(doc_ref, "🕐 Iniciando Ponto Eletrônico (SIGRH)...")
    script = os.path.join(os.path.dirname(__file__), 'ponto_eletronico.py')
    result = subprocess.run(
        ['python', script],
        capture_output=True, text=True, timeout=300,
    )
    for linha in (result.stdout or '').strip().split('\n'):
        if linha:
            _log(doc_ref, linha)
    if result.returncode == 0:
        _log(doc_ref, "✅ Ponto Eletrônico concluído com sucesso.")
        return True
    _log(doc_ref, f"❌ Falhou (código {result.returncode}).")
    for linha in (result.stderr or '').strip().split('\n'):
        if linha:
            _log(doc_ref, f"   {linha}")
    return False


def _run_executar_pgd(payload: dict, doc_ref) -> bool:
    _log(doc_ref, f"📋 Iniciando PGD para {payload.get('mes_ano', '?')}...")
    try:
        sys.path.insert(0, os.path.dirname(__file__))
        from execucao_pgd import preencher_execucao_pgd  # noqa: PLC0415
        preencher_execucao_pgd(payload)
        _log(doc_ref, "✅ PGD sincronizado com sucesso.")
        return True
    except Exception as exc:
        _log(doc_ref, f"❌ Erro no PGD: {exc}")
        return False


HANDLERS = {
    'ponto_eletronico': _run_ponto_eletronico,
    'executar_pgd': _run_executar_pgd,
}


# ---------------------------------------------------------------------------
# Task lifecycle
# ---------------------------------------------------------------------------

def processar_tarefa(doc_ref, data: dict):
    doc_id = doc_ref.id

    with _lock:
        if doc_id in _active_tasks:
            return
        _active_tasks.add(doc_id)

    try:
        tipo = data.get('tipo', '')
        payload = data.get('payload', {})
        tentativas_anteriores = data.get('tentativas', 0)

        handler = HANDLERS.get(tipo)
        if not handler:
            doc_ref.update({'status': 'erro_permanente', 'erro': f"Tipo desconhecido: {tipo}"})
            return

        doc_ref.update({
            'status': 'processando',
            'tentativas': tentativas_anteriores + 1,
            'iniciado_em': firestore.SERVER_TIMESTAMP,
        })

        try:
            sucesso = handler(payload, doc_ref)
        except Exception as exc:
            _log(doc_ref, f"💥 Exceção inesperada: {exc}")
            sucesso = False

        nova_contagem = tentativas_anteriores + 1
        if sucesso:
            doc_ref.update({'status': 'concluido', 'concluido_em': firestore.SERVER_TIMESTAMP})
        elif nova_contagem < MAX_TENTATIVAS:
            atraso = BACKOFF_BASE_S * (2 ** tentativas_anteriores)
            proxima = datetime.now(timezone.utc).timestamp() + atraso
            doc_ref.update({'status': 'aguardando_retry', 'proxima_tentativa_em': proxima})
            _log(doc_ref, f"⏳ Tentativa {nova_contagem}/{MAX_TENTATIVAS}. Próxima em {atraso}s.")
        else:
            doc_ref.update({'status': 'erro_permanente', 'concluido_em': firestore.SERVER_TIMESTAMP})
            _log(doc_ref, f"💀 Máximo de {MAX_TENTATIVAS} tentativas atingido. Tarefa arquivada.")
    finally:
        with _lock:
            _active_tasks.discard(doc_id)


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def watch_queue(db):
    print('\n' + '=' * 52)
    print('⚡ HERMES QUEUE PROCESSOR: OPERANTE')
    print('   Coleção : fila_automacoes')
    print('   Handlers: ponto_eletronico, executar_pgd')
    print('   Retry   : 3x com backoff exponencial (30s base)')
    print('=' * 52 + '\n')

    col_ref = db.collection('fila_automacoes')

    def on_snapshot(col_snapshot, changes, read_time):
        for change in changes:
            if change.type.name not in ('ADDED', 'MODIFIED'):
                continue
            doc = change.document
            data = doc.to_dict()
            if not data or data.get('status') != 'pendente':
                continue
            ts = datetime.now().strftime('%H:%M:%S')
            print(f"[{ts}] 📥 {doc.id[:8]}… tipo={data.get('tipo')}")
            t = threading.Thread(
                target=processar_tarefa,
                args=(doc.reference, data),
                daemon=True,
            )
            t.start()

    watch = col_ref.on_snapshot(on_snapshot)

    try:
        while True:
            time.sleep(30)
            agora = datetime.now(timezone.utc).timestamp()
            for doc in col_ref.where('status', '==', 'aguardando_retry').stream():
                d = doc.to_dict() or {}
                if d.get('proxima_tentativa_em', float('inf')) <= agora:
                    doc.reference.update({'status': 'pendente'})
                    ts = datetime.now().strftime('%H:%M:%S')
                    print(f"[{ts}] 🔁 Retry: {doc.id[:8]}…")
    except KeyboardInterrupt:
        print('\n🛑 Queue processor encerrado.')
        watch.unsubscribe()
        sys.exit(0)


if __name__ == '__main__':
    db = init_db()
    watch_queue(db)
