"""P03 sub-entrega 3/N: normalizador de resultados legados.

`mcp_server._handle_tools_call` deriva `is_error` de duas formas apenas:
`bool(result.get("erro"))` para dict, ou `_looks_like_error(result)` (prefixo
`ERRO|`/`⚠️`) para string. Uma auditoria de todos os 105 tools MCP (3 agentes
independentes, em paralelo) achou 21 pontos de falha reais que essa checagem
não reconhecia -- o cliente MCP via `isError=False` para chamadas que, na
prática, falharam.

Cada teste abaixo força o mesmo ramo de falha que a auditoria encontrou, e
prova que o retorno agora é reconhecido como erro pelo MESMO critério que
`_handle_tools_call` usa -- não só que o texto interno mudou.
"""

import unittest
from unittest.mock import MagicMock, patch

import mcp_server
from tools import hermes_tools
from tools.tool_context import ToolContext


def _erro_reconhecido(resultado) -> bool:
    """Réplica exata do critério de `mcp_server._handle_tools_call` (linha
    ~1137): `.get("erro")` para dict, `_looks_like_error` para string."""
    if isinstance(resultado, dict):
        return bool(resultado.get("erro"))
    return mcp_server._looks_like_error(resultado)


def _ctx(**kw) -> ToolContext:
    kw.setdefault("_db", MagicMock())
    return ToolContext(**kw)


class TestHermesToolsStringsDeErro(unittest.TestCase):
    """Handlers de `tools/hermes_tools.py` que devolvem string de erro."""

    def test_consultar_lista_compras_filtro_invalido(self):
        from tools import lista_compras

        with patch.object(
            lista_compras, "consultar",
            side_effect=lista_compras.ListaComprasError("filtro_invalido", "Filtro desconhecido."),
        ):
            r = hermes_tools._consultar_lista_compras(_ctx(), {"filtro": "xyz"})
        self.assertTrue(_erro_reconhecido(r))
        self.assertIn("Filtro desconhecido.", r)

    def test_consultar_agenda_nao_configurada(self):
        with patch("main.get_calendar_service", return_value=None), \
             patch("main.get_sync_calendar_ids", return_value=[]):
            r = hermes_tools._consultar_agenda(_ctx(), {})
        self.assertTrue(_erro_reconhecido(r))
        self.assertIn("Google Calendar nao configurado", r)

    def test_consultar_agenda_excecao(self):
        with patch("main.get_calendar_service", side_effect=RuntimeError("timeout googleapi")):
            r = hermes_tools._consultar_agenda(_ctx(), {})
        self.assertTrue(_erro_reconhecido(r))
        self.assertIn("timeout googleapi", r)
        self.assertIn("NAO trate isto como agenda vazia", r)

    def test_encontrar_slot_livre_nao_configurada(self):
        with patch("main.get_calendar_service", return_value=None), \
             patch("main.get_sync_calendar_ids", return_value=[]):
            r = hermes_tools._encontrar_slot_livre(_ctx(), {})
        self.assertTrue(_erro_reconhecido(r))
        self.assertIn("Google Calendar nao configurado", r)

    def test_encontrar_slot_livre_excecao(self):
        """2a lacuna de pipe nesta função, achada na implementação -- o
        agente de auditoria só sinalizou o ramo "não configurada" acima."""
        with patch("main.get_calendar_service", side_effect=RuntimeError("api indisponivel")):
            r = hermes_tools._encontrar_slot_livre(_ctx(), {})
        self.assertTrue(_erro_reconhecido(r))
        self.assertIn("api indisponivel", r)
        self.assertIn("NAO trate isto como", r)

    def test_consultar_saude_excecao(self):
        with patch("health_tools.build_health_summary", side_effect=RuntimeError("firestore indisponivel")):
            r = hermes_tools._consultar_saude(_ctx(), {})
        self.assertTrue(_erro_reconhecido(r))
        self.assertIn("firestore indisponivel", r)

    def test_consultar_dados_cadastrais_chave_error_em_ingles(self):
        """`dados_cadastrais.get_dados_cadastrais` sinaliza falha com "error"
        (inglês, dentro do dict); o wrapper MCP precisa traduzir para o
        prefixo `ERRO|` porque a função sempre serializa o dict para string
        antes de devolver -- a chave nunca chegava a ser vista crua."""
        with patch("dados_cadastrais.get_dados_cadastrais", return_value={"error": "secao_invalida"}):
            r = hermes_tools._consultar_dados_cadastrais(_ctx(), {"secao": "x"})
        self.assertTrue(_erro_reconhecido(r))
        self.assertIn("secao_invalida", r)

    def test_consultar_dados_cadastrais_excecao(self):
        with patch("dados_cadastrais.get_dados_cadastrais", side_effect=RuntimeError("boom")):
            r = hermes_tools._consultar_dados_cadastrais(_ctx(), {})
        self.assertTrue(_erro_reconhecido(r))

    def test_consultar_dados_cadastrais_sucesso_nao_marca_erro(self):
        """Contraprova: sem a chave 'error', o resultado passa raso."""
        with patch("dados_cadastrais.get_dados_cadastrais", return_value={"nome": "André"}):
            r = hermes_tools._consultar_dados_cadastrais(_ctx(), {})
        self.assertFalse(_erro_reconhecido(r))

    def test_buscar_e_analisar_email_excecao(self):
        # `tools.buscar_e_analisar_email` depende de `html2text`, ausente
        # neste sandbox -- o próprio `ModuleNotFoundError` do import (dentro
        # do try/except da função) já exercita o ramo de exceção real, sem
        # precisar simular outra falha.
        r = hermes_tools._buscar_e_analisar_email(_ctx(), {"query": "fatura"})
        self.assertTrue(_erro_reconhecido(r))
        self.assertTrue(r.startswith("ERRO|Erro: "))

    def test_salvar_memoria_global_excecao(self):
        with patch("main._classify_memory_candidate", side_effect=RuntimeError("gemini fora do ar")):
            r = hermes_tools._salvar_memoria_global(
                _ctx(_gemini_key="k"), {"fato": "x", "categoria": "y"})
        self.assertTrue(_erro_reconhecido(r))
        self.assertIn("gemini fora do ar", r)


class TestPesquisarInternetELerPaginaWeb(unittest.TestCase):
    """3 retornos de erro em cada função -- strings com forma de JSON (chave
    "error", inglês) mas sem o prefixo `ERRO|` que o dispatch MCP reconhece."""

    def test_pesquisar_internet_sem_tavily_key(self):
        doc = MagicMock(exists=True)
        doc.to_dict.return_value = {}
        with patch("main._cached_doc_get", return_value=doc):
            r = hermes_tools.pesquisar_internet(_ctx(), {"query": "clima"})
        self.assertTrue(_erro_reconhecido(r))

    def test_pesquisar_internet_timeout(self):
        import requests

        doc = MagicMock(exists=True)
        doc.to_dict.return_value = {"tavily_api_key": "k"}
        with patch("main._cached_doc_get", return_value=doc), \
             patch("requests.post", side_effect=requests.exceptions.Timeout()):
            r = hermes_tools.pesquisar_internet(_ctx(), {"query": "clima"})
        self.assertTrue(_erro_reconhecido(r))

    def test_pesquisar_internet_falha_generica(self):
        doc = MagicMock(exists=True)
        doc.to_dict.return_value = {"tavily_api_key": "k"}
        with patch("main._cached_doc_get", return_value=doc), \
             patch("requests.post", side_effect=RuntimeError("dns falhou")):
            r = hermes_tools.pesquisar_internet(_ctx(), {"query": "clima"})
        self.assertTrue(_erro_reconhecido(r))
        self.assertIn("dns falhou", r)

    def test_ler_pagina_web_bloqueada(self):
        resp = MagicMock(status_code=403)
        with patch("requests.get", return_value=resp):
            r = hermes_tools.ler_pagina_web(_ctx(), {"url": "https://x.com"})
        self.assertTrue(_erro_reconhecido(r))

    def test_ler_pagina_web_timeout(self):
        import requests

        with patch("requests.get", side_effect=requests.exceptions.Timeout()):
            r = hermes_tools.ler_pagina_web(_ctx(), {"url": "https://x.com"})
        self.assertTrue(_erro_reconhecido(r))

    def test_ler_pagina_web_falha_generica(self):
        with patch("requests.get", side_effect=RuntimeError("conexao recusada")):
            r = hermes_tools.ler_pagina_web(_ctx(), {"url": "https://x.com"})
        self.assertTrue(_erro_reconhecido(r))
        self.assertIn("conexao recusada", r)


class TestWrappersAditivos(unittest.TestCase):
    """`_strategy` e `_via_callable`: a correção só ADICIONA a chave "erro"
    quando ausente -- "status"/"reason"/"message" têm de sobreviver
    intactas, porque outros consumidores (UI web, chamadores diretos de
    `strategy_tools`) dependem delas com o shape original."""

    def test_strategy_adiciona_erro_preservando_status_e_reason(self):
        import strategy_tools

        with patch.object(
            strategy_tools, "criar_objetivo_estrategico",
            return_value={"status": "error", "reason": "titulo_obrigatorio"},
        ):
            r = hermes_tools._strategy("criar_objetivo_estrategico")(_ctx(), {"titulo": ""})
        self.assertTrue(_erro_reconhecido(r))
        self.assertEqual(r["status"], "error")
        self.assertEqual(r["reason"], "titulo_obrigatorio")
        self.assertEqual(r["erro"], "titulo_obrigatorio")

    def test_strategy_nao_sobrescreve_erro_ja_presente(self):
        import strategy_tools

        with patch.object(
            strategy_tools, "editar_objetivo_estrategico",
            return_value={"status": "error", "reason": "x", "erro": "mensagem original"},
        ):
            r = hermes_tools._strategy("editar_objetivo_estrategico")(_ctx(), {})
        self.assertEqual(r["erro"], "mensagem original")

    def test_strategy_sucesso_passa_intacto(self):
        import strategy_tools

        with patch.object(
            strategy_tools, "gerenciar_item_estrategico",
            return_value={"status": "ok", "item_id": "abc"},
        ):
            r = hermes_tools._strategy("gerenciar_item_estrategico")(_ctx(), {})
        self.assertFalse(_erro_reconhecido(r))
        self.assertNotIn("erro", r)

    def test_strategy_reason_vazio_ainda_produz_erro_nao_vazio(self):
        """Achado da revisão adversarial desta sub-entrega: `.get("reason",
        default)` só cai no default quando a chave está AUSENTE -- um
        "reason" presente mas None/"" reintroduziria a mesma falha
        (mcp_server lê `bool(erro)` como False) que esta correção existe
        para fechar. Trocado por `or`."""
        import strategy_tools

        with patch.object(
            strategy_tools, "excluir_objetivo_estrategico",
            return_value={"status": "error", "reason": None},
        ):
            r = hermes_tools._strategy("excluir_objetivo_estrategico")(_ctx(), {})
        self.assertTrue(_erro_reconhecido(r))
        self.assertTrue(r["erro"])

    def test_via_callable_adiciona_erro_preservando_status_e_message(self):
        with patch(
            "tools.callable_bridge.invoke_callable",
            return_value={"status": "invalidated", "message": "Acao ja concluida."},
        ):
            r = hermes_tools._via_callable("confirmarEdicaoAcao")(_ctx(), {"task_id": "abc"})
        self.assertTrue(_erro_reconhecido(r))
        self.assertEqual(r["status"], "invalidated")
        self.assertEqual(r["message"], "Acao ja concluida.")
        self.assertEqual(r["erro"], "Acao ja concluida.")

    def test_via_callable_sucesso_passa_intacto(self):
        with patch(
            "tools.callable_bridge.invoke_callable",
            return_value={"success": True, "taskId": "abc"},
        ):
            r = hermes_tools._via_callable("confirmarEdicaoAcao")(_ctx(), {"task_id": "abc"})
        self.assertFalse(_erro_reconhecido(r))
        self.assertNotIn("erro", r)

    def test_via_callable_message_vazia_ainda_produz_erro_nao_vazio(self):
        """Mesmo achado da revisão adversarial, para `_via_callable`."""
        with patch(
            "tools.callable_bridge.invoke_callable",
            return_value={"status": "invalidated", "message": ""},
        ):
            r = hermes_tools._via_callable("confirmarEdicaoAcao")(_ctx(), {"task_id": "abc"})
        self.assertTrue(_erro_reconhecido(r))
        self.assertTrue(r["erro"])


class _Snap:
    def __init__(self, exists=False, data=None):
        self.exists = exists
        self._data = data or {}

    def to_dict(self):
        return dict(self._data)


class _Ref:
    def __init__(self, snap=None):
        self._snap = snap or _Snap()

    def get(self):
        return self._snap


class _Collection:
    def document(self, ident=None):
        return _Ref()

    def where(self, *a, **k):
        return self

    def stream(self):
        return []


class _Db:
    def collection(self, name):
        return _Collection()


class TestTelegramExtended(unittest.TestCase):
    """9 pontos de retorno de erro em `tools/telegram_extended.py::execute`,
    todos strings (planas ou com forma de JSON) sem o prefixo `ERRO|` antes
    desta correção. O fake de Firestore abaixo devolve sempre `exists=False`
    e coleções vazias -- suficiente para cada um dos ramos de falha, que
    nunca dependem de um documento realmente existir."""

    def test_obter_contexto_tela_tarefa_nao_encontrada(self):
        from tools import telegram_extended

        r = telegram_extended.execute("obter_contexto_tela", {"task_id": "abc"}, _Db())
        self.assertTrue(_erro_reconhecido(r))

    def test_salvar_pop_global_sem_titulo(self):
        from tools import telegram_extended

        r = telegram_extended.execute("salvar_pop_global", {}, _Db())
        self.assertTrue(_erro_reconhecido(r))

    def test_salvar_pop_global_sem_instrucao(self):
        from tools import telegram_extended

        r = telegram_extended.execute("salvar_pop_global", {"titulo": "x"}, _Db())
        self.assertTrue(_erro_reconhecido(r))

    def test_salvar_pop_global_sem_gatilhos(self):
        from tools import telegram_extended

        r = telegram_extended.execute(
            "salvar_pop_global", {"titulo": "x", "instrucao_sistema": "y"}, _Db())
        self.assertTrue(_erro_reconhecido(r))

    def test_resolver_conflito_memoria_decisao_invalida(self):
        from tools import telegram_extended

        r = telegram_extended.execute(
            "resolver_conflito_memoria", {"memoria_id": "m1", "decisao": "invalida"}, _Db())
        self.assertTrue(_erro_reconhecido(r))

    def test_registrar_transacao_financeira_sem_descricao(self):
        from tools import telegram_extended

        r = telegram_extended.execute(
            "registrar_transacao_financeira_publica", {"description": "", "amount": 10}, _Db())
        self.assertTrue(_erro_reconhecido(r))

    def test_mutar_portal_compras_sem_item_id(self):
        from tools import telegram_extended

        r = telegram_extended.execute(
            "mutar_portal_compras_publico", {"action": "toggle_planned"}, _Db())
        self.assertTrue(_erro_reconhecido(r))

    def test_mutar_portal_compras_item_nao_encontrado(self):
        from tools import telegram_extended

        r = telegram_extended.execute(
            "mutar_portal_compras_publico", {"action": "toggle_planned", "item_id": "x"}, _Db())
        self.assertTrue(_erro_reconhecido(r))

    def test_mutar_portal_compras_acao_invalida(self):
        from tools import telegram_extended

        r = telegram_extended.execute("mutar_portal_compras_publico", {"action": "voar"}, _Db())
        self.assertTrue(_erro_reconhecido(r))

    def test_mutar_lista_compras_erro_de_dominio(self):
        from tools import lista_compras, telegram_extended

        with patch.object(
            lista_compras, "mutar",
            side_effect=lista_compras.ListaComprasError("item_invalido", "Item nao existe."),
        ):
            r = telegram_extended.execute("mutar_lista_compras", {"action": "add"}, _Db())
        self.assertTrue(_erro_reconhecido(r))
        self.assertIn("Item nao existe.", r)

    def test_obter_projeto_bolsas_sem_project_id(self):
        from tools import telegram_extended

        r = telegram_extended.execute("obter_projeto_bolsas_publico", {}, _Db())
        self.assertTrue(_erro_reconhecido(r))

    def test_obter_projeto_bolsas_nao_encontrado(self):
        from tools import telegram_extended

        r = telegram_extended.execute(
            "obter_projeto_bolsas_publico", {"project_id": "p1"}, _Db())
        self.assertTrue(_erro_reconhecido(r))

    def test_registrar_inscricao_bolsa_dados_invalidos(self):
        from tools import telegram_extended

        r = telegram_extended.execute("registrar_inscricao_bolsa_publica", {}, _Db())
        self.assertTrue(_erro_reconhecido(r))

    def test_registrar_inscricao_bolsa_campos_ausentes(self):
        from tools import telegram_extended

        r = telegram_extended.execute(
            "registrar_inscricao_bolsa_publica",
            {"project_id": "p1", "formData": {"nome": "A"}}, _Db())
        self.assertTrue(_erro_reconhecido(r))

    def test_registrar_inscricao_bolsa_projeto_nao_encontrado(self):
        from tools import telegram_extended

        form = {"nome": "A", "cpf": "1", "rg": "2", "email": "a@x.com", "telefone": "1"}
        r = telegram_extended.execute(
            "registrar_inscricao_bolsa_publica", {"project_id": "p1", "formData": form}, _Db())
        self.assertTrue(_erro_reconhecido(r))

    def test_registrar_item_financeiro_tipo_invalido(self):
        from tools import telegram_extended

        r = telegram_extended.execute(
            "registrar_item_financeiro_v2", {"tipo": "tipo_que_nao_existe"}, _Db())
        self.assertTrue(_erro_reconhecido(r))


if __name__ == "__main__":
    unittest.main()
