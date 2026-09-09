"""Rascunhos de mensagens de WhatsApp com aprovação em um toque pelo Telegram.

Separação entre redação (feita pelo agente) e aprovação (feita pelo dono no Telegram).
Rascunhos são persistidos na coleção `whatsapp_outbox` com status `aguardando_aprovacao`.
Aprovar troca atomicamente para `pending`, permitindo ao worker enviar.
"""

from __future__ import annotations

import datetime
from datetime import timezone
import html
import os
import zoneinfo

from firebase_admin import firestore

COLLECTION = "whatsapp_outbox"

STATUS_AGUARDANDO = "aguardando_aprovacao"
STATUS_AGUARDANDO_JANELA = "aguardando_janela"
STATUS_PENDING = "pending"
STATUS_DESCARTADO = "descartado"
STATUS_EXPIRADO = "expirado"
STATUS_SENT = "sent"
STATUS_FAILED = "failed"


# ---------------------------------------------------------------------------
# Lógica pura (separada de Firestore / rede para testes unitários)
# ---------------------------------------------------------------------------

def validar_transicao_aprovacao(status_atual: str | None) -> tuple[bool, str]:
    """Valida se o rascunho pode transicionar para pending."""
    if status_atual in (STATUS_AGUARDANDO, STATUS_AGUARDANDO_JANELA):
        return True, ""
    if status_atual is None:
        return False, "Rascunho não encontrado."
    return False, f"já decidido (status atual: {status_atual})"


def validar_transicao_descarte(status_atual: str | None) -> tuple[bool, str]:
    """Valida se o rascunho pode ser descartado."""
    if status_atual in (STATUS_AGUARDANDO, STATUS_AGUARDANDO_JANELA):
        return True, ""
    if status_atual is None:
        return False, "Rascunho não encontrado."
    return False, f"já decidido (status atual: {status_atual})"


def montar_card_telegram(
    destinatario_nome: str,
    motivo: str,
    content: str,
    outbox_id: str,
) -> tuple[str, list[list[dict]]]:
    """Monta o texto e os botões inline para o card de aprovação no Telegram."""
    nome_limpo = str(destinatario_nome or "").strip() or "Destinatário"
    motivo_limpo = str(motivo or "").strip()
    texto_msg = str(content or "").strip()

    corpo = (
        f"✉️ <b>Rascunho para {html.escape(nome_limpo)}</b>\n"
        f"{html.escape(motivo_limpo)}\n\n"
        f'"{html.escape(texto_msg)}"'
    )
    botoes = [
        [
            {"text": "✅ Enviar", "callback_data": f"outbox:{outbox_id}:ok"},
            {"text": "✏️ Editar", "callback_data": f"outbox:{outbox_id}:edit"},
            {"text": "🗑️ Descartar", "callback_data": f"outbox:{outbox_id}:no"},
        ]
    ]
    return corpo, botoes


def montar_card_telegram_promovido(
    destinatario_nome: str,
    motivo: str,
    content: str,
    outbox_id: str,
    minutos_janela: int = 10,
) -> tuple[str, list[list[dict]]]:
    """Monta o card no Telegram para rascunho de tipo promovido com botão de cancelamento."""
    nome_limpo = str(destinatario_nome or "").strip() or "Destinatário"
    motivo_limpo = str(motivo or "").strip()
    texto_msg = str(content or "").strip()

    corpo = (
        f"🤖 <b>Envio autônomo para {html.escape(nome_limpo)}</b>\n"
        f"{html.escape(motivo_limpo)}\n\n"
        f'"{html.escape(texto_msg)}"\n\n'
        f"⏱️ <i>Vai para a fila automaticamente em até {minutos_janela} min — toque abaixo para cancelar.</i>"
    )
    botoes = [
        [
            {"text": "🛑 Cancelar", "callback_data": f"outbox:{outbox_id}:no"},
        ]
    ]
    return corpo, botoes


def avaliar_expirados(
    rascunhos: list[dict],
    agora: datetime.datetime,
    limite_horas: int = 48,
) -> list[str]:
    """Filtra puramente quais rascunhos em aguardando_aprovacao já expiraram."""
    expirados: list[str] = []
    limite_delta = datetime.timedelta(hours=limite_horas)

    for r in rascunhos:
        if r.get("status") != STATUS_AGUARDANDO:
            continue
        criado = r.get("created_at")
        if isinstance(criado, str):
            try:
                criado = datetime.datetime.fromisoformat(criado.replace("Z", "+00:00"))
            except ValueError:
                continue
        elif hasattr(criado, "to_datetime"):
            criado = criado.to_datetime()

        if not isinstance(criado, datetime.datetime):
            continue

        if criado.tzinfo is None:
            criado = criado.replace(tzinfo=timezone.utc)
        agora_utc = agora if agora.tzinfo else agora.replace(tzinfo=timezone.utc)

        if (agora_utc - criado) >= limite_delta:
            doc_id = str(r.get("id") or r.get("outbox_id") or "").strip()
            if doc_id:
                expirados.append(doc_id)

    return expirados


def avaliar_liberacao_promovidos(
    rascunhos: list[dict],
    agora: datetime.datetime,
) -> list[str]:
    """Filtra puramente quais rascunhos em aguardando_janela já venceram a janela de cancelamento.

    Garante o veto humano: só libera se o card Telegram com o botão de cancelamento foi
    comprovadamente emitido (telegram_message_id presente).
    """
    prontos: list[str] = []
    agora_utc = agora if agora.tzinfo else agora.replace(tzinfo=timezone.utc)

    for r in rascunhos:
        if r.get("status") != STATUS_AGUARDANDO_JANELA:
            continue
        # Veto humano inegociável: só libera se o card com botão de cancelamento foi entregue
        if not r.get("telegram_message_id"):
            continue
        liberado_em = r.get("envio_liberado_em")
        if isinstance(liberado_em, str):
            try:
                liberado_em = datetime.datetime.fromisoformat(liberado_em.replace("Z", "+00:00"))
            except ValueError:
                continue
        elif hasattr(liberado_em, "to_datetime"):
            liberado_em = liberado_em.to_datetime()

        if not isinstance(liberado_em, datetime.datetime):
            continue

        if liberado_em.tzinfo is None:
            liberado_em = liberado_em.replace(tzinfo=timezone.utc)

        if agora_utc >= liberado_em:
            doc_id = str(r.get("id") or r.get("outbox_id") or "").strip()
            if doc_id:
                prontos.append(doc_id)

    return prontos


# ---------------------------------------------------------------------------
# Operações de Banco e Integrações
# ---------------------------------------------------------------------------

def _to_iso(val) -> str | None:
    if val is None:
        return None
    if isinstance(val, (datetime.datetime, datetime.date)):
        return val.isoformat()
    if hasattr(val, "isoformat"):
        return val.isoformat()
    if hasattr(val, "to_datetime"):
        return val.to_datetime().isoformat()
    return str(val)


def _obter_janela_cancelamento_min(db) -> int:
    """Obtém a janela de cancelamento em minutos: Firestore -> ENV -> padrão 10."""
    try:
        snap = db.collection("system").document("mcp_access").get()
        if snap.exists:
            val = (snap.to_dict() or {}).get("janela_cancelamento_min")
            if val is not None:
                return max(1, int(val))
    except Exception:
        pass
    env_val = os.environ.get("PROMOCAO_JANELA_MIN")
    if env_val:
        try:
            return max(1, int(env_val))
        except ValueError:
            pass
    return 10


def _tipos_promovidos(db) -> set[str]:
    """Lê diretamente os tipos promovidos cadastrados em system/mcp_access."""
    promovidos: set[str] = set()
    try:
        snap = db.collection("system").document("mcp_access").get()
        if snap.exists:
            lista = (snap.to_dict() or {}).get("tipos_promovidos") or []
            promovidos = {str(t).strip().lower() for t in lista if str(t).strip()}
    except Exception as err:
        print(f"[OutboxAprovacao] Falha ao ler tipos_promovidos de system/mcp_access: {err}")
    return promovidos


def criar_rascunho(
    db,
    contact_number: str,
    message: str,
    motivo: str,
    acao_id: str | None = None,
    item_atencao_id: str | None = None,
    origem: str = "claude",
    ctx=None,
    telegram_token: str | None = None,
    chat_id: str | int | None = None,
    tipo: str = "outro",
    envio_imediato: bool = False,
) -> dict:
    """Cria um rascunho de WhatsApp e envia o card de aprovação ao Telegram."""
    contact_number = str(contact_number or "").strip()
    message = str(message or "").strip()
    motivo = str(motivo or "").strip()
    acao_id = str(acao_id).strip() if acao_id else None
    item_atencao_id = str(item_atencao_id).strip() if item_atencao_id else None
    tipo_limpo = str(tipo or "outro").strip() or "outro"

    if not contact_number:
        return {"erro": "contact_number é obrigatório."}
    if not message:
        return {"erro": "message é obrigatório."}
    if not motivo:
        return {"erro": "motivo é obrigatório."}

    # Resolução de destinatário reutilizando a mesma lógica do preview
    try:
        from tools.hermes_tools import _destinatario_whatsapp_previa
        if ctx is not None:
            res_dest = _destinatario_whatsapp_previa(ctx, contact_number)
        else:
            from tools.hermes_tools import ToolContext
            dummy_ctx = ToolContext(_db=db)
            res_dest = _destinatario_whatsapp_previa(dummy_ctx, contact_number)
    except Exception as dest_err:
        print(f"[OutboxAprovacao] Falha ao resolver destinatário: {dest_err}")
        res_dest = {"encontrado": False, "informado": contact_number, "sugestoes": []}

    if not res_dest.get("encontrado"):
        ambiguo = res_dest.get("ambiguo")
        sugestoes = res_dest.get("sugestoes") or []
        motivo_falha = (
            "Destinatário ambíguo (múltiplas correspondências encontradas)."
            if ambiguo
            else "Destinatário não encontrado na base de contatos/conversas do Hermes."
        )
        return {
            "erro": motivo_falha,
            "status": "destinatario_invalido",
            "informado": contact_number,
            "sugestoes": sugestoes,
        }

    destinatario_nome = res_dest.get("nome") or contact_number
    destino_real = res_dest.get("chat_id") or contact_number

    # Verifica se o tipo de rascunho tem envio imediato ou está promovido para autonomia com janela
    scheduled_for = None
    if envio_imediato:
        is_promovido = False
        janela_min = 0
        envio_liberado_em = None
        status_inicial = STATUS_PENDING
        # Envio imediato é "agendado para agora", não "sem agendamento": o worker
        # seleciona jobs pendentes com scheduled_for <= agora(), e essa comparação
        # no Firestore exclui documentos com o campo null/ausente.
        scheduled_for = datetime.datetime.now(timezone.utc)
    else:
        promovidos = _tipos_promovidos(db)
        is_promovido = tipo_limpo.lower() in promovidos
        janela_min = _obter_janela_cancelamento_min(db) if is_promovido else 0
        agora_utc = datetime.datetime.now(timezone.utc)
        envio_liberado_em = (agora_utc + datetime.timedelta(minutes=janela_min)) if is_promovido else None
        status_inicial = STATUS_AGUARDANDO_JANELA if is_promovido else STATUS_AGUARDANDO

    doc_ref = db.collection(COLLECTION).document()
    outbox_id = doc_ref.id

    payload = {
        "to_number": destino_real,
        "content": message,
        "status": status_inicial,
        "motivo": motivo,
        "acao_id": acao_id,
        "item_atencao_id": item_atencao_id,
        "origem": origem or "claude",
        "destinatario_nome": destinatario_nome,
        "tipo": tipo_limpo,
        "foi_editado": False,
        "created_at": firestore.SERVER_TIMESTAMP,
    }
    if is_promovido:
        payload["envio_liberado_em"] = envio_liberado_em
    if scheduled_for is not None:
        payload["scheduled_for"] = scheduled_for

    doc_ref.set(payload)

    # Dispara o card no Telegram (ou notificação informativa para envio imediato)
    telegram_msg_id = None
    try:
        from hermes_core_logic import (
            _get_telegram_token,
            _send_telegram_message,
            _send_telegram_message_with_keyboard,
        )
        from main import _resolve_default_telegram_chat_id

        token = telegram_token or _get_telegram_token(db)
        target_chat = chat_id or _resolve_default_telegram_chat_id(db)
        if token and target_chat:
            if envio_imediato:
                # Notificação puramente informativa (sem botões) para visibilidade do que foi respondido
                texto_info = (
                    f"🤖 <b>Hermes Bot respondeu a {html.escape(destinatario_nome)}:</b>\n\n"
                    f"{html.escape(message)}"
                )
                telegram_msg_id = _send_telegram_message(token, target_chat, texto_info)
            elif is_promovido:
                card_text, card_keyboard = montar_card_telegram_promovido(
                    destinatario_nome=destinatario_nome,
                    motivo=motivo,
                    content=message,
                    outbox_id=outbox_id,
                    minutos_janela=janela_min,
                )
                telegram_msg_id = _send_telegram_message_with_keyboard(
                    token, target_chat, card_text, card_keyboard
                )
            else:
                card_text, card_keyboard = montar_card_telegram(
                    destinatario_nome=destinatario_nome,
                    motivo=motivo,
                    content=message,
                    outbox_id=outbox_id,
                )
                telegram_msg_id = _send_telegram_message_with_keyboard(
                    token, target_chat, card_text, card_keyboard
                )
            if telegram_msg_id:
                doc_ref.update({"telegram_message_id": telegram_msg_id})
    except Exception as tg_err:
        print(f"[OutboxAprovacao] Falha ao enviar card Telegram para {outbox_id}: {tg_err}")

    if envio_imediato:
        return {
            "status": STATUS_PENDING,
            "outbox_id": outbox_id,
            "destinatario_nome": destinatario_nome,
            "telegram_notificado": bool(telegram_msg_id),
            "instrucao": (
                "Rascunho criado com envio imediato e status pending para entrega pelo worker WhatsApp."
            ),
        }

    if is_promovido and not telegram_msg_id:
        # Se a emissão do card Telegram falhou, degrada para aprovação regular
        # para impedir envio autônomo sem supervisão humana efetiva
        doc_ref.update({
            "status": STATUS_AGUARDANDO,
            "envio_liberado_em": None,
            "degradado_motivo": "falha_entrega_card_telegram",
        })
        return {
            "status": STATUS_AGUARDANDO,
            "outbox_id": outbox_id,
            "destinatario_nome": destinatario_nome,
            "telegram_notificado": False,
            "instrucao": (
                "Tipo promovido, mas o card do Telegram falhou no envio. Degradado para aprovação manual "
                "por segurança para impedir envio sem confirmação do dono."
            ),
        }

    if is_promovido:
        return {
            "status": STATUS_AGUARDANDO_JANELA,
            "outbox_id": outbox_id,
            "destinatario_nome": destinatario_nome,
            "telegram_notificado": bool(telegram_msg_id),
            "envio_liberado_em": _to_iso(envio_liberado_em),
            "instrucao": (
                f"Tipo promovido — vai para a fila automaticamente em até {janela_min} min "
                "salvo cancelamento do dono. Não afirme que foi enviado; consulte "
                "consultar_envio_whatsapp com este id para saber o estado real."
            ),
        }

    return {
        "status": STATUS_AGUARDANDO,
        "outbox_id": outbox_id,
        "destinatario_nome": destinatario_nome,
        "telegram_notificado": bool(telegram_msg_id),
        "instrucao": (
            "O rascunho foi para aprovação do dono no Telegram. Não afirme que a "
            "mensagem foi enviada; use consultar_envio_whatsapp com este id para "
            "saber o estado real."
        ),
    }


def aprovar_rascunho(
    db,
    outbox_id: str,
    telegram_token: str | None = None,
    chat_id: str | int | None = None,
    ctx=None,
    aprovado_via: str = "telegram",
) -> dict:
    """Transição atômica de aguardando_aprovacao para pending.

    Resolve item_atencao_id e anota no diário da acao_id quando presentes.
    """
    outbox_id = str(outbox_id or "").strip()
    if not outbox_id:
        return {"erro": "outbox_id é obrigatório."}

    doc_ref = db.collection(COLLECTION).document(outbox_id)

    # Transação atômica
    agora_utc = datetime.datetime.now(timezone.utc)

    # Sem suporte a transação real, não há como garantir exclusão mútua com
    # liberar_rascunhos_promovidos (achado A04) — recusa em vez de arriscar
    # uma escrita não protegida.
    if not hasattr(db, "transaction"):
        return {
            "status": "erro_configuracao",
            "erro": "Backend Firestore sem suporte a transação; aprovação recusada para evitar condição de corrida.",
        }

    # Achado P1 da revisão Codex na PR #219 (revogar_promocao_autonomia):
    # `liberar_rascunhos_promovidos` checa o mandato via
    # `mandatos_io.mandato_tipo_promovido` ANTES de chamar esta função --
    # mas aquela leitura não é atômica com a aprovação em si, e o resultado
    # fica em cache por `tipo` para o laço inteiro (vários rascunhos do
    # mesmo tipo reaproveitam uma única leitura). Se `revogar_promocao_
    # autonomia` commitar entre a checagem e esta transação (ou entre a
    # aprovação de um rascunho e a do próximo, do mesmo tipo, no mesmo
    # laço), o rascunho ainda seria enviado sozinho mesmo já revogado --
    # exatamente o "sucesso" que o André veria ao revogar, seguido do envio
    # de qualquer forma. Por isso a liberação automática (só ela; aprovação
    # manual via Telegram/WhatsApp/Cowork é a própria decisão humana e não
    # depende de `tipos_promovidos`) rechecka `system/mcp_access` DENTRO
    # desta mesma transação que muda o status -- é isto que faz o Firestore
    # aplicar controle de concorrência otimista de verdade entre as duas
    # funções: como ambas leem/escrevem o mesmo documento
    # (`system/mcp_access`) dentro de suas respectivas transações, uma das
    # duas é forçada a abortar/repetir se rodarem de fato em paralelo --
    # nunca as duas commitam com visões inconsistentes. A checagem de fora
    # continua útil (evita o custo de abrir a transação para um rascunho já
    # sabidamente sem mandato), mas só esta aqui é a garantia real.
    mcp_ref = db.collection("system").document("mcp_access") if aprovado_via == "janela_automatica" else None

    try:
        transaction = db.transaction()

        @firestore.transactional
        def _exec_approve(tx):
            snap = doc_ref.get(transaction=tx)
            if not snap.exists:
                return {"status": "not_found", "erro": f"Rascunho '{outbox_id}' não encontrado."}
            data = snap.to_dict() or {}
            valido, motivo = validar_transicao_aprovacao(data.get("status"))
            if not valido:
                return {
                    "status": "already_decided",
                    "erro": f"Rascunho {motivo}",
                    "dados": data,
                }

            if mcp_ref is not None:
                tipo_rascunho = str(data.get("tipo") or "").strip().lower()
                mcp_snap = mcp_ref.get(transaction=tx)
                tipos_promovidos_agora = set()
                if mcp_snap.exists:
                    lista = (mcp_snap.to_dict() or {}).get("tipos_promovidos") or []
                    tipos_promovidos_agora = {str(t).strip().lower() for t in lista if str(t).strip()}
                if tipo_rascunho not in tipos_promovidos_agora:
                    return {
                        "status": "mandato_revogado",
                        "erro": f"Tipo '{tipo_rascunho}' não está mais promovido; aprovação automática recusada.",
                        "dados": data,
                    }

            tx.update(
                doc_ref,
                {
                    "status": STATUS_PENDING,
                    "aprovado_em": firestore.SERVER_TIMESTAMP,
                    "aprovado_via": aprovado_via,
                    "scheduled_for": agora_utc,
                },
            )
            return {"status": "ok", "dados": data}

        transaction_result = _exec_approve(transaction)
    except Exception as tx_err:
        # Falha real de transação (ex.: Aborted após esgotar tentativas). Não há
        # fallback para escrita desprotegida — retorna erro explícito em vez de
        # arriscar uma condição de corrida com liberar_rascunhos_promovidos.
        print(f"[OutboxAprovacao] Transação Firestore de aprovação falhou: {tx_err}")
        return {
            "status": "erro_transacao",
            "erro": f"Não foi possível aprovar de forma atômica: {tx_err}",
        }

    if transaction_result.get("status") != "ok":
        return transaction_result

    data = transaction_result.get("dados") or {}
    item_atencao_id = data.get("item_atencao_id")
    acao_id = data.get("acao_id")
    dest_nome = data.get("destinatario_nome") or data.get("to_number") or ""
    motivo_rascunho = data.get("motivo") or "envio aprovado"

    # Se houver item_atencao_id, marca o item como resolvido
    if item_atencao_id:
        try:
            from atencao import resolver_item
            resolver_item(
                db,
                item_id=item_atencao_id,
                novo_estado="resolvido",
                desfecho="mensagem aprovada e enviada para a fila",
                ctx=ctx,
            )
        except Exception as at_err:
            print(f"[OutboxAprovacao] Falha ao resolver item_atencao {item_atencao_id}: {at_err}")

    # Se houver acao_id (e não já resolvido pelo resolver_item da mesma acao)
    if acao_id and not item_atencao_id:
        try:
            from tools.hermes_tools import registrar_no_diario, ToolContext
            nota_diario = f"[WhatsApp: {dest_nome}] Rascunho aprovado e enviado para a fila: {motivo_rascunho}"
            if ctx is not None:
                registrar_no_diario(ctx, {"task_id_alvo": acao_id, "nota": nota_diario})
            else:
                dummy_ctx = ToolContext(_db=db)
                registrar_no_diario(dummy_ctx, {"task_id_alvo": acao_id, "nota": nota_diario})
        except Exception as diary_err:
            print(f"[OutboxAprovacao] Falha ao registrar diário na ação {acao_id}: {diary_err}")

    # Edita mensagem no Telegram para "✅ Enviado para a fila às HH:MM"
    telegram_msg_id = data.get("telegram_message_id")
    if telegram_msg_id:
        try:
            from core.telegram_api import edit_message
            from hermes_core_logic import _get_telegram_token
            from main import _resolve_default_telegram_chat_id

            token = telegram_token or _get_telegram_token(db)
            target_chat = chat_id or _resolve_default_telegram_chat_id(db)
            if token and target_chat:
                sp_tz = zoneinfo.ZoneInfo("America/Sao_Paulo")
                hora_formatada = datetime.datetime.now(sp_tz).strftime("%H:%M")
                if aprovado_via == "whatsapp":
                    sufixo_canal = " (via WhatsApp)"
                elif aprovado_via == "janela_automatica":
                    sufixo_canal = " (liberação automática)"
                elif aprovado_via == "cowork":
                    sufixo_canal = " (via Cowork)"
                else:
                    sufixo_canal = ""
                novo_texto = (
                    f"✅ <b>Enviado para a fila às {hora_formatada}{sufixo_canal}</b>\n"
                    f"Destino: {html.escape(str(dest_nome))}\n"
                    f"Motivo: {html.escape(str(motivo_rascunho))}"
                )
                edit_message(token, target_chat, int(telegram_msg_id), novo_texto)
        except Exception as edit_err:
            print(f"[OutboxAprovacao] Falha ao editar mensagem Telegram {telegram_msg_id}: {edit_err}")

    return {
        "status": "ok",
        "outbox_id": outbox_id,
        "mensagem": "Rascunho aprovado e enviado para a fila.",
    }


def descartar_rascunho(
    db,
    outbox_id: str,
    telegram_token: str | None = None,
    chat_id: str | int | None = None,
    telegram_msg_id: int | None = None,
    motivo: str | None = None,
) -> dict:
    """Descarta um rascunho de WhatsApp e reabre o item da fila de atenção se houver.

    Executa via transação atômica Firestore para garantir exclusão mútua com a
    aprovação automática (liberar_rascunhos_promovidos), evitando condições de corrida.
    """
    outbox_id = str(outbox_id or "").strip()
    if not outbox_id:
        return {"erro": "outbox_id é obrigatório."}

    doc_ref = db.collection(COLLECTION).document(outbox_id)
    agora_utc = datetime.datetime.now(timezone.utc)

    # Sem suporte a transação real, não há como garantir exclusão mútua com
    # liberar_rascunhos_promovidos (achado A04) — recusa em vez de arriscar
    # uma escrita não protegida.
    if not hasattr(db, "transaction"):
        return {
            "status": "erro_configuracao",
            "erro": "Backend Firestore sem suporte a transação; descarte recusado para evitar condição de corrida.",
        }

    try:
        transaction = db.transaction()

        @firestore.transactional
        def _exec_discard(tx):
            snap = doc_ref.get(transaction=tx)
            if not snap.exists:
                return {"status": "not_found", "erro": f"Rascunho '{outbox_id}' não encontrado."}
            data = snap.to_dict() or {}
            valido, mot = validar_transicao_descarte(data.get("status"))
            if not valido:
                return {
                    "status": "already_decided",
                    "erro": f"Rascunho {mot}",
                    "dados": data,
                }

            update_fields = {
                "status": STATUS_DESCARTADO,
                "descartado_em": firestore.SERVER_TIMESTAMP if hasattr(firestore, "SERVER_TIMESTAMP") else agora_utc,
            }
            if motivo:
                update_fields["descartado_motivo"] = str(motivo).strip()

            tx.update(doc_ref, update_fields)
            return {"status": "ok", "dados": data}

        transaction_result = _exec_discard(transaction)
    except Exception as tx_err:
        # Falha real de transação. Sem fallback para escrita desprotegida —
        # retorna erro explícito em vez de arriscar uma condição de corrida.
        print(f"[OutboxAprovacao] Transação Firestore de descarte falhou: {tx_err}")
        return {
            "status": "erro_transacao",
            "erro": f"Não foi possível descartar de forma atômica: {tx_err}",
        }

    if transaction_result.get("status") != "ok":
        return transaction_result

    data = transaction_result.get("dados") or {}

    # Item da fila de atenção volta para aberto (o dono descartou o texto, não o assunto)
    item_atencao_id = data.get("item_atencao_id")
    if item_atencao_id:
        try:
            db.collection("atencao").document(item_atencao_id).update({
                "estado": "aberto",
                "resolvido_em": None,
                "desfecho": None,
                "atualizado_em": firestore.SERVER_TIMESTAMP if hasattr(firestore, "SERVER_TIMESTAMP") else agora_utc,
            })
        except Exception as at_err:
            print(f"[OutboxAprovacao] Falha ao reabrir item de atenção {item_atencao_id}: {at_err}")

    # Edita mensagem no Telegram para "🗑️ Descartado"
    tg_id = telegram_msg_id or data.get("telegram_message_id")
    if tg_id:
        try:
            from core.telegram_api import edit_message
            from hermes_core_logic import _get_telegram_token
            from main import _resolve_default_telegram_chat_id

            token = telegram_token or _get_telegram_token(db)
            target_chat = chat_id or _resolve_default_telegram_chat_id(db)
            if token and target_chat:
                dest_nome = data.get("destinatario_nome") or data.get("to_number") or ""
                novo_texto = (
                    f"🗑️ <b>Rascunho descartado</b>\n"
                    f"Destino: {html.escape(str(dest_nome))}"
                )
                if motivo:
                    novo_texto += f"\nMotivo: {html.escape(str(motivo))}"
                edit_message(token, target_chat, int(tg_id), novo_texto)
        except Exception as edit_err:
            print(f"[OutboxAprovacao] Falha ao editar mensagem Telegram {tg_id}: {edit_err}")

    return {
        "status": "ok",
        "outbox_id": outbox_id,
        "mensagem": "Rascunho descartado com sucesso.",
    }


def aplicar_edicao_rascunho(
    db,
    outbox_id: str,
    novo_texto: str,
    telegram_token: str | None = None,
    chat_id: str | int | None = None,
) -> dict:
    """Aplica o texto editado pelo dono diretamente ao rascunho e reenvia o card.

    Transação atômica Firestore (achado A04 -- mesmo padrão de aprovar_rascunho/
    descartar_rascunho, pendência registrada desde a sub-entrega 1/N de P01):
    antes desta correção, esta função fazia um get()+update() incondicional, sem
    reler nem revalidar o status dentro de uma transação. Dois problemas reais,
    não só teóricos: (1) corrida com liberar_rascunhos_promovidos/
    descartar_rascunho -- uma edição chegando no mesmo instante em que o
    rascunho é liberado/descartado por outro caminho podia perder ou sobrescrever
    a decisão concorrente; (2) mais grave, a ausência de QUALQUER checagem de
    status fazia o update() reescrever `status` para aguardando_aprovacao
    incondicionalmente -- uma edição tardia (sessão do Telegram/WhatsApp
    obsoleta, retry, etc.) sobre um rascunho que já tinha sido enviado
    (sent), aprovado (pending) ou descartado o ressuscitaria silenciosamente
    de volta para aguardando_aprovacao, reabrindo uma decisão já tomada.
    """
    outbox_id = str(outbox_id or "").strip()
    novo_texto = str(novo_texto or "").strip()
    if not outbox_id:
        return {"erro": "outbox_id é obrigatório."}
    if not novo_texto:
        return {"erro": "novo_texto é obrigatório."}

    doc_ref = db.collection(COLLECTION).document(outbox_id)
    agora_utc = datetime.datetime.now(timezone.utc)

    # Sem suporte a transação real, não há como garantir exclusão mútua com
    # liberar_rascunhos_promovidos/descartar_rascunho (achado A04) — recusa em
    # vez de arriscar uma escrita não protegida.
    if not hasattr(db, "transaction"):
        return {
            "status": "erro_configuracao",
            "erro": "Backend Firestore sem suporte a transação; edição recusada para evitar condição de corrida.",
        }

    try:
        transaction = db.transaction()

        @firestore.transactional
        def _exec_edit(tx):
            snap = doc_ref.get(transaction=tx)
            if not snap.exists:
                return {"status": "not_found", "erro": f"Rascunho '{outbox_id}' não encontrado."}
            data = snap.to_dict() or {}
            # Mesmo domínio de validar_transicao_aprovacao/validar_transicao_
            # descarte (idênticas entre si): só é possível editar um rascunho
            # ainda não decidido (aguardando_aprovacao ou aguardando_janela) --
            # reutilizada em vez de duplicada.
            valido, motivo = validar_transicao_aprovacao(data.get("status"))
            if not valido:
                return {
                    "status": "already_decided",
                    "erro": f"Rascunho {motivo}",
                    "dados": data,
                }

            tx.update(
                doc_ref,
                {
                    "content": novo_texto,
                    "status": STATUS_AGUARDANDO,
                    "foi_editado": True,
                    "atualizado_em": firestore.SERVER_TIMESTAMP if hasattr(firestore, "SERVER_TIMESTAMP") else agora_utc,
                },
            )
            return {"status": "ok", "dados": data}

        transaction_result = _exec_edit(transaction)
    except Exception as tx_err:
        # Falha real de transação. Sem fallback para escrita desprotegida —
        # retorna erro explícito em vez de arriscar uma condição de corrida.
        print(f"[OutboxAprovacao] Transação Firestore de edição falhou: {tx_err}")
        return {
            "status": "erro_transacao",
            "erro": f"Não foi possível editar de forma atômica: {tx_err}",
        }

    if transaction_result.get("status") != "ok":
        return transaction_result

    data = transaction_result.get("dados") or {}
    destinatario_nome = data.get("destinatario_nome") or data.get("to_number") or "Destinatário"
    motivo = data.get("motivo") or "Rascunho editado"

    # Reenvia card de aprovação no Telegram
    new_telegram_msg_id = None
    try:
        from hermes_core_logic import _get_telegram_token, _send_telegram_message_with_keyboard
        from main import _resolve_default_telegram_chat_id

        token = telegram_token or _get_telegram_token(db)
        target_chat = chat_id or _resolve_default_telegram_chat_id(db)
        if token and target_chat:
            card_text, card_keyboard = montar_card_telegram(
                destinatario_nome=destinatario_nome,
                motivo=f"{motivo} (editado)",
                content=novo_texto,
                outbox_id=outbox_id,
            )
            new_telegram_msg_id = _send_telegram_message_with_keyboard(
                token, target_chat, card_text, card_keyboard
            )
            if new_telegram_msg_id:
                doc_ref.update({"telegram_message_id": new_telegram_msg_id})
    except Exception as tg_err:
        print(f"[OutboxAprovacao] Falha ao reenviar card Telegram após edição: {tg_err}")

    return {
        "status": "ok",
        "outbox_id": outbox_id,
        "novo_conteudo": novo_texto,
        "telegram_message_id": new_telegram_msg_id,
    }


def expirar_rascunhos_pendentes(
    db,
    agora: datetime.datetime | None = None,
    limite_horas: int = 48,
    telegram_token: str | None = None,
    chat_id: str | int | None = None,
) -> int:
    """Varre e expira rascunhos em aguardando_aprovacao com mais de 48h."""
    agora_utc = agora or datetime.datetime.now(timezone.utc)
    if agora_utc.tzinfo is None:
        agora_utc = agora_utc.replace(tzinfo=timezone.utc)

    query = db.collection(COLLECTION).where("status", "==", STATUS_AGUARDANDO)
    docs = list(query.stream())

    expirados_count = 0
    limite_delta = datetime.timedelta(hours=limite_horas)

    for doc in docs:
        d = doc.to_dict() or {}
        criado = d.get("created_at")
        if isinstance(criado, str):
            try:
                criado = datetime.datetime.fromisoformat(criado.replace("Z", "+00:00"))
            except ValueError:
                continue
        elif hasattr(criado, "to_datetime"):
            criado = criado.to_datetime()

        if not isinstance(criado, datetime.datetime):
            continue

        if criado.tzinfo is None:
            criado = criado.replace(tzinfo=timezone.utc)

        if (agora_utc - criado) >= limite_delta:
            doc.reference.update({
                "status": STATUS_EXPIRADO,
                "expirado_em": firestore.SERVER_TIMESTAMP if hasattr(firestore, "SERVER_TIMESTAMP") else agora_utc,
            })
            expirados_count += 1

            # Atualiza mensagem no Telegram se houver telegram_message_id
            tg_id = d.get("telegram_message_id")
            if tg_id:
                try:
                    from core.telegram_api import edit_message
                    from hermes_core_logic import _get_telegram_token
                    from main import _resolve_default_telegram_chat_id

                    token = telegram_token or _get_telegram_token(db)
                    target_chat = chat_id or _resolve_default_telegram_chat_id(db)
                    if token and target_chat:
                        dest_nome = d.get("destinatario_nome") or d.get("to_number") or ""
                        edit_message(
                            token,
                            target_chat,
                            int(tg_id),
                            f"⏱️ <b>Rascunho expirado</b> (mais de {limite_horas}h sem aprovação)\nDestino: {html.escape(str(dest_nome))}",
                        )
                except Exception as tg_err:
                    print(f"[OutboxAprovacao] Falha ao editar mensagem de expiração {tg_id}: {tg_err}")

    return expirados_count


def _degradar_rascunho_promovido_sem_mandato(db, outbox_id: str, motivo_codigo: str) -> bool:
    """Rebaixa um rascunho de `aguardando_janela` para `aguardando_aprovacao`
    (aprovação manual) quando `liberar_rascunhos_promovidos` descobre, na
    hora da liberação, que nenhum mandato cobre mais o `tipo` do rascunho.

    TRANSACIONAL e revalida o status atual antes de escrever -- mesmo padrão
    de `aprovar_rascunho`/`descartar_rascunho` (achado A04, documentado
    acima). Achado BLOQUEANTE da revisão adversarial desta sub-entrega
    (P02 17/N): a primeira versão fazia um `.update()` cru, sem revalidar
    status nem transação. Entre a consulta em `query.stream()`, no topo de
    `liberar_rascunhos_promovidos`, e esta função alcançar o documento (um
    intervalo alargado por esta própria sub-entrega, que agora faz 1-2
    leituras extras + uma escrita em `policy_decisions` por rascunho antes
    de chegar aqui), um humano pode ter tocado "Cancelar" no card do
    Telegram, e `descartar_rascunho` já ter transacionado o documento para
    `STATUS_DESCARTADO`. Um `.update()` cru sobrescreveria isso de volta
    para `aguardando_aprovacao` -- ressuscitando silenciosamente um
    rascunho que o dono já tinha descartado, o oposto exato do "veto humano
    inegociável" que `avaliar_liberacao_promovidos` documenta.

    Retorna `True` só quando de fato degradou (o status ainda era
    `aguardando_janela` dentro da transação); `False` quando o documento já
    tinha mudado de status por um caminho concorrente (nesse caso este
    caminho não faz nada -- o outro já decidiu) ou quando a escrita não pôde
    ser feita com segurança (sem suporte a transação, ou falha real de
    transação) -- mesmo raciocínio de "recusar em vez de arriscar escrita
    desprotegida" já aplicado a `aprovar_rascunho`/`descartar_rascunho`.
    """
    doc_ref = db.collection(COLLECTION).document(outbox_id)

    if not hasattr(db, "transaction"):
        print(
            f"[OutboxAprovacao] Backend sem suporte a transação; não é seguro "
            f"degradar {outbox_id} sem revalidar status -- deixado como está."
        )
        return False

    try:
        transaction = db.transaction()

        @firestore.transactional
        def _exec_degradar(tx):
            snap = doc_ref.get(transaction=tx)
            if not snap.exists:
                return False
            data = snap.to_dict() or {}
            if data.get("status") != STATUS_AGUARDANDO_JANELA:
                # Já decidido por outro caminho concorrente (aprovado,
                # descartado, ou até degradado por outra chamada) -- não
                # sobrescreve uma decisão que já aconteceu.
                return False
            tx.update(doc_ref, {
                "status": STATUS_AGUARDANDO,
                "envio_liberado_em": None,
                "degradado_motivo": motivo_codigo,
            })
            return True

        return bool(_exec_degradar(transaction))
    except Exception as exc:
        print(f"[OutboxAprovacao] Falha ao degradar {outbox_id} para aprovação manual: {exc}")
        return False


def liberar_rascunhos_promovidos(
    db,
    agora: datetime.datetime | None = None,
    telegram_token: str | None = None,
    chat_id: str | int | None = None,
) -> int:
    """Varre e libera rascunhos em aguardando_janela cujo envio_liberado_em <= agora."""
    # Preflight de autonomia (P02 sub-entrega 15/N, passo 1 do plano —
    # primeira religação real deste arquivo a autonomy/policy.py). Esta é a
    # ÚNICA função de todo o outbox que envia SEM um toque humano por
    # instância — rascunhos "promovidos" (ver `_tipos_promovidos`) só
    # aguardam a janela de cancelamento passar, depois `aprovar_rascunho` é
    # chamado sozinho, aqui embaixo, com `aprovado_via="janela_automatica"`.
    # Por não haver decisão humana concreta neste caminho (diferente de um
    # toque real no Telegram), tanto PAUSADO quanto SOMENTE_PREPARACAO
    # bloqueiam — o nome "somente preparação" já diz que enviar de verdade a
    # terceiros não é preparação. Fail-closed também na FALHA de leitura do
    # estado (SOMENTE_PREPARACAO é o resultado de `estado_autonomia_atual`
    # quando o Firestore não responde — ver docstring lá).
    #
    # P02 sub-entrega 17/N: além deste preflight global, cada rascunho agora
    # passa por `avaliar()` de verdade com um `Mandato` resolvido na hora
    # (`autonomy.mandatos_io.mandato_tipo_promovido`, ver
    # docs/autonomia/proposta-p02-mandato-io-wrapper.md) — não mais só o
    # status `aguardando_janela` decidido no PASSADO (na criação do
    # rascunho). Fecha a janela em que `tipo` é revogado de
    # `tipos_promovidos` DEPOIS de o rascunho ter sido criado como promovido
    # mas ANTES de a janela de cancelamento vencer: sem esta checagem, o
    # rascunho seria enviado sozinho mesmo já não estando mais coberto por
    # nenhum mandato. Quando o mandato não cobre (revogado nesse intervalo,
    # ou qualquer outra razão que `avaliar()` decida diferente de ALLOW), o
    # rascunho é degradado para aprovação manual (`STATUS_AGUARDANDO`) em vez
    # de enviado ou descartado silenciosamente — mesmo padrão já usado em
    # `criar_rascunho` para "falha_entrega_card_telegram", logo acima.
    from autonomy import mandatos_io
    from autonomy import policy as autonomy_policy
    from autonomy.contracts import (
        ClasseEfeito,
        Decisao,
        EstadoAutonomia,
        Principal,
        PolicyRequest,
        TipoPrincipal,
    )

    estado = autonomy_policy.estado_autonomia_atual(db)
    if estado in (EstadoAutonomia.PAUSADO, EstadoAutonomia.SOMENTE_PREPARACAO):
        print(
            f"[OutboxAprovacao] Autonomia {estado.value} "
            "(system/autonomy_state.global); pulando liberação automática de "
            "rascunhos promovidos."
        )
        return 0

    agora_utc = agora or datetime.datetime.now(timezone.utc)
    if agora_utc.tzinfo is None:
        agora_utc = agora_utc.replace(tzinfo=timezone.utc)

    query = db.collection(COLLECTION).where("status", "==", STATUS_AGUARDANDO_JANELA)
    docs = list(query.stream())

    rascunhos_dados = []
    for doc in docs:
        d = doc.to_dict() or {}
        d["id"] = doc.id
        rascunhos_dados.append(d)

    ids_liberar = avaliar_liberacao_promovidos(rascunhos_dados, agora_utc)
    rascunhos_por_id = {r["id"]: r for r in rascunhos_dados}

    # Principal do worker que libera sozinho: RUNNER_SERVICO ("processo de
    # longa duração agindo em nome do dono sem sessão interativa... o tipo
    # mais restrito: nunca deve conseguir conceder a si mesmo uma
    # permissão" — autonomy/contracts.py) é exatamente este caso, não
    # ROTINA_COWORK (que pressupõe uma rotina agendada do Cowork, um canal
    # diferente). `eh_dono()` é False para os dois, então a distinção não
    # muda a decisão de `avaliar()` aqui, mas identifica corretamente a
    # origem na trilha de auditoria (`registrar_decisao`).
    principal_worker = Principal(uid=None, tipo=TipoPrincipal.RUNNER_SERVICO, canal="outbox_worker")

    # Cache por `tipo` dentro desta chamada — evita reler
    # `system/mcp_access`/`promocoes_autonomia_sugeridas` uma vez por
    # rascunho quando vários rascunhos prontos compartilham o mesmo tipo.
    mandatos_cache: dict[str, object] = {}
    liberados_count = 0

    for doc_id in ids_liberar:
        rascunho = rascunhos_por_id.get(doc_id) or {}
        tipo = str(rascunho.get("tipo") or "").strip().lower()

        if tipo not in mandatos_cache:
            mandatos_cache[tipo] = mandatos_io.mandato_tipo_promovido(db, tipo, agora=agora_utc)
        mandato = mandatos_cache[tipo]

        request = PolicyRequest(
            principal=principal_worker,
            ferramenta="liberar_rascunhos_promovidos",
            classe_efeito=ClasseEfeito.COMPROMISSO_TERCEIROS,
            argumentos_resolvidos={"outbox_id": doc_id, "tipo": tipo},
            missao=f"envio_promovido:{tipo}",
            sensibilidade=tipo,
            estado_autonomia=estado,
            mandatos_aplicaveis=(mandato,) if mandato else (),
        )
        try:
            decisao = autonomy_policy.avaliar(request, agora=agora_utc)
        except Exception as exc:  # noqa: BLE001 — nunca deixa um erro de avaliação liberar por engano
            decisao = autonomy_policy.decisao_erro_avaliacao(
                request,
                motivo_legivel=(
                    f"Falha interna ao avaliar mandato do tipo '{tipo}' para {doc_id}; "
                    "bloqueado por segurança."
                ),
            )
        autonomy_policy.registrar_decisao(db, request, decisao)

        if decisao.decision != Decisao.ALLOW:
            print(
                f"[OutboxAprovacao] Mandato não cobre mais o tipo '{tipo}' para {doc_id} "
                f"({decisao.reason_code}); degradando para aprovação manual em vez de liberar."
            )
            _degradar_rascunho_promovido_sem_mandato(
                db, doc_id, motivo_codigo=f"mandato_nao_cobre:{decisao.reason_code}",
            )
            continue

        res = aprovar_rascunho(
            db,
            outbox_id=doc_id,
            telegram_token=telegram_token,
            chat_id=chat_id,
            aprovado_via="janela_automatica",
        )
        if res.get("status") == "ok":
            liberados_count += 1
        elif res.get("status") == "mandato_revogado":
            # Achado P1 da revisão Codex na PR #219: a checagem de mandato
            # logo acima (`mandato_tipo_promovido`, com cache por tipo para
            # o laço inteiro) já passou para este rascunho, mas
            # `aprovar_rascunho` rechecou de novo DENTRO da própria
            # transação e descobriu que o tipo foi revogado nesse meio-
            # tempo (revogação concorrente, ou cache deste laço já
            # desatualizado por um rascunho anterior do mesmo tipo). Mesmo
            # tratamento de "mandato não cobre mais": degrada para
            # aprovação manual em vez de deixar em aguardando_janela para
            # sempre.
            print(
                f"[OutboxAprovacao] Tipo '{tipo}' revogado durante a própria aprovação de {doc_id} "
                "(corrida com revogar_promocao_autonomia); degradando para aprovação manual."
            )
            _degradar_rascunho_promovido_sem_mandato(
                db, doc_id, motivo_codigo="mandato_revogado_durante_aprovacao",
            )

    return liberados_count


def listar_rascunhos(db, limite: int = 20) -> dict:
    """Lista rascunhos de WhatsApp com status aguardando_aprovacao ou aguardando_janela."""
    limite_ajustado = max(1, min(int(limite or 20), 50))
    query = (
        db.collection(COLLECTION)
        .where("status", "in", [STATUS_AGUARDANDO, STATUS_AGUARDANDO_JANELA])
    )

    docs = list(query.stream())
    rascunhos: list[dict] = []

    for doc in docs:
        d = doc.to_dict() or {}
        rascunhos.append({
            "id": doc.id,
            "status": d.get("status"),
            "destinatario_nome": d.get("destinatario_nome"),
            "to_number": d.get("to_number"),
            "motivo": d.get("motivo"),
            "trecho": str(d.get("content") or "")[:120],
            "acao_id": d.get("acao_id"),
            "item_atencao_id": d.get("item_atencao_id"),
            "origem": d.get("origem"),
            "tipo": d.get("tipo", "outro"),
            "foi_editado": bool(d.get("foi_editado", False)),
            "envio_liberado_em": _to_iso(d.get("envio_liberado_em")),
            "criado_em": _to_iso(d.get("created_at")),
            "telegram_message_id": d.get("telegram_message_id"),
        })

    def _sort_key(x: dict) -> str:
        return x.get("criado_em") or ""

    rascunhos.sort(key=_sort_key, reverse=True)
    return {
        "total": len(rascunhos),
        "rascunhos": rascunhos[:limite_ajustado],
    }


def contar_pendentes(db) -> int:
    """Retorna a contagem de rascunhos em aguardando_aprovacao ou aguardando_janela."""
    try:
        query = (
            db.collection(COLLECTION)
            .where("status", "in", [STATUS_AGUARDANDO, STATUS_AGUARDANDO_JANELA])
        )
        return len(list(query.stream()))
    except Exception:
        try:
            total = 0
            for st in (STATUS_AGUARDANDO, STATUS_AGUARDANDO_JANELA):
                total += len(list(db.collection(COLLECTION).where("status", "==", st).stream()))
            return total
        except Exception as fallback_exc:
            print(f"[OutboxAprovacao] Falha ao contar pendentes: {fallback_exc}")
            return 0


def metricas_por_tipo(db, tipo: str, limite: int = 20) -> dict:
    """Calcula métricas de aprovação e edição de rascunhos para um tipo específico.

    Busca os últimos `limite` documentos com aquele `tipo` e `status` em
    ('pending', 'sent') — ou seja, já aprovados e decididos pelo dono, ignorando
    rascunhos ainda pendentes de aprovação, descartados ou expirados.
    Ordena por `aprovado_em` decrescente.
    """
    tipo_limpo = str(tipo or "").strip()
    limite_ajustado = max(1, min(int(limite or 20), 100))

    if not tipo_limpo:
        return {
            "tipo": tipo_limpo,
            "amostra": 0,
            "aprovados_sem_edicao": 0,
            "taxa_sem_edicao": 0.0,
        }

    query = db.collection(COLLECTION).where("tipo", "==", tipo_limpo)
    docs = list(query.stream())

    # Filtra apenas os já decididos e aprovados (pending, sent)
    aprovados = []
    for doc in docs:
        d = doc.to_dict() or {}
        st = d.get("status")
        if st in (STATUS_PENDING, STATUS_SENT):
            aprovados.append(d)

    # Ordena por aprovado_em decrescente
    def _sort_aprovado(x: dict) -> str:
        val = x.get("aprovado_em")
        if val is None:
            return ""
        if isinstance(val, (datetime.datetime, datetime.date)):
            return val.isoformat()
        if hasattr(val, "isoformat"):
            return val.isoformat()
        return str(val)

    aprovados.sort(key=_sort_aprovado, reverse=True)
    amostra_docs = aprovados[:limite_ajustado]

    amostra = len(amostra_docs)
    sem_edicao = sum(1 for d in amostra_docs if not d.get("foi_editado", False))
    taxa = (sem_edicao / amostra) if amostra > 0 else 0.0

    return {
        "tipo": tipo_limpo,
        "amostra": amostra,
        "aprovados_sem_edicao": sem_edicao,
        "taxa_sem_edicao": taxa,
    }
