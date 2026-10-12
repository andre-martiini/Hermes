"""Callbacks do Telegram - confirmacoes (acao, financeiro, WhatsApp)

Extraido de hermes_core_logic.py::_handle_telegram_callback (P02, modularizacao
por area -- hermes_core_logic.py e telegram_utils.py cresceram alem do teto de
~64000 tokens de saida por chamada de escrita do Argos; ver decisao do Andre em
2026-09-08). Split puramente mecanico: nenhuma linha de logica foi reescrita, so
movida e envolvida por `def handle(...) -> bool`. Cada `return
https_fn.Response("OK", status=200)` virou `return True` (o chamador, em
telegram_handlers_core.py, sempre monta essa mesma resposta no fim -- o valor de
retorno aqui so diz se este modulo tratou o callback, para o dispatcher decidir
se tenta o proximo).

ATENCAO para mock.patch/mock.patch.object em testes: as funcoes deste arquivo
resolvem nomes livres (`_send_telegram_message`, `_answer_callback_query`,
etc.) pelo namespace DESTE modulo, nao pelo de hermes_core_logic nem de
telegram_handlers_core -- mesmo padrao documentado em telegram_utils.py. Um
`mock.patch.object(hermes_core_logic, "_send_telegram_message", ...)` nao
intercepta uma chamada feita de dentro de uma funcao deste arquivo.
"""
import html
import json
from datetime import datetime, timezone

from autonomy import policy as autonomy_policy
from autonomy.contracts import Decisao, Principal, TipoPrincipal
from telegram_utils import (
    _answer_callback_query,
    _clear_telegram_inline_keyboard,
    _save_session,
    _send_telegram_message,
)

def handle(db, token, query_id, chat_id, data, message, session, copilot_session_id, _persist_callback_turn, _pending_web_card, _clear_pending_web_card) -> bool:
    """Trata confirm_acao/cancel_acao, confirm_financeiro/cancel_financeiro, confirm_whatsapp/cancel_whatsapp e wa_cancel:. Retorna True se tratou."""
    if data == "confirm_acao":
        _answer_callback_query(token, query_id, "Processando registro...")
        # Remove o teclado inline imediatamente para que um duplo toque acidental não
        # reenvie o mesmo callback_query enquanto esta chamada ainda está em andamento.
        _clear_telegram_inline_keyboard(token, chat_id, message.get("message_id"))
        pending = session.get("pending_confirmations", {}).get("acao")
        if not pending:
            response_text = "⚠️ Nenhuma ação pendente de confirmação encontrada ou o prazo expirou."
            _persist_callback_turn("Botão: confirmar registro de ação", response_text)
            _send_telegram_message(token, chat_id, response_text)
            return True

        # Reivindicação atômica (título, data, horário) — evita criar a mesma ação mais de
        # uma vez quando o Telegram reenvia o mesmo callback_query (timeout de webhook) ou
        # o usuário toca duas vezes antes do teclado acima ser removido. Ver bug de eventos
        # duplicados na agenda / claim_action_dedup_slot em main.py.
        from main import claim_action_dedup_slot, store_action_dedup_result, release_action_dedup_slot
        _dedup_status, _dedup_task_id = claim_action_dedup_slot(
            db, pending.get("titulo"), pending.get("data_limite"), pending.get("horario_inicio")
        )
        if _dedup_status == "duplicate":
            response_text = f"✅ Essa ação já havia sido registrada.\nID: <code>{_dedup_task_id}</code>\nTítulo: {pending.get('titulo')}"
            _persist_callback_turn("Botão: confirmar registro de ação", response_text)
            _send_telegram_message(token, chat_id, response_text)
            session.get("pending_confirmations", {}).pop("acao", None)
            if session.get("_pending_confirm_type") == "acao":
                session.pop("_pending_confirm_type", None)
            _save_session(db, chat_id, session)
            return True
        if _dedup_status == "pending":
            response_text = "⏳ Essa ação já está sendo registrada por outra chamada. Verifique a lista de ações em alguns segundos."
            _persist_callback_turn("Botão: confirmar registro de ação", response_text)
            _send_telegram_message(token, chat_id, response_text)
            return True

        # Executa a criação (lógica de criar_acao_no_sistema)
        try:
            import uuid as _uuid
            now_iso = datetime.now(timezone.utc).isoformat()
            task_id = str(_uuid.uuid4())[:20]

            # Reuso da lógica de reagendamento se houver horários
            try:
                from main import get_calendar_service, get_target_calendar_id
                import hermes_calendar_tools as hc_tools
                c_service = get_calendar_service()
                c_id = get_target_calendar_id(db)
                if c_service and c_id and pending.get("horario_inicio") and pending.get("horario_fim"):
                    hc_tools.reagendar_acoes_hermes(db, c_service, c_id, pending.get("data_limite"), pending.get("horario_inicio"), pending.get("horario_fim"))
            except Exception: pass

            import subtarefas as _sub
            plano_convertido = _sub.converter_plano(pending.get("plano_acao"))

            doc = {
                "id": task_id,
                "titulo": pending["titulo"].strip(),
                "descricao": pending.get("descricao") or "",
                "area_tematica": pending.get("area_tematica") or "GERAL",
                "data_limite": pending.get("data_limite"),
                "prazo_final": pending.get("prazo_final"),
                "horario_inicio": pending.get("horario_inicio"),
                "horario_fim": pending.get("horario_fim"),
                "tipo_acao": pending.get("tipo_acao") or "fast",
                "tags": pending.get("tags") or [],
                "notas": pending.get("notas") or "",
                "plano_acao": plano_convertido,
                "status": "em andamento",
                "criado_em": now_iso,
                "data_criacao": now_iso,
                "origem_ingestao": "telegram",
                "sync_status": "new",
            }
            db.collection("tarefas").document(task_id).set(doc)
            store_action_dedup_result(db, pending.get("titulo"), pending.get("data_limite"), pending.get("horario_inicio"), task_id)

            # Limpa pendência
            session.get("pending_confirmations", {}).pop("acao", None)
            if session.get("_pending_confirm_type") == "acao":
                session.pop("_pending_confirm_type", None)
            _save_session(db, chat_id, session)

            response_text = f"✅ <b>Ação registrada com sucesso!</b>\nID: <code>{task_id}</code>\nTítulo: {pending['titulo']}"
            _persist_callback_turn("Botão: confirmar registro de ação", response_text)
            _send_telegram_message(token, chat_id, response_text)
        except Exception as e:
            release_action_dedup_slot(db, pending.get("titulo"), pending.get("data_limite"), pending.get("horario_inicio"))
            response_text = f"❌ Erro ao registrar ação: {e}"
            _persist_callback_turn("Botão: confirmar registro de ação", response_text)
            _send_telegram_message(token, chat_id, response_text)

    elif data == "cancel_acao":
        _answer_callback_query(token, query_id, "Cancelado.")
        session.get("pending_confirmations", {}).pop("acao", None)
        if session.get("_pending_confirm_type") == "acao":
            session.pop("_pending_confirm_type", None)
        _save_session(db, chat_id, session)
        response_text = "❌ Registro de ação cancelado pelo usuário."
        _persist_callback_turn("Botão: cancelar registro de ação", response_text)
        _send_telegram_message(token, chat_id, response_text)

    elif data == "confirm_financeiro":
        _answer_callback_query(token, query_id, "Processando lançamento...")
        pending = session.get("pending_confirmations", {}).get("financeiro")
        if not pending:
            response_text = "⚠️ Nenhum lançamento financeiro pendente."
            _persist_callback_turn("Botão: confirmar lançamento financeiro", response_text)
            _send_telegram_message(token, chat_id, response_text)
            return True

        try:
            from tools.telegram_extended import execute
            res = execute("registrar_item_financeiro_v2", pending, db)

            session.get("pending_confirmations", {}).pop("financeiro", None)
            if session.get("_pending_confirm_type") == "financeiro":
                session.pop("_pending_confirm_type", None)
            _save_session(db, chat_id, session)

            response_text = f"✅ <b>Lançamento financeiro realizado!</b>\n{res}"
            _persist_callback_turn("Botão: confirmar lançamento financeiro", response_text)
            _send_telegram_message(token, chat_id, response_text)
        except Exception as e:
            response_text = f"❌ Erro no financeiro: {e}"
            _persist_callback_turn("Botão: confirmar lançamento financeiro", response_text)
            _send_telegram_message(token, chat_id, response_text)

    elif data == "cancel_financeiro":
        _answer_callback_query(token, query_id, "Cancelado.")
        session.get("pending_confirmations", {}).pop("financeiro", None)
        if session.get("_pending_confirm_type") == "financeiro":
            session.pop("_pending_confirm_type", None)
        _save_session(db, chat_id, session)
        response_text = "❌ Lançamento financeiro descartado."
        _persist_callback_turn("Botão: cancelar lançamento financeiro", response_text)
        _send_telegram_message(token, chat_id, response_text)

    elif data == "confirm_whatsapp":
        _answer_callback_query(token, query_id, "Enfileirando mensagem...")
        pending = session.get("pending_confirmations", {}).get("whatsapp")
        if not pending:
            response_text = "⚠️ Nenhuma mensagem de WhatsApp pendente."
            _persist_callback_turn("Botão: confirmar WhatsApp", response_text)
            _send_telegram_message(token, chat_id, response_text)
            return True

        # Preflight de autonomy.policy (P02 sub-entrega 10/N) — este é o
        # único ponto de integração possível para este fluxo: a closure de
        # tool-calling do Gemini que monta `pending` (schedule_whatsapp_message,
        # mais abaixo neste arquivo) roda dentro do processamento da mensagem
        # e nunca teve acesso resolvido a `db`/política; a decisão real de
        # "isto pode ser enviado" só pode ser tomada aqui, no clique do botão
        # "Confirmar" — imediatamente antes do envio de fato, o que também
        # cobre o caso de o estado de autonomia mudar entre a prévia e a
        # confirmação (limitação que mcp_server.py ainda tem, ver
        # `_decisao_piso_mcp`). TipoPrincipal.DONO_INTERATIVO + origem_humana
        # =True porque este é literalmente um clique de botão em tempo real
        # do próprio dono — o canal com o sinal de presença humana mais forte
        # que existe hoje (mais forte que CLIENTE_ASSISTIDO, usado pelo MCP).
        # Hoje (`system/autonomy_state` ainda não é escrito por nada) isto
        # sempre resolve REQUIRE_APPROVAL e cai no mesmo fluxo de sempre, sem
        # mudar nenhum comportamento visível — só passa a bloquear no dia em
        # que autonomia for pausada ou posta em somente-preparação. Em
        # nenhum dos dois ramos de bloqueio o `pending` é descartado: o dono
        # pode tentar "Confirmar" de novo mais tarde (se destravar) ou usar o
        # botão "Cancelar" já existente — um bloqueio temporário de política
        # não deve apagar silenciosamente o rascunho que ele já aprovou.
        principal = Principal(
            uid=session.get("userId"),
            tipo=TipoPrincipal.DONO_INTERATIVO,
            canal="telegram",
            origem_humana=True,
        )
        decisao_piso = autonomy_policy.decisao_piso(db, principal, "schedule_whatsapp_message", pending)
        if decisao_piso is not None and decisao_piso.decision == Decisao.DENY:
            response_text = (
                "🚫 Bloqueado pela política de autonomia vigente: "
                + html.escape(decisao_piso.motivo_legivel or "ação não permitida agora.")
            )
            _persist_callback_turn("Botão: confirmar WhatsApp", response_text)
            _send_telegram_message(token, chat_id, response_text)
            return True
        if decisao_piso is not None and decisao_piso.decision == Decisao.PREPARE_ONLY:
            response_text = (
                "⏸️ Autonomia está em modo somente-preparação: esta mensagem não "
                "pode ser enviada agora. " + html.escape(decisao_piso.motivo_legivel or "")
            ).strip()
            _persist_callback_turn("Botão: confirmar WhatsApp", response_text)
            _send_telegram_message(token, chat_id, response_text)
            return True

        try:
            from tools.schedule_whatsapp_message import schedule_whatsapp_message as _schedule_whatsapp
            res = _schedule_whatsapp(
                db,
                pending.get("contact_number") or "",
                pending.get("message") or "",
                pending.get("scheduled_time") or "",
            )

            session.get("pending_confirmations", {}).pop("whatsapp", None)
            if session.get("_pending_confirm_type") == "whatsapp":
                session.pop("_pending_confirm_type", None)
            _save_session(db, chat_id, session)

            response_text = f"✅ <b>WhatsApp confirmado.</b>\n{html.escape(str(res))}"
            _persist_callback_turn("Botão: confirmar WhatsApp", response_text)
            _send_telegram_message(token, chat_id, response_text)
        except Exception as e:
            response_text = f"❌ Erro ao enfileirar WhatsApp: {html.escape(str(e))}"
            _persist_callback_turn("Botão: confirmar WhatsApp", response_text)
            _send_telegram_message(token, chat_id, response_text)

    elif data == "cancel_whatsapp":
        _answer_callback_query(token, query_id, "Cancelado.")
        session.get("pending_confirmations", {}).pop("whatsapp", None)
        if session.get("_pending_confirm_type") == "whatsapp":
            session.pop("_pending_confirm_type", None)
        _save_session(db, chat_id, session)
        response_text = "❌ Envio de WhatsApp descartado."
        _persist_callback_turn("Botão: cancelar WhatsApp", response_text)
        _send_telegram_message(token, chat_id, response_text)

    elif data == "confirm_memoria_manter":
        # P06 sub-entrega 3/N -- resolve direto pelo botão, em vez de
        # depender do modelo repassar `memoria_id` numa 2ª chamada de
        # ferramenta (ver comentário de `salvar_memoria_global` em
        # telegram_message_tools.py). `pending` vem de
        # `session["pending_confirmations"]["memoria_conflito"]`, gravado
        # por aquele closure quando `_save_memory_node` devolve "conflict".
        #
        # Toast otimista ("Mantendo...") disparado ANTES de validar
        # `pending` -- mesmo padrão já usado por confirm_financeiro/
        # confirm_acao/confirm_whatsapp acima neste arquivo (achado de
        # revisão adversarial independente desta sub-entrega, não
        # corrigido aqui para não divergir desses 3 fluxos existentes só
        # neste botão novo; severidade baixa, o texto final enviado por
        # `_send_telegram_message` sempre reflete o resultado real).
        _answer_callback_query(token, query_id, "Mantendo o fato existente...")
        pending = session.get("pending_confirmations", {}).get("memoria_conflito")
        if not pending:
            response_text = "⚠️ Nenhum conflito de memória pendente encontrado ou o prazo expirou."
            _persist_callback_turn("Botão: manter memória existente", response_text)
            _send_telegram_message(token, chat_id, response_text)
            return True

        # `categoria` aqui é a do FATO NOVO (descartado nesta decisão) --
        # achado real de revisão adversarial independente desta
        # sub-entrega: `execute("resolver_conflito_memoria", ...)` hoje
        # ignora esse campo por completo quando decisao="manter_existente"
        # (só grava conflito_resolvido_em/ultima_decisao_humana, ver
        # tools/telegram_extended.py), então isto não é um bug de
        # comportamento HOJE -- mas enviar a categoria do fato rejeitado
        # mesmo assim seria um dado semanticamente errado se aquele código
        # um dia passar a usar o campo. Usa `categoria_existente` (a do nó
        # que de fato permanece) em vez de `categoria`.
        try:
            from tools.telegram_extended import execute
            resultado_json = execute("resolver_conflito_memoria", {
                "memoria_id": pending.get("memory_id"),
                "decisao": "manter_existente",
                "fato_atualizado": "",
                "categoria": pending.get("categoria_existente") or "fato_isolado",
            }, db)
        except Exception as e:
            response_text = f"❌ Erro ao resolver conflito de memória: {html.escape(str(e))}"
            _persist_callback_turn("Botão: manter memória existente", response_text)
            _send_telegram_message(token, chat_id, response_text)
            return True

        # Achado real de uma 2ª rodada de revisão adversarial independente:
        # `execute(...)` pode devolver um JSON com status "error" (ex.:
        # `memoria_id` apagado/inexistente) SEM lançar excecão -- o
        # try/except acima sozinho não pega isso, e sem este check o botão
        # reportaria sucesso falso e ainda limparia a pendência (impedindo
        # uma nova tentativa). `resolver_conflito_memoria` (closure-
        # ferramenta irmão, telegram_message_tools.py) já faz esse mesmo
        # parsing de status antes de decidir limpar -- replicado aqui.
        try:
            status_resultado = json.loads(resultado_json).get("status")
        except (ValueError, TypeError, AttributeError):
            status_resultado = None
        if status_resultado not in ("resolved", "updated"):
            response_text = (
                "❌ Não foi possível resolver o conflito de memória "
                f"(resposta inesperada: {html.escape(str(status_resultado))})."
            )
            _persist_callback_turn("Botão: manter memória existente", response_text)
            _send_telegram_message(token, chat_id, response_text)
            return True

        response_text = (
            "✅ <b>Fato existente mantido.</b>\n"
            f"• Mantido: {html.escape(pending.get('existing_text') or '(sem texto registrado)')}\n"
            f"• Descartado: {html.escape(pending.get('fato_atualizado') or '')}"
        )
        # Limpeza da pendência/sessão separada da chamada a `execute` acima
        # (achado real de revisão adversarial independente desta
        # sub-entrega): se `execute` já tiver resolvido o conflito de
        # verdade no Firestore mas `_save_session` falhar (ex.: blip de
        # rede), isso NÃO é uma falha da resolução -- reportar como erro
        # nesse caso seria uma mensagem falsa ao usuário. A pendência pode
        # ficar obsoleta na sessão persistida (o botão reaparece, um novo
        # toque reenvia a mesma decisão -- idempotente do lado do
        # Firestore, já que é só um merge de campos fixos), mas o usuário
        # não é informado de uma falha que não ocorreu.
        try:
            session.get("pending_confirmations", {}).pop("memoria_conflito", None)
            if session.get("_pending_confirm_type") == "memoria_conflito":
                session.pop("_pending_confirm_type", None)
            _save_session(db, chat_id, session)
        except Exception as e:
            print(f"[TelegramCallback] Conflito de memória resolvido, mas falha ao salvar sessão: {e}")
            response_text += "\n⚠️ A operação foi concluída, mas houve um problema ao atualizar a sessão."

        _persist_callback_turn("Botão: manter memória existente", response_text)
        _send_telegram_message(token, chat_id, response_text)

    elif data == "confirm_memoria_substituir":
        # P06 sub-entrega 3/N -- mesmo raciocínio de confirm_memoria_manter
        # acima, decisão "substituir_pelo_novo" (aqui `categoria` É a do
        # fato novo, correta para este ramo -- `fato_atualizado`/
        # `categoria` do fato proposto são exatamente o que
        # `execute("resolver_conflito_memoria", ...)` grava quando
        # substitui).
        _answer_callback_query(token, query_id, "Substituindo pelo novo fato...")
        pending = session.get("pending_confirmations", {}).get("memoria_conflito")
        if not pending:
            response_text = "⚠️ Nenhum conflito de memória pendente encontrado ou o prazo expirou."
            _persist_callback_turn("Botão: substituir memória pelo novo fato", response_text)
            _send_telegram_message(token, chat_id, response_text)
            return True

        try:
            from tools.telegram_extended import execute
            resultado_json = execute("resolver_conflito_memoria", {
                "memoria_id": pending.get("memory_id"),
                "decisao": "substituir_pelo_novo",
                "fato_atualizado": pending.get("fato_atualizado") or "",
                "categoria": pending.get("categoria") or "fato_isolado",
            }, db)
        except Exception as e:
            response_text = f"❌ Erro ao resolver conflito de memória: {html.escape(str(e))}"
            _persist_callback_turn("Botão: substituir memória pelo novo fato", response_text)
            _send_telegram_message(token, chat_id, response_text)
            return True

        # Achado real de uma 2ª rodada de revisão adversarial independente:
        # para "substituir_pelo_novo", `execute(...)` propaga o resultado
        # de `main._save_memory_node(force_update_id=...)`, que devolve
        # `{"status": "error", "reason": "memory_not_found"}` SEM lançar
        # excecão se o nó tiver sido apagado/alterado entre a detecção do
        # conflito e o toque no botão (a pendência pode viver vários
        # turnos) -- "updated" é o status real de sucesso aqui, nunca
        # "resolved" (esse é só de "manter_existente"). Sem este check, o
        # botão reportaria sucesso falso e limparia a pendência mesmo
        # assim.
        try:
            status_resultado = json.loads(resultado_json).get("status")
        except (ValueError, TypeError, AttributeError):
            status_resultado = None
        if status_resultado not in ("resolved", "updated"):
            response_text = (
                "❌ Não foi possível resolver o conflito de memória "
                f"(resposta inesperada: {html.escape(str(status_resultado))})."
            )
            _persist_callback_turn("Botão: substituir memória pelo novo fato", response_text)
            _send_telegram_message(token, chat_id, response_text)
            return True

        response_text = (
            "✅ <b>Memória atualizada com o novo fato.</b>\n"
            f"• Novo texto: {html.escape(pending.get('fato_atualizado') or '')}\n"
            f"• Texto anterior: {html.escape(pending.get('existing_text') or '(sem texto registrado)')}"
        )
        # Mesmo raciocínio de confirm_memoria_manter acima: limpeza
        # separada da chamada a `execute` que já teve sucesso.
        try:
            session.get("pending_confirmations", {}).pop("memoria_conflito", None)
            if session.get("_pending_confirm_type") == "memoria_conflito":
                session.pop("_pending_confirm_type", None)
            _save_session(db, chat_id, session)
        except Exception as e:
            print(f"[TelegramCallback] Conflito de memória resolvido, mas falha ao salvar sessão: {e}")
            response_text += "\n⚠️ A operação foi concluída, mas houve um problema ao atualizar a sessão."

        _persist_callback_turn("Botão: substituir memória pelo novo fato", response_text)
        _send_telegram_message(token, chat_id, response_text)

    elif data.startswith("wa_cancel:"):
        doc_id = data.split("wa_cancel:")[1].strip()
        # Corrigido ao construir cancelar_envio_whatsapp: isto era uma escrita
        # direta, sem transação nem revalidação de status -- uma corrida real
        # contra claimOutboxMessage (o worker também disputa o mesmo
        # documento) podia sobrescrever silenciosamente um envio já
        # 'sending'/'sent' de volta para 'canceled': não impede o envio (o
        # worker já tinha reivindicado antes) e ainda corrompe o registro de
        # auditoria. Roteado pela mesma função transacional que
        # cancelar_envio_whatsapp usa -- perde a corrida de forma segura em
        # vez de escrever por cima às cegas.
        #
        # Achado da revisão adversarial (22/09/2026): a versão anterior
        # respondia "cancelado" ao dono incondicionalmente, mesmo quando
        # cancelar_envio recusava (já enviado, já em andamento...) -- o toque
        # no botão parecia ter funcionado mesmo quando não funcionou. Agora o
        # resultado real decide o texto.
        resultado: dict = {}
        try:
            if doc_id:
                from outbox_aprovacao import cancelar_envio
                resultado = cancelar_envio(db, doc_id, cancelado_via="telegram") or {}
        except Exception as exc:
            print(f"[TelegramCallback] Erro ao cancelar WhatsApp agendado {doc_id}: {exc}")
            resultado = {"status": "erro_transacao", "erro": str(exc)}

        status_resultado = resultado.get("status")
        if status_resultado in ("ok", "already_canceled"):
            toast = "Agendamento cancelado."
            response_text = "❌ <b>Envio de WhatsApp agendado foi cancelado.</b>"
        elif status_resultado == "nao_cancelavel":
            status_atual = html.escape(str(resultado.get("status_atual") or "?"))
            toast = "Não foi possível cancelar."
            response_text = (
                f"⚠️ <b>Não foi possível cancelar</b> — o envio já está em "
                f"'{status_atual}'."
            )
        elif status_resultado == "not_found":
            toast = "Não encontrado."
            response_text = "⚠️ <b>Envio não encontrado</b> — talvez já tenha sido tratado."
        else:
            toast = "Falha ao cancelar."
            response_text = "⚠️ <b>Falha ao tentar cancelar</b> — tente de novo em instantes."

        _answer_callback_query(token, query_id, toast)
        _persist_callback_turn("Botão: cancelar WhatsApp agendado", response_text)
        _send_telegram_message(token, chat_id, response_text)

    elif data.startswith("wa_confirm_sent:"):
        # Fecha o ciclo do fallback de notificacao manual (ai_notification_planner.py::
        # dispatch_scheduled_whatsapp_messages): o botao "Sim, Enviar no WhatsApp" e um
        # link wa.me que abre o app e o toque final de enviar e invisivel para o Hermes.
        # Sem este handler, o doc ficava para sempre em status "notified"/tentativas=0,
        # mesmo apos a entrega real (caso relatado por Andre em 16/09/2026, job
        # bae25bc6-0729-4213-a24d-c37feea5d687, entregue as 16:28 e nunca marcado "sent").
        # Achado da 2ª rodada de revisão adversarial de cancelar_envio_whatsapp
        # (22/09/2026): isto fazia a MESMA escrita crua, sem transação nem
        # revalidação, que wa_cancel: fazia antes de ser corrigido -- os dois
        # botões vêm juntos no mesmo cartão do Telegram, então um toque
        # duplicado/reentregue (o webhook do Telegram reenvia callback_query
        # em timeout) podia confirmar como "sent" um envio que "❌ Cancelar"
        # já tinha transacionado para "canceled" no mesmo cartão. Roteado
        # pela mesma disciplina transacional de cancelar_envio/
        # marcar_notificado.
        doc_id = data.split("wa_confirm_sent:")[1].strip()
        resultado: dict = {}
        try:
            if doc_id:
                from outbox_aprovacao import confirmar_envio_manual
                resultado = confirmar_envio_manual(
                    db, doc_id, sent_at=datetime.now(timezone.utc)
                ) or {}
        except Exception as exc:
            print(f"[TelegramCallback] Erro ao confirmar envio manual de WhatsApp {doc_id}: {exc}")
            resultado = {"status": "erro_transacao", "erro": str(exc)}

        status_resultado = resultado.get("status")
        if status_resultado in ("ok", "already_sent"):
            toast = "Marcado como enviado."
            response_text = "☑️ <b>Envio de WhatsApp confirmado como feito.</b>"
        elif status_resultado == "nao_confirmavel":
            status_atual = html.escape(str(resultado.get("status_atual") or "?"))
            toast = "Não foi possível confirmar."
            response_text = (
                f"⚠️ <b>Não foi possível confirmar</b> — o envio já está em "
                f"'{status_atual}'."
            )
        elif status_resultado == "not_found":
            toast = "Não encontrado."
            response_text = "⚠️ <b>Envio não encontrado</b> — talvez já tenha sido tratado."
        else:
            toast = "Falha ao confirmar."
            response_text = "⚠️ <b>Falha ao tentar confirmar</b> — tente de novo em instantes."

        _answer_callback_query(token, query_id, toast)
        _persist_callback_turn("Botão: confirmar envio manual de WhatsApp", response_text)
        _send_telegram_message(token, chat_id, response_text)

    else:
        return False
    return True
