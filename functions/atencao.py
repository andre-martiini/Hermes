"""Fila de atenção unificada — agrega pendências determinísticas de ações,
conversas e canais que demandam decisão ou acompanhamento do dono.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
try:
    import zoneinfo
except ImportError:
    from backports import zoneinfo

from firebase_admin import firestore
from firebase_functions import scheduler_fn, options

try:
    from ai_notification_planner import (
        _reserve_and_create_notification,
        AI_PLANNER_WINDOW_START,
        AI_PLANNER_WINDOW_END,
    )
except ImportError:
    _reserve_and_create_notification = None
    AI_PLANNER_WINDOW_START = "07:00"
    AI_PLANNER_WINDOW_END = "22:00"

import subtarefas

_TZ_SP = zoneinfo.ZoneInfo("America/Sao_Paulo")

COLLECTION = "atencao"

# Origens permitidas
ORIGENS = ("acao", "whatsapp", "email", "agenda", "repo", "financeiro", "saude", "secretario_whatsapp")

# Tipos de detectores
TIPO_AGUARDANDO_TERCEIRO_VENCIDO = "aguardando_terceiro_vencido"
TIPO_CONTA_VENCENDO = "conta_vencendo"
TIPO_ROTINA_SAUDE_AUSENTE = "rotina_saude_ausente"
TIPO_SECRETARIO_DECISAO_FORCADA = "secretario_decisao_forcada"
TIPO_SECRETARIO_INSISTENCIA = "secretario_insistencia"
TIPO_SECRETARIO_ASSUNTO_SENSIVEL = "secretario_assunto_sensivel"

# Prioridades
PRIORIDADE_ALTA = "alta"
PRIORIDADE_MEDIA = "media"
PRIORIDADE_BAIXA = "baixa"
_PRIORITY_ORDER = {PRIORIDADE_ALTA: 0, PRIORIDADE_MEDIA: 1, PRIORIDADE_BAIXA: 2}

# Estados
ESTADO_ABERTO = "aberto"
ESTADO_DELEGADO = "delegado_ao_agente"
ESTADO_AGUARDANDO_ANDRE = "aguardando_andre"
ESTADO_RESOLVIDO = "resolvido"
ESTADO_DESCARTADO = "descartado"
ESTADOS_VALIDOS = (
    ESTADO_ABERTO,
    ESTADO_DELEGADO,
    ESTADO_AGUARDANDO_ANDRE,
    ESTADO_RESOLVIDO,
    ESTADO_DESCARTADO,
)
ESTADOS_FECHADOS = (ESTADO_RESOLVIDO, ESTADO_DESCARTADO)

# Aliases reutilizados de inbox_pendentes
_ACTIVE_STATUS_ALIASES = {"em andamento", "andamento", "nao iniciado", "não iniciado", "pendente"}
_STANDBY_STATUS_ALIASES = {"stand-by", "standby", "stand by", "cgby"}


def _acao_e_critica(tarefa: dict, hoje_str: str) -> bool:
    """Verifica se a ação é crítica reutilizando os critérios de morning_summary."""
    degradacao = int(tarefa.get("degradation_count") or 0)
    if degradacao >= 3:
        return True
    if tarefa.get("cobrar"):
        return True
    prazo_final = str(tarefa.get("prazo_final") or "").strip()
    if prazo_final and len(prazo_final) >= 10:
        try:
            dias = (
                datetime.strptime(prazo_final[:10], "%Y-%m-%d").date()
                - datetime.strptime(hoje_str, "%Y-%m-%d").date()
            ).days
            if dias <= 2:
                return True
        except ValueError:
            pass
    return False


def mapear_acoes_ativas_por_chat(db) -> dict[str, dict]:
    """Chat_id -> tarefa (dict completo, com 'id') para toda acao ativa/stand-by que
    tenha `whatsapp_vinculos`. Local unico da varredura para nao repeti-la em cada
    detector reativo de WhatsApp (ver functions/atencao_whatsapp.py). Nao reaproveitado
    por detectar_atencao_acoes nesta PR para nao tocar em codigo ja mergeado/testado -
    fica como limpeza futura."""
    resultado: dict[str, dict] = {}
    for doc in db.collection("tarefas").stream():
        d = doc.to_dict() or {}
        status = str(d.get("status") or "").strip().lower()
        if status not in _ACTIVE_STATUS_ALIASES and status not in _STANDBY_STATUS_ALIASES:
            continue
        d["id"] = doc.id
        for v in (d.get("whatsapp_vinculos") or []):
            if isinstance(v, dict) and str(v.get("chat_id") or "").strip():
                resultado[str(v["chat_id"]).strip()] = d
    return resultado


def avaliar_etapas(
    tarefas: list[dict],
    hoje: date,
    respostas_por_chat: dict[str, list] | None = None,
) -> list[dict]:
    """Avaliação pura e determinística de etapas vencidas aguardando terceiro.

    Separação sem Firestore para testes de unidade rápidos e previsíveis.
    """
    itens: list[dict] = []
    hoje_str = hoje.strftime("%Y-%m-%d")
    respostas_por_chat = respostas_por_chat or {}

    for tarefa in tarefas:
        status = str(tarefa.get("status") or "").strip().lower()
        if status not in _ACTIVE_STATUS_ALIASES and status not in _STANDBY_STATUS_ALIASES:
            continue

        acao_id = str(tarefa.get("id") or "").strip()
        titulo_acao = str(tarefa.get("titulo") or "").strip()
        plano = tarefa.get("plano_acao") or []
        if not isinstance(plano, list):
            continue

        e_critica = _acao_e_critica(tarefa, hoje_str)
        prioridade = PRIORIDADE_ALTA if e_critica else PRIORIDADE_MEDIA

        # Chats do WhatsApp vinculados à ação
        vinculos = tarefa.get("whatsapp_vinculos") or []
        chat_ids = [
            v.get("chat_id")
            for v in vinculos
            if isinstance(v, dict) and v.get("chat_id")
        ]

        for idx, step in enumerate(plano):
            if not isinstance(step, dict):
                continue

            estado_etapa = subtarefas.estado_de(step)
            if estado_etapa != subtarefas.AGUARDANDO_TERCEIRO:
                continue

            data_prevista_str = subtarefas.data_prevista_de(step, tarefa.get("data_limite"), plano)
            if not data_prevista_str:
                continue

            try:
                data_prevista = datetime.strptime(data_prevista_str[:10], "%Y-%m-%d").date()
            except ValueError:
                continue

            if data_prevista >= hoje:
                continue

            # Se existir vínculo tarefas.whatsapp_vinculos e houver mensagem em whatsapp_messages
            # daquele chat com timestamp >= data_prevista e from_me == false, não criar o item
            # (a pessoa respondeu; quem avalia se resolveu é o dono).
            # Registre isso num comentário: é a única inteligência do detector e é o que evita o ruído mais óbvio.
            respondeu = False
            for cid in chat_ids:
                msgs = respostas_por_chat.get(cid, [])
                for msg in msgs:
                    if isinstance(msg, dict):
                        if msg.get("from_me"):
                            continue
                        ts = msg.get("timestamp")
                    else:
                        ts = msg

                    msg_date = None
                    if isinstance(ts, datetime):
                        msg_date = ts.date()
                    elif hasattr(ts, "date"):
                        msg_date = ts.date()
                    elif isinstance(ts, str):
                        try:
                            msg_date = datetime.fromisoformat(ts.replace("Z", "+00:00")).date()
                        except ValueError:
                            pass

                    if msg_date and msg_date >= data_prevista:
                        respondeu = True
                        break
                if respondeu:
                    break

            if respondeu:
                continue

            etapa_id = str(step.get("id") or idx)
            aguardando_de = str(step.get("aguardando_de") or "").strip() or "Terceiro"
            texto_etapa = subtarefas.texto_de(step)
            titulo = f"{aguardando_de} deveria ter respondido sobre: {texto_etapa}"
            sugestao = f"Cobrar {aguardando_de} ou reagendar a etapa"
            resumo = f"Ação '{titulo_acao}': etapa '{texto_etapa}' aguarda retorno de {aguardando_de} desde {data_prevista_str}."
            if len(resumo) > 400:
                resumo = resumo[:397] + "..."

            chave_dedupe = f"aguardando_terceiro_vencido:{acao_id}:{etapa_id}"

            item = {
                "origem": "acao",
                "tipo": TIPO_AGUARDANDO_TERCEIRO_VENCIDO,
                "prioridade": prioridade,
                "titulo": titulo,
                "resumo": resumo,
                "acao_id": acao_id or None,
                "etapa_id": etapa_id or None,
                "pessoa": aguardando_de,
                "prazo": data_prevista_str,
                "evidencia": {
                    "acao_id": acao_id or None,
                    "etapa_id": etapa_id or None,
                    "chat_id": chat_ids[0] if chat_ids else None,
                    "mensagem_ids": [],
                },
                "sugestao": sugestao,
                "estado": ESTADO_ABERTO,
                "chave_dedupe": chave_dedupe,
            }
            itens.append(item)

    return itens


def _persistir_itens_atencao(db, itens: list[dict]) -> int:
    """Persiste lista de itens na coleção atencao de forma idempotente e determinística."""
    gravados = 0
    agora_utc = datetime.now(timezone.utc)
    for item in itens:
        chave = item["chave_dedupe"]
        doc_ref = db.collection(COLLECTION).document(chave)
        existing_snap = doc_ref.get()

        prazo_str = item.get("prazo")
        prazo_dt = None
        if prazo_str and len(str(prazo_str)) >= 10:
            try:
                prazo_dt = datetime.strptime(str(prazo_str)[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except ValueError:
                prazo_dt = None

        payload = {
            "origem": item["origem"],
            "tipo": item["tipo"],
            "prioridade": item["prioridade"],
            "titulo": item["titulo"],
            "resumo": item["resumo"],
            "acao_id": item.get("acao_id"),
            "etapa_id": item.get("etapa_id"),
            "pessoa": item.get("pessoa"),
            "prazo": prazo_dt,
            "prazo_origem": prazo_str,
            "evidencia": item.get("evidencia") or {},
            "sugestao": item.get("sugestao") or "",
            "chave_dedupe": chave,
            "atualizado_em": firestore.SERVER_TIMESTAMP if hasattr(firestore, "SERVER_TIMESTAMP") else agora_utc,
        }

        if existing_snap.exists:
            existing_data = existing_snap.to_dict() or {}
            existing_estado = existing_data.get("estado")
            existing_prazo = existing_data.get("prazo_origem")

            if existing_estado in ESTADOS_FECHADOS:
                if existing_prazo == prazo_str:
                    # Não reabrir se o prazo de origem não mudou
                    continue
                # Se o prazo mudou para outra data também vencida, reabre
                payload["estado"] = ESTADO_ABERTO
                payload["resolvido_em"] = None
                payload["desfecho"] = None
            else:
                payload["estado"] = existing_estado or ESTADO_ABERTO

            doc_ref.set(payload, merge=True)
        else:
            payload["estado"] = ESTADO_ABERTO
            payload["criado_em"] = firestore.SERVER_TIMESTAMP if hasattr(firestore, "SERVER_TIMESTAMP") else agora_utc
            doc_ref.set(payload)
        gravados += 1
    return gravados


def avaliar_contas_vencendo(
    contas: list[dict],
    hoje: date,
    dias_antecedencia: int = 3,
) -> list[dict]:
    """Avaliação pura e determinística de contas a vencer ou vencidas (origem 'financeiro').

    Regra de ouro: silêncio por padrão. Só gera item para contas do mês corrente
    não pagas que estejam vencidas ou vencendo em até `dias_antecedencia` dias.
    """
    itens: list[dict] = []
    hoje_ano = hoje.year
    hoje_mes = hoje.month

    for conta in contas:
        if conta.get("isPaid") or conta.get("paid"):
            continue

        due_day = conta.get("dueDay")
        if due_day is None:
            due_day = conta.get("due_day")
        if due_day is None:
            continue
        try:
            due_day = int(due_day)
        except (ValueError, TypeError):
            continue

        if due_day <= 0:
            continue

        # Ano e mês da conta (padrão: mês/ano de hoje se não especificados)
        # Atenção: no Firestore, 'month' é gravado 0-11 pelo frontend JS
        conta_mes_raw = conta.get("month")
        conta_ano = conta.get("year") or hoje_ano
        if conta_mes_raw is not None:
            try:
                conta_mes = int(conta_mes_raw) + 1  # converte 0-11 para 1-12
            except (ValueError, TypeError):
                conta_mes = hoje_mes
        else:
            conta_mes = hoje_mes

        try:
            vencimento = date(int(conta_ano), int(conta_mes), due_day)
        except ValueError:
            continue

        delta_dias = (vencimento - hoje).days

        # Só gera item se estiver vencida no mês ou vencendo em até dias_antecedencia
        if delta_dias > dias_antecedencia:
            continue

        doc_id = str(conta.get("id") or conta.get("doc_id") or "").strip()
        descricao = str(conta.get("description") or "(sem descrição)").strip()
        valor = conta.get("amount")
        try:
            valor_str = f"R$ {float(valor):.2f}" if valor is not None else "valor não informado"
        except (ValueError, TypeError):
            valor_str = str(valor or "valor não informado")
        vencimento_str = vencimento.strftime("%Y-%m-%d")

        if delta_dias < 0:
            dias_vencida = abs(delta_dias)
            prioridade = PRIORIDADE_ALTA
            titulo = f"Conta '{descricao}' vencida há {dias_vencida} dia(s)"
            resumo = f"Conta fixa '{descricao}' ({valor_str}) venceu em {vencimento_str} e não consta como paga."
        elif delta_dias == 0:
            prioridade = PRIORIDADE_ALTA
            titulo = f"Conta '{descricao}' vence hoje"
            resumo = f"Conta fixa '{descricao}' ({valor_str}) vence hoje ({vencimento_str}) e aguarda pagamento."
        else:
            prioridade = PRIORIDADE_MEDIA
            titulo = f"Conta '{descricao}' vence em {delta_dias} dia(s)"
            resumo = f"Conta fixa '{descricao}' ({valor_str}) vence em {vencimento_str}."

        chave_dedupe = f"conta_vencendo:{doc_id or descricao}:{vencimento_str}"

        itens.append({
            "origem": "financeiro",
            "tipo": TIPO_CONTA_VENCENDO,
            "prioridade": prioridade,
            "titulo": titulo,
            "resumo": resumo,
            "acao_id": None,
            "etapa_id": None,
            "pessoa": None,
            "prazo": vencimento_str,
            "evidencia": {
                "bill_id": doc_id,
                "descricao": descricao,
                "amount": valor,
                "due_date": vencimento_str,
                "delta_dias": delta_dias,
            },
            "sugestao": "Pagar a conta e registrar pagamento no módulo Financeiro",
            "estado": ESTADO_ABERTO,
            "chave_dedupe": chave_dedupe,
        })

    return itens


def detectar_atencao_financeiro(
    db, hoje: date | None = None, settings: dict | None = None
) -> list[dict]:
    """Varre contas fixas do mês e grava pendências financeiras na fila atencao.

    Respeita a flag system/settings.atencao.financeiro.enabled (padrão False, desligado).
    """
    if settings is None:
        try:
            settings_doc = db.collection("system").document("settings").get()
            settings = settings_doc.to_dict() if settings_doc.exists else {}
        except Exception as set_err:
            print(f"[AtencaoFinanceiro] Falha ao consultar settings: {set_err}")
            settings = {}

    enabled = (
        (settings or {})
        .get("atencao", {})
        .get("financeiro", {})
        .get("enabled", False)
    )
    if not enabled:
        print("[AtencaoFinanceiro] Detector financeiro desligado em system/settings; abortando.")
        return []

    sp_tz = zoneinfo.ZoneInfo("America/Sao_Paulo")
    hoje_dt = hoje or datetime.now(sp_tz).date()

    ano = hoje_dt.year
    mes = hoje_dt.month

    contas: list[dict] = []
    try:
        # month no Firestore é 0-based (0=Jan ... 11=Dez)
        docs = (
            db.collection("fixed_bills")
            .where("month", "==", mes - 1)
            .where("year", "==", ano)
            .stream()
        )
        for doc in docs:
            d = doc.to_dict() or {}
            d["id"] = doc.id
            contas.append(d)
    except Exception as exc:
        print(f"[AtencaoFinanceiro] Falha ao consultar fixed_bills: {exc}")
        return []

    itens = avaliar_contas_vencendo(contas, hoje_dt)
    if itens:
        _persistir_itens_atencao(db, itens)
    return itens


def avaliar_rotinas_saude(
    registros_saude: dict,
    hoje: date,
    dias_sem_registro_alerta: int = 3,
) -> list[dict]:
    """Avaliação pura e determinística de rotinas essenciais de saúde (origem 'saude').

    Gera alerta se a rotina de pesagem matinal estiver sem registro há >= dias_sem_registro_alerta.
    """
    itens: list[dict] = []
    ultima_pesagem = registros_saude.get("ultima_pesagem")
    if not ultima_pesagem:
        return itens

    data_pesagem_raw = ultima_pesagem.get("date")
    if not data_pesagem_raw:
        return itens

    try:
        data_pesagem = datetime.strptime(str(data_pesagem_raw)[:10], "%Y-%m-%d").date()
    except ValueError:
        return itens

    dias_sem_pesagem = (hoje - data_pesagem).days
    if dias_sem_pesagem >= dias_sem_registro_alerta:
        data_str = data_pesagem.strftime("%Y-%m-%d")
        peso_val = ultima_pesagem.get("weight")
        peso_str = f" ({peso_val} kg)" if peso_val else ""
        itens.append({
            "origem": "saude",
            "tipo": TIPO_ROTINA_SAUDE_AUSENTE,
            "prioridade": PRIORIDADE_MEDIA,
            "titulo": f"Pesagem não registrada há {dias_sem_pesagem} dias",
            "resumo": f"Último registro de peso foi em {data_pesagem.strftime('%d/%m/%Y')}{peso_str}. Manter pesagem regular apoia o acompanhamento de saúde.",
            "acao_id": None,
            "etapa_id": None,
            "pessoa": None,
            "prazo": hoje.strftime("%Y-%m-%d"),
            "evidencia": {
                "ultima_pesagem_data": data_str,
                "dias_sem_pesagem": dias_sem_pesagem,
                "ultimo_peso": peso_val,
            },
            "sugestao": "Registrar pesagem matinal no módulo Saúde do Hermes",
            "estado": ESTADO_ABERTO,
            "chave_dedupe": f"saude_pesagem_ausente:{data_str}",
        })

    return itens


def detectar_atencao_saude(
    db, hoje: date | None = None, settings: dict | None = None
) -> list[dict]:
    """Varre registros de saúde e grava alertas de rotinas ausentes na fila atencao.

    Respeita a flag system/settings.atencao.saude.enabled (padrão False, desligado).
    """
    if settings is None:
        try:
            settings_doc = db.collection("system").document("settings").get()
            settings = settings_doc.to_dict() if settings_doc.exists else {}
        except Exception as set_err:
            print(f"[AtencaoSaude] Falha ao consultar settings: {set_err}")
            settings = {}

    enabled = (
        (settings or {})
        .get("atencao", {})
        .get("saude", {})
        .get("enabled", False)
    )
    if not enabled:
        print("[AtencaoSaude] Detector saude desligado em system/settings; abortando.")
        return []

    sp_tz = zoneinfo.ZoneInfo("America/Sao_Paulo")
    hoje_dt = hoje or datetime.now(sp_tz).date()
    hoje_str = hoje_dt.strftime("%Y-%m-%d")

    registros_saude: dict = {}
    try:
        limite_busca_str = (hoje_dt - timedelta(days=60)).strftime("%Y-%m-%d")
        docs = (
            db.collection("health_weights")
            .where("date", ">=", limite_busca_str)
            .where("date", "<=", hoje_str)
            .stream()
        )
        medidas = []
        for doc in docs:
            d = doc.to_dict() or {}
            dt = str(d.get("date") or "")[:10]
            val = float(d.get("weight") or 0)
            if val > 0 and dt:
                medidas.append({"date": dt, "weight": val})
        medidas.sort(key=lambda m: m["date"])
        if medidas:
            registros_saude["ultima_pesagem"] = medidas[-1]
    except Exception as exc:
        print(f"[AtencaoSaude] Falha ao consultar health_weights: {exc}")
        return []

    itens = avaliar_rotinas_saude(registros_saude, hoje_dt)
    if itens:
        _persistir_itens_atencao(db, itens)
    return itens


@scheduler_fn.on_schedule(
    schedule="every 30 minutes",
    timezone="America/Sao_Paulo",
    memory=options.MemoryOption.MB_256,
    timeout_sec=120,
)
def detectar_atencao_acoes(event: scheduler_fn.ScheduledEvent = None) -> None:
    """Cloud Function agendada a cada 30 min para detectar pendências determinísticas."""
    from main import get_db

    db = get_db()
    sp_tz = zoneinfo.ZoneInfo("America/Sao_Paulo")
    hoje = datetime.now(sp_tz).date()

    settings_doc = db.collection("system").document("settings").get()
    settings = settings_doc.to_dict() if settings_doc.exists else {}

    # Executa detectores de finanças e saúde em conjunto (respeitando flags de settings)
    try:
        detectar_atencao_financeiro(db, hoje, settings=settings)
        detectar_atencao_saude(db, hoje, settings=settings)
    except Exception as fs_err:
        print(f"[Atencao] Falha ao executar detectores de financeiro/saude: {fs_err}")
    enabled = (
        settings.get("atencao", {})
        .get("aguardando_terceiro", {})
        .get("enabled", False)
    )
    if not enabled:
        print("[Atencao] Detector aguardando_terceiro_vencido desligado em system/settings; abortando.")
        return

    tarefas_docs = list(db.collection("tarefas").stream())
    tarefas_ativas: list[dict] = []
    chats_para_consultar: set[str] = set()

    for doc in tarefas_docs:
        d = doc.to_dict() or {}
        d["id"] = doc.id
        status = str(d.get("status") or "").strip().lower()
        if status in _ACTIVE_STATUS_ALIASES or status in _STANDBY_STATUS_ALIASES:
            tarefas_ativas.append(d)
            for v in (d.get("whatsapp_vinculos") or []):
                if isinstance(v, dict) and v.get("chat_id"):
                    chats_para_consultar.add(v["chat_id"])

    respostas_por_chat: dict[str, list[dict]] = {}
    for cid in chats_para_consultar:
        try:
            msgs = list(
                db.collection("whatsapp_messages")
                .where("chat_id", "==", cid)
                .where("from_me", "==", False)
                .stream()
            )
            respostas_por_chat[cid] = [
                {"timestamp": m.to_dict().get("timestamp"), "from_me": False}
                for m in msgs
            ]
        except Exception as msg_err:
            print(f"[Atencao] Falha ao consultar mensagens de {cid}: {msg_err}")

    itens = avaliar_etapas(tarefas_ativas, hoje, respostas_por_chat)
    _persistir_itens_atencao(db, itens)


def _to_iso(val) -> str | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val.isoformat()
    if hasattr(val, "isoformat"):
        return val.isoformat()
    if hasattr(val, "to_datetime"):
        return val.to_datetime().isoformat()
    return str(val)


def coletar_fila_atencao(
    db,
    estado: str | None = "aberto",
    origem: str | None = None,
    limite: int = 20,
) -> dict:
    """Coleta itens da fila de atenção com ordenação estável por prioridade e prazo."""
    limite_ajustado = max(1, min(int(limite or 20), 100))
    query = db.collection(COLLECTION)

    if estado:
        query = query.where("estado", "==", estado)
    if origem:
        query = query.where("origem", "==", origem)

    docs = list(query.stream())
    itens: list[dict] = []

    for doc in docs:
        d = doc.to_dict() or {}
        item = {
            "id": doc.id,
            "origem": d.get("origem"),
            "tipo": d.get("tipo"),
            "prioridade": d.get("prioridade"),
            "titulo": d.get("titulo"),
            "resumo": d.get("resumo"),
            "acao_id": d.get("acao_id"),
            "etapa_id": d.get("etapa_id"),
            "pessoa": d.get("pessoa"),
            "prazo": _to_iso(d.get("prazo")),
            "evidencia": d.get("evidencia") or {},
            "sugestao": d.get("sugestao"),
            "estado": d.get("estado"),
            "chave_dedupe": d.get("chave_dedupe") or doc.id,
            "criado_em": _to_iso(d.get("criado_em")),
            "atualizado_em": _to_iso(d.get("atualizado_em")),
            "resolvido_em": _to_iso(d.get("resolvido_em")),
            "desfecho": d.get("desfecho"),
        }
        itens.append(item)

    def _sort_key(x: dict) -> tuple:
        prio = _PRIORITY_ORDER.get(x.get("prioridade"), 9)
        prazo = x.get("prazo") or "9999-99-99"
        criado = x.get("criado_em") or ""
        return (prio, prazo, criado)

    itens.sort(key=_sort_key)
    return {
        "total": len(itens),
        "itens": itens[:limite_ajustado],
    }


def resolver_item(
    db,
    item_id: str,
    novo_estado: str,
    desfecho: str | None = None,
    ctx=None,
) -> dict:
    """Resolve, descarta ou delega um item da fila de atenção."""
    item_id = str(item_id or "").strip()
    if not item_id:
        return {"erro": "item_id é obrigatório."}

    doc_ref = db.collection(COLLECTION).document(item_id)
    doc = doc_ref.get()
    if not doc.exists:
        return {"erro": f"Item '{item_id}' não encontrado.", "status": "not_found"}

    if novo_estado not in (ESTADO_DELEGADO, ESTADO_AGUARDANDO_ANDRE, ESTADO_RESOLVIDO, ESTADO_DESCARTADO):
        return {"erro": f"Estado '{novo_estado}' inválido."}

    desfecho_limpo = (desfecho or "").strip()
    if novo_estado in ESTADOS_FECHADOS and not desfecho_limpo:
        return {"erro": "Desfecho é obrigatório para resolver ou descartar um item da fila de atenção."}

    item_data = doc.to_dict() or {}
    update_data: dict = {
        "estado": novo_estado,
        "atualizado_em": firestore.SERVER_TIMESTAMP,
    }
    if desfecho_limpo:
        update_data["desfecho"] = desfecho_limpo
    if novo_estado in ESTADOS_FECHADOS:
        update_data["resolvido_em"] = firestore.SERVER_TIMESTAMP

    doc_ref.update(update_data)

    # Se o item tiver acao_id, registra no diário de bordo da ação
    acao_id = item_data.get("acao_id")
    if acao_id and desfecho_limpo:
        try:
            from tools.hermes_tools import registrar_no_diario, ToolContext
            if ctx is not None:
                registrar_no_diario(
                    ctx,
                    {
                        "task_id_alvo": acao_id,
                        "nota": f"[Fila de Atenção: {item_data.get('titulo') or item_id}] {desfecho_limpo}",
                    },
                )
            else:
                dummy_ctx = ToolContext(db=db, user_uid=None, task_id=acao_id)
                registrar_no_diario(
                    dummy_ctx,
                    {
                        "task_id_alvo": acao_id,
                        "nota": f"[Fila de Atenção: {item_data.get('titulo') or item_id}] {desfecho_limpo}",
                    },
                )
        except Exception as diary_err:
            print(f"[Atencao] Falha ao registrar desfecho no diário da ação {acao_id}: {diary_err}")

    return {
        "status": "ok",
        "item_id": item_id,
        "estado": novo_estado,
        "desfecho": desfecho_limpo or None,
    }


def mapear_origem_categoria_notificacao(origem: str | None) -> str:
    """Mapeia a origem do item de atenção para a categoria de scheduled_notifications.

    'acao' -> 'acoes'
    qualquer outra origem ('whatsapp', 'email', 'financeiro', 'saude', etc.) -> 'geral'.
    """
    origem_limpa = str(origem or "").strip().lower()
    if origem_limpa == "acao":
        return "acoes"
    return "geral"


def dentro_janela_permitida(
    horario_sp: str | datetime,
    window_start: str = AI_PLANNER_WINDOW_START,
    window_end: str = AI_PLANNER_WINDOW_END,
) -> bool:
    """Verifica se o horário HH:MM (America/Sao_Paulo) está dentro da janela permitida de notificação.

    Por padrão, entre AI_PLANNER_WINDOW_START (07:00) e AI_PLANNER_WINDOW_END (22:00), inclusive.
    Fora desse intervalo vigora o período de silêncio.
    """
    if isinstance(horario_sp, datetime):
        if horario_sp.tzinfo is None:
            sp_dt = horario_sp.replace(tzinfo=_TZ_SP)
        else:
            sp_dt = horario_sp.astimezone(_TZ_SP)
        horario_str = sp_dt.strftime("%H:%M")
    elif isinstance(horario_sp, str):
        horario_str = horario_sp.strip()
    else:
        return False

    return window_start <= horario_str <= window_end


esta_na_janela_silencio = dentro_janela_permitida


def avaliar_interrupcao_atencao(db, now: datetime | None = None) -> dict:
    """Varre itens de alta prioridade na fila de atenção e agenda notificações no Telegram.

    Executado a cada 1 minuto (via check_and_send_reminders) de forma determinística,
    sem chamadas a LLM. Reutiliza o orçamento diário compartilhado com o planejador de IA
    (_reserve_and_create_notification) e a janela de silêncio (07:00 a 22:00 SP).
    """
    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=_TZ_SP)

    now_sp = now.astimezone(_TZ_SP)
    today_str = now_sp.strftime("%Y-%m-%d")
    horario_sp_str = now_sp.strftime("%H:%M")

    candidatos = []
    try:
        query = (
            db.collection(COLLECTION)
            .where("estado", "==", ESTADO_ABERTO)
            .where("prioridade", "==", PRIORIDADE_ALTA)
        )
        for doc in query.stream():
            data = doc.to_dict() or {}
            # Ignora se já foi avaliado anteriormente
            if data.get("avaliado_interrupcao_em") is not None:
                continue
            # Defesa adicional em memória
            if data.get("estado") != ESTADO_ABERTO or data.get("prioridade") != PRIORIDADE_ALTA:
                continue
            candidatos.append((doc, data))
    except Exception as exc:
        print(f"[AtencaoInterrupcao] Falha ao consultar candidatos de atencao: {exc}")
        return {"status": "erro", "erro": str(exc), "avaliados": 0, "notificados": 0, "pulados_janela": 0}

    avaliados = 0
    notificados = 0
    pulados_janela = 0

    for doc, item in candidatos:
        try:
            # a. Janela de silêncio: se fora da janela permitida, pula sem marcar
            # avaliado_interrupcao_em para retentar automaticamente no próximo minuto
            if not dentro_janela_permitida(horario_sp_str, AI_PLANNER_WINDOW_START, AI_PLANNER_WINDOW_END):
                pulados_janela += 1
                continue

            # b. Monta título e mensagem a partir dos campos do item (sem LLM)
            titulo = str(item.get("titulo") or "Item de atenção prioritário").strip()[:120]
            resumo = str(item.get("resumo") or "").strip()
            sugestao = str(item.get("sugestao") or "").strip()
            if sugestao:
                mensagem = f"{resumo}\nSugestão: {sugestao}" if resumo else sugestao
            else:
                mensagem = resumo or titulo
            mensagem = mensagem[:600]

            # c. Mapeia categoria de scheduled_notifications
            categoria = mapear_origem_categoria_notificacao(item.get("origem"))

            # d. Reserva vaga no teto diário compartilhado e cria o documento
            notif_ref = db.collection("scheduled_notifications").document()
            payload = {
                "title": titulo,
                "message": mensagem,
                "category": categoria,
                "send_at": now,
                "status": "pending",
                "source": "atencao_interrupcao",
                "motivo": f"Item de atenção ({item.get('origem') or 'geral'}): {titulo}"[:300],
                "created_at": firestore.SERVER_TIMESTAMP,
                "planner_run_date": today_str,
                "feedback": None,
                "atencao_id": getattr(doc, "id", None),
            }

            reservado = False
            if _reserve_and_create_notification is not None:
                reservado = _reserve_and_create_notification(db, today_str, notif_ref, payload)

            if reservado:
                notificados += 1

            # e. Grava avaliado_interrupcao_em (reservou ou não por orçamento esgotado)
            doc_ref = getattr(doc, "reference", None) or db.collection(COLLECTION).document(doc.id)
            doc_ref.update({"avaliado_interrupcao_em": firestore.SERVER_TIMESTAMP})
            avaliados += 1

        except Exception as exc:
            print(f"[AtencaoInterrupcao] Erro ao processar item {getattr(doc, 'id', 'desconhecido')}: {exc}")

    return {
        "status": "ok",
        "candidatos": len(candidatos),
        "avaliados": avaliados,
        "notificados": notificados,
        "pulados_janela": pulados_janela,
    }

