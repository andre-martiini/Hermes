"""
Grava/atualiza os dados cadastrais pessoais completos do usuário em
usuarios/{uid}.dados_cadastrais (ver functions/dados_cadastrais.py). Lido sob
demanda pela ferramenta consultar_dados_cadastrais (main.py e godmode.py) —
não é injetado na persona estática de nenhuma superfície.

O payload em si (CPF, RG, dados bancários etc.) NÃO fica neste script nem no
repositório — vem de um arquivo JSON local, fora do controle de versão (ver
.gitignore: scripts/dados_cadastrais_seed.json).

Uso: python scripts/seed_dados_cadastrais.py [--file scripts/dados_cadastrais_seed.json] [--uid UID]
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

import firebase_admin
from firebase_admin import credentials, firestore

KEY_FILE = 'firebase_service_account_key.json'
DEFAULT_PAYLOAD_FILE = 'scripts/dados_cadastrais_seed.json'


def init_db():
    cred = credentials.Certificate(KEY_FILE)
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)
    return firestore.client()


def resolve_uid(db) -> str:
    """Sistema pessoal de um único usuário — mesma resolução usada em
    personal_diary.py:_resolve_default_uid. Sem HERMES_DEFAULT_USER_ID,
    usa o único documento existente em 'usuarios'."""
    uid = os.environ.get('HERMES_DEFAULT_USER_ID', '').strip()
    if uid:
        return uid
    docs = list(db.collection('usuarios').limit(2).stream())
    if len(docs) != 1:
        print(
            f"ERRO: esperava exatamente 1 documento em 'usuarios' para resolver o uid "
            f"automaticamente (encontrei {len(docs)}). Defina HERMES_DEFAULT_USER_ID ou rode com --uid."
        )
        sys.exit(1)
    return docs[0].id


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--file', default=DEFAULT_PAYLOAD_FILE, help='Caminho do JSON com os dados cadastrais (não versionado).')
    parser.add_argument('--uid', default=None, help='UID do usuário. Se omitido, resolve automaticamente (sistema de usuário único).')
    args = parser.parse_args()

    try:
        with open(args.file, 'r', encoding='utf-8') as f:
            payload = json.load(f)
    except FileNotFoundError:
        print(f"ERRO: arquivo '{args.file}' não encontrado. Salve o JSON com os dados cadastrais nesse caminho antes de rodar.")
        sys.exit(1)

    if not isinstance(payload, dict) or not payload:
        print("ERRO: o arquivo precisa conter um objeto JSON não vazio.")
        sys.exit(1)

    db = init_db()
    uid = args.uid or resolve_uid(db)

    # merge=True faria um merge RECURSIVO: um campo removido do payload (ex.: uma
    # conta bancária encerrada) sobreviveria como resíduo obsoleto dentro de
    # dados_cadastrais em vez de sumir. merge=[<field paths>] substitui cada campo
    # listado por inteiro (sem mesclar o conteúdo aninhado dele), preservando ao
    # mesmo tempo os demais campos do documento (ex.: ai_profile).
    db.collection('usuarios').document(uid).set(
        {
            'dados_cadastrais': payload,
            'dados_cadastrais_atualizado_em': datetime.now(timezone.utc).isoformat(),
        },
        merge=['dados_cadastrais', 'dados_cadastrais_atualizado_em'],
    )

    secoes = ', '.join(sorted(payload.keys()))
    print(f"Gravado: usuarios/{uid}.dados_cadastrais ({len(payload)} seção(ões): {secoes})")


if __name__ == '__main__':
    main()
