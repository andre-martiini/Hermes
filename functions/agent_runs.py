"""Observabilidade do que o Gaspar faz (agent_runs).

Registra execuções de rotinas agendadas, escritas feitas pelo Telegram e pelo
MCP, ações autônomas e tarefas externas do Claude, para o briefing das 05:00
("O que o Gaspar fez / O que espera você / O que pode ser desfeito / Falhas") e
para a consulta sob demanda (`consultar_execucoes_agente`).

Regras: o `resumo` é UMA linha com contagens e IDs, nunca texto de mensagem,
e-mail ou documento; o registro expira em 90 dias (TTL do Firestore sobre
`expira_em`); falha ao registrar nunca derruba a rotina instrumentada.
"""

from __future__ import annotations

import datetime
import re
from contextlib import contextmanager

from firebase_admin import firestore

COLLECTION = "agent_runs"

STATUS_SUCESSO = "sucesso"
STATUS_ERRO = "erro"
STATUS_PARCIAL = "parcial"

STATUS_VALIDOS = {STATUS_SUCESSO, STATUS_ERRO, STATUS_PARCIAL}
ORIGENS_VALIDAS = {"agendada", "telegram", "mcp", "autonoma", "manual"}
ESTADOS_VERIFICADOS = {"verificado", "falhou", "pendente"}

RETENCAO_DIAS = 90
RESUMO_MAX = 200
_MAX_IDS = 50
_MAX_EVIDENCIAS = 20


# ---------------------------------------------------------------------------
# Lógica pura (montagem e validação)
# ---------------------------------------------------------------------------


def _uma_linha(texto: str, limite: int) -> str:
    linha = re.sub(r"\s+", " ", str(texto or "")).strip()
    return linha if len(linha) <= limite else linha[: limite - 1] + "…"


def _lista_de_textos(valores, limite: int) -> list[str]:
    if not valores:
        return []
    if isinstance(valores, str):
        valores = [valores]
    vistos: list[str] = []
    for v in valores:
        texto = str(v or "").strip()
        if texto and texto not in vistos:
            vistos.append(texto)
    return vistos[:limite]


def montar_registro(
    rotina: str,
    resumo: str,
    contadores: dict | None = None,
    status: str = STATUS_SUCESSO,
    erro: str | None = None,
    iniciado_em: str | None = None,
    finalizado_em: str | None = None,
    *,
    origem: str | None = None,
    estado_verificado: str | None = None,
    acoes_afetadas=None,
    aguarda_usuario: bool | None = None,
    motivo_espera: str | None = None,
    reversivel: bool | None = None,
    como_desfazer: str | None = None,
    evidencias=None,
) -> dict:
    """Valida os dados da execução e monta o dicionário pronto para gravação.

    Os campos opcionais só entram quando preenchidos: quem já chamava com os
    sete campos originais recebe exatamente o mesmo dicionário de antes.
    Retorna {'erro': '...'} caso haja inconsistência nos dados.
    """
    rotina_limpa = str(rotina or "").strip()
    if not rotina_limpa:
        return {"erro": "rotina é obrigatória."}

    resumo_limpo = _uma_linha(resumo, RESUMO_MAX)
    if not resumo_limpo:
        return {"erro": "resumo é obrigatório."}

    status_limpo = str(status or STATUS_SUCESSO).strip().lower()
    if status_limpo not in STATUS_VALIDOS:
        return {"erro": f"status inválido: '{status}'. Permitidos: {sorted(STATUS_VALIDOS)}"}

    erro_limpo = str(erro).strip()[:500] if erro is not None and str(erro).strip() != "" else None
    if status_limpo == STATUS_ERRO and not erro_limpo:
        return {"erro": "erro é obrigatório quando status é 'erro'."}

    if contadores is not None and not isinstance(contadores, dict):
        return {"erro": "contadores deve ser um objeto/dicionário."}

    registro = {
        "rotina": rotina_limpa,
        "resumo": resumo_limpo,
        "status": status_limpo,
        "contadores": dict(contadores) if contadores else {},
        "erro": erro_limpo,
        "iniciado_em": str(iniciado_em).strip() if iniciado_em else None,
        "finalizado_em": str(finalizado_em).strip() if finalizado_em else None,
    }

    if origem is not None:
        origem_limpa = str(origem).strip().lower()
        if origem_limpa not in ORIGENS_VALIDAS:
            return {"erro": f"origem inválida: '{origem}'. Permitidas: {sorted(ORIGENS_VALIDAS)}"}
        registro["origem"] = origem_limpa
    if estado_verificado is not None:
        estado = str(estado_verificado).strip().lower()
        if estado not in ESTADOS_VERIFICADOS:
            return {"erro": f"estado_verificado inválido: '{estado_verificado}'. "
                            f"Permitidos: {sorted(ESTADOS_VERIFICADOS)}"}
        registro["estado_verificado"] = estado
    acoes = _lista_de_textos(acoes_afetadas, _MAX_IDS)
    if acoes:
        registro["acoes_afetadas"] = acoes
    if aguarda_usuario:
        registro["aguarda_usuario"] = True
        registro["motivo_espera"] = _uma_linha(motivo_espera, RESUMO_MAX) or None
    elif aguarda_usuario is False:
        registro["aguarda_usuario"] = False
    if reversivel:
        if not str(como_desfazer or "").strip():
            return {"erro": "como_desfazer é obrigatório quando reversivel é verdadeiro."}
        registro["reversivel"] = True
        registro["como_desfazer"] = _uma_linha(como_desfazer, RESUMO_MAX)
    refs = _lista_de_textos(evidencias, _MAX_EVIDENCIAS)
    if refs:
        registro["evidencias"] = refs
    return registro


def id_do_run(run_id: str | None) -> str | None:
    """`run_id` vira ID de documento: repetir a mesma execução não duplica."""
    if not run_id:
        return None
    limpo = re.sub(r"[/\s]+", "_", str(run_id).strip())[:300]
    return limpo or None


def _to_iso(dt: object) -> str | None:
    if dt is None:
        return None
    if hasattr(dt, "isoformat"):
        return dt.isoformat()
    return str(dt)


def _agora() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


# ---------------------------------------------------------------------------
# Operações Firestore (I/O)
# ---------------------------------------------------------------------------


def registrar(db, run_id: str | None = None, **kwargs) -> dict:
    """Valida e grava um registro de execução. Com `run_id`, o documento tem
    esse ID e uma nova gravação o substitui (idempotência)."""
    doc_data = montar_registro(**kwargs)
    if "erro" in doc_data and "rotina" not in doc_data:
        return doc_data

    payload = dict(doc_data)
    payload["criado_em"] = firestore.SERVER_TIMESTAMP
    payload["expira_em"] = _agora() + datetime.timedelta(days=RETENCAO_DIAS)
    if not payload.get("finalizado_em"):
        payload["finalizado_em"] = firestore.SERVER_TIMESTAMP

    col = db.collection(COLLECTION)
    doc_id = id_do_run(run_id)
    if doc_id:
        col.document(doc_id).set(payload)
        novo_id = doc_id
    else:
        add_res = col.add(payload)
        if isinstance(add_res, tuple):
            novo_id = add_res[1].id
        elif hasattr(add_res, "id"):
            novo_id = add_res.id
        else:
            novo_id = str(add_res)

    return {
        "status": "ok",
        "run_id": novo_id,
        "registro": doc_data,
    }


def _item_publico(doc_id: str, d: dict) -> dict:
    """Os nove campos do outputSchema publicado de consultar_execucoes_agente
    (additionalProperties: false) — nem um a mais."""
    return {
        "id": doc_id,
        "rotina": d.get("rotina"),
        "status": d.get("status"),
        "resumo": d.get("resumo"),
        "contadores": d.get("contadores") or {},
        "erro": d.get("erro"),
        "iniciado_em": _to_iso(d.get("iniciado_em")),
        "finalizado_em": _to_iso(d.get("finalizado_em")),
        "criado_em": _to_iso(d.get("criado_em")),
    }


_CAMPOS_COMPLETOS = ("origem", "estado_verificado", "acoes_afetadas", "aguarda_usuario", "motivo_espera",
                     "reversivel", "como_desfazer", "evidencias")


def _como_datahora(valor):
    if valor is None or isinstance(valor, datetime.datetime):
        return valor
    try:
        dt = datetime.datetime.fromisoformat(str(valor).strip().replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"desde inválido: '{valor}'. Use data/hora ISO, ex.: 2026-10-01T19:00:00-03:00")
    return dt if dt.tzinfo else dt.replace(tzinfo=datetime.timezone.utc)


def listar_recentes(
    db,
    rotina: str | None = None,
    limite: int = 20,
    *,
    desde=None,
    status: str | None = None,
    origem: str | None = None,
    aguarda_usuario: bool | None = None,
    completo: bool = False,
) -> dict:
    """Execuções mais recentes primeiro, filtradas no Firestore (índices
    compostos em firestore.indexes.json). Teto de 50. `completo=True` inclui os
    campos novos (uso interno: briefing); a resposta do MCP fica nos nove
    campos publicados."""
    limite_ajustado = max(1, min(int(limite or 20), 50))
    query = db.collection(COLLECTION)
    if rotina:
        query = query.where("rotina", "==", str(rotina).strip())
    if status:
        query = query.where("status", "==", str(status).strip().lower())
    if origem:
        query = query.where("origem", "==", str(origem).strip().lower())
    if aguarda_usuario is not None:
        query = query.where("aguarda_usuario", "==", bool(aguarda_usuario))
    desde_dt = _como_datahora(desde)
    if desde_dt is not None:
        query = query.where("criado_em", ">=", desde_dt)
    query = query.order_by("criado_em", direction=firestore.Query.DESCENDING).limit(limite_ajustado)

    runs: list[dict] = []
    for doc in query.stream():
        d = doc.to_dict() or {}
        item = _item_publico(doc.id, d)
        if completo:
            item.update({c: d.get(c) for c in _CAMPOS_COMPLETOS})
        runs.append(item)
    return {"total": len(runs), "runs": runs}


# ---------------------------------------------------------------------------
# Instrumentação de rotinas
# ---------------------------------------------------------------------------


class Execucao:
    """O que uma rotina instrumentada conta sobre si durante a execução."""

    def __init__(self, rotina: str, origem: str, run_id: str | None):
        self.rotina = rotina
        self.origem = origem
        self.run_id = run_id
        self.contadores: dict = {}
        self.status = STATUS_SUCESSO
        self.erro: str | None = None
        self._resumo: str | None = None
        self._extras: dict = {}

    def contar(self, **valores) -> None:
        for chave, valor in valores.items():
            self.contadores[chave] = valor

    def resumo(self, texto: str) -> None:
        self._resumo = texto

    def parcial(self, motivo: str) -> None:
        self.status = STATUS_PARCIAL
        self.erro = motivo

    def aguardando(self, motivo: str) -> None:
        self._extras.update(aguarda_usuario=True, motivo_espera=motivo)

    def reversivel(self, como_desfazer: str) -> None:
        self._extras.update(reversivel=True, como_desfazer=como_desfazer)

    def afetou(self, *acao_ids) -> None:
        self._extras.setdefault("acoes_afetadas", []).extend(a for a in acao_ids if a)

    def evidencia(self, *refs) -> None:
        self._extras.setdefault("evidencias", []).extend(r for r in refs if r)

    def verificado(self, estado: str) -> None:
        self._extras["estado_verificado"] = estado

    def texto_resumo(self) -> str:
        if self._resumo:
            return self._resumo
        partes = [f"{k}={v}" for k, v in self.contadores.items()]
        return f"{self.rotina}: " + (", ".join(partes) if partes else "executada")


def _gravar_execucao(db, run: Execucao, iniciado_em: datetime.datetime, status: str, erro: str | None) -> None:
    try:
        res = registrar(
            db,
            run_id=run.run_id,
            rotina=run.rotina,
            resumo=run.texto_resumo(),
            contadores=run.contadores,
            status=status,
            erro=erro,
            iniciado_em=iniciado_em.isoformat(),
            finalizado_em=_agora().isoformat(),
            origem=run.origem,
            **run._extras,
        )
        if "erro" in res and "status" not in res:
            print(f"[agent_runs] Registro recusado para {run.rotina}: {res['erro']}")
    except Exception as exc:
        print(f"[agent_runs] Falha ao registrar {run.rotina}: {exc}")


@contextmanager
def registrar_execucao(db, rotina: str, origem: str = "agendada", run_id: str | None = None):
    """Registra a execução da rotina mesmo em erro. Exceção dentro do bloco vira
    status=erro e continua propagando; falha ao registrar é logada e ignorada.

        with registrar_execucao(db, "briefing_matinal_acoes") as run:
            ...
            run.contar(tarefas=7, eventos=3)
    """
    run = Execucao(rotina, origem, run_id)
    inicio = _agora()
    try:
        yield run
    except Exception as exc:
        _gravar_execucao(db, run, inicio, STATUS_ERRO, f"{type(exc).__name__}: {exc}")
        raise
    _gravar_execucao(db, run, inicio, run.status, run.erro)
