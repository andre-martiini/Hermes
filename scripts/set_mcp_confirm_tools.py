#!/usr/bin/env python3
"""Define quais tools exigem confirmacao dupla no canal MCP.

O canal MCP tem seu proprio gate: uma tool listada em
`system/mcp_access.confirm_tools` so executa quando a chamada traz
`_confirmed: true`. Sem a lista no Firestore vale o padrao do codigo
(`mcp_server._CONFIRMACAO_PADRAO`), que hoje e `{"schedule_whatsapp_message"}`.

Esse padrao veio de uma decisao explicita do dono do sistema em 2026-08-25:
envio de WhatsApp manda mensagem em nome dele para terceiros, e e o unico efeito
que nao da para desfazer de dentro do Hermes.

Esvaziar a lista **nao** significa envio desacompanhado: o `_meta.mutates` da
tool continua verdadeiro, e o proprio cliente Claude pede permissao por chamada.
O que sai e a ida e volta extra no servidor, que na pratica travava o envio
porque o cliente nao repetia a chamada.

Uso:
    python scripts/set_mcp_confirm_tools.py --liberar-whatsapp
    python scripts/set_mcp_confirm_tools.py --restaurar-padrao
    python scripts/set_mcp_confirm_tools.py --mostrar
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CHAVE = os.environ.get("HERMES_SERVICE_ACCOUNT",
                        os.path.join(_RAIZ, "firebase_service_account_key.json"))


def _db():
    import firebase_admin
    from firebase_admin import credentials, firestore

    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(_CHAVE))
    return firestore.client()


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--liberar-whatsapp", action="store_true",
                   help="esvazia confirm_tools: nenhuma tool exige _confirmed no MCP")
    g.add_argument("--restaurar-padrao", action="store_true",
                   help="volta a exigir confirmacao no envio de WhatsApp")
    g.add_argument("--mostrar", action="store_true", help="so imprime o estado atual")
    args = p.parse_args()

    db = _db()
    ref = db.collection("system").document("mcp_access")
    atual = (ref.get().to_dict() or {}).get("confirm_tools")
    print(f"confirm_tools antes: {atual!r}"
          f"{'   (None = vale o padrao do codigo)' if atual is None else ''}")

    if args.mostrar:
        return 0

    nova = [] if args.liberar_whatsapp else ["schedule_whatsapp_message"]
    ref.set({
        "confirm_tools": nova,
        "confirm_tools_atualizado_em": datetime.now(timezone.utc).isoformat(),
    }, merge=True)

    print(f"confirm_tools agora: {nova!r}")
    print("Efeito em ate 5 minutos — o servidor memoiza esta leitura "
          "(_ACCESS_CACHE_TTL_SEC).")
    if args.liberar_whatsapp:
        print("\nA permissao por chamada do cliente Claude continua valendo. Se voce "
              "tambem marcar a tool como permitida no cliente, o envio passa a ser "
              "desacompanhado de ponta a ponta.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
