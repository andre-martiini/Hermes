"""Backfill pontual: ativa a captura de WhatsApp (chats_allowlist) para todo
chat_id ja presente em tarefas.whatsapp_vinculos que ainda nao esta na
allowlist de captura.

Contexto: ate 18/08/2026, vincular um chat do WhatsApp a uma acao
(TaskExecutionView.tsx) nao adicionava o chat a
system/settings.whatsapp_ingest.chats_allowlist, entao nenhuma mensagem
desses contatos chegava a whatsapp_messages e o vinculo ficava sem efeito
pratico. O fluxo de vinculo novo ja foi corrigido para ativar a captura
automaticamente (handleSaveWhatsappLinks); este script e so para corrigir
retroativamente os vinculos criados antes dessa correcao.

Uso: python scripts/backfill_whatsapp_capture_allowlist.py [--apply]
Sem --apply, roda em modo dry-run (so mostra o que faria).
"""
import sys
import firebase_admin
from firebase_admin import credentials, firestore

KEY_FILE = 'firebase_service_account_key.json'


def init_db():
    cred = credentials.Certificate(KEY_FILE)
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
    return firestore.client()


def main():
    apply_changes = '--apply' in sys.argv
    db = init_db()

    settings_ref = db.collection('system').document('settings')
    settings_snap = settings_ref.get()
    settings_data = settings_snap.to_dict() if settings_snap.exists else {}
    wa_cfg = settings_data.get('whatsapp_ingest') or {}
    allowlist = [str(x).strip() for x in (wa_cfg.get('chats_allowlist') or []) if str(x).strip()]
    allowlist_set = set(allowlist)

    missing = {}  # chat_id -> {chat_name, tasks: [titulo,...]}
    for doc in db.collection('tarefas').stream():
        data = doc.to_dict() or {}
        vinculos = data.get('whatsapp_vinculos') or []
        if not vinculos:
            continue
        titulo = data.get('titulo') or doc.id
        for v in vinculos:
            chat_id = str(v.get('chat_id') or '').strip()
            if not chat_id or chat_id in allowlist_set:
                continue
            entry = missing.setdefault(chat_id, {'chat_name': v.get('chat_name') or chat_id, 'tasks': []})
            entry['tasks'].append(titulo)

    if not missing:
        print('Nenhum vinculo pendente de ativacao de captura. Nada a fazer.')
        return

    print(f'{len(missing)} chat(s) vinculado(s) a acoes sem captura ativa:')
    for chat_id, info in missing.items():
        tasks_str = ', '.join(info['tasks'])
        print(f'  - {info["chat_name"]} ({chat_id}) -> {tasks_str}')

    if not apply_changes:
        print('\nDry-run (nenhuma alteracao gravada). Rode novamente com --apply para ativar a captura desses chats.')
        return

    new_allowlist = allowlist + [c for c in missing if c not in allowlist_set]
    settings_ref.set({'whatsapp_ingest': {'chats_allowlist': new_allowlist}}, merge=True)
    print(f'\nCaptura ativada para {len(missing)} chat(s). Allowlist agora tem {len(new_allowlist)} entrada(s).')


if __name__ == '__main__':
    main()
