"""Testes de `tools/hermes_tools.py::_consultar_saude_integracoes` -- a tool
`consultar_saude_integracoes` da seção 6 do plano de autonomia (P05,
continuação do passo 8). É a wiring de Firestore que os leitores puros de
`autonomy/integrations_sync.py` (P05 sub-entrega 3/N) deliberadamente não
fazem: busca os 4 docs de sync reais em `system/*` e devolve o
`IntegrationHealth` de cada uma das 7 integrações (calendar, contacts,
gmail, whatsapp, sipac, finanças, repositório) como JSON.

Fake Firestore mínimo (mesmo padrão de `test_registrar_saude.py`): só a
coleção `system` é necessária, já que é a única lida por este handler."""

import json
import unittest
from datetime import datetime, timedelta, timezone

from main import CONTACTS_SYNC_STATE_DOC_ID
from tools import hermes_tools
from tools.tool_context import ToolContext

_AGORA = datetime.now(timezone.utc)


class _Snapshot:
    def __init__(self, dados=None):
        self._d = dados

    def to_dict(self):
        return dict(self._d) if self._d else None


class _DocRef:
    def __init__(self, dados=None):
        self._d = dados

    def get(self):
        return _Snapshot(self._d)


class _Colecao:
    def __init__(self, dados=None):
        self.dados = dict(dados or {})

    def document(self, doc_id):
        return _DocRef(self.dados.get(doc_id))


class _Db:
    def __init__(self, system_docs=None):
        self._system = _Colecao(system_docs)

    def collection(self, nome):
        if nome != "system":
            raise AssertionError(f"coleção inesperada: {nome}")
        return self._system


def _ctx(system_docs=None):
    return ToolContext(_db=_Db(system_docs))


class TestConsultarSaudeIntegracoes(unittest.TestCase):
    def test_todos_os_docs_ausentes_reporta_7_integracoes_todas_unknown(self):
        resultado = json.loads(hermes_tools._consultar_saude_integracoes(_ctx(), {}))
        integracoes = {i["integration"]: i for i in resultado["integracoes"]}
        self.assertEqual(
            set(integracoes),
            {"calendar", "contacts", "gmail", "whatsapp", "sipac", "financas", "repositorio"},
        )
        for nome in ("calendar", "contacts", "gmail", "whatsapp", "sipac", "financas", "repositorio"):
            self.assertEqual(integracoes[nome]["status"], "unknown")
            self.assertIsNone(integracoes[nome]["last_success_at"])
            self.assertIsNone(integracoes[nome]["lag_seconds"])
        self.assertIn("heartbeat_at", resultado)

    def test_calendar_saudavel_a_partir_do_doc_real(self):
        recente = (_AGORA - timedelta(minutes=5)).isoformat()
        ctx = _ctx({"sync": {"status": "completed", "last_success": recente}})
        resultado = json.loads(hermes_tools._consultar_saude_integracoes(ctx, {}))
        calendar = next(i for i in resultado["integracoes"] if i["integration"] == "calendar")
        self.assertEqual(calendar["status"], "healthy")
        self.assertIsNotNone(calendar["last_success_at"])
        self.assertIsNone(calendar["error_code"])

    def test_calendar_com_erro_reporta_error_code(self):
        antigo = (_AGORA - timedelta(hours=10)).isoformat()
        ctx = _ctx({"sync": {"status": "error", "last_success": antigo, "error_message": "falhou"}})
        resultado = json.loads(hermes_tools._consultar_saude_integracoes(ctx, {}))
        calendar = next(i for i in resultado["integracoes"] if i["integration"] == "calendar")
        self.assertEqual(calendar["status"], "unavailable")
        self.assertEqual(calendar["error_code"], "falhou")

    def test_contacts_le_o_doc_pelo_id_correto(self):
        recente = (_AGORA - timedelta(hours=1)).isoformat()
        ctx = _ctx({CONTACTS_SYNC_STATE_DOC_ID: {"ultima_execucao": recente}})
        resultado = json.loads(hermes_tools._consultar_saude_integracoes(ctx, {}))
        contacts = next(i for i in resultado["integracoes"] if i["integration"] == "contacts")
        self.assertEqual(contacts["status"], "healthy")

    def test_gmail_degradado_por_frescor(self):
        antigo = (_AGORA - timedelta(hours=10)).isoformat()
        ctx = _ctx({"gmail_sync": {"status": "completed", "last_success": antigo}})
        resultado = json.loads(hermes_tools._consultar_saude_integracoes(ctx, {}))
        gmail = next(i for i in resultado["integracoes"] if i["integration"] == "gmail")
        self.assertIn(gmail["status"], {"degraded", "unavailable"})

    def test_whatsapp_le_cursor_last_processed_at(self):
        recente = _AGORA - timedelta(minutes=10)
        ctx = _ctx({"whatsapp_ingest": {"last_processed_at": recente}})
        resultado = json.loads(hermes_tools._consultar_saude_integracoes(ctx, {}))
        whatsapp = next(i for i in resultado["integracoes"] if i["integration"] == "whatsapp")
        self.assertEqual(whatsapp["status"], "healthy")

    def test_erro_inesperado_devolve_string_erro_com_pipe(self):
        class _DbQuebrado:
            def collection(self, nome):
                raise RuntimeError("firestore fora do ar")

        ctx = ToolContext(_db=_DbQuebrado())
        resultado = hermes_tools._consultar_saude_integracoes(ctx, {})
        self.assertTrue(resultado.startswith("ERRO|"))


if __name__ == "__main__":
    unittest.main()
