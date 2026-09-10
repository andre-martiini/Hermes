"""Testes de `registry.mcp_annotations` e da sua ligação a `tools/list`
(`mcp_server._handle_tools_list`).

P03 passo 3 do plano de autonomia (docs/plano-hermes-autonomo-2026-09-06.md):
"Adicionar outputSchema, structuredContent, annotations e envelope aos
caminhos compatíveis; manter content legado". `readOnlyHint`/
`destructiveHint` vieram da sub-entrega 6/N, derivados com confiança do
inventário tipado da sub-entrega 1/N (`tools/inventory.py`):
`readOnlyHint` de `leitura_escrita`, `destructiveHint` de
`reversibilidade`. `openWorldHint` vem desta sub-entrega (7/N), do campo
`dominio_rede` (`tools/inventory.py::DominioRede`) -- não de
`necessidade_de_rede` direto, ver a docstring de `registry.mcp_annotations`
para o porquê. `idempotentHint` continua deliberadamente fora -- nenhum
campo do inventário atual sustenta esse hint com confiança, e um hint
errado é pior que a omissão, já que a própria especificação MCP já assume o
lado mais cauteloso -- `destructiveHint`/`openWorldHint` default `true` --
para quem não declara `ToolAnnotations`.

Duas frentes:
1. `TestMcpAnnotations` -- a função pura em `tools/registry.py`, incluindo
   paridade com TODAS as 105 entradas reais do inventário (não amostra):
   toda tool leitura pura tem `readOnlyHint=True` e nunca leva
   `destructiveHint`; toda tool de escrita (pura ou mista) tem
   `readOnlyHint=False` e `destructiveHint` correspondendo exatamente à
   `reversibilidade` (`irreversivel`->`True`, `reversivel`/`nao_aplica`->
   `False`); `openWorldHint` correspondendo exatamente a `dominio_rede`
   (`FECHADO`->`False`, `ABERTO`->`True`, `None`->omitido).
2. `TestHandleToolsListAnnotations` -- ponta a ponta via
   `mcp_server._handle_tools_list()`: o campo `annotations` chega no
   catálogo publicado, com os valores corretos para tools reais de cada
   categoria, e nenhuma tool inventada aparece com annotations vazias (o
   campo é omitido, não um dict vazio, quando não há nada a dizer).
"""

from __future__ import annotations

import unittest

import mcp_server
from tools import inventory, registry
from tools.inventory import DominioRede, LeituraEscrita, Reversibilidade


class TestMcpAnnotations(unittest.TestCase):
    def test_tool_inexistente_devolve_dict_vazio(self):
        self.assertEqual(registry.mcp_annotations("tool_que_nao_existe_de_verdade"), {})

    def test_leitura_pura_e_read_only_sem_destructive_hint(self):
        # `consultar_historico_acoes`: leitura, nao_aplica.
        anotacoes = registry.mcp_annotations("consultar_historico_acoes")
        self.assertEqual(anotacoes, {"readOnlyHint": True})
        self.assertNotIn("destructiveHint", anotacoes)

    def test_escrita_irreversivel_e_destructive_hint_true(self):
        # `criar_rascunho_email`: leitura_e_escrita, irreversivel (COMPROMISSO_
        # TERCEIROS -- ver nota em tools/inventory.py). rede_servico="Gmail
        # API" -- dominio_rede=FECHADO (conta do proprio dono).
        self.assertEqual(
            registry.mcp_annotations("criar_rascunho_email"),
            {"readOnlyHint": False, "destructiveHint": True, "openWorldHint": False},
        )

    def test_escrita_reversivel_e_destructive_hint_false(self):
        # `criar_acao_no_sistema`: escrita, reversivel. rede_servico=
        # "Google Calendar (...) + Gemini condicional" -- dominio_rede=
        # FECHADO (agenda do proprio dono + chamada de IA interna).
        self.assertEqual(
            registry.mcp_annotations("criar_acao_no_sistema"),
            {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": False},
        )

    def test_criar_rascunho_whatsapp_e_destructive_hint_true(self):
        # Achado real da revisão adversarial da sub-entrega 6/N: a
        # classificação original de `criar_rascunho_whatsapp` em
        # tools/inventory.py era REVERSIVEL, apesar da própria nota dizer
        # "reversível ... exceto tipos promovidos (liberam sozinhos após a
        # janela)" -- a mesma forma de nuance que `decidir_elevacao`/
        # `decidir_promocao_autonomia` já tratam classificando a tool
        # inteira como IRREVERSIVEL (lado conservador). A classificação
        # antiga produzia destructiveHint=False -- um cliente MCP poderia
        # usar isso para pular confirmação extra, mesmo no caso de risco
        # real (tipo promovido entrega a terceiro sem nova confirmação).
        # Corrigido em tools/inventory.py para IRREVERSIVEL, mesma convenção
        # das outras duas tools. Este teste prova o valor correto chegando
        # em mcp_annotations, não só a classificação bruta do inventário.
        # rede_servico="Telegram Bot API (notifica o dono)" -- dominio_rede=
        # FECHADO (canal fixo e conhecido, não conteúdo externo arbitrário).
        self.assertEqual(
            registry.mcp_annotations("criar_rascunho_whatsapp"),
            {"readOnlyHint": False, "destructiveHint": True, "openWorldHint": False},
        )

    def test_leitura_e_escrita_com_efeito_colateral_passivo_e_destructive_hint_false(self):
        # As 3 tools leitura_e_escrita/nao_aplica (escrita e efeito colateral
        # passivo ou idempotente, nunca o propósito da tool -- ver nota de
        # cada uma em tools/inventory.py): tratadas como não-destrutivas,
        # não como um terceiro valor especial.
        for nome in (
            "consultar_autorizacao_argos",
            "consultar_contatos_prioritarios_secretario",
            "consultar_investimentos",
        ):
            with self.subTest(tool=nome):
                self.assertEqual(
                    registry.mcp_annotations(nome),
                    {"readOnlyHint": False, "destructiveHint": False},
                )

    def test_annotations_nunca_leva_idempotent_hint(self):
        # idempotentHint continua inteiramente fora de escopo (ver docstring
        # de registry.mcp_annotations) -- em toda tool, com ou sem rede, com
        # ou sem openWorldHint.
        for nome in ("consultar_historico_acoes", "criar_acao_no_sistema", "pesquisar_internet"):
            with self.subTest(tool=nome):
                self.assertNotIn("idempotentHint", registry.mcp_annotations(nome))

    def test_dominio_rede_fechado_e_open_world_hint_false(self):
        # `criar_acao_no_sistema`: rede_servico envolve Google Calendar (do
        # próprio dono) -- dominio_rede=FECHADO.
        self.assertEqual(registry.mcp_annotations("criar_acao_no_sistema").get("openWorldHint"), False)

    def test_dominio_rede_aberto_e_open_world_hint_true(self):
        # `pesquisar_internet`/`ler_pagina_web`: conteúdo web arbitrário --
        # dominio_rede=ABERTO, os únicos dois hoje.
        for nome in ("pesquisar_internet", "ler_pagina_web"):
            with self.subTest(tool=nome):
                self.assertEqual(registry.mcp_annotations(nome).get("openWorldHint"), True)

    def test_dominio_rede_nao_classificado_omite_open_world_hint(self):
        # Tool sem necessidade de rede (dominio_rede=None por definição --
        # nunca foi candidata) e tools com rede mas deliberadamente não
        # classificadas por ambiguidade genuína (ver docstring de
        # registry.mcp_annotations): nenhuma leva openWorldHint, nem True
        # nem False -- omissão, não um terceiro valor.
        for nome in (
            "consultar_historico_acoes",  # sem rede
            "confirmar_acao",  # alvo variável, delega para outra tool
            "consultar_processo_sipac",  # scraper de portal externo
            "acompanhar_processo_sipac",  # idem
            "anexar_arquivo",  # pode envolver URL arbitrária conforme a origem
            "consultar_investimentos",  # serviço externo de dados de mercado
            "registrar_aporte_investimento",  # idem
            "registrar_execucao_investimento",  # idem
        ):
            with self.subTest(tool=nome):
                self.assertNotIn("openWorldHint", registry.mcp_annotations(nome))

    def test_paridade_com_todas_as_entradas_reais_do_inventario(self):
        # Não por amostragem: para TODA tool do catálogo (105 hoje), o trio
        # (readOnlyHint, destructiveHint, openWorldHint) tem que corresponder
        # exatamente à classificação real do inventário -- nunca um valor
        # inventado nem uma tool esquecida.
        for nome, entry in sorted(inventory.list_inventory().items()):
            with self.subTest(tool=nome):
                anotacoes = registry.mcp_annotations(nome)
                esperado_read_only = entry.leitura_escrita == LeituraEscrita.LEITURA
                self.assertEqual(anotacoes.get("readOnlyHint"), esperado_read_only)
                if esperado_read_only:
                    self.assertNotIn("destructiveHint", anotacoes)
                else:
                    esperado_destructive = entry.reversibilidade == Reversibilidade.IRREVERSIVEL
                    self.assertEqual(anotacoes.get("destructiveHint"), esperado_destructive)
                if entry.dominio_rede == DominioRede.FECHADO:
                    self.assertEqual(anotacoes.get("openWorldHint"), False)
                elif entry.dominio_rede == DominioRede.ABERTO:
                    self.assertEqual(anotacoes.get("openWorldHint"), True)
                else:
                    self.assertNotIn("openWorldHint", anotacoes)


class TestHandleToolsListAnnotations(unittest.TestCase):
    def setUp(self):
        self.catalogo = {t["name"]: t for t in mcp_server._handle_tools_list()["tools"]}

    def test_toda_tool_publicada_tem_annotations(self):
        # Paridade garantida por TestParidadeComCatalogo (test_tool_inventory.py):
        # nenhuma tool do catálogo real fica sem entrada no inventário hoje,
        # então nenhuma deveria chegar ao cliente sem o campo `annotations`.
        sem_annotations = [nome for nome, tool in self.catalogo.items() if "annotations" not in tool]
        self.assertEqual(sem_annotations, [], f"Tools publicadas sem annotations: {sem_annotations}")

    def test_leitura_pura_chega_com_read_only_hint_true(self):
        self.assertEqual(
            self.catalogo["consultar_historico_acoes"]["annotations"],
            {"readOnlyHint": True},
        )

    def test_escrita_irreversivel_chega_com_destructive_hint_true(self):
        self.assertEqual(
            self.catalogo["criar_rascunho_email"]["annotations"],
            {"readOnlyHint": False, "destructiveHint": True, "openWorldHint": False},
        )

    def test_escrita_reversivel_chega_com_destructive_hint_false(self):
        self.assertEqual(
            self.catalogo["criar_acao_no_sistema"]["annotations"],
            {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": False},
        )

    def test_dominio_aberto_chega_com_open_world_hint_true(self):
        self.assertEqual(
            self.catalogo["pesquisar_internet"]["annotations"],
            {"readOnlyHint": True, "openWorldHint": True},
        )

    def test_dominio_ambiguo_chega_sem_open_world_hint(self):
        # `consultar_processo_sipac`: rede via scraper de portal externo,
        # deliberadamente não classificado (ver registry.mcp_annotations).
        self.assertNotIn("openWorldHint", self.catalogo["consultar_processo_sipac"]["annotations"])

    def test_annotations_nao_interfere_no_resto_do_meta(self):
        # `_meta` (needsConfirmation/mutates/voiceEnabled, sub-entregas
        # anteriores ao P03) continua presente e correto ao lado do campo
        # novo -- annotations é aditivo, não substitui nada.
        tool = self.catalogo["criar_rascunho_email"]
        self.assertIn("_meta", tool)
        self.assertIn("needsConfirmation", tool["_meta"])
        self.assertIn("annotations", tool)
