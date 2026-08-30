"""Cliente HTTP do Sistema de Decisao de Investimentos (repo `sistema-decisao-investimentos`).

O contrato entre os dois sistemas e a API HTTP daquele servico, e so ela. O
Hermes NUNCA escreve nas colecoes `decisao_investimentos_*` do Firestore, nem
mesmo para "corrigir" um valor: elas sao do servico, que mantem invariantes que
uma escrita por fora quebraria em silencio — `aporte_total` acumulado,
`data_primeiro_aporte` fixada na primeira vez, e o log em
`decisao_investimentos_movimentos` que registra cada mexida. Gravar direto
deixaria o estado e o log divergentes sem nenhum erro visivel.

Tambem nao ha nada aqui que decida compra ou venda. O motor e determinístico e
mora em `app/engine.py` do outro repositorio; este modulo so le a carteira e
registra o que o USUARIO declarou ter feito na corretora.

## Autenticacao

Token OIDC assinado como `hermes-investimentos-invoker@...`, identidade que tem
`roles/run.invoker` SO no servico `decisao-investimentos`. As functions rodam sob
a SA padrao do Compute e assumem essa identidade
(`roles/iam.serviceAccountTokenCreator`).

Daria para chamar direto com a SA de Compute — ela tem `run.invoker` no projeto
inteiro. Nao e o que se faz aqui de proposito: assim a chamada dependeria de um
privilegio amplo que se quer estreitar um dia, e apertar o Compute quebraria
esta integracao sem aviso. Com a identidade dedicada, que tem binding proprio no
servico, apertar o Compute nao muda nada.

Nao ha chave em arquivo: a credencial de origem vem do metadata server.

## Por que nenhuma escrita e repetida automaticamente

`POST /carteira/aporte` SOMA ao `aporte_total` — nao e idempotente. Um retry
depois de um timeout, onde a primeira requisicao na verdade chegou, dobraria o
aporte registrado e envenenaria o calculo de rendimento para sempre, sem erro
nenhum aparecendo. Entao timeout numa escrita e reportado como ambiguo, com a
instrucao de conferir, e nunca reenviado. Perder uma escrita se conserta com uma
segunda chamada consciente; duplicar uma escrita nao se conserta por aqui, e o
servico nao expoe endpoint de estorno.
"""
from __future__ import annotations

import os

import google.auth
from google.auth import impersonated_credentials
from google.auth.transport.requests import AuthorizedSession

# URL base do servico. E tambem o `audience` do token OIDC — se um dia o servico
# passar a responder 401, e a primeira coisa a conferir: o Cloud Run mudou o
# formato das URLs e o `HANDOFF.md` do outro repositorio ainda registra a antiga
# (`decisao-investimentos-cmpmsnw5zq-uc.a.run.app`). Esta e a que o
# `gcloud run services list` reporta hoje.
SERVICO_URL = os.environ.get(
    "INVESTIMENTOS_URL",
    "https://decisao-investimentos-1003307358410.us-central1.run.app",
).rstrip("/")

SA_INVOKER = os.environ.get(
    "INVESTIMENTOS_SA",
    "hermes-investimentos-invoker@gestao-hermes.iam.gserviceaccount.com",
)

_ESCOPO = "https://www.googleapis.com/auth/cloud-platform"

# O servico escala a zero e `GET /carteira` busca cotacao no yfinance e o CDI no
# SGS do Bacen. Cold start mais duas chamadas externas passa folgado de 10s, daí
# a leitura ter teto bem maior que a escrita — que so grava no Firestore.
TIMEOUT_LEITURA = 45
TIMEOUT_ESCRITA = 30
# Leitura feita como contexto de fundo, nao a pedido: prefere-se a linha
# faltar a resposta inteira travar num cold start.
TIMEOUT_CONTEXTO = 8

ATIVOS_VALIDOS = ("CDI", "BOVA11", "IVVB11")

_sessao: AuthorizedSession | None = None


def _sessao_autenticada() -> AuthorizedSession:
    global _sessao
    if _sessao is None:
        origem, _ = google.auth.default(scopes=[_ESCOPO])
        alvo = impersonated_credentials.Credentials(
            source_credentials=origem,
            target_principal=SA_INVOKER,
            target_scopes=[_ESCOPO],
        )
        _sessao = AuthorizedSession(
            impersonated_credentials.IDTokenCredentials(
                alvo, target_audience=SERVICO_URL, include_email=True
            )
        )
    return _sessao


def _erro(mensagem: str, **extra) -> dict:
    return {"erro": mensagem, **extra}


def _chamar(metodo: str, caminho: str, *, params: dict | None = None, timeout: int) -> dict:
    """Uma requisicao ao servico. Nunca levanta: devolve `{"erro": ...}`.

    `escrita_ambigua=True` marca o caso em que nao se sabe se a gravacao
    aconteceu — quem chama tem de dizer isso ao usuario em vez de tentar de novo.
    """
    url = f"{SERVICO_URL}{caminho}"
    escrita = metodo.upper() != "GET"
    try:
        resposta = _sessao_autenticada().request(
            metodo, url, params=params or {}, timeout=timeout
        )
    except Exception as exc:  # noqa: BLE001 — rede, DNS, credencial, timeout
        if escrita:
            return _erro(
                f"Nao deu para confirmar se o registro foi gravado: {exc}. "
                "A requisicao pode ter chegado ao servico. NAO repita a chamada — "
                "confira com `consultar_investimentos` e so registre de novo se "
                "o valor nao tiver entrado.",
                escrita_ambigua=True,
            )
        return _erro(f"Nao consegui falar com o servico de investimentos: {exc}")

    if resposta.status_code == 401 or resposta.status_code == 403:
        return _erro(
            "O servico de investimentos recusou a credencial "
            f"(HTTP {resposta.status_code}). Verifique se "
            f"`{SA_INVOKER}` ainda tem roles/run.invoker no servico e se "
            f"`{SERVICO_URL}` e a URL atual."
        )
    if resposta.status_code == 422:
        return _erro(f"O servico recusou os dados: {_detalhe(resposta)}")
    if resposta.status_code >= 400:
        return _erro(
            f"O servico de investimentos respondeu HTTP {resposta.status_code}: "
            f"{_detalhe(resposta)}",
            # Uma escrita que voltou 5xx tambem e ambigua: o erro pode ter
            # acontecido depois da gravacao.
            **({"escrita_ambigua": True} if escrita and resposta.status_code >= 500 else {}),
        )

    try:
        return resposta.json()
    except ValueError:
        return _erro(f"Resposta ilegivel do servico: {resposta.text[:200]}")


def _detalhe(resposta) -> str:
    try:
        corpo = resposta.json()
    except ValueError:
        return resposta.text[:200]
    if isinstance(corpo, dict) and "detail" in corpo:
        return str(corpo["detail"])[:300]
    return str(corpo)[:300]


def carteira(timeout: int | None = None) -> dict:
    """Valor atual da carteira e comparacao com o CDI. Somente leitura.

    Enquanto nao houver primeiro aporte o servico responde 200 com
    `{"status": "carteira nao registrada"}` — isso e o estado normal do sistema
    novo, nao uma falha, e quem chama nao deve tratar como erro.
    """
    return _chamar("GET", "/carteira", timeout=timeout or TIMEOUT_LEITURA)


def registrar_aporte(valor: float) -> dict:
    """Registra dinheiro novo enviado a corretora. SOMA ao total aportado.

    Nao e idempotente do lado do servico: chamar duas vezes com R$ 500 registra
    R$ 1.000. Ver o cabecalho do modulo sobre por que nada aqui e repetido
    automaticamente.
    """
    if valor is None or float(valor) <= 0:
        return _erro("O valor do aporte tem de ser maior que zero.")
    return _chamar(
        "POST", "/carteira/aporte", params={"valor": float(valor)}, timeout=TIMEOUT_ESCRITA
    )


def confirmar_execucao(
    ativo: str,
    quantidade: float | None = None,
    preco: float | None = None,
    valor: float | None = None,
    caixa: float | None = None,
) -> dict:
    """Registra o que o usuario passou a ter depois de executar na corretora.

    Declarativo, nao transacional: informa-se a posicao resultante, e o servico
    substitui o estado. Repetir a mesma chamada nao acumula posicao (ao contrario
    do aporte), mas grava uma segunda linha no log de movimentos.
    """
    ativo = str(ativo or "").strip().upper()
    if ativo not in ATIVOS_VALIDOS:
        return _erro(f"`ativo` tem de ser um de {', '.join(ATIVOS_VALIDOS)} — veio {ativo!r}.")
    if ativo == "CDI" and valor is None:
        return _erro("Para CDI informe `valor`: quanto foi aplicado.")
    if ativo != "CDI" and (quantidade is None or preco is None):
        return _erro(f"Para {ativo} informe `quantidade` de cotas e `preco` pago por cota.")

    params: dict = {"ativo": ativo}
    for nome, bruto in (
        ("quantidade", quantidade), ("preco", preco), ("valor", valor), ("caixa", caixa),
    ):
        if bruto is not None:
            params[nome] = float(bruto)
    return _chamar(
        "POST", "/carteira/confirmar", params=params, timeout=TIMEOUT_ESCRITA
    )
