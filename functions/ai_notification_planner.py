"""
Planejador proativo de notificações — módulo aditivo, independente do
Copiloto e do Godmode. Uma vez por dia, um agente sobre Claude (mesmo
provider/loop de tool-calling do Godmode) varre tarefas ativas e metas
estratégicas pessoais e decide, com um teto diário rígido, se algum insight
cruzando esses domínios merece virar notificação no Telegram — sem duplicar
os lembretes determinísticos que o Hermes já dispara (prazo de tarefa
configurado, pesagem, rotina de saúde).

Cada proposta aceita é gravada em `scheduled_notifications` (status
'pending'). O envio de fato acontece depois, em `dispatch_pending_ai_notifications`,
chamado a partir de `check_and_send_reminders` (main.py) — o mesmo motor de
1 em 1 minuto que já despacha os demais lembretes. Essa separação mantém o
custo de LLM concentrado numa única chamada diária e o caminho de envio
determinístico e barato.

Financeiro e saúde ficam fora do escopo aqui pela mesma razão que estão fora
do Godmode hoje: sem ferramentas de leitura calibradas para esses domínios
ainda (ver `godmode.py`).
"""

import datetime
import os
import re

try:
    import zoneinfo
except ImportError:
    from backports import zoneinfo

from firebase_admin import firestore
from firebase_functions import scheduler_fn, options

from llm_providers import claude_provider

AI_PLANNER_MODEL = os.environ.get("AI_PLANNER_MODEL", "claude-fable-5")
AI_PLANNER_FALLBACK_MODEL = os.environ.get("AI_PLANNER_FALLBACK_MODEL", "claude-opus-4-8")
AI_PLANNER_MAX_TOKENS = int(os.environ.get("AI_PLANNER_MAX_TOKENS", "2048"))
AI_PLANNER_MAX_DAILY_NOTIFICATIONS = int(os.environ.get("AI_PLANNER_MAX_DAILY_NOTIFICATIONS", "3"))
AI_PLANNER_WINDOW_START = os.environ.get("AI_PLANNER_WINDOW_START", "07:00")
AI_PLANNER_WINDOW_END = os.environ.get("AI_PLANNER_WINDOW_END", "22:00")
AI_PLANNER_STALE_HOURS = 2

_CATEGORY_ICONS = {"acoes": "🗒️", "estrategia": "🎯", "geral": "🤖"}

AI_PLANNER_PERSONA = (
    "Você é o planejador proativo do Hermes: um processo que roda uma vez por dia, sem "
    "interação com o usuário, e decide se vale a pena interromper o dia dele com alguma "
    "notificação no Telegram.\n\n"
    "Escopo desta rodada: apenas tarefas/ações (`tarefas`) e metas estratégicas pessoais "
    "(`estrategia_pessoal`). Financeiro e saúde ainda não têm ferramentas aqui — não invente "
    "dados desses domínios nem tente compensar a ausência deles.\n\n"
    "Regra de ouro: silêncio é o resultado padrão e correto na maioria dos dias. O sistema já "
    "dispara lembretes determinísticos e confiáveis para prazo de tarefa configurado, pesagem "
    "e rotina de saúde — NUNCA duplique esses avisos. Seu valor está em cruzar dados que "
    "nenhuma regra fixa cruza: uma meta estratégica sem nenhuma tarefa ativa vinculada há "
    "semanas, um padrão de degradação (degradation_count subindo) numa área que sustenta uma "
    "meta, um marco de meta cuja métrica não é atualizada há muito tempo, uma tarefa com prazo "
    "próximo sem plano de ação definido. Só proponha algo com um motivo concreto, ancorado em "
    "dado real obtido via ferramenta — nunca por especulação.\n\n"
    f"Limite rígido: no máximo {AI_PLANNER_MAX_DAILY_NOTIFICATIONS} notificações por dia, "
    "espaçadas ao longo do dia (não todas no mesmo horário, dentro da janela permitida). Antes "
    "de propor qualquer coisa, consulte o histórico recente com consultar_notificacoes_recentes "
    "— se um tipo de alerta foi dispensado (feedback 'dismissed') recentemente, não repita a "
    "mesma sugestão.\n\n"
    "Toda proposta real de notificação deve ser feita SOMENTE via a ferramenta "
    "propor_notificacao — nunca escreva a lista de sugestões como texto livre na resposta "
    "final. O texto de 'mensagem' passado para a ferramenta é o que o usuário vai ler direto "
    "no Telegram: curto (1 a 3 frases), direto, sem markdown ou HTML.\n\n"
    "Ao final da rodada, escreva 1-2 frases resumindo o que foi decidido (inclusive se a "
    "decisão foi não propor nada e por quê) — esse texto é só para log interno, o usuário não "
    "vê essa resposta."
)


def _build_tools(db, now_sp: "datetime.datetime", today_str: str, existing_count: int):
    """Registro de ferramentas do planejador: 3 de leitura + 1 de escrita (propor_notificacao)."""
    proposed_count = existing_count

    def consultar_tarefas_ativas(area_tematica: str = "") -> dict:
        query = db.collection("tarefas")
        if area_tematica:
            query = query.where("area_tematica", "==", area_tematica)
        tarefas = []
        for d in query.limit(300).stream():
            data = d.to_dict() or {}
            status = data.get("status")
            if status not in ("em andamento", "stand-by"):
                continue
            if area_tematica and data.get("area_tematica") != area_tematica:
                continue
            plano = data.get("plano_acao") or []
            pendentes = [
                str(item.get("text") or "").strip()
                for item in plano
                if isinstance(item, dict) and item.get("text") and not item.get("completed")
            ][:3]
            tarefas.append({
                "id": d.id,
                "titulo": data.get("titulo"),
                "status": status,
                "area_tematica": data.get("area_tematica"),
                "projeto": data.get("projeto"),
                "data_limite": data.get("data_limite"),
                "prazo_final": data.get("prazo_final"),
                "execution_lane": data.get("execution_lane"),
                "degradation_count": data.get("degradation_count"),
                "proximos_passos_pendentes": pendentes,
                "estrategia_objetivo_id": data.get("estrategia_objetivo_id"),
            })
            if len(tarefas) >= 150:
                break
        return {"tarefas": tarefas}

    def consultar_metas_estrategicas() -> dict:
        metas = []
        for d in db.collection("estrategia_pessoal").limit(80).stream():
            data = d.to_dict() or {}
            status = str(data.get("status", "")).lower()
            if status in ("concluido", "concluído", "cancelado", "arquivado"):
                continue
            metas.append({
                "id": d.id,
                "pilar": data.get("pilar"),
                "objetivoMacro": data.get("objetivoMacro"),
                "tipoMeta": data.get("tipoMeta"),
                "metricaAlvo": data.get("metricaAlvo"),
                "marcos": data.get("marcos"),
                "status": data.get("status"),
            })
        return {"metas": metas}

    def consultar_notificacoes_recentes(dias: int = 7) -> dict:
        dias = max(1, min(int(dias or 7), 30))
        cutoff = now_sp - datetime.timedelta(days=dias)
        recentes = []
        try:
            query = db.collection("scheduled_notifications").where("created_at", ">=", cutoff).limit(60)
            for d in query.stream():
                data = d.to_dict() or {}
                if data.get("source") != "ai_planner":
                    continue
                recentes.append({
                    "titulo": data.get("title"),
                    "categoria": data.get("category"),
                    "status": data.get("status"),
                    "feedback": data.get("feedback"),
                    "motivo": data.get("motivo"),
                })
        except Exception as exc:
            return {"erro": f"Falha ao consultar historico: {exc}"}
        return {"notificacoes_recentes": recentes}

    def propor_notificacao(titulo: str, mensagem: str, horario: str, categoria: str = "geral", motivo: str = "") -> dict:
        nonlocal proposed_count
        titulo = str(titulo or "").strip()
        mensagem = str(mensagem or "").strip()
        horario = str(horario or "").strip()
        categoria = str(categoria or "geral").strip().lower()
        motivo = str(motivo or "").strip()
        if categoria not in ("acoes", "estrategia", "geral"):
            categoria = "geral"
        if not titulo or not mensagem:
            return {"erro": "titulo e mensagem sao obrigatorios."}
        if not re.match(r"^([01]\d|2[0-3]):[0-5]\d$", horario):
            return {"erro": "horario deve estar no formato HH:MM (24h)."}
        if horario < AI_PLANNER_WINDOW_START or horario > AI_PLANNER_WINDOW_END:
            return {"erro": f"horario fora da janela permitida ({AI_PLANNER_WINDOW_START}-{AI_PLANNER_WINDOW_END})."}
        if proposed_count >= AI_PLANNER_MAX_DAILY_NOTIFICATIONS:
            return {"erro": f"Limite diario de {AI_PLANNER_MAX_DAILY_NOTIFICATIONS} notificacoes ja atingido."}

        hh, mm = horario.split(":")
        send_dt = now_sp.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
        if send_dt <= now_sp + datetime.timedelta(minutes=1):
            return {"erro": "horario ja passou ou esta a menos de 1 minuto de distancia — escolha um horario mais tarde hoje."}

        doc_ref = db.collection("scheduled_notifications").document()
        doc_ref.set({
            "title": titulo[:120],
            "message": mensagem[:600],
            "category": categoria,
            "send_at": send_dt,
            "status": "pending",
            "source": "ai_planner",
            "motivo": motivo[:300] if motivo else None,
            "created_at": firestore.SERVER_TIMESTAMP,
            "planner_run_date": today_str,
            "feedback": None,
        })
        proposed_count += 1
        return {"ok": True, "id": doc_ref.id, "agendado_para": horario}

    function_map = {
        "consultar_tarefas_ativas": consultar_tarefas_ativas,
        "consultar_metas_estrategicas": consultar_metas_estrategicas,
        "consultar_notificacoes_recentes": consultar_notificacoes_recentes,
        "propor_notificacao": propor_notificacao,
    }

    tools_schema = [
        {
            "name": "consultar_tarefas_ativas",
            "description": (
                "Lista tarefas/ações com status 'em andamento' ou 'stand-by' (nunca concluídas), "
                "com prazos, execution_lane, degradation_count, próximos passos pendentes do "
                "plano de ação e o vínculo com meta estratégica (estrategia_objetivo_id), se houver."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "area_tematica": {
                        "type": "string",
                        "description": "Filtra por área temática exata, se conhecida. Deixe vazio para todas.",
                    },
                },
            },
        },
        {
            "name": "consultar_metas_estrategicas",
            "description": (
                "Lista os objetivos/metas estratégicas pessoais ativos (oculta concluídos, "
                "cancelados e arquivados), com pilar, métrica alvo/atual e marcos."
            ),
            "input_schema": {"type": "object", "properties": {}},
        },
        {
            "name": "consultar_notificacoes_recentes",
            "description": (
                "Lista as notificações que este mesmo planejador já propôs nos últimos N dias, "
                "com o feedback do usuário (útil/dispensada), para evitar repetir sugestões já "
                "recusadas. Consulte sempre antes de propor algo novo."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "dias": {"type": "integer", "description": "Janela em dias (padrão 7, máximo 30)."},
                },
            },
        },
        {
            "name": "propor_notificacao",
            "description": (
                "Agenda uma notificação real para ser enviada ao usuário no Telegram hoje, no "
                "horário indicado. É a ÚNICA forma válida de propor algo — sujeita a validação "
                "server-side de horário e ao teto diário de notificações."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "titulo": {"type": "string", "description": "Título curto da notificação."},
                    "mensagem": {
                        "type": "string",
                        "description": "Corpo da mensagem, 1 a 3 frases, texto puro (sem markdown/HTML).",
                    },
                    "horario": {
                        "type": "string",
                        "description": f"Horário de envio hoje, formato HH:MM (24h), dentro de {AI_PLANNER_WINDOW_START}-{AI_PLANNER_WINDOW_END}.",
                    },
                    "categoria": {
                        "type": "string",
                        "enum": ["acoes", "estrategia", "geral"],
                        "description": "Domínio principal que motivou a notificação.",
                    },
                    "motivo": {
                        "type": "string",
                        "description": "Justificativa curta (dado concreto que embasou a proposta) — fica só no log interno.",
                    },
                },
                "required": ["titulo", "mensagem", "horario"],
            },
        },
    ]

    return tools_schema, function_map


@scheduler_fn.on_schedule(
    schedule="30 6 * * *",  # Todos os dias às 6:30 (após o briefing matinal das 5h)
    timezone="America/Sao_Paulo",
    memory=options.MemoryOption.MB_512,
    timeout_sec=180,
)
def ai_notification_planner_daily(event: scheduler_fn.ScheduledEvent):
    """Roda o planejador de IA 1x/dia; grava propostas em scheduled_notifications (status pending)."""
    from main import get_db, _cached_doc_get

    try:
        import anthropic
    except ImportError:
        print("[AIPlanner] Dependência 'anthropic' não instalada; abortando.")
        return

    db = get_db()
    keys_doc = _cached_doc_get(db, "system", "api_keys")
    claude_key = (keys_doc.to_dict() or {}).get("claude_api_key") if keys_doc.exists else None
    if not claude_key:
        print("[AIPlanner] claude_api_key não configurada em system/api_keys; abortando.")
        return

    sp_tz = zoneinfo.ZoneInfo("America/Sao_Paulo")
    now_sp = datetime.datetime.now(sp_tz)
    today_str = now_sp.strftime("%Y-%m-%d")

    existing_today = 0
    try:
        existing_today = sum(
            1 for _ in db.collection("scheduled_notifications")
            .where("planner_run_date", "==", today_str)
            .where("source", "==", "ai_planner")
            .stream()
        )
    except Exception as exc:
        print(f"[AIPlanner] Falha ao contar notificações já propostas hoje: {exc}")

    if existing_today >= AI_PLANNER_MAX_DAILY_NOTIFICATIONS:
        print(f"[AIPlanner] Teto diário ({AI_PLANNER_MAX_DAILY_NOTIFICATIONS}) já atingido hoje; não há necessidade de rodar.")
        return

    tools, function_map = _build_tools(db, now_sp, today_str, existing_today)
    client = anthropic.Anthropic(api_key=claude_key)
    user_message = (
        f"Hoje é {today_str}. Analise o estado atual do sistema e proponha, via a ferramenta "
        "propor_notificacao, apenas os lembretes/insights que realmente merecem interromper o "
        "dia do usuário agora. Se nada for suficientemente relevante, não chame a ferramenta e "
        "apenas explique brevemente por que não há nada a propor hoje."
    )

    try:
        result = claude_provider.run_tool_loop(
            client=client,
            model=AI_PLANNER_MODEL,
            system_instruction=AI_PLANNER_PERSONA,
            tools=tools,
            function_map=function_map,
            history=[],
            user_message=user_message,
            max_tokens=AI_PLANNER_MAX_TOKENS,
            fallback_model=AI_PLANNER_FALLBACK_MODEL,
        )
    except Exception as exc:
        print(f"[AIPlanner] Falha na chamada à Claude API: {exc}")
        return

    print(
        f"[AIPlanner] Rodada concluída. tools_used={result['tools_used']} "
        f"modelo={result['model_used']} resumo={result['text'][:300]!r}"
    )


def dispatch_pending_ai_notifications(db, now) -> None:
    """
    Consome `scheduled_notifications` com status 'pending' e send_at <= agora,
    enviando cada uma ao Telegram com botões de feedback (👍 útil / 👎 dispensar).
    Chamado a partir de check_and_send_reminders (main.py), a cada 1 minuto —
    o mesmo motor determinístico que já despacha os demais lembretes.
    """
    from main import _resolve_default_telegram_chat_id, _send_telegram_message_raw_with_keyboard

    try:
        pending = (
            db.collection("scheduled_notifications")
            .where("status", "==", "pending")
            .where("send_at", "<=", now)
            .stream()
        )
    except Exception as exc:
        print(f"[AINotifications] Falha ao consultar fila de notificações agendadas: {exc}")
        return

    for doc_snap in pending:
        data = doc_snap.to_dict() or {}
        title = str(data.get("title") or "Hermes IA").strip()
        message = str(data.get("message") or "").strip()
        category = str(data.get("category") or "geral").strip()
        icon = _CATEGORY_ICONS.get(category, "🤖")

        chat_id = _resolve_default_telegram_chat_id(db)
        if not chat_id:
            print(f"[AINotifications] Nenhum chat_id do Telegram configurado; notificação {doc_snap.id} permanece pendente.")
            continue

        text = f"{icon} Hermes IA — {title}\n\n{message}" if message else f"{icon} Hermes IA — {title}"
        keyboard = [[
            {"text": "👍 Útil", "callback_data": f"ai_notif:{doc_snap.id}:useful"},
            {"text": "👎 Dispensar", "callback_data": f"ai_notif:{doc_snap.id}:dismiss"},
        ]]
        sent = _send_telegram_message_raw_with_keyboard(db, chat_id, text, keyboard)

        if sent:
            doc_snap.reference.update({"status": "sent", "sent_at": now.isoformat(), "telegram_sent": True})
            continue

        send_at_dt = data.get("send_at")
        stale = False
        try:
            if send_at_dt and (now - send_at_dt) > datetime.timedelta(hours=AI_PLANNER_STALE_HOURS):
                stale = True
        except Exception:
            pass

        if stale:
            doc_snap.reference.update({"status": "failed", "telegram_sent": False})
            print(f"[AINotifications] Notificação {doc_snap.id} expirou após falhas repetidas; marcada como 'failed'.")
        else:
            print(f"[AINotifications] Falha ao enviar notificação {doc_snap.id}; nova tentativa no próximo ciclo.")
