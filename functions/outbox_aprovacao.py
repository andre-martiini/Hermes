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
    if envio_imediato:
        is_promovido = False
        janela_min = 0
        envio_liberado_em = None
        status_inicial = STATUS_PENDING
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
    transaction_result = {}

    transaction_success = False
    if hasattr(db, "transaction"):
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
            transaction_success = True
        except Exception as tx_err:
            print(f"[OutboxAprovacao] Transação Firestore falhou ou mock sem suporte: {tx_err}")

    if not transaction_success:
        # Fallback sem transaction real (testes / mocks simples)
        snap = doc_ref.get()
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
        doc_ref.update({
            "status": STATUS_PENDING,
            "aprovado_em": agora_utc,
            "aprovado_via": aprovado_via,
            "scheduled_for": agora_utc,
        })
        transaction_result = {"status": "ok", "dados": data}

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
                desfecho="mensagem aprovada e enviada",
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
    transaction_result = {}
    transaction_success = False

    if hasattr(db, "transaction"):
        try:
            transaction = db.transaction()

            @firestore.transactional
            def _exec_discard(tx):
                snap = doc_ref.get(transaction=tx)
                if not snap.exists:
                    return {"status": "not_found", "erro": f"Rascunho '{outbox_id}' não encontrado."}
                data = snap.to_dict() or {}
                valido, motivo = validar_transicao_descarte(data.get("status"))
                if not valido:
                    return {
                        "status": "already_decided",
                        "erro": f"Rascunho {motivo}",
                        "dados": data,
                    }

                tx.update(
                    doc_ref,
                    {
                        "status": STATUS_DESCARTADO,
                        "descartado_em": firestore.SERVER_TIMESTAMP if hasattr(firestore, "SERVER_TIMESTAMP") else agora_utc,
                    },
                )
                return {"status": "ok", "dados": data}

            transaction_result = _exec_discard(transaction)
            transaction_success = True
        except Exception as tx_err:
            print(f"[OutboxAprovacao] Transação Firestore de descarte falhou ou mock sem suporte: {tx_err}")

    if not transaction_success:
        snap = doc_ref.get()
        if not snap.exists:
            return {"status": "not_found", "erro": f"Rascunho '{outbox_id}' não encontrado."}
        data = snap.to_dict() or {}
        valido, motivo = validar_transicao_descarte(data.get("status"))
        if not valido:
            return {"status": "already_decided", "erro": f"Rascunho {motivo}", "dados": data}
        doc_ref.update({
            "status": STATUS_DESCARTADO,
            "descartado_em": agora_utc,
        })
        transaction_result = {"status": "ok", "dados": data}

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
    """Aplica o texto editado pelo dono diretamente ao rascunho e reenvia o card."""
    outbox_id = str(outbox_id or "").strip()
    novo_texto = str(novo_texto or "").strip()
    if not outbox_id:
        return {"erro": "outbox_id é obrigatório."}
    if not novo_texto:
        return {"erro": "novo_texto é obrigatório."}

    doc_ref = db.collection(COLLECTION).document(outbox_id)
    snap = doc_ref.get()
    if not snap.exists:
        return {"status": "not_found", "erro": f"Rascunho '{outbox_id}' não encontrado."}

    data = snap.to_dict() or {}
    agora_utc = datetime.datetime.now(timezone.utc)

    doc_ref.update({
        "content": novo_texto,
        "status": STATUS_AGUARDANDO,
        "foi_editado": True,
        "atualizado_em": firestore.SERVER_TIMESTAMP if hasattr(firestore, "SERVER_TIMESTAMP") else agora_utc,
    })

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


def liberar_rascunhos_promovidos(
    db,
    agora: datetime.datetime | None = None,
    telegram_token: str | None = None,
    chat_id: str | int | None = None,
) -> int:
    """Varre e libera rascunhos em aguardando_janela cujo envio_liberado_em <= agora."""
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
    liberados_count = 0

    for doc_id in ids_liberar:
        res = aprovar_rascunho(
            db,
            outbox_id=doc_id,
            telegram_token=telegram_token,
            chat_id=chat_id,
            aprovado_via="janela_automatica",
        )
        if res.get("status") == "ok":
            liberados_count += 1

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
