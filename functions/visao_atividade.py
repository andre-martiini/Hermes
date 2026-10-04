"""Visão de atividade: o que o Gaspar fez, o que espera o André e o que pode ser desfeito.

Duas peças (PR 4 do plano "confirmação verificada"):

1. `secao_atividade` monta a seção do briefing das 05:00 a partir de
   `agent_runs` (das 19h de ontem até agora, horário de Brasília) e dos itens
   abertos da fila de atenção: Falhas (em destaque, primeiro), O que o Gaspar
   fez, O que espera você e O que pode ser desfeito, cortada para caber no
   limite de 4096 caracteres da mensagem do Telegram.
2. `on_whatsapp_outbox_escrito` grava em `agent_runs` o estado atual de cada
   mensagem da fila de WhatsApp (um registro por mensagem, substituído a cada
   transição). Reversível só enquanto não saiu. Sem destinatário nem texto.
"""

from __future__ import annotations

import datetime
import html

from firebase_functions import firestore_fn, options

import agent_runs

TZ_SP = "America/Sao_Paulo"
TELEGRAM_MAX_CHARS = 4096
ROTINA_WHATSAPP = "fila_whatsapp"
_MAX_ITENS = 5

_ROTULOS = {
    "relatorio_diario_custos": "Relatório de custos",
    "briefing_matinal_acoes": "Briefing das 5h",
    ROTINA_WHATSAPP: "WhatsApp",
    "escritas_mcp": "Ações editadas pelo Claude (MCP)",
    "escritas_telegram": "Ações editadas pelo Telegram",
    "escritas_web": "Ações editadas pelo app",
}

# status do outbox -> (contador, rótulo, estado_verificado)
_ESTADOS_OUTBOX = {
    "aguardando_aprovacao": ("aguardando_aprovacao", "aguardando sua aprovação", "pendente"),
    "aguardando_janela": ("aguardando_janela", "aguardando a janela de envio", "pendente"),
    "pending": ("na_fila", "na fila de envio", "pendente"),
    "notified": ("envio_manual", "aguardando envio manual pelo link", "pendente"),
    "sent": ("enviado", "enviado", "verificado"),
    "failed": ("falhou", "falhou", "falhou"),
    "canceled": ("cancelado", "cancelado", None),
    "descartado": ("descartado", "descartado", None),
    "expirado": ("expirado", "expirado", None),
}

_PLURAIS = {
    "enviado": ("enviado", "enviados"), "falhou": ("falhou", "falharam"), "na_fila": ("na fila", "na fila"),
    "cancelado": ("cancelado", "cancelados"), "descartado": ("descartado", "descartados"),
    "expirado": ("expirado", "expirados"), "aguardando_aprovacao": ("aguardando aprovação", "aguardando aprovação"),
    "aguardando_janela": ("aguardando a janela", "aguardando a janela"),
    "envio_manual": ("aguardando envio manual", "aguardando envio manual"),
}


# ---------------------------------------------------------------------------
# Seção do briefing (lógica pura)
# ---------------------------------------------------------------------------


def inicio_janela(agora_sp: datetime.datetime) -> datetime.datetime:
    """19h do dia anterior, no fuso de Brasília."""
    ontem = (agora_sp - datetime.timedelta(days=1)).date()
    return datetime.datetime.combine(ontem, datetime.time(19, 0), tzinfo=agora_sp.tzinfo)


LINHA_MAX = 140


def _e(texto, limite: int = LINHA_MAX) -> str:
    """Uma linha do briefing: cortada antes de escapar (o corte não parte uma entidade HTML)."""
    linha = " ".join(str(texto or "").split())
    if len(linha) > limite:
        linha = linha[: limite - 1].rstrip() + "…"
    return html.escape(linha)


def _rotulo(rotina: str) -> str:
    return _ROTULOS.get(rotina, rotina)


def _falhou(run: dict) -> bool:
    return run.get("status") == agent_runs.STATUS_ERRO or run.get("estado_verificado") == "falhou"


def _linha_whatsapp(runs: list[dict]) -> str:
    total: dict[str, int] = {}
    for run in runs:
        for chave, valor in (run.get("contadores") or {}).items():
            if isinstance(valor, (int, float)):
                total[chave] = total.get(chave, 0) + int(valor)
    partes = []
    for chave, (singular, plural) in _PLURAIS.items():
        n = total.get(chave, 0)
        if n:
            partes.append(f"{n} {singular if n == 1 else plural}")
    return "WhatsApp: " + (", ".join(partes) if partes else f"{len(runs)} movimentações")


def _linhas_fez(runs: list[dict]) -> list[str]:
    por_rotina: dict[str, list[dict]] = {}
    for run in runs:
        por_rotina.setdefault(run.get("rotina") or "?", []).append(run)
    linhas = []
    for rotina, lista in sorted(por_rotina.items(), key=lambda kv: -len(kv[1])):
        if rotina == ROTINA_WHATSAPP:
            linhas.append(_e(_linha_whatsapp(lista)))
        elif rotina.startswith("escritas_"):
            acoes = {a for r in lista for a in (r.get("acoes_afetadas") or [])}
            edicoes = f"{len(lista)} edição" if len(lista) == 1 else f"{len(lista)} edições"
            linhas.append(_e(f"{_rotulo(rotina)}: {edicoes}" + (f" em {len(acoes)} ações" if len(acoes) > 1 else "")))
        elif len(lista) == 1:
            linhas.append(_e(lista[0].get("resumo") or _rotulo(rotina)))
        else:
            linhas.append(_e(f"{_rotulo(rotina)}: {len(lista)} execuções — a última: {lista[0].get('resumo')}"))
    return linhas


def _bloco(titulo: str, itens: list[str], maximo: int, fora_da_lista: int = 0) -> list[str]:
    """`fora_da_lista`: itens que existem mas nem chegaram à lista (ex.: a fila de
    atenção é lida com teto), para o "+N" contar todos."""
    if not itens:
        return []
    linhas = [titulo] + [f"• {i}" for i in itens[:maximo]]
    restantes = max(0, len(itens) - maximo) + max(0, fora_da_lista)
    if restantes:
        linhas.append(f"+{restantes} itens")
    return linhas


def montar_secao(runs: list[dict], atencao: list[dict], limite: int = TELEGRAM_MAX_CHARS,
                 atencao_total: int | None = None) -> str:
    """Seção em HTML do Telegram, com no máximo `limite` caracteres. `atencao_total`
    é o total de itens abertos na fila, que pode ser maior que a lista lida."""
    atencao_fora = max(0, (atencao_total or 0) - len(atencao))
    runs = [r for r in runs if r.get("rotina") != "briefing_matinal_acoes"]
    falhas = [_e(f"{_rotulo(r.get('rotina'))}: {r.get('erro') or r.get('resumo')}") for r in runs if _falhou(r)]
    fez = _linhas_fez([r for r in runs if not _falhou(r)])
    espera = [_e(r.get("motivo_espera") or r.get("resumo")) for r in runs if r.get("aguarda_usuario")]
    espera += [_e(f"{i.get('titulo')} — {i.get('sugestao')}" if i.get("sugestao") else i.get("titulo"))
               for i in atencao if i.get("titulo")]
    desfazer = [_e(f"{r.get('resumo')} — {r.get('como_desfazer')}") for r in runs if r.get("reversivel")]

    for maximo in (_MAX_ITENS, 3, 1):
        linhas = (_bloco("⚠️ <b>Falhas</b>", falhas, maximo)
                  + _bloco("🤖 <b>O que o Gaspar fez</b>", fez, maximo)
                  + _bloco("⏳ <b>O que espera você</b>", espera, maximo, atencao_fora)
                  + _bloco("↩️ <b>O que pode ser desfeito</b>", desfazer, maximo))
        if not linhas:
            linhas = ["🤖 <b>O que o Gaspar fez</b>", "Nada registrado desde as 19h de ontem."]
        texto = "\n".join(linhas)
        if len(texto) <= limite:
            return texto
    return texto[: max(0, limite - 2)].rsplit("\n", 1)[0] + "\n…"


# ---------------------------------------------------------------------------
# Seção do briefing (leitura)
# ---------------------------------------------------------------------------


def secao_atividade(db, agora_sp: datetime.datetime, limite: int = TELEGRAM_MAX_CHARS) -> str:
    """Lê agent_runs (janela das 19h de ontem) e a fila de atenção aberta."""
    from atencao import coletar_fila_atencao

    runs = agent_runs.listar_recentes(db, limite=50, desde=inicio_janela(agora_sp), completo=True)["runs"]
    try:
        fila = coletar_fila_atencao(db, estado="aberto", limite=10)
        itens, total = fila["itens"], fila.get("total")
    except Exception as exc:
        print(f"[VisaoAtividade] Fila de atenção indisponível: {exc}")
        itens, total = [], None
    return montar_secao(runs, itens, limite, atencao_total=total)


# ---------------------------------------------------------------------------
# Fila de WhatsApp -> agent_runs
# ---------------------------------------------------------------------------


def registro_outbox(outbox_id: str, dados: dict) -> dict | None:
    """Argumentos de `agent_runs.registrar` para o estado atual de uma mensagem
    do outbox; None para estados transitórios (ex.: sending)."""
    status = (dados or {}).get("status")
    if status not in _ESTADOS_OUTBOX:
        return None
    contador, rotulo, estado = _ESTADOS_OUTBOX[status]
    tipo = (dados.get("tipo") or "").strip()
    resumo = f"WhatsApp{(' ' + tipo) if tipo else ''} {rotulo} (outbox {outbox_id})"
    args = {
        "run_id": f"whatsapp_outbox:{outbox_id}",
        "rotina": ROTINA_WHATSAPP,
        "resumo": resumo,
        "contadores": {contador: 1},
        "origem": "autonoma" if dados.get("aprovado_via") == "janela_automatica" else "agendada",
        "estado_verificado": estado,
        "acoes_afetadas": [dados["acao_id"]] if dados.get("acao_id") else None,
    }
    if status == "failed":
        args["status"] = agent_runs.STATUS_ERRO
        args["erro"] = str(dados.get("error_message") or "falha no envio")[:200]
    if status in ("aguardando_aprovacao", "notified"):
        args["aguarda_usuario"] = True
        args["motivo_espera"] = ("aprovar o rascunho de WhatsApp" if status == "aguardando_aprovacao"
                                 else "enviar pelo link ou tocar em \"Já enviei\"") + f" (outbox {outbox_id})"
    if status in ("aguardando_aprovacao", "aguardando_janela"):
        args["reversivel"] = True
        args["como_desfazer"] = f"descartar_rascunho_whatsapp(outbox_id={outbox_id})"
    elif status in ("pending", "notified"):
        args["reversivel"] = True
        args["como_desfazer"] = f"cancelar_envio_whatsapp(job_id={outbox_id}) enquanto não sair"
    return args


@firestore_fn.on_document_written(
    document="whatsapp_outbox/{outbox_id}",
    memory=options.MemoryOption.MB_256,
    timeout_sec=60,
)
def on_whatsapp_outbox_escrito(event: firestore_fn.Event[firestore_fn.Change[firestore_fn.DocumentSnapshot | None]]) -> None:
    """Cada mudança de status de uma mensagem do outbox vira o registro dela em agent_runs."""
    antes = event.data.before.to_dict() if event.data.before is not None and event.data.before.exists else {}
    depois = event.data.after.to_dict() if event.data.after is not None and event.data.after.exists else None
    if depois is None or (antes or {}).get("status") == depois.get("status"):
        return
    args = registro_outbox(event.params["outbox_id"], depois)
    if args is None:
        return
    from main import get_db

    try:
        agent_runs.registrar(get_db(), **args)
    except Exception as exc:
        print(f"[VisaoAtividade] Falha ao registrar outbox {event.params['outbox_id']}: {exc}")
