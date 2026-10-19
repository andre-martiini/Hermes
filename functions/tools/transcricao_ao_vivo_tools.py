"""Leitura da transcrição ao vivo pelo conector MCP (somente leitura, sem IA).

`listar_transcricoes_ao_vivo` acha a sessão; `ler_transcricao_ao_vivo` devolve
os trechos depois de um cursor (`apos_seq`) e o `proximo_seq` para a chamada
seguinte. Os dados vêm de `transcricoes_ao_vivo` (ver
`functions/transcricao_ao_vivo.py`): o seq é contínuo e nenhum trecho muda
depois de gravado, então a mesma chamada devolve sempre os mesmos trechos.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from transcricao_ao_vivo import AO_VIVO, COLECAO, ENCERRADA, SUBCOLECAO

MAIS_RECENTE = "mais_recente_ativa"
MAX_CARACTERES_PADRAO = 12000
MAX_CARACTERES_MIN = 1000
MAX_CARACTERES_MAX = 50000
LIMITE_TRECHOS_CONSULTA = 300
LIMITE_LISTAR_PADRAO = 10
LIMITE_LISTAR_MAX = 30
ULTIMOS_MINUTOS_MAX = 24 * 60
# Sem lote nem sinal de vida (o navegador manda um a cada 30 s): a gravação parou de chegar.
SEM_SINAL_S = 120
# Sessão "ao_vivo" sem sinal há mais que isso (aba fechada no meio) sai da lista de ativas.
ABANDONADA_S = 30 * 60
INTERVALO_SUGERIDO_S = 30


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _segundos_desde(quando, agora: datetime) -> int | None:
    if not isinstance(quando, datetime):
        return None
    if quando.tzinfo is None:
        quando = quando.replace(tzinfo=timezone.utc)
    return max(0, int((agora - quando).total_seconds()))


def _iso_brasilia(quando) -> str | None:
    if not isinstance(quando, datetime):
        return None
    if quando.tzinfo is None:
        quando = quando.replace(tzinfo=timezone.utc)
    try:
        from zoneinfo import ZoneInfo

        return quando.astimezone(ZoneInfo("America/Sao_Paulo")).isoformat(timespec="seconds")
    except Exception:  # noqa: BLE001 - sem base de fusos, fica em UTC
        return quando.astimezone(timezone.utc).isoformat(timespec="seconds")


def _inteiro(valor, padrao: int | None, minimo: int, maximo: int) -> int | None:
    if valor is None or valor == "" or isinstance(valor, bool):
        return padrao
    try:
        n = int(valor)
    except (TypeError, ValueError, OverflowError):
        return padrao
    return max(minimo, min(n, maximo))


def _bool(valor, padrao: bool) -> bool:
    if isinstance(valor, bool):
        return valor
    if isinstance(valor, str) and valor.strip().lower() in ("false", "0", "nao", "não", "no"):
        return False
    if isinstance(valor, str) and valor.strip().lower() in ("true", "1", "sim", "yes"):
        return True
    return padrao


def _abandonada(sessao: dict, agora: datetime) -> bool:
    desde = _segundos_desde(sessao.get("atualizada_em"), agora)
    return desde is None or desde > ABANDONADA_S


def _resumo(sessao: dict, agora: datetime) -> dict:
    desde_atualizacao = _segundos_desde(sessao.get("atualizada_em"), agora)
    ao_vivo = sessao.get("estado") == AO_VIVO
    return {
        "sessao_id": sessao.get("id"),
        "titulo": sessao.get("titulo"),
        "estado": sessao.get("estado"),
        "iniciada_em": _iso_brasilia(sessao.get("iniciada_em")),
        "encerrada_em": _iso_brasilia(sessao.get("encerrada_em")),
        "ultimo_seq": int(sessao.get("ultimo_seq") or 0),
        "segundos_desde_ultimo_trecho": _segundos_desde(sessao.get("ultimo_trecho_em"), agora),
        "sem_sinal": bool(ao_vivo and (desde_atualizacao is None or desde_atualizacao > SEM_SINAL_S)),
        "total_caracteres": int(sessao.get("total_caracteres") or 0),
        "terceiros_presentes": bool(sessao.get("terceiros_presentes")),
        "reuniao_id": sessao.get("reuniao_id"),
    }


def _ativas(db, agora: datetime) -> list[dict]:
    """Sessões `ao_vivo` com sinal nos últimos 30 min, a mais recente primeiro (filtro e ordem em memória: sem índice composto)."""
    docs = db.collection(COLECAO).where("estado", "==", AO_VIVO).limit(50).stream()
    sessoes = [d.to_dict() or {} for d in docs]
    sessoes = [s for s in sessoes if not _abandonada(s, agora)]
    sessoes.sort(key=lambda s: s.get("atualizada_em") or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return sessoes


def listar(ctx, args: dict) -> dict:
    args = args or {}
    agora = _agora()
    apenas_ativas = _bool(args.get("apenas_ativas"), True)
    limite = _inteiro(args.get("limite"), LIMITE_LISTAR_PADRAO, 1, LIMITE_LISTAR_MAX)
    if apenas_ativas:
        sessoes = _ativas(ctx.db, agora)[:limite]
    else:
        docs = ctx.db.collection(COLECAO).order_by("iniciada_em", direction="DESCENDING").limit(limite).stream()
        sessoes = [d.to_dict() or {} for d in docs]
    itens = [_resumo(s, agora) for s in sessoes]
    saida = {"apenas_ativas": apenas_ativas, "total": len(itens), "sessoes": itens}
    if itens:
        saida["orientacao"] = ("leia com ler_transcricao_ao_vivo(sessao_id) e continue pelo cursor: "
                               "passe o proximo_seq devolvido como apos_seq na chamada seguinte")
    elif apenas_ativas:
        saida["orientacao"] = ("nenhuma transcrição ao vivo agora; peça ao André para gravar na ferramenta "
                               "Reuniões em Tempo Real do Gaspar, ou liste com apenas_ativas=false as encerradas")
    return saida


def _sessao(ctx, sessao_id: str, agora: datetime) -> tuple[dict | None, dict | None]:
    if not sessao_id or sessao_id == MAIS_RECENTE:
        ativas = _ativas(ctx.db, agora)
        if not ativas:
            return None, {"erro": "nenhuma transcrição ao vivo agora",
                          "orientacao": "chame listar_transcricoes_ao_vivo(apenas_ativas=false) para ver as encerradas"}
        return ativas[0], None
    if "/" in sessao_id:
        return None, {"erro": "sessão de transcrição não encontrada"}
    snap = ctx.db.collection(COLECAO).document(sessao_id).get()
    if not snap.exists:
        return None, {"erro": "sessão de transcrição não encontrada",
                      "orientacao": "confira o id com listar_transcricoes_ao_vivo"}
    return snap.to_dict() or {}, None


def _cursor_por_minutos(ref, minutos: int, agora: datetime, ultimo_seq: int) -> int:
    """Seq anterior ao primeiro trecho gravado nos últimos `minutos` (sem trecho na janela: o último seq)."""
    limite = agora - timedelta(minutes=minutos)
    docs = list(ref.collection(SUBCOLECAO).where("criado_em", ">=", limite)
                .order_by("criado_em").limit(1).stream())
    if not docs:
        return ultimo_seq
    return max(0, int(docs[0].get("seq") or 1) - 1)


def ler(ctx, args: dict) -> dict:
    args = args or {}
    agora = _agora()
    sessao_id = str(args.get("sessao_id") or MAIS_RECENTE).strip()
    sessao, erro = _sessao(ctx, sessao_id, agora)
    if erro:
        return erro
    sessao_id = sessao.get("id")
    ref = ctx.db.collection(COLECAO).document(sessao_id)
    ultimo_seq = int(sessao.get("ultimo_seq") or 0)
    max_caracteres = _inteiro(args.get("max_caracteres"), MAX_CARACTERES_PADRAO, MAX_CARACTERES_MIN, MAX_CARACTERES_MAX)
    apos_seq = _inteiro(args.get("apos_seq"), None, 0, 10**9)
    minutos = _inteiro(args.get("ultimos_minutos"), None, 1, ULTIMOS_MINUTOS_MAX)
    if apos_seq is None:
        apos_seq = _cursor_por_minutos(ref, minutos, agora, ultimo_seq) if minutos else 0

    trechos, usados = [], 0
    if apos_seq < ultimo_seq:
        docs = (ref.collection(SUBCOLECAO).where("seq", ">", apos_seq).order_by("seq")
                .limit(LIMITE_TRECHOS_CONSULTA).stream())
        for d in docs:
            t = d.to_dict() or {}
            texto = t.get("texto") or ""
            if trechos and usados + len(texto) > max_caracteres:
                break
            trechos.append({"seq": int(t.get("seq") or 0), "t_inicio": t.get("t_inicio"), "t_fim": t.get("t_fim"),
                            "falante": t.get("falante"), "texto": texto})
            usados += len(texto)
    proximo_seq = trechos[-1]["seq"] if trechos else apos_seq
    truncado = proximo_seq < ultimo_seq
    estado = sessao.get("estado")
    resumo = _resumo(sessao, agora)
    saida = {
        "sessao_id": sessao_id,
        "titulo": sessao.get("titulo"),
        "estado": estado,
        "apos_seq": apos_seq,
        "trechos": trechos,
        "proximo_seq": proximo_seq,
        "ultimo_seq": ultimo_seq,
        "truncado": truncado,
        "atraso_segundos": resumo["segundos_desde_ultimo_trecho"],
        "sem_sinal": resumo["sem_sinal"],
        "caracteres": usados,
    }
    if truncado:
        saida["orientacao"] = (f"há mais trechos já gravados: chame de novo agora com apos_seq={proximo_seq} "
                               "(o mesmo sessao_id) até truncado=false")
    elif estado == ENCERRADA:
        saida["orientacao"] = "a sessão foi encerrada e não terá trechos novos; esta leitura continua valendo"
    elif resumo["sem_sinal"]:
        saida["orientacao"] = ("a gravação parou de mandar sinal (aba fechada ou sem internet?); "
                               f"tente de novo mais tarde com apos_seq={proximo_seq}")
    else:
        saida["orientacao"] = (f"ao vivo: para os trechos novos, chame de novo em ~{INTERVALO_SUGERIDO_S} s "
                               f"com apos_seq={proximo_seq}")
    return saida
