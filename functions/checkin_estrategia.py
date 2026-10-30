"""Check-in semanal da estratégia no Telegram (A8, relançamento de 30/10/2026).

Uma mensagem curta com, por meta, o atual, o esperado de hoje e o estado, e UM ajuste
sugerido quando alguma está atrasada. Nunca sugere ligação, call ou reunião. Não
envia nada quando todas as metas estão pausadas (ou nenhuma tem perfil).

O horário é configurável sem novo deploy: o agendamento roda de hora em hora e só
envia quando dia e hora batem com `system/settings.estrategia.checkin`
(`dia_semana` 0=segunda … 6=domingo, `hora` 0-23, `inicio` YYYY-MM-DD, `ativo`).
O padrão é domingo às 18h de Brasília, a partir de 08/11/2026 (provisório: o André ajusta).
`estrategia_checkins/{data}` marca o envio do dia e impede repetição.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from firebase_functions import options, scheduler_fn
from google.api_core.exceptions import AlreadyExists

from agent_runs import instrumentada

CONFIG_PADRAO = {"ativo": True, "dia_semana": 6, "hora": 18, "inicio": "2026-11-08"}
_PROIBIDO = re.compile(r"\b(liga[çc][aã]o|ligar|call|reuni[aã]o|videochamada)\b", re.IGNORECASE)
_ROTULO = {"no_perfil": "no perfil", "atrasado": "atrasado", "adiantado": "adiantado", "sem_dado": "sem dado"}


def configuracao(settings: dict | None) -> dict:
    gravada = ((settings or {}).get("estrategia") or {}).get("checkin") or {}
    return {**CONFIG_PADRAO, **{k: v for k, v in gravada.items() if k in CONFIG_PADRAO}}


def deve_enviar(agora: datetime, config: dict, ja_enviado_hoje: bool) -> bool:
    """`agora` já no fuso de Brasília."""
    ativo = config.get("ativo")
    if isinstance(ativo, str):  # "false" em texto não pode ligar o envio
        ativo = ativo.strip().lower() not in ("false", "0", "nao", "não", "")
    if not ativo or ja_enviado_hoje:
        return False
    try:
        inicio = date.fromisoformat(str(config.get("inicio"))[:10])
    except ValueError:
        inicio = date.fromisoformat(CONFIG_PADRAO["inicio"])
    return (agora.date() >= inicio and agora.weekday() == int(config.get("dia_semana", 6))
            and agora.hour == int(config.get("hora", 18)))


def _valor(valor, ind: dict) -> str:
    if valor is None:
        return "—"
    if ind.get("em_centavos"):
        reais = f"{valor / 100:,.0f}".replace(",", ".")
        return f"R$ {reais}"
    texto = f"{valor:.2f}".rstrip("0").rstrip(".").replace(".", ",")
    return f"{texto} {ind.get('unidade') or ''}".strip()


def _semanas_ate(data_iso: str, hoje: date) -> int:
    return max(1, -(-(date.fromisoformat(data_iso) - hoje).days // 7))


def sugerir_ajuste(metas: list[dict], hoje: date) -> str | None:
    """UM ajuste, para o indicador mais atrasado (maior distância relativa ao esperado);
    sem indicador numérico atrasado, o marco sem número vencido mais antigo."""
    piores = []
    for meta in metas:
        for ind in (meta.get("perfil") or {}).get("indicadores") or []:
            if ind.get("estado") != "atrasado" or ind.get("atual") is None or not ind.get("esperado_hoje"):
                continue
            piores.append((abs(ind["atual"] - ind["esperado_hoje"]) / abs(ind["esperado_hoje"]), meta, ind))
    if piores:
        _, meta, ind = max(piores, key=lambda p: p[0])
        alvo = ind.get("proximo_marco") or {"valor": ind["esperado_hoje"], "data": hoje.isoformat()}
        falta = abs(alvo["valor"] - ind["atual"])
        semanas = _semanas_ate(alvo["data"], hoje) if alvo["data"] > hoje.isoformat() else 1
        por_semana = falta / semanas if ind.get("em_centavos") else round(falta / semanas, 2)
        return (f"Ajuste sugerido ({meta['objetivo']}): {ind['rotulo']} precisa de {_valor(falta, ind)} até "
                f"{_valor(alvo['valor'], ind)} em {alvo['data'][8:10]}/{alvo['data'][5:7]}, cerca de "
                f"{_valor(por_semana, ind)} por semana. Vale escolher agora, no Gaspar, a ação desta semana que mais move esse número.")
    vencidos = [(m.get("dataAlvo") or "", meta, m) for meta in metas
                for m in (meta.get("perfil") or {}).get("marcos_sem_numero") or [] if m.get("estado") == "atrasado"]
    if vencidos:
        data_alvo, meta, marco = min(vencidos, key=lambda v: v[0])
        return (f"Ajuste sugerido ({meta['objetivo']}): o marco '{marco['descricao']}' venceu em "
                f"{data_alvo[8:10]}/{data_alvo[5:7]}. Concluir esta semana ou remarcar a data no Gaspar.")
    return None


def montar_mensagem(metas: list[dict], hoje: date) -> str | None:
    """Texto do check-in, ou None quando não há meta ativa com perfil (todas pausadas, por exemplo)."""
    ativas = [m for m in metas if not m.get("pausada") and m.get("perfil") and m["perfil"].get("estado")]
    if not ativas:
        return None
    linhas = [f"📊 Check-in da estratégia ({hoje.strftime('%d/%m')})"]
    for meta in ativas:
        perfil = meta["perfil"]
        linhas.append(f"\n• {meta['objetivo']}: {_ROTULO.get(perfil['estado'], perfil['estado'])}")
        for ind in perfil.get("indicadores") or []:
            linhas.append(f"  {ind['rotulo']}: {_valor(ind.get('atual'), ind)} "
                          f"(esperado {_valor(ind.get('esperado_hoje'), ind)}) — {_ROTULO.get(ind.get('estado'), 'sem perfil')}")
        for marco in perfil.get("marcos_sem_numero") or []:
            if marco.get("estado") == "atrasado":
                linhas.append(f"  Marco vencido: {marco['descricao']}")
    ajuste = sugerir_ajuste(ativas, hoje)
    if ajuste and not _PROIBIDO.search(ajuste):  # trava: nunca ligação, call ou reunião
        linhas.append(f"\n{ajuste}")
    return "\n".join(linhas)


@scheduler_fn.on_schedule(
    schedule="5 * * * *",
    timezone="America/Sao_Paulo",
    memory=options.MemoryOption.MB_256,
    timeout_sec=120,
)
@instrumentada("checkin_estrategia_semanal")
def checkin_estrategia_semanal(event: scheduler_fn.ScheduledEvent = None) -> None:
    """De hora em hora; só envia no dia e hora configurados (padrão domingo 18h BRT)."""
    from zoneinfo import ZoneInfo

    from hermes_core_logic import _get_allowed_chat_id, _send_telegram_message
    from main import _get_telegram_token, get_db

    db = get_db()
    agora = datetime.now(ZoneInfo("America/Sao_Paulo"))
    settings_doc = db.collection("system").document("settings").get()
    config = configuracao(settings_doc.to_dict() if settings_doc.exists else {})
    hoje = agora.date().isoformat()
    marca = db.collection("estrategia_checkins").document(hoje)
    if not deve_enviar(agora, config, False):
        return
    # `create` é atômico: duas execuções na mesma hora (o Scheduler entrega pelo menos uma vez)
    # não mandam duas mensagens; a segunda encontra a marca e sai.
    try:
        marca.create({"enviado": False, "em_iso": agora.isoformat()})
    except AlreadyExists:
        return

    import morning_summary as ms

    saude = ms._coletar_saude(db, hoje, ms._shift(hoje, -1))
    medicoes = {k: v for k, v in {"peso": (saude.get("peso") or {}).get("ultimo"),
                                  "cintura": (saude.get("cintura") or {}).get("ultimo")}.items() if v}
    metas = ms._coletar_estrategia(db, hoje, {}, {}, saude.get("ultimo_registro"), medicoes=medicoes)["metas"]
    partes = [montar_mensagem(metas, agora.date())]
    try:  # a linha do teto não pode derrubar o check-in da estratégia
        import avisos_teto

        dia = agora.date()
        fin = db.collection("finance_settings").document("config").get()
        transacoes = avisos_teto.carregar_transacoes(db, min(dia.replace(day=1), dia - timedelta(days=6)))
        partes.append(avisos_teto.linha_semanal(transacoes, fin.to_dict() if fin.exists else {}, dia))
    except Exception as exc:
        print(f"[CheckinEstrategia] Linha do teto falhou: {exc}")
    mensagem = "\n\n".join(p for p in partes if p) or None
    marca.update({"enviado": bool(mensagem), "mensagem": mensagem})
    if not mensagem:
        print("[CheckinEstrategia] Nenhuma meta ativa com perfil nem teto; nada enviado.")
        return
    chat_id = _get_allowed_chat_id()
    if chat_id:
        _send_telegram_message(_get_telegram_token(db), chat_id, mensagem)
    else:
        print("[CheckinEstrategia] Sem chat_id do Telegram; check-in só registrado.")
