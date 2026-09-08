"""Testes do preflight de `autonomy.policy` no callback "Confirmar" do envio
de WhatsApp via Telegram (P02 sub-entrega 10/N).

NOTA (honestidade epistêmica): esta sub-entrega não pôde ser documentada em
docs/autonomia/execucao.md — ver PR #198 (que resolveu o segundo conflito de
merge da sub-entrega anterior) para o diagnóstico: o arquivo já passou do
que a API de escrita do Argos consegue publicar numa chamada só. Este
docstring é o registro que normalmente estaria lá.

Contexto: `hermes_core_logic.py::_handle_telegram_callback` tinha, até esta
sub-entrega, um `elif data == "confirm_whatsapp":` que chamava
`tools.schedule_whatsapp_message.schedule_whatsapp_message(...)` direto —
sem NUNCA consultar `autonomy.policy`, mesmo esse tool estando no piso de
confirmação obrigatória (`FLOOR_CONFIRMACAO_OBRIGATORIA`) desde a sub-entrega
1/N. Diferente do canal MCP (`mcp_server.py::_decisao_piso_mcp`, consultado
na CRIAÇÃO da prévia de confirmação), o Telegram monta a prévia numa closure
de tool-calling do Gemini (`schedule_whatsapp_message`, dentro de
`_process_telegram_message`) sem `db` resolvido nem acesso a política — o
único ponto de integração possível é aqui, no clique do botão "Confirmar",
imediatamente antes do envio de fato.

Espelha o padrão de `test_mcp_server.py::TestDecisaoPisoMcp` /
`TestHandleToolsCallPreflight`: mocka só a fronteira de I/O do motor de
política (`autonomy_policy.estado_autonomia_atual`/`registrar_decisao`),
deixando `autonomy_policy.decisao_piso()`/`avaliar()` REAIS decidirem — prova
o mapeamento DENY/PREPARE_ONLY -> resposta do bot, não reimplementa o motor
em si (isso já é coberto por `test_policy.py`).

`_handle_telegram_callback` não tinha nenhum teste antes desta sub-entrega
(confirmado por busca no repositório: nenhum `test_*.py` a importava).
Escopo deliberadamente estreito, como o de `test_mcp_server.py` quando
`mcp_server.py` ganhou seu primeiro teste: só o ramo `confirm_whatsapp`, que
é o único tocado por esta mudança — não uma tentativa de cobrir a função
inteira (que também trata check-in de saúde, edição de rascunho, lançamento
financeiro, cancelamento de agendamento, etc., nenhum alterado aqui).

NOTA (P02, modularização por área, 2026-09-08): `_handle_telegram_callback`
foi dividido entre `telegram_handlers_core.py` (setup: allowlist/sessão) e
`telegram_callbacks_confirmacoes.py` (o próprio ramo `confirm_whatsapp`, com
`autonomy_policy`/`Principal`/`Decisao` incluídos). Os mocks abaixo miram o
módulo onde cada nome livre é resolvido — não mais `hermes_core_logic`, que
virou puro shim de reexportação. Ver docstring de `telegram_utils.py` para o
porquê (mock.patch.object não intercepta uma chamada de nome livre feita de
dentro de uma função que mora em outro módulo).
"""
import contextlib
import unittest
from unittest.mock import MagicMock, patch

import hermes_core_logic
import telegram_callbacks_confirmacoes
import telegram_handlers_core
from autonomy.contracts import Decisao, EstadoAutonomia


def _callback_query(chat_id="123456", query_id="q1"):
    return {
        "id": query_id,
        "data": "confirm_whatsapp",
        "message": {"chat": {"id": chat_id}},
        "from": {"id": chat_id},
    }


def _session_com_pending(uid="dono-uid"):
    return {
        "chat_id": "123456",
        "userId": uid,
        "pending_confirmations": {
            "whatsapp": {
                "contact_number": "+5511999999999",
                "message": "Oi, tudo bem?",
                "scheduled_time": "2026-09-08T12:00:00Z",
            }
        },
        "_pending_confirm_type": "whatsapp",
    }


class _ConfirmWhatsappTestBase(unittest.TestCase):
    """Monta os mocks de infraestrutura comuns (sessão/allowlist/Telegram) a
    todos os testes deste ramo, deixando só o estado de autonomia e o envio
    de fato variarem por teste — mesmo raciocínio do helper `_gating()` de
    `test_hermes_tools.py`."""

    @contextlib.contextmanager
    def _contexto(self, estado: EstadoAutonomia, session: dict | None = None):
        session = session if session is not None else _session_com_pending()
        with patch.object(
            telegram_handlers_core, "_get_allowed_chat_id", return_value=None,
        ), patch.object(
            telegram_handlers_core, "_get_session", return_value=session,
        ), patch.object(
            telegram_handlers_core, "_ensure_copilot_session", return_value="copilot-session-test",
        ), patch.object(
            telegram_handlers_core, "_save_session",
        ), patch.object(
            telegram_callbacks_confirmacoes, "_save_session",
        ) as mock_save_session, patch.object(
            telegram_callbacks_confirmacoes, "_answer_callback_query",
        ), patch.object(
            telegram_callbacks_confirmacoes, "_send_telegram_message",
        ) as mock_send, patch.object(
            telegram_callbacks_confirmacoes.autonomy_policy, "estado_autonomia_atual", return_value=estado,
        ), patch.object(
            telegram_callbacks_confirmacoes.autonomy_policy, "registrar_decisao",
        ) as mock_registrar, patch(
            "tools.schedule_whatsapp_message.schedule_whatsapp_message",
            return_value="Mensagem ENFILEIRADA (ainda nao enviada) para +5511999999999. job_id=abc123.",
        ) as mock_schedule:
            resultado = hermes_core_logic._handle_telegram_callback(
                MagicMock(), "fake-token", _callback_query()
            )
            yield resultado, session, mock_save_session, mock_send, mock_registrar, mock_schedule


class TestConfirmWhatsappPolicyPreflight(_ConfirmWhatsappTestBase):
    def test_pausado_bloqueia_e_nunca_chama_schedule(self):
        with self._contexto(EstadoAutonomia.PAUSADO) as (
            resultado, session, mock_save_session, mock_send, mock_registrar, mock_schedule,
        ):
            pass
        mock_schedule.assert_not_called()
        mock_registrar.assert_called_once()
        # PolicyRequest avaliado de fato veio do piso (autonomia_pausada) —
        # não é um erro genérico não relacionado à política.
        request_avaliado = mock_registrar.call_args.args[1]
        self.assertEqual(request_avaliado.ferramenta, "schedule_whatsapp_message")
        texto = mock_send.call_args.args[2]
        self.assertIn("Bloqueado pela política de autonomia", texto)
        # O rascunho pendente não é descartado por um bloqueio temporário —
        # o dono pode tentar de novo mais tarde (se destravar) ou cancelar
        # explicitamente pelo botão já existente.
        self.assertIn("whatsapp", session.get("pending_confirmations", {}))

    def test_somente_preparacao_bloqueia_e_nunca_chama_schedule(self):
        with self._contexto(EstadoAutonomia.SOMENTE_PREPARACAO) as (
            resultado, session, mock_save_session, mock_send, mock_registrar, mock_schedule,
        ):
            pass
        mock_schedule.assert_not_called()
        texto = mock_send.call_args.args[2]
        self.assertIn("somente-preparação", texto)
        self.assertIn("whatsapp", session.get("pending_confirmations", {}))

    def test_ativo_prossegue_e_chama_schedule_com_os_dados_pendentes(self):
        with self._contexto(EstadoAutonomia.ATIVO) as (
            resultado, session, mock_save_session, mock_send, mock_registrar, mock_schedule,
        ):
            pass
        mock_schedule.assert_called_once()
        _db_usado, contact_number, message, scheduled_time = mock_schedule.call_args.args
        self.assertEqual(contact_number, "+5511999999999")
        self.assertEqual(message, "Oi, tudo bem?")
        self.assertEqual(scheduled_time, "2026-09-08T12:00:00Z")
        # Fluxo de sempre, sem mudança de comportamento visível quando ATIVO
        # (o estado real de produção hoje — system/autonomy_state ainda não
        # é escrito por nada).
        texto = mock_send.call_args.args[2]
        self.assertIn("WhatsApp confirmado", texto)
        # Confirmação consumida só quando o envio de fato prossegue.
        self.assertNotIn("whatsapp", session.get("pending_confirmations", {}))

    def test_principal_do_telegram_e_dono_interativo_com_origem_humana(self):
        with self._contexto(EstadoAutonomia.ATIVO) as (
            resultado, session, mock_save_session, mock_send, mock_registrar, mock_schedule,
        ):
            pass
        request_avaliado = mock_registrar.call_args.args[1]
        principal = request_avaliado.principal
        self.assertEqual(principal.uid, "dono-uid")
        self.assertEqual(principal.tipo.value, "dono_interativo")
        self.assertEqual(principal.canal, "telegram")
        self.assertIs(principal.origem_humana, True)
        self.assertTrue(principal.eh_dono())

    def test_decisao_do_piso_usa_os_argumentos_pendentes_resolvidos(self):
        # `pending` (contact_number/message/scheduled_time) é o que chega
        # como `argumentos_resolvidos` — mesmo pedido que de fato seria
        # enviado, não um placeholder vazio.
        with self._contexto(EstadoAutonomia.ATIVO) as (
            resultado, session, mock_save_session, mock_send, mock_registrar, mock_schedule,
        ):
            pass
        request_avaliado = mock_registrar.call_args.args[1]
        self.assertEqual(
            request_avaliado.argumentos_resolvidos.get("contact_number"), "+5511999999999",
        )

    def test_sem_pending_nao_chama_motor_de_politica(self):
        # Regressão: o ramo "sem pendência" (já existente, inalterado) não
        # deve nem tentar consultar a política.
        session_vazia = {"chat_id": "123456", "userId": "dono-uid"}
        with self._contexto(EstadoAutonomia.ATIVO, session=session_vazia) as (
            resultado, session, mock_save_session, mock_send, mock_registrar, mock_schedule,
        ):
            pass
        mock_registrar.assert_not_called()
        mock_schedule.assert_not_called()
        texto = mock_send.call_args.args[2]
        self.assertIn("Nenhuma mensagem de WhatsApp pendente", texto)


if __name__ == "__main__":
    unittest.main()
