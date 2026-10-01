"""Trava de confirmação nas respostas do copiloto (web, Telegram e MCP).

O defeito do peso (28 e 30/09/2026: "registrei" sem gravação nenhuma) pode se
repetir com qualquer ferramenta. Esta trava tem duas metades:

1. Depois de cada ferramenta de escrita, `verificar_ferramenta` relê no banco o
   que ela diz ter gravado e devolve um `verificacao.ResultadoOperacao`. O
   resultado entregue ao modelo ganha esse estado (`anotar_resultado`).
2. Antes de a resposta sair, `aplicar_trava` procura verbos de conclusão
   ("registrei", "criei", "agendei"...). Se o turno não teve nenhuma escrita
   `verificado`, o caso é registrado em `trava_confirmacao` e, no modo
   "bloquear", o texto é substituído.

Modo e verbos ficam em `system/settings.trava_confirmacao`
(`{"modo": "registrar" | "bloquear" | "desligado", "verbos": [...]}`); o padrão
é "registrar": nada é bloqueado até os casos registrados serem revisados.
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from verificacao import ResultadoOperacao, montar_confirmacao
from verificadores_escrita import PROPOSTAS, VERIFICADORES

MODOS = ("registrar", "bloquear", "desligado")
MODO_PADRAO = "registrar"
COLECAO_LOG = "trava_confirmacao"
RETENCAO_LOG_DIAS = 14

VERBOS_PADRAO = (
    "registrei", "salvei", "criei", "concluí", "agendei", "enviei", "atualizei", "anotei",
    "gravei", "reagendei", "cadastrei", "lancei", "marquei", "cancelei", "adicionei", "removi", "excluí",
)

MENSAGEM_SEM_ACAO = "Não executei nenhuma ação nesta mensagem. Quer que eu registre?"

REGRA_PROMPT = (
    "## CONFIRMAÇÃO DE ESCRITAS — REGRA ABSOLUTA\n"
    "Só afirme que algo foi feito (registrei, salvei, criei, agendei, enviei, atualizei, anotei) "
    "depois de receber `estado: verificado` de uma ferramenta NESTE turno; o retorno das ferramentas "
    "de escrita traz um campo `verificacao` com esse estado. Se vier `falhou`, diga que não conseguiu e "
    "o motivo. Proposta ou rascunho aguardando confirmação não é ação feita. Se não houver ferramenta "
    "para o pedido, diga que não consegue fazer por aqui.\n\n"
)

_NEGACAO_ANTES = re.compile(r"\b(?:n[aã]o|nunca|jamais|nem|sem)\b[^.!?\n]{0,25}$", re.IGNORECASE)

_CACHE_CFG: dict = {"em": 0.0, "valor": None}
_CACHE_TTL = 60.0


def _sem_acento(texto: str) -> str:
    return (texto.replace("í", "i").replace("Í", "I").replace("ã", "a").replace("Ã", "A"))


def config(db) -> dict:
    """Lê `system/settings.trava_confirmacao` com cache de 60 s por instância."""
    agora = time.monotonic()
    if _CACHE_CFG["valor"] is not None and agora - _CACHE_CFG["em"] < _CACHE_TTL:
        return _CACHE_CFG["valor"]
    cfg = {}
    try:
        doc = db.collection("system").document("settings").get()
        cfg = ((doc.to_dict() or {}) if doc.exists else {}).get("trava_confirmacao") or {}
    except Exception as exc:
        print(f"[Trava] Falha ao ler a configuração: {exc}")
    modo = cfg.get("modo") if cfg.get("modo") in MODOS else MODO_PADRAO
    verbos = tuple(v for v in (cfg.get("verbos") or VERBOS_PADRAO) if isinstance(v, str) and v.strip())
    valor = {"modo": modo, "verbos": verbos or VERBOS_PADRAO}
    _CACHE_CFG.update(em=agora, valor=valor)
    return valor


def verbos_de_conclusao(texto: str, verbos=VERBOS_PADRAO) -> list[str]:
    """Verbos de conclusão em primeira pessoa, ignorando os negados ("não registrei")."""
    if not texto:
        return []
    alvo = _sem_acento(texto)
    achados: list[str] = []
    for verbo in verbos:
        padrao = re.compile(rf"\b{re.escape(_sem_acento(verbo))}\b", re.IGNORECASE)
        for m in padrao.finditer(alvo):
            if _NEGACAO_ANTES.search(alvo[max(0, m.start() - 40):m.start()]):
                continue
            if verbo not in achados:
                achados.append(verbo)
            break
    return achados


def _trecho(texto: str, verbo: str, limite: int = 160) -> str:
    alvo = _sem_acento(texto)
    m = re.search(rf"\b{re.escape(_sem_acento(verbo))}\b", alvo, re.IGNORECASE)
    if not m:
        return ""
    inicio = max(alvo.rfind(s, 0, m.start()) for s in ".!?\n") + 1
    fins = [p for p in (alvo.find(s, m.end()) for s in ".!?\n") if p != -1]
    fim = min(fins) + 1 if fins else len(texto)
    return texto[inicio:fim].strip()[:limite]


def _registrar_caso(db, *, canal, modo, substituida, verbos, chamadas, texto) -> None:
    agora = datetime.now(timezone.utc)
    try:
        db.collection(COLECAO_LOG).add({
            "criado_em": agora,
            "expira_em": agora + timedelta(days=RETENCAO_LOG_DIAS),
            "canal": canal,
            "modo": modo,
            "substituida": substituida,
            "verbos": verbos,
            "ferramentas": [{"nome": c.get("name"), "estado": c.get("estado")} for c in chamadas],
            "trecho": _trecho(texto, verbos[0]) if verbos else "",
        })
    except Exception as exc:
        print(f"[Trava] Falha ao registrar caso: {exc}")


def aplicar_trava(db, texto: str, chamadas, canal: str = "web") -> str:
    """Devolve o texto a enviar. `chamadas` = perf_state["tool_calls"] do turno,
    com `estado` preenchido nas ferramentas de escrita."""
    cfg = config(db)
    if cfg["modo"] == "desligado":
        return texto
    verbos = verbos_de_conclusao(texto, cfg["verbos"])
    if not verbos:
        return texto
    chamadas = list(chamadas or [])
    if any(c.get("estado") == "verificado" for c in chamadas):
        return texto
    bloquear = cfg["modo"] == "bloquear"
    _registrar_caso(db, canal=canal, modo=cfg["modo"], substituida=bloquear, verbos=verbos,
                    chamadas=chamadas, texto=texto)
    if not bloquear:
        return texto
    falhas = [c["resultado"] for c in chamadas if c.get("estado") == "falhou" and c.get("resultado")]
    if falhas:
        return "\n".join(montar_confirmacao(ResultadoOperacao(**r)) for r in falhas)
    return MENSAGEM_SEM_ACAO


# --- Verificação por releitura, ferramenta a ferramenta -----------------------

ALVO_PROPOSTA = "proposta"


def verificar_ferramenta(db, nome: str, args, resultado) -> Optional[ResultadoOperacao]:
    """ResultadoOperacao para ferramentas de escrita e propostas; None para leituras."""
    if nome in PROPOSTAS:
        return ResultadoOperacao("pendente", nome, ALVO_PROPOSTA)
    verificador = VERIFICADORES.get(nome)
    if verificador is None:
        return None
    try:
        return verificador(db, dict(args or {}), resultado)
    except Exception as exc:
        return ResultadoOperacao("falhou", nome, "?", motivo=f"não consegui conferir a gravação ({exc})")


def anotar_resultado(resultado, res: Optional[ResultadoOperacao]):
    """Acrescenta `verificacao` ao retorno que vai ao modelo, sem quebrar quem
    faz `json.loads` do retorno (JSON continua JSON). Propostas não são anotadas:
    o copiloto web relê o JSON delas para montar o cartão de confirmação."""
    if res is None or res.alvo == ALVO_PROPOSTA:
        return resultado
    nota = {"ok": res.ok, "estado": res.estado, "alvo": res.alvo}
    if res.motivo:
        nota["motivo"] = res.motivo
    if isinstance(resultado, dict):
        return {**resultado, "verificacao": nota}
    texto = "" if resultado is None else str(resultado)
    if texto.lstrip().startswith("{"):
        try:
            dados = json.loads(texto)
            if isinstance(dados, dict):
                return json.dumps({**dados, "verificacao": nota}, ensure_ascii=False, default=str)
        except ValueError:
            pass
    return f"{texto}\n[verificacao: {json.dumps(nota, ensure_ascii=False)}]"


def verificar_e_anotar_mcp(ctx, nome: str, args, resultado):
    """Lado MCP: relê o que a ferramenta gravou e acrescenta `verificacao` ao retorno.
    Ferramentas com outputSchema publicado ficam intactas: o cliente valida contra
    o esquema em cache e um campo a mais vira erro (incidente de 20/09/2026)."""
    from tools.registry import output_schema

    try:
        if output_schema(nome) is not None:
            return resultado
        return anotar_resultado(resultado, verificar_ferramenta(ctx.db, nome, args, resultado))
    except Exception as exc:
        print(f"[Trava] Falha ao verificar {nome} no MCP: {exc}")
        return resultado


def anotar_chamada(chamada: dict, res: Optional[ResultadoOperacao]) -> None:
    """Grava o estado na entrada de perf_state["tool_calls"] usada por `aplicar_trava`."""
    if res is None:
        return
    chamada["estado"] = res.estado
    chamada["resultado"] = res.to_dict()
