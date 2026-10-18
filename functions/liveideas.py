"""Cliente do canal `/gaspar` do Live Ideas (Realtime Database).

O Gaspar grava um pedido em `gaspar/comandos/<id>` e espera a resposta do
notebook em `gaspar/respostas/<id>`. O notebook publica presença em
`quadro/servidor/online`. A credencial (JSON da conta de serviço) fica em
`system/api_keys.liveideas_conta_servico`; o acesso é sempre como `uid: gaspar`.
"""
from __future__ import annotations

import json
import time
import uuid

import firebase_admin
from firebase_admin import credentials
from firebase_admin import db as rtdb

DATABASE_URL = "https://quadro-ao-vivo-andre-default-rtdb.firebaseio.com"
NOME_APP = "liveideas"
INTERVALO_S = 0.5

MSG_DESLIGADO = "o notebook do Live Ideas está desligado (ligue-o e peça de novo)"
MSG_SEM_RESPOSTA = "o notebook não respondeu; tente de novo em instantes"
MSG_SEM_CREDENCIAL = (
    "falta a credencial do Live Ideas no cofre do Gaspar "
    "(system/api_keys.liveideas_conta_servico)"
)

_apps: dict = {}  # raiz do banco, criada uma vez por instância


class LiveIdeasIndisponivel(Exception):
    """O Live Ideas não pôde atender; `mensagem` é a frase em português para o usuário."""

    def __init__(self, mensagem: str):
        super().__init__(mensagem)
        self.mensagem = mensagem


def banco_liveideas(db):
    """Raiz do Realtime Database do Live Ideas, com a conta de serviço do cofre."""
    if NOME_APP in _apps:
        return _apps[NOME_APP]
    doc = db.collection("system").document("api_keys").get()
    texto = ((doc.to_dict() or {}).get("liveideas_conta_servico") if doc.exists else None)
    if not texto:
        raise LiveIdeasIndisponivel(MSG_SEM_CREDENCIAL)
    try:
        conta = json.loads(texto) if isinstance(texto, str) else dict(texto)
    except ValueError:
        raise LiveIdeasIndisponivel(
            "a credencial do Live Ideas no cofre do Gaspar não é um JSON válido "
            "(system/api_keys.liveideas_conta_servico)")
    app = firebase_admin.initialize_app(
        credentials.Certificate(conta),
        {"databaseURL": DATABASE_URL, "databaseAuthVariableOverride": {"uid": "gaspar"}},
        name=NOME_APP,
    )
    _apps[NOME_APP] = rtdb.reference("/", app=app)
    return _apps[NOME_APP]


def notebook_ligado(raiz) -> bool:
    return raiz.child("quadro/servidor/online").get() is True


def comando(raiz, acao: str, corpo: dict, espera_s: float = 20) -> tuple[int, dict]:
    """Envia `acao` ao notebook e devolve `(status, corpo)` da resposta."""
    if not notebook_ligado(raiz):
        raise LiveIdeasIndisponivel(MSG_DESLIGADO)
    id_ = uuid.uuid4().hex
    pedido = raiz.child(f"gaspar/comandos/{id_}")
    resposta = raiz.child(f"gaspar/respostas/{id_}")
    pedido.set({"acao": acao, "corpo": json.dumps(corpo, ensure_ascii=False), "em": int(time.time() * 1000)})
    limite = time.monotonic() + espera_s
    while True:
        r = resposta.get()
        if r is not None:
            resposta.delete()
            return int(r["status"]), json.loads(r["corpo"])
        restante = limite - time.monotonic()
        if restante <= 0:
            pedido.delete()
            raise LiveIdeasIndisponivel(MSG_SEM_RESPOSTA)
        time.sleep(min(INTERVALO_S, restante))
