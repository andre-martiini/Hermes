"""Testes para P06 sub-entrega 4/N (docs/plano-hermes-autonomo-2026-09-06.md,
pacote P06, passo 3 / achado A07): o sinal de atividade operacional das
chamadas de tool do canal MCP passa a gravar em `ai_profile.atividade_operacional`
(`mcp_signals.py::salvar_atividade_operacional`), trilha separada de
`historico_deduzido` — reservado ao que o usuário de fato declarou via
`askCopilotoHermes` (`main.py::_save_user_profile_signal`, não tocado por esta
sub-entrega).

`salvar_atividade_operacional` vive em mcp_signals.py (não em main.py) por
limite operacional do pipeline de escrita no repositório: main.py tem ~729.000
caracteres, acima do teto de 200.000 por escrita de
`argos_escrever_arquivo_repositorio` (sempre do arquivo inteiro, não é patch)
-- ver docstring do módulo mcp_signals para o detalhe.

`test_auditoria_mcp.py::TestGravaSoNaNuvem.test_sinal_de_intencao_nao_grava_fora_da_nuvem`
já cobre o bloqueio de gravação fora da nuvem; não duplicado aqui.
"""

import os
import unittest
from unittest import mock

NA_NUVEM = {"K_SERVICE": "mcpserver"}


def _thread_sincrona(target=None, args=(), kwargs=None, daemon=None):
    """Substitui threading.Thread para rodar o alvo na hora, de forma
    síncrona e determinística (sem daemon thread real em teste)."""
    (target or (lambda: None))(*(args or ()), **(kwargs or {}))
    return mock.Mock()


class TestRegistrarUsaTrilhaOperacionalPropria(unittest.TestCase):
    def test_registrar_chama_salvar_atividade_operacional(self):
        import mcp_signals

        db = mock.MagicMock()
        with mock.patch.dict(os.environ, NA_NUVEM), \
                mock.patch("firebase_admin.firestore.client", return_value=db), \
                mock.patch("mcp_signals.threading.Thread", side_effect=_thread_sincrona), \
                mock.patch("mcp_signals.salvar_atividade_operacional") as save_mock:
            mcp_signals.registrar("uid-1", "buscar_arquivos_acervo", {"query": "contrato 2026"}, "task-9")

        save_mock.assert_called_once_with(db, "uid-1", "buscou no acervo: contrato 2026", "task-9", None)

    def test_registrar_nunca_chama_save_user_profile_signal_humano(self):
        """A trilha de declaração humana (historico_deduzido) fica reservada a
        `askCopilotoHermes` — o canal MCP nunca deve escrever nela."""
        import mcp_signals

        db = mock.MagicMock()
        with mock.patch.dict(os.environ, NA_NUVEM), \
                mock.patch("firebase_admin.firestore.client", return_value=db), \
                mock.patch("mcp_signals.threading.Thread", side_effect=_thread_sincrona), \
                mock.patch("main._save_user_profile_signal") as save_humano:
            mcp_signals.registrar("uid-1", "buscar_contato", {"termo": "Joana"}, None)

        save_humano.assert_not_called()

    def test_tool_sem_sinal_nao_grava_nada(self):
        import mcp_signals

        with mock.patch.dict(os.environ, NA_NUVEM), \
                mock.patch("mcp_signals.threading.Thread", side_effect=AssertionError("nao deveria gravar")):
            mcp_signals.registrar("uid-1", "calculadora", {"expressao": "2+2"})


class TestSalvarAtividadeOperacionalSeparadaDoHistoricoHumano(unittest.TestCase):
    def _fake_profile_ref(self, ai_profile_inicial):
        doc_snap = mock.MagicMock()
        doc_snap.to_dict.return_value = {"ai_profile": ai_profile_inicial}
        doc_ref = mock.MagicMock()
        doc_ref.get.return_value = doc_snap
        db = mock.MagicMock()
        db.collection.return_value.document.return_value = doc_ref
        return db, doc_ref

    def test_grava_em_atividade_operacional_sem_tocar_historico_deduzido(self):
        import mcp_signals

        db, doc_ref = self._fake_profile_ref({
            "historico_deduzido": [{"texto": "prefere reunioes de manha", "at": "t0"}],
        })

        mcp_signals.salvar_atividade_operacional(db, "uid-1", "buscou no acervo: contrato 2026", "task-9", None)

        gravado = doc_ref.set.call_args[0][0]["ai_profile"]
        self.assertEqual(gravado["atividade_operacional"][-1]["texto"], "buscou no acervo: contrato 2026")
        self.assertEqual(gravado["atividade_operacional"][-1]["taskId"], "task-9")
        self.assertEqual(
            gravado["historico_deduzido"],
            [{"texto": "prefere reunioes de manha", "at": "t0"}],
        )

    def test_nao_duplica_entrada_identica_consecutiva(self):
        import mcp_signals

        db, doc_ref = self._fake_profile_ref({
            "atividade_operacional": [{"texto": "buscou no acervo: contrato 2026", "at": "t0"}],
        })

        mcp_signals.salvar_atividade_operacional(db, "uid-1", "buscou no acervo: contrato 2026", None, None)

        gravado = doc_ref.set.call_args[0][0]["ai_profile"]
        self.assertEqual(len(gravado["atividade_operacional"]), 1)

    def test_mantem_so_as_10_mais_recentes(self):
        import mcp_signals

        historico = [{"texto": f"buscou {i}", "at": str(i)} for i in range(10)]
        db, doc_ref = self._fake_profile_ref({"atividade_operacional": historico})

        mcp_signals.salvar_atividade_operacional(db, "uid-1", "buscou 10", None, None)

        gravado = doc_ref.set.call_args[0][0]["ai_profile"]
        self.assertEqual(len(gravado["atividade_operacional"]), 10)
        self.assertEqual(gravado["atividade_operacional"][0]["texto"], "buscou 1")
        self.assertEqual(gravado["atividade_operacional"][-1]["texto"], "buscou 10")

    def test_sem_uid_ou_sem_texto_nao_grava(self):
        import mcp_signals

        db = mock.MagicMock()
        mcp_signals.salvar_atividade_operacional(db, None, "buscou algo", None, None)
        mcp_signals.salvar_atividade_operacional(db, "uid-1", "", None, None)
        db.collection.assert_not_called()

    def test_trunca_texto_longo_em_177_chars_mais_reticencias(self):
        import mcp_signals

        db, doc_ref = self._fake_profile_ref({})
        texto_longo = "x" * 250

        mcp_signals.salvar_atividade_operacional(db, "uid-1", texto_longo, None, None)

        gravado = doc_ref.set.call_args[0][0]["ai_profile"]
        salvo = gravado["atividade_operacional"][-1]["texto"]
        self.assertEqual(len(salvo), 180)
        self.assertTrue(salvo.endswith("..."))
        self.assertEqual(salvo, "x" * 177 + "...")

    def test_nao_toca_last_task_id_nem_last_system_id(self):
        """Esses campos pertencem à trilha humana (main.py::_save_user_profile_signal,
        não tocado por esta sub-entrega); a trilha operacional não deve
        sobrescrevê-los -- as duas funções escrevem em threads separadas sobre
        o mesmo doc, e last-write-wins entre elas misturaria as duas trilhas
        outra vez (achado de revisão adversarial da sub-entrega 4/N)."""
        import mcp_signals

        db, doc_ref = self._fake_profile_ref({"last_task_id": "task-humano", "last_system_id": "sistema-humano"})

        mcp_signals.salvar_atividade_operacional(db, "uid-1", "buscou no acervo: X", "task-mcp", "sistema-mcp")

        gravado = doc_ref.set.call_args[0][0]["ai_profile"]
        self.assertEqual(gravado["last_task_id"], "task-humano")
        self.assertEqual(gravado["last_system_id"], "sistema-humano")


class TestVoiceContextSeparaAtividadeDePreferencia(unittest.TestCase):
    def test_format_user_profile_rotula_atividade_separadamente(self):
        import copilot_context

        db = mock.MagicMock()
        snap = mock.MagicMock()
        snap.exists = True
        snap.id = "uid-1"
        snap.to_dict.return_value = {
            "ai_profile": {
                "historico_deduzido": [{"texto": "prefere reunioes de manha", "at": "t0"}],
                "atividade_operacional": [{"texto": "buscou no acervo: contrato 2026", "at": "t1"}],
            }
        }
        db.collection.return_value.document.return_value.get.return_value = snap

        texto = copilot_context._format_user_profile(db, "uid-1")

        self.assertIn("historico_deduzido_recente", texto)
        self.assertIn("atividade_operacional_recente", texto)
        self.assertIn("NAO e preferencia", texto)

    def test_mostra_as_5_mais_recentes_nao_as_5_mais_antigas(self):
        """A lista é gravada com .append() (cronológica crescente); mostrar
        "recente" com `lista[:5]` exibiria as 5 mais ANTIGAS da janela de 10 --
        copilot_context.py já usava `[-5:]` para historico_deduzido antes
        desta sub-entrega, e a seção nova de atividade_operacional segue o
        mesmo padrão correto desde a origem."""
        import copilot_context

        db = mock.MagicMock()
        snap = mock.MagicMock()
        snap.exists = True
        snap.id = "uid-1"
        snap.to_dict.return_value = {
            "ai_profile": {
                "atividade_operacional": [{"texto": f"buscou {i}", "at": str(i)} for i in range(8)],
            }
        }
        db.collection.return_value.document.return_value.get.return_value = snap

        texto = copilot_context._format_user_profile(db, "uid-1")

        linha = next(l for l in texto.splitlines() if l.startswith("- atividade_operacional_recente"))
        self.assertIn("buscou 7", linha)
        self.assertIn("buscou 3", linha)
        self.assertNotIn("buscou 0", linha)
        self.assertNotIn("buscou 2", linha)


if __name__ == "__main__":
    unittest.main()
