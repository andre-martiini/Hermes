"""Cliente do canal `/gaspar` do Live Ideas (Realtime Database).

O Gaspar grava um pedido em `gaspar/comandos/<id>` e espera a resposta do
notebook em `gaspar/respostas/<id>`. O notebook publica presença em
`quadro/servidor/online`. A credencial (JSON da conta de serviço) fica em
`system/api_keys.liveideas_conta_servico`; o acesso é sempre como `uid: gaspar`.

Nenhuma mensagem de erro daqui carrega texto da credencial: as exceções da
biblioteca (que podem conter a chave privada) são trocadas por frases fixas.
"""
from __future__ import annotations

import json
import threading
import time
import uuid

import firebase_admin
from firebase_admin import credentials
from firebase_admin import db as rtdb

DATABASE_URL = "https://quadro-ao-vivo-andre-default-rtdb.firebaseio.com"
NOME_APP = "liveideas"
INTERVALO_S = 0.5
# O padrão do firebase_admin é 120 s com retry, o que estouraria o prazo do comando.
HTTP_TIMEOUT_S = 5
# A regra do banco recusa `corpo` acima disto (comprimento de texto do JavaScript, em UTF-16).
LIMITE_CORPO = 200000

MSG_DESLIGADO = "o notebook do Live Ideas está desligado (ligue-o e peça de novo)"
MSG_SEM_RESPOSTA = "o notebook não respondeu; tente de novo em instantes"
MSG_SEM_CREDENCIAL = (
    "falta a credencial do Live Ideas no cofre do Gaspar "
    "(system/api_keys.liveideas_conta_servico)"
)
MSG_JSON_INVALIDO = (
    "a credencial do Live Ideas no cofre do Gaspar não é um JSON válido "
    "(system/api_keys.liveideas_conta_servico)"
)
MSG_CREDENCIAL_RECUSADA = (
    "a credencial do Live Ideas no cofre do Gaspar não foi aceita "
    "(system/api_keys.liveideas_conta_servico)"
)
MSG_REDE = "não consegui falar com o Live Ideas agora; tente de novo em instantes"
MSG_RESPOSTA_INVALIDA = "o notebook devolveu uma resposta inválida"
MSG_GRANDE_DEMAIS = (
    "o texto é grande demais para mandar ao Live Ideas "
    "(limite de cerca de 200.000 caracteres)"
)
MSG_CORPO_INVALIDO = "o pedido ao Live Ideas tem um valor que não vira JSON; confira os campos e peça de novo"

_apps: dict = {}  # raiz do banco, criada uma vez por instância
_trava_app = threading.Lock()  # duas chamadas numa instância fria não podem criar o app duas vezes


class LiveIdeasIndisponivel(Exception):
    """O Live Ideas não pôde atender; `mensagem` é a frase em português para o usuário."""

    def __init__(self, mensagem: str):
        super().__init__(mensagem)
        self.mensagem = mensagem


def banco_liveideas(db):
    """Raiz do Realtime Database do Live Ideas, com a conta de serviço do cofre."""
    if NOME_APP in _apps:
        return _apps[NOME_APP]
    with _trava_app:
        if NOME_APP not in _apps:
            _apps[NOME_APP] = rtdb.reference("/", app=_app_liveideas(db))
    return _apps[NOME_APP]


def _app_existente():
    try:
        return firebase_admin.get_app(NOME_APP)
    except ValueError:
        return None


def _app_liveideas(db):
    app = _app_existente()
    if app is not None:
        return app
    doc = db.collection("system").document("api_keys").get()
    texto = ((doc.to_dict() or {}).get("liveideas_conta_servico") if doc.exists else None)
    if not texto:
        raise LiveIdeasIndisponivel(MSG_SEM_CREDENCIAL)
    try:
        conta = json.loads(texto) if isinstance(texto, str) else texto
    except ValueError:
        # `from None`: o erro de JSON guarda o segredo em `.doc`
        raise LiveIdeasIndisponivel(MSG_JSON_INVALIDO) from None
    if not isinstance(conta, dict):
        # texto codificado duas vezes ou lista: Certificate() vazaria o segredo na mensagem
        raise LiveIdeasIndisponivel(MSG_JSON_INVALIDO)
    try:
        cred = credentials.Certificate(conta)
    except Exception:
        raise LiveIdeasIndisponivel(MSG_CREDENCIAL_RECUSADA) from None
    try:
        return firebase_admin.initialize_app(
            cred,
            {
                "databaseURL": DATABASE_URL,
                "databaseAuthVariableOverride": {"uid": "gaspar"},
                "httpTimeout": HTTP_TIMEOUT_S,
            },
            name=NOME_APP,
        )
    except Exception:
        # "já existe" (criado por outro caminho nesta instância) não é credencial recusada
        app = _app_existente()
        if app is None:
            raise LiveIdeasIndisponivel(MSG_CREDENCIAL_RECUSADA) from None
        return app


def notebook_ligado(raiz) -> bool:
    return raiz.child("quadro/servidor/online").get() is True


def _rede(chamada):
    """Roda uma chamada ao banco; falha de rede vira LiveIdeasIndisponivel com texto fixo."""
    try:
        return chamada()
    except LiveIdeasIndisponivel:
        raise
    except Exception:
        raise LiveIdeasIndisponivel(MSG_REDE) from None


def comando(raiz, acao: str, corpo: dict, espera_s: float = 20) -> tuple[int, dict]:
    """Envia `acao` ao notebook e devolve `(status, corpo)` da resposta."""
    limite = time.monotonic() + espera_s  # conta desde antes da primeira chamada de rede
    try:
        texto = json.dumps(corpo, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError):
        raise LiveIdeasIndisponivel(MSG_CORPO_INVALIDO) from None
    if len(texto.encode("utf-16-le", "surrogatepass")) // 2 > LIMITE_CORPO:
        raise LiveIdeasIndisponivel(MSG_GRANDE_DEMAIS)
    if not _rede(lambda: notebook_ligado(raiz)):
        raise LiveIdeasIndisponivel(MSG_DESLIGADO)
    id_ = uuid.uuid4().hex
    pedido = raiz.child(f"gaspar/comandos/{id_}")
    resposta = raiz.child(f"gaspar/respostas/{id_}")
    try:
        # `criado`: hora do servidor do Firebase; o notebook conta o prazo por ela, não pelo relógio daqui
        _rede(lambda: pedido.set({"acao": acao, "corpo": texto, "em": int(time.time() * 1000),
                                  "criado": {".sv": "timestamp"}}))
    except LiveIdeasIndisponivel:
        try:  # o set pode ter chegado ao banco mesmo sem resposta a tempo
            pedido.delete()
        except Exception:
            pass
        raise
    while True:
        r = _rede(resposta.get)
        if r is not None:
            try:  # melhor esforço: o notebook também limpa respostas esquecidas
                resposta.delete()
            except Exception:
                pass
            try:
                status, corpo_resp = int(r["status"]), json.loads(r["corpo"])
            except (KeyError, TypeError, ValueError):
                raise LiveIdeasIndisponivel(MSG_RESPOSTA_INVALIDA) from None
            if not isinstance(corpo_resp, dict):
                raise LiveIdeasIndisponivel(MSG_RESPOSTA_INVALIDA)
            return status, corpo_resp
        restante = limite - time.monotonic()
        if restante <= 0:
            try:  # a falha da limpeza não pode esconder a mensagem de sem resposta
                pedido.delete()
            except Exception:
                pass
            raise LiveIdeasIndisponivel(MSG_SEM_RESPOSTA)
        time.sleep(min(INTERVALO_S, restante))
