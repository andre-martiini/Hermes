"""Callbacks `confirm_memoria_manter`/`confirm_memoria_substituir` do
Telegram (P06 sub-entrega 3/N, docs/plano-hermes-autonomo-2026-09-06.md).

Contexto: a P06 sub-entrega 2/N adicionou o closure `resolver_conflito_memoria`
(telegram_message_tools.py) para o motor Telegram legado resolver um status
"conflict" devolvido por `main._save_memory_node` -- mas documentou uma
LIMITAÇÃO CONHECIDA, NÃO RESOLVIDA: o `memoria_id` que o MODELO precisaria
repassar àquele closure numa 2ª chamada de ferramenta não sobrevivia ao fim
do turno (`telegram_handlers_core.py` só persiste o TEXTO final de cada
turno no histórico da sessão, nunca as partes de function-call/response).

Esta sub-entrega fecha essa limitação pelo mesmo caminho já usado por
`confirm_financeiro`/`confirm_acao`/`confirm_whatsapp`: `salvar_memoria_global`
(telegram_message_tools.py) agora grava o conflito em
`session["pending_confirmations"]["memoria_conflito"]` quando
`_save_memory_node` devolve "conflict" (coberto em
`test_telegram_salvar_memoria_global.py::TestTelegramSalvarMemoriaGlobalConflitoGravaPendingConfirmations`,
não aqui), e dois botões inline (`_CONFIRM_MEMORIA_KEYBOARD`,
telegram_utils.py) resolvem direto pela sessão, sem depender do modelo
carregar nenhum ID entre turnos.

Mesma técnica de `test_wa_outbox_manual_confirmation.py`: chama
`telegram_callbacks_confirmacoes.handle(...)` diretamente (não via
`_handle_telegram_callback`), com um `db` mockado e mockando só a fronteira
de I/O (`tools.telegram_extended.execute`, `_answer_callback_query`,
`_send_telegram_message`, `_save_session`) -- a lógica de resolução de
conflito em si (`tools/telegram_extended.py::execute("resolver_conflito_memoria",
...)`) já é testada em
`test_telegram_extended.py::TestResolverConflitoMemoriaIdempotente` (P03
sub-entrega 19/N) e não é reimplementada aqui.
"""
import unittest
from unittest.mock import MagicMock, patch

import telegram_callbacks_confirmacoes as tcc


def _session_com_pending_memoria(**overrides):
    # "categoria" (fato novo, proposto) e "categoria_existente" (fato que
    # SERIA mantido) propositalmente diferentes -- cobre o achado real de
    # revisão adversarial independente desta sub-entrega sobre os dois
    # campos poderem ser trocados entre si sem nenhum teste detectar.
    pending = {
        "memory_id": "mem-existente-1",
        "fato_atualizado": "André prefere almoçar depois das 13h30.",
        "categoria": "preferencia",
        "categoria_existente": "fato_isolado",
        "existing_text": "André prefere almoçar depois das 13h.",
    }
    pending.update(overrides)
    return {
        "chat_id": "123456",
        "pending_confirmations": {"memoria_conflito": pending},
        "_pending_confirm_type": "memoria_conflito",
    }


class _CallbackTestBase(unittest.TestCase):
    def _chamar(self, data, session, save_session_side_effect=None):
        db = MagicMock()
        with patch.object(tcc, "_answer_callback_query") as mock_answer, \
             patch.object(tcc, "_send_telegram_message") as mock_send, \
             patch.object(tcc, "_save_session", side_effect=save_session_side_effect) as mock_save:
            tratado = tcc.handle(
                db, "fake-token", "q1", "123456", data,
                message={"message_id": 1}, session=session, copilot_session_id="cs1",
                _persist_callback_turn=MagicMock(),
                _pending_web_card=MagicMock(), _clear_pending_web_card=MagicMock(),
            )
        return tratado, db, mock_answer, mock_send, mock_save


class TestConfirmMemoriaManter(_CallbackTestBase):
    def test_delega_para_execute_com_decisao_manter_existente(self):
        session = _session_com_pending_memoria()
        with patch("tools.telegram_extended.execute") as mock_execute:
            mock_execute.return_value = '{"status": "resolved", "decision": "kept_existing"}'
            tratado, db, mock_answer, mock_send, mock_save = self._chamar(
                "confirm_memoria_manter", session
            )

        self.assertTrue(tratado)
        mock_execute.assert_called_once_with(
            "resolver_conflito_memoria",
            {
                "memoria_id": "mem-existente-1",
                "decisao": "manter_existente",
                "fato_atualizado": "",
                # A categoria do fato EXISTENTE (mantido), nunca a do fato
                # novo descartado -- achado real de revisão adversarial
                # independente desta sub-entrega.
                "categoria": "fato_isolado",
            },
            db,
        )

    def test_limpa_a_pendencia_apos_resolver(self):
        session = _session_com_pending_memoria()
        with patch("tools.telegram_extended.execute", return_value='{"status": "resolved"}'):
            self._chamar("confirm_memoria_manter", session)

        self.assertNotIn("memoria_conflito", session.get("pending_confirmations", {}))
        self.assertNotIn("_pending_confirm_type", session)

    def test_texto_enviado_mostra_o_fato_mantido_e_o_descartado(self):
        session = _session_com_pending_memoria()
        with patch("tools.telegram_extended.execute", return_value='{"status": "resolved"}'):
            _, _, _, mock_send, _ = self._chamar("confirm_memoria_manter", session)

        texto = mock_send.call_args.args[2]
        self.assertIn("mantido", texto.lower())
        self.assertIn("André prefere almoçar depois das 13h.", texto)
        self.assertIn("André prefere almoçar depois das 13h30.", texto)

    def test_sem_pendencia_nao_chama_execute_e_avisa_usuario(self):
        session = {"chat_id": "123456"}
        with patch("tools.telegram_extended.execute") as mock_execute:
            tratado, _, _, mock_send, _ = self._chamar("confirm_memoria_manter", session)

        self.assertTrue(tratado)
        mock_execute.assert_not_called()
        texto = mock_send.call_args.args[2]
        self.assertIn("Nenhum conflito de memória pendente", texto)

    def test_excecao_de_execute_nao_propaga_e_informa_erro(self):
        session = _session_com_pending_memoria()
        with patch("tools.telegram_extended.execute", side_effect=RuntimeError("Firestore indisponível")):
            tratado, _, _, mock_send, mock_save = self._chamar("confirm_memoria_manter", session)

        self.assertTrue(tratado)
        texto = mock_send.call_args.args[2]
        self.assertIn("Erro ao resolver conflito de memória", texto)
        self.assertIn("Firestore indisponível", texto)
        # Exceção durante a resolução não deve limpar a pendência -- o
        # usuário pode tentar de novo tocando no botão (mesma postura de
        # confirm_financeiro/confirm_acao: só limpa a pendência no caminho
        # feliz).
        self.assertIn("memoria_conflito", session.get("pending_confirmations", {}))

    def test_falha_ao_salvar_sessao_apos_resolver_com_sucesso_nao_e_reportada_como_erro(self):
        """Achado real de revisão adversarial independente desta
        sub-entrega: `execute(...)` e a limpeza/`_save_session` viviam no
        MESMO `try`, então uma falha ao salvar a sessão (depois do
        conflito já ter sido resolvido de verdade no Firestore) era
        reportada ao usuário como "❌ Erro ao resolver conflito de
        memória" -- uma mensagem FALSA, já que a resolução em si teve
        sucesso. Agora as duas etapas são separadas."""
        session = _session_com_pending_memoria()
        with patch("tools.telegram_extended.execute", return_value='{"status": "resolved"}'):
            tratado, _, _, mock_send, _ = self._chamar(
                "confirm_memoria_manter", session,
                save_session_side_effect=RuntimeError("Firestore indisponível"),
            )

        self.assertTrue(tratado)
        texto = mock_send.call_args.args[2]
        self.assertNotIn("Erro ao resolver conflito de memória", texto)
        self.assertIn("mantido", texto.lower())
        self.assertIn("problema ao atualizar a sessão", texto)

    def test_status_error_sem_excecao_nao_e_reportado_como_sucesso(self):
        """Achado real de uma 2ª rodada de revisão adversarial
        independente: `execute(...)` pode devolver um JSON com
        `status != "resolved"/"updated"` SEM lançar excecão Python -- o
        try/except em volta da chamada, sozinho, não detecta isso. Sem
        este check, o botão reportaria sucesso falso ao usuário e ainda
        limparia a pendência, perdendo a chance de tentar de novo."""
        session = _session_com_pending_memoria()
        with patch("tools.telegram_extended.execute", return_value='{"status": "error", "reason": "memory_not_found"}'):
            tratado, _, _, mock_send, _ = self._chamar("confirm_memoria_manter", session)

        self.assertTrue(tratado)
        texto = mock_send.call_args.args[2]
        self.assertNotIn("mantido", texto.lower())
        self.assertIn("Não foi possível resolver", texto)
        self.assertIn("memoria_conflito", session.get("pending_confirmations", {}))


class TestConfirmMemoriaSubstituir(_CallbackTestBase):
    def test_delega_para_execute_com_decisao_substituir_pelo_novo(self):
        session = _session_com_pending_memoria()
        with patch("tools.telegram_extended.execute") as mock_execute:
            mock_execute.return_value = '{"status": "updated", "decision": "replaced_existing"}'
            tratado, db, _, _, _ = self._chamar("confirm_memoria_substituir", session)

        self.assertTrue(tratado)
        mock_execute.assert_called_once_with(
            "resolver_conflito_memoria",
            {
                "memoria_id": "mem-existente-1",
                "decisao": "substituir_pelo_novo",
                "fato_atualizado": "André prefere almoçar depois das 13h30.",
                "categoria": "preferencia",
            },
            db,
        )

    def test_limpa_a_pendencia_apos_resolver(self):
        session = _session_com_pending_memoria()
        # "updated" -- status real que `execute(...)` devolve para
        # "substituir_pelo_novo" (propagado de
        # `main._save_memory_node(force_update_id=...)`), nunca "resolved"
        # (achado real de 2ª rodada de revisão adversarial).
        with patch("tools.telegram_extended.execute", return_value='{"status": "updated"}'):
            self._chamar("confirm_memoria_substituir", session)

        self.assertNotIn("memoria_conflito", session.get("pending_confirmations", {}))
        self.assertNotIn("_pending_confirm_type", session)

    def test_texto_enviado_mostra_o_novo_texto_e_o_anterior(self):
        session = _session_com_pending_memoria()
        with patch("tools.telegram_extended.execute", return_value='{"status": "updated"}'):
            _, _, _, mock_send, _ = self._chamar("confirm_memoria_substituir", session)

        texto = mock_send.call_args.args[2]
        self.assertIn("atualizada", texto.lower())
        self.assertIn("André prefere almoçar depois das 13h30.", texto)
        self.assertIn("André prefere almoçar depois das 13h.", texto)

    def test_sem_pendencia_nao_chama_execute_e_avisa_usuario(self):
        session = {"chat_id": "123456"}
        with patch("tools.telegram_extended.execute") as mock_execute:
            tratado, _, _, mock_send, _ = self._chamar("confirm_memoria_substituir", session)

        self.assertTrue(tratado)
        mock_execute.assert_not_called()
        texto = mock_send.call_args.args[2]
        self.assertIn("Nenhum conflito de memória pendente", texto)

    def test_excecao_de_execute_nao_propaga_e_informa_erro(self):
        session = _session_com_pending_memoria()
        with patch("tools.telegram_extended.execute", side_effect=RuntimeError("Firestore indisponível")):
            tratado, _, _, mock_send, _ = self._chamar("confirm_memoria_substituir", session)

        self.assertTrue(tratado)
        texto = mock_send.call_args.args[2]
        self.assertIn("Erro ao resolver conflito de memória", texto)
        self.assertIn("memoria_conflito", session.get("pending_confirmations", {}))

    def test_falha_ao_salvar_sessao_apos_resolver_com_sucesso_nao_e_reportada_como_erro(self):
        session = _session_com_pending_memoria()
        with patch("tools.telegram_extended.execute", return_value='{"status": "updated"}'):
            tratado, _, _, mock_send, _ = self._chamar(
                "confirm_memoria_substituir", session,
                save_session_side_effect=RuntimeError("Firestore indisponível"),
            )

        self.assertTrue(tratado)
        texto = mock_send.call_args.args[2]
        self.assertNotIn("Erro ao resolver conflito de memória", texto)
        self.assertIn("atualizada", texto.lower())
        self.assertIn("problema ao atualizar a sessão", texto)

    def test_status_error_sem_excecao_nao_e_reportado_como_sucesso(self):
        """Mesmo achado de TestConfirmMemoriaManter acima, neste ramo é o
        cenário mais plausível na prática: `memory_not_found` (nó apagado/
        alterado entre a detecção do conflito e o toque no botão) é um
        erro de NEGÓCIO de `main._save_memory_node(force_update_id=...)`,
        devolvido sem excecão Python."""
        session = _session_com_pending_memoria()
        with patch("tools.telegram_extended.execute", return_value='{"status": "error", "reason": "memory_not_found"}'):
            tratado, _, _, mock_send, _ = self._chamar("confirm_memoria_substituir", session)

        self.assertTrue(tratado)
        texto = mock_send.call_args.args[2]
        self.assertNotIn("atualizada", texto.lower())
        self.assertIn("Não foi possível resolver", texto)
        self.assertIn("memoria_conflito", session.get("pending_confirmations", {}))


class TestInlineKeyboardAnexado(unittest.TestCase):
    """`telegram_handlers_core.py` decide qual teclado inline anexar com
    base em `_pending_confirm_type` -- confirma que "memoria_conflito"
    resolve para `_CONFIRM_MEMORIA_KEYBOARD`, o mesmo teclado cujos
    `callback_data` os testes acima exercitam (sem isso, os botões
    poderiam nunca aparecer para o usuário tocar)."""

    def test_memoria_conflito_resolve_para_confirm_memoria_keyboard(self):
        import telegram_utils

        callback_datas = {
            botao["callback_data"]
            for linha in telegram_utils._CONFIRM_MEMORIA_KEYBOARD
            for botao in linha
        }
        self.assertEqual(callback_datas, {"confirm_memoria_manter", "confirm_memoria_substituir"})


if __name__ == "__main__":
    unittest.main()
