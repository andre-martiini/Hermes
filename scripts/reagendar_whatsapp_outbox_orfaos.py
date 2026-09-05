#!/usr/bin/env python3
"""Encontra e corrige jobs órfãos na fila `whatsapp_outbox`.

Bug corrigido em `functions/outbox_aprovacao.py`: o caminho de envio imediato
(`criar_rascunho(..., envio_imediato=True)`, usado pelo Secretário para
responder na hora) gravava o job com `status: "pending"` mas sem o campo
`scheduled_for`. O worker (`services/whatsapp-capture/index.js` e o fallback
`dispatch_scheduled_whatsapp_messages`) seleciona jobs pendentes com
`scheduled_for <= agora()`, e essa comparação no Firestore exclui documentos
com o campo null/ausente — o job nunca é selecionado e fica "pending" para
sempre, com `attempts` em 0 e nenhum erro registrado.

Este script varre `whatsapp_outbox` em busca de documentos com
`status == "pending"` e `scheduled_for` ausente/None (jobs criados antes da
correção) e, com `--aplicar`, grava `scheduled_for = agora()` para que o
worker os selecione no próximo ciclo.

## Regras

- Simulação por padrão. Escrever exige `--aplicar`.
- Só toca em `status == "pending"`: jobs já `sent`/`failed`/`sending`/
  `aguardando_aprovacao`/`aguardando_janela` não são órfãos deste bug e ficam
  intocados.
- Idempotente: um job que já tem `scheduled_for` não casa com o filtro.

Uso:
    python scripts/reagendar_whatsapp_outbox_orfaos.py
    python scripts/reagendar_whatsapp_outbox_orfaos.py --aplicar
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_RAIZ, "functions"))
_CHAVE = os.environ.get("HERMES_SERVICE_ACCOUNT",
                        os.path.join(_RAIZ, "firebase_service_account_key.json"))

COLLECTION = "whatsapp_outbox"


def _db():
    import firebase_admin
    from firebase_admin import credentials, firestore

    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(_CHAVE))
    return firestore.client()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--aplicar", action="store_true", help="grava (sem isto, so simula)")
    args = p.parse_args()

    db = _db()
    from firebase_admin import firestore

    orfaos = []
    for doc in db.collection(COLLECTION).where("status", "==", "pending").stream():
        dados = doc.to_dict() or {}
        if dados.get("scheduled_for") is None:
            orfaos.append((doc, dados))

    print(f"{'APLICADO' if args.aplicar else 'SIMULAÇÃO'}")
    print(f"  jobs pending com scheduled_for ausente: {len(orfaos)}")

    if not orfaos:
        return 0

    print("\njobs órfãos:")
    for doc, dados in orfaos:
        criado = dados.get("created_at")
        print(f"  {doc.id}  to={dados.get('to_number')!r}  "
              f"attempts={dados.get('attempts', 0)}  origem={dados.get('origem')!r}  "
              f"created_at={criado!r}  content={str(dados.get('content'))[:60]!r}")

    if args.aplicar:
        agora = datetime.now(timezone.utc)
        for doc, _dados in orfaos:
            doc.reference.update({
                "scheduled_for": agora,
                "updated_at": firestore.SERVER_TIMESTAMP,
            })
        print(f"\n{len(orfaos)} job(s) atualizado(s) com scheduled_for = {agora.isoformat()}.")
        print("O worker deve selecioná-los no próximo ciclo (cron de 1 min).")
    else:
        print("\n(nada gravado — revise a lista acima; rode com --aplicar para reagendar "
              "para agora, ou decida manualmente reenviar/descartar cada um)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
