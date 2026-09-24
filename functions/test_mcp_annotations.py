"""Testes de `registry.mcp_annotations` e da sua ligação a `tools/list`
(`mcp_server._handle_tools_list`).

P03 passo 3 do plano de autonomia (docs/plano-hermes-autonomo-2026-09-06.md):
"Adicionar outputSchema, structuredContent, annotations e envelope aos
caminhos compatíveis; manter content legado". `readOnlyHint`/
`destructiveHint` vieram da sub-entrega 6/N, derivados com confiança do
inventário tipado da sub-entrega 1/N (`tools/inventory.py`):
`readOnlyHint` de `leitura_escrita`, `destructiveHint` de
`reversibilidade`. `openWorldHint` vem da sub-entrega 7/N, do campo
`dominio_rede` (`tools/inventory.py::DominioRede`) -- não de
`necessidade_de_rede` direto, ver a docstring de `registry.mcp_annotations`
para o porquê. `idempotentHint` vem das sub-entregas 16/N-23/N: 53 das ~61
tools de escrita/leitura_e_escrita elegíveis têm `idempotencia`
classificada no inventário (`tools/inventory.py::Idempotencia`) -- as ~8
restantes continuam sem o hint (omitido, não um valor inventado) por
ambiguidade genuína já investigada e documentada, não por falta de leitura
do handler, mesmo raciocínio já usado
para `dominio_rede` (a espec. MCP já assume o lado mais cauteloso --
`destructiveHint`/`openWorldHint` default `true` -- para quem não declara
`ToolAnnotations`, e um hint errado é pior que a omissão).

Duas frentes:
1. `TestMcpAnnotations` -- a função pura em `tools/registry.py`, incluindo
   paridade com TODAS as entradas reais do inventário (não amostra): toda
   tool leitura pura tem `readOnlyHint=True` e nunca leva `destructiveHint`
   nem `idempotentHint`; toda tool de escrita (pura ou mista) tem
   `readOnlyHint=False` e `destructiveHint` correspondendo exatamente à
   `reversibilidade` (`irreversivel`->`True`, `reversivel`/`nao_aplica`->
   `False`); `openWorldHint` correspondendo exatamente a `dominio_rede`
   (`FECHADO`->`False`, `ABERTO`->`True`, `None`->omitido); `idempotentHint`
   correspondendo exatamente a `idempotencia` quando classificada
   (`IDEMPOTENTE`->`True`, `NAO_IDEMPOTENTE`->`False`, `None`->omitido).
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
from tools.inventory import DominioRede, Idempotencia, LeituraEscrita, Reversibilidade


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
        # API" -- dominio_rede=FECHADO (conta do proprio dono). NAO_IDEMPOTENTE
        # desde a sub-entrega 17/N (drafts.create sem chave de idempotencia).
        self.assertEqual(
            registry.mcp_annotations("criar_rascunho_email"),
            {"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False, "openWorldHint": False},
        )

    def test_escrita_reversivel_e_destructive_hint_false(self):
        # `criar_acao_no_sistema`: escrita, reversivel. rede_servico=
        # "Google Calendar (...) + Gemini condicional" -- dominio_rede=
        # FECHADO (agenda do proprio dono + chamada de IA interna).
        # idempotentHint=True desde a sub-entrega 16/N -- dedup por chave
        # exata (titulo, data_limite, horario_inicio) em claim_action_dedup_slot.
        self.assertEqual(
            registry.mcp_annotations("criar_acao_no_sistema"),
            {
                "readOnlyHint": False,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            },
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
        # NAO_IDEMPOTENTE desde a sub-entrega 19/N (outbox_aprovacao.py::
        # criar_rascunho sem dedup, ID automático a cada chamada).
        self.assertEqual(
            registry.mcp_annotations("criar_rascunho_whatsapp"),
            {
                "readOnlyHint": False,
                "destructiveHint": True,
                "idempotentHint": False,
                "openWorldHint": False,
            },
        )

    def test_leitura_e_escrita_idempotente_e_destructive_hint_false(self):
        # `consultar_investimentos`: leitura_e_escrita/nao_aplica, mas
        # IDEMPOTENTE desde a sub-entrega 17/N (dedupe por tag em
        # investimentos_sync -- ver nota em tools/inventory.py).
        # `consultar_autorizacao_argos`: mesmo desenho leitura_e_escrita/
        # nao_aplica, IDEMPOTENTE desde a sub-entrega 20/N (a escrita passiva
        # de expiração só acontece uma vez -- ver nota em tools/inventory.py).
        # `consultar_contatos_prioritarios_secretario`: mesmíssimo desenho,
        # IDEMPOTENTE desde a sub-entrega 23/N -- era o último exemplo deste
        # arquivo de "leitura_e_escrita/nao_aplica ainda sem idempotencia
        # classificada" (o teste dedicado a esse caso foi removido nesta
        # sub-entrega por não haver mais nenhuma tool desse formato sem
        # classificação -- ver tools/registry.py::mcp_annotations).
        for nome in (
            "consultar_investimentos",
            "consultar_autorizacao_argos",
            "consultar_contatos_prioritarios_secretario",
        ):
            with self.subTest(tool=nome):
                self.assertEqual(
                    registry.mcp_annotations(nome),
                    {"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True},
                )

    def test_leitura_pura_nunca_leva_idempotent_hint(self):
        # Leitura pura nunca leva idempotentHint -- o hint só é significativo
        # quando readOnlyHint é False (mesma convenção de destructiveHint),
        # e `idempotencia` nunca é classificada para LEITURA (ver docstring
        # de `Idempotencia` em tools/inventory.py).
        for nome in ("consultar_historico_acoes", "pesquisar_internet"):
            with self.subTest(tool=nome):
                self.assertNotIn("idempotentHint", registry.mcp_annotations(nome))

    def test_escrita_investigada_e_ambigua_omite_idempotent_hint(self):
        # `decidir_elevacao`: escrita real, JÁ investigada (ver nota em
        # tools/inventory.py) mas deixada deliberadamente sem classificação
        # por ambiguidade genuína -- idempotencia=None, hint omitido (não um
        # valor inventado). Desde a sub-entrega 23/N não existe mais nenhuma
        # tool elegível "nunca investigada": as ~8 que restam sem
        # idempotencia (`decidir_elevacao`, `decidir_promocao_autonomia`,
        # `confirmar_acao`, `mutar_portal_compras_publico`, `mutar_lista_
        # compras`, `revogar_promocao_autonomia`, `excluir_objetivo_
        # estrategico`, `gerenciar_item_estrategico`) foram todas lidas e
        # documentadas como ambíguas, não puladas. `schedule_whatsapp_
        # message` (usada aqui até a sub-entrega 22/N) foi classificada
        # NAO_IDEMPOTENTE na sub-entrega 23/N e não serve mais de exemplo.
        self.assertNotIn("idempotentHint", registry.mcp_annotations("decidir_elevacao"))

    def test_idempotente_leva_idempotent_hint_true(self):
        # As 4 tools classificadas IDEMPOTENTE na sub-entrega 16/N + as 2 da
        # sub-entrega 17/N + as 3 da sub-entrega 18/N + as 3 da sub-entrega
        # 19/N + as 3 da sub-entrega 20/N + as 3 da sub-entrega 23/N (ver
        # nota de cada uma em tools/inventory.py para a evidência por
        # handler; `consultar_autorizacao_argos`, também IDEMPOTENTE desde a
        # 20/N, tem teste dedicado em
        # test_leitura_e_escrita_idempotente_e_destructive_hint_false).
        for nome in (
            "criar_acao_no_sistema",
            "salvar_memoria_global",
            "dispensar_resposta_pendente",
            "concluir_pedido_agente",
            "registrar_saude",
            "consultar_investimentos",
            "desativar_modo_secretario",
            "cancelar_contato_prioritario_secretario",
            "editar_objetivo_estrategico",
            "salvar_pop_global",
            "atualizar_personalidade",
            "resolver_conflito_memoria",
            "aprovar_rascunho_whatsapp",
            "descartar_rascunho_whatsapp",
            "consumir_autorizacao_argos",
            "acompanhar_processo_sipac",
            "consultar_contatos_prioritarios_secretario",
            "registrar_inscricao_bolsa_publica",
        ):
            with self.subTest(tool=nome):
                self.assertEqual(registry.mcp_annotations(nome).get("idempotentHint"), True)

    def test_nao_idempotente_leva_idempotent_hint_false(self):
        # As 5 tools classificadas NAO_IDEMPOTENTE na sub-entrega 16/N + as 7
        # da sub-entrega 17/N + as 6 da sub-entrega 18/N + as 6 da sub-entrega
        # 19/N + a 1 da sub-entrega 20/N + as 4 da sub-entrega 21/N + a 1 da
        # sub-entrega 22/N + as 2 da sub-entrega 23/N (ver nota de cada uma
        # em tools/inventory.py para a evidência por handler).
        for nome in (
            "agendar_lembrete_acao",
            "registrar_no_diario",
            "editar_acao",
            "resolver_item_atencao",
            "registrar_execucao_agente",
            "registrar_transacao_financeira_publica",
            "registrar_item_financeiro_v2",
            "pausar_conversa",
            "criar_rascunho_email",
            "registrar_interacao_contato",
            "registrar_aporte_investimento",
            "registrar_execucao_investimento",
            "ativar_modo_secretario",
            "preparar_contato_prioritario_secretario",
            "remover_anexo",
            "criar_objetivo_estrategico",
            "preparar_upload",
            "anexar_arquivo",
            "registrar_correcao_procedimento",
            "resolver_conflito_procedimento",
            "editar_plano_acao",
            "gerar_relatorio",
            "gerar_imagem",
            "criar_rascunho_whatsapp",
            "solicitar_autorizacao_argos",
            "confirmar_edicao_em_lote",
            "editar_acoes_em_lote",
            "confirmar_reagendamento_em_lote",
            "reagendar_acoes_em_lote",
            "confirmar_edicao_acao",
            "consolidar_whatsapp",
            "schedule_whatsapp_message",
        ):
            with self.subTest(tool=nome):
                self.assertEqual(registry.mcp_annotations(nome).get("idempotentHint"), False)

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
        # Não por amostragem: para TODA tool do catálogo, o quarteto
        # (readOnlyHint, destructiveHint, openWorldHint, idempotentHint) tem
        # que corresponder exatamente à classificação real do inventário --
        # nunca um valor inventado nem uma tool esquecida.
        for nome, entry in sorted(inventory.list_inventory().items()):
            with self.subTest(tool=nome):
                anotacoes = registry.mcp_annotations(nome)
                esperado_read_only = entry.leitura_escrita == LeituraEscrita.LEITURA
                self.assertEqual(anotacoes.get("readOnlyHint"), esperado_read_only)
                if esperado_read_only:
                    self.assertNotIn("destructiveHint", anotacoes)
                    self.assertNotIn("idempotentHint", anotacoes)
                else:
                    esperado_destructive = entry.reversibilidade == Reversibilidade.IRREVERSIVEL
                    self.assertEqual(anotacoes.get("destructiveHint"), esperado_destructive)
                    if entry.idempotencia == Idempotencia.IDEMPOTENTE:
                        self.assertEqual(anotacoes.get("idempotentHint"), True)
                    elif entry.idempotencia == Idempotencia.NAO_IDEMPOTENTE:
                        self.assertEqual(anotacoes.get("idempotentHint"), False)
                    else:
                        self.assertNotIn("idempotentHint", anotacoes)
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
            {"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False, "openWorldHint": False},
        )

    def test_escrita_reversivel_chega_com_destructive_hint_false(self):
        self.assertEqual(
            self.catalogo["criar_acao_no_sistema"]["annotations"],
            {
                "readOnlyHint": False,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": False,
            },
        )

    def test_escrita_nao_idempotente_chega_com_idempotent_hint_false(self):
        # `registrar_execucao_agente`: escrita, irreversivel, sem rede,
        # NAO_IDEMPOTENTE desde a sub-entrega 16/N (agent_runs.registrar faz
        # col.add() sem chave de dedup).
        self.assertEqual(
            self.catalogo["registrar_execucao_agente"]["annotations"],
            {"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False},
        )

    def test_escrita_investigada_e_ambigua_chega_sem_idempotent_hint(self):
        # `decidir_elevacao`: investigada e deliberadamente deixada sem
        # classificação por ambiguidade genuína (ver tools/inventory.py) --
        # idempotentHint omitido, não um valor inventado. `schedule_
        # whatsapp_message` (usada aqui até a sub-entrega 22/N) foi
        # classificada NAO_IDEMPOTENTE na sub-entrega 23/N e não serve mais
        # de exemplo -- ver test_escrita_nao_idempotente_chega_com_
        # idempotent_hint_false para o catálogo completo de NAO_IDEMPOTENTE.
        self.assertNotIn("idempotentHint", self.catalogo["decidir_elevacao"]["annotations"])

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
