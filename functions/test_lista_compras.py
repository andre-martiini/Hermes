"""Lista de compras: a escrita tem de aparecer na tela, e o retorno tem de dizer o que fez.

O caso que originou estes testes esta em `TestCriterioDeAceite`, e e a sequencia
natural de quem troca a lista da semana:

    clear_planning  -> {"success": true, "affected": 6}
    import_batch    -> {"success": true, "created": 3}

Duas respostas de sucesso, e a tela de compras vazia. `clear_planning` desmarcou
os seis planejados e `import_batch` criou os novos fora do planejamento; item
assim nao aparece na tela que o usuario abre. Pior: nenhum dos dois retornos
permitia perceber isso — `affected: 6` nao distingue "apagou seis" de
"desmarcou seis", e `created: 3` de cinco linhas nao diz o que houve com as
outras duas.

Os demais testes travam as pecas que sustentam esse criterio: importar planeja,
nome repetido com intencao de planejamento marca o que existe em vez de recusar,
e `consultar` devolve os `item_id` — sem os quais `update` e `delete` eram
inalcancaveis pelo MCP.

Sem rede e sem Firestore: o fake abaixo implementa so o que o modulo usa.
"""

import unittest

from tools import lista_compras as lc


class _Ref:
    def __init__(self, colecao, doc_id):
        self._col = colecao
        self.id = doc_id

    def get(self):
        return _Snap(self._col, self.id)

    def set(self, dados):
        self._col.dados[self.id] = dict(dados)

    def update(self, dados):
        if self.id not in self._col.dados:
            raise AssertionError(f"update em documento inexistente: {self.id}")
        self._col.dados[self.id].update(dados)

    def delete(self):
        self._col.dados.pop(self.id, None)


class _Snap:
    def __init__(self, colecao, doc_id):
        self._col = colecao
        self.id = doc_id
        self.exists = doc_id in colecao.dados
        self.reference = _Ref(colecao, doc_id)

    def to_dict(self):
        return dict(self._col.dados.get(self.id) or {})


class _Colecao:
    def __init__(self):
        self.dados = {}
        self._seq = 0

    def document(self, doc_id=None):
        if doc_id is None:
            self._seq += 1
            doc_id = f"auto{self._seq}"
        return _Ref(self, str(doc_id))

    def stream(self):
        return [_Snap(self, doc_id) for doc_id in list(self.dados)]


class _Batch:
    def __init__(self):
        self._ops = []

    def set(self, ref, dados):
        self._ops.append((ref.set, dados))

    def update(self, ref, dados):
        self._ops.append((ref.update, dados))

    def commit(self):
        for aplicar, dados in self._ops:
            aplicar(dados)
        self._ops = []


class _Db:
    def __init__(self):
        self.cols = {}

    def collection(self, nome):
        return self.cols.setdefault(nome, _Colecao())

    def batch(self):
        return _Batch()


def _db_com(*itens, planejados=False):
    """Catalogo com os itens dados, todos na mesma situacao."""
    db = _Db()
    col = db.collection(lc.COLECAO)
    for i, nome in enumerate(itens, start=1):
        col.dados[f"id{i}"] = {
            "nome": nome,
            "categoria": "Mercado",
            "quantidade": "1",
            "unit": "un",
            "isPlanned": planejados,
            "isPurchased": False,
        }
    return db


def _nomes_planejados(db):
    return sorted(
        item["nome"] for item in lc.consultar(db, filtro="planejados")["itens"]
    )


LISTA_DA_SEMANA = "manteiga\npó de café\nleite sem lactose\nmuçarela\nqueijo"


class TestCriterioDeAceite(unittest.TestCase):
    """`clear_planning` + `import_batch` com cinco itens => os cinco na tela."""

    def setUp(self):
        # Os seis que estavam planejados quando o teste de 28/08 rodou.
        self.db = _db_com(
            "manteiga", "pó de café", "arroz", "feijão", "sabão em pó", "papel toalha",
            planejados=True,
        )

    def test_a_sequencia_do_relato_deixa_os_cinco_itens_na_tela(self):
        limpeza = lc.mutar(self.db, "clear_planning", {})
        self.assertEqual(limpeza["affected"], 6)

        importacao = lc.mutar(self.db, "import_batch", {"importText": LISTA_DA_SEMANA})

        self.assertEqual(
            _nomes_planejados(self.db),
            ["leite sem lactose", "manteiga", "muçarela", "pó de café", "queijo"],
            "a tela de compras nao mostra os cinco itens importados",
        )
        self.assertEqual(importacao["planejados"], 5)

    def test_consultar_devolve_os_cinco_com_item_id(self):
        lc.mutar(self.db, "clear_planning", {})
        lc.mutar(self.db, "import_batch", {"importText": LISTA_DA_SEMANA})

        planejados = lc.consultar(self.db, filtro="planejados")["itens"]
        self.assertEqual(len(planejados), 5)
        for item in planejados:
            self.assertTrue(item["item_id"], f"item sem id: {item}")
            self.assertEqual(
                set(item) >= {"nome", "categoria", "quantidade", "unit", "isPlanned", "isPurchased"},
                True,
                f"campos faltando em {item}",
            )

    def test_renomear_pelo_item_id_obtido_na_consulta(self):
        """"queijo" e ambiguo na prateleira; renomear e operacao corriqueira."""
        lc.mutar(self.db, "clear_planning", {})
        lc.mutar(self.db, "import_batch", {"importText": LISTA_DA_SEMANA})

        queijo = next(
            item for item in lc.consultar(self.db, busca="queijo")["itens"]
            if item["nome"] == "queijo"
        )
        lc.mutar(self.db, "update", {
            "item_id": queijo["item_id"], "nome": "queijo prato (ou o que ele decidir)",
        })

        self.assertIn("queijo prato (ou o que ele decidir)", _nomes_planejados(self.db))
        self.assertNotIn("queijo", _nomes_planejados(self.db))

    def test_o_retorno_da_importacao_explica_cada_item(self):
        lc.mutar(self.db, "clear_planning", {})
        r = lc.mutar(self.db, "import_batch", {"importText": LISTA_DA_SEMANA})

        self.assertEqual(r["created"], ["leite sem lactose", "muçarela", "queijo"])
        self.assertEqual(
            [(i["nome"], i["motivo"]) for i in r["ignorados"]],
            [("manteiga", lc.MOTIVO_JA_EXISTE), ("pó de café", lc.MOTIVO_JA_EXISTE)],
        )
        for ignorado in r["ignorados"]:
            self.assertTrue(ignorado["item_id"], "ignorado sem item_id para agir em cima")
            self.assertTrue(ignorado["planejado"], "item que ja existia ficou fora da tela")


class TestImportacao(unittest.TestCase):

    def test_importa_planejado_por_padrao(self):
        db = _db_com()
        lc.mutar(db, "import_batch", {"importText": "manteiga\nqueijo"})
        self.assertEqual(_nomes_planejados(db), ["manteiga", "queijo"])

    def test_is_planned_falso_alimenta_so_o_cadastro(self):
        """Quem discorda do padrao tem como pedir o comportamento antigo."""
        db = _db_com()
        r = lc.mutar(db, "import_batch", {"importText": "manteiga", "isPlanned": False})
        self.assertEqual(_nomes_planejados(db), [])
        self.assertEqual(r["planejados"], 0)
        self.assertIn("nada aparece na tela de compras", r["detalhe"])

    def test_categoria_depois_da_barra(self):
        db = _db_com()
        lc.mutar(db, "import_batch", {"importText": "muçarela|Frios"})
        self.assertEqual(lc.consultar(db)["itens"][0]["categoria"], "Frios")

    def test_linha_repetida_no_texto_tem_motivo_proprio(self):
        db = _db_com()
        r = lc.mutar(db, "import_batch", {"importText": "queijo\nQueijo"})
        self.assertEqual(r["created"], ["queijo"])
        self.assertEqual(
            [i["motivo"] for i in r["ignorados"]], [lc.MOTIVO_DUPLICADO_NO_TEXTO]
        )

    def test_linha_sem_nome_e_reportada_e_nao_criada(self):
        db = _db_com()
        r = lc.mutar(db, "import_batch", {"importText": "|Frios\nqueijo"})
        self.assertEqual(r["created"], ["queijo"])
        self.assertEqual([i["motivo"] for i in r["ignorados"]], [lc.MOTIVO_NOME_VAZIO])

    def test_linha_em_branco_nao_vira_item_nem_ruido(self):
        db = _db_com()
        r = lc.mutar(db, "import_batch", {"importText": "queijo\n\n   \nmanteiga"})
        self.assertEqual(r["created"], ["queijo", "manteiga"])
        self.assertEqual(r["ignorados"], [])

    def test_nome_repetido_ignora_acento_e_caixa(self):
        db = _db_com("Pó de Café")
        r = lc.mutar(db, "import_batch", {"importText": "po de cafe"})
        self.assertEqual(r["created"], [])
        self.assertEqual(lc.consultar(db)["total"], 1, "criou um duplicado do mesmo item")

    def test_texto_vazio_e_erro_explicito(self):
        with self.assertRaises(lc.ListaComprasError) as ctx:
            lc.mutar(_db_com(), "import_batch", {"importText": "   "})
        self.assertEqual(ctx.exception.code, "invalid_argument")

    def test_item_ja_comprado_continua_comprado(self):
        db = _db_com("manteiga")
        col = db.collection(lc.COLECAO)
        col.dados["id1"].update({"isPlanned": True, "isPurchased": True})
        lc.mutar(db, "import_batch", {"importText": "manteiga"})
        self.assertTrue(col.dados["id1"]["isPurchased"])

    def test_detalhe_nao_nega_planejamento_que_existe(self):
        """`isPlanned: false` sobre item ja planejado nao deixa a tela vazia — nem o texto pode dizer que sim."""
        db = _db_com("manteiga", planejados=True)
        r = lc.mutar(db, "import_batch", {"importText": "manteiga", "isPlanned": False})
        self.assertEqual(r["planejados"], 1)
        self.assertNotIn("Nenhum item desta importacao esta planejado", r["detalhe"])
        self.assertIn("1 item(ns) desta importacao estao planejados", r["detalhe"])

    def test_detalhe_nao_diz_que_marcou_o_que_ja_estava_marcado(self):
        db = _db_com("manteiga", planejados=True)
        r = lc.mutar(db, "import_batch", {"importText": "manteiga"})
        self.assertIn("ja planejado(s)", r["detalhe"])
        self.assertNotIn("passou(aram) a planejado", r["detalhe"])
        self.assertTrue(r["ignorados"][0]["ja_planejado"])

    def test_detalhe_separa_quem_passou_a_planejado_agora(self):
        db = _db_com("manteiga", "queijo")
        db.collection(lc.COLECAO).dados["id2"]["isPlanned"] = True
        r = lc.mutar(db, "import_batch", {"importText": "manteiga\nqueijo"})
        self.assertIn("1 ja existia(m) e passou(aram) a planejado(s) (manteiga)", r["detalhe"])
        self.assertIn("1 ja estava(m) na lista e ja planejado(s) (queijo)", r["detalhe"])

    def test_detalhe_aponta_quem_ficou_fora_do_planejamento(self):
        db = _db_com("manteiga")
        r = lc.mutar(db, "import_batch", {"importText": "manteiga", "isPlanned": False})
        self.assertIn("segue(m) sem planejamento (manteiga)", r["detalhe"])
        self.assertIn("Nenhum item desta importacao esta planejado", r["detalhe"])

    def test_acima_do_limite_do_batch_grava_tudo(self):
        """Firestore recusa mais de 500 escritas por commit."""
        db = _db_com()
        texto = "\n".join(f"item {n}" for n in range(600))
        r = lc.mutar(db, "import_batch", {"importText": texto})
        self.assertEqual(len(r["created"]), 600)
        self.assertEqual(lc.consultar(db)["total"], 600)


class TestLimpezaDoPlanejamento(unittest.TestCase):

    def test_desmarca_sem_excluir_e_diz_isso(self):
        db = _db_com("arroz", "feijão", "sal", planejados=True)
        r = lc.mutar(db, "clear_planning", {})

        self.assertEqual((r["desmarcados"], r["excluidos"]), (3, 0))
        self.assertEqual(r["itens_no_catalogo"], 3)
        self.assertEqual(r["sem_planejamento"], 3)
        self.assertIn("Nenhum item foi excluido", r["detalhe"])
        self.assertEqual(lc.consultar(db)["total"], 3, "clear_planning apagou itens")

    def test_lista_o_que_desmarcou(self):
        db = _db_com("arroz", "feijão", planejados=True)
        r = lc.mutar(db, "clear_planning", {})
        self.assertEqual(
            sorted(i["nome"] for i in r["itens_desmarcados"]), ["arroz", "feijão"]
        )

    def test_finalize_tambem_limpa_o_comprado(self):
        db = _db_com("arroz", planejados=True)
        db.collection(lc.COLECAO).dados["id1"]["isPurchased"] = True
        lc.mutar(db, "finalize", {})
        item = lc.consultar(db)["itens"][0]
        self.assertEqual((item["isPlanned"], item["isPurchased"]), (False, False))


class TestCriarComNomeExistente(unittest.TestCase):
    """Nome repetido com intencao de planejar e intencao, nao erro."""

    def test_marca_o_existente_em_vez_de_recusar(self):
        db = _db_com("manteiga")
        r = lc.mutar(db, "create", {
            "nome": "manteiga", "isPlanned": True, "categoria": "Mercado",
        })
        self.assertTrue(r["success"])
        self.assertTrue(r["ja_existia"])
        self.assertEqual(r["id"], "id1")
        self.assertEqual(_nomes_planejados(db), ["manteiga"])
        self.assertEqual(lc.consultar(db)["total"], 1, "criou um segundo item com o mesmo nome")

    def test_nao_apaga_campo_que_a_chamada_nao_informou(self):
        """`quantidade` ausente na chamada nao pode virar o padrao "1"."""
        db = _db_com("manteiga")
        db.collection(lc.COLECAO).dados["id1"]["quantidade"] = "3"
        lc.mutar(db, "create", {"nome": "manteiga", "isPlanned": True})
        self.assertEqual(db.collection(lc.COLECAO).dados["id1"]["quantidade"], "3")

    def test_cria_de_fato_quando_o_nome_e_novo(self):
        db = _db_com()
        r = lc.mutar(db, "create", {"nome": "muçarela", "isPlanned": True})
        self.assertTrue(r["criado"])
        self.assertFalse(r["ja_existia"])
        self.assertEqual(_nomes_planejados(db), ["muçarela"])

    def test_criar_sem_planejar_avisa_que_o_item_nao_aparece(self):
        db = _db_com()
        r = lc.mutar(db, "create", {"nome": "muçarela"})
        self.assertIn("nao aparece na tela de compras", r["detalhe"])

    def test_create_nunca_desmarca_o_que_ja_existe(self):
        """`create` so acrescenta intencao; tirar do planejamento e trabalho de `update`.

        O card da web monta o payload inteiro, preenchendo com `Geral`/`1`/`un` e
        flags falsas tudo que o copiloto omitiu. Sem esta regra, "cria manteiga"
        desplanejava a manteiga que ja estava na lista.
        """
        db = _db_com("manteiga", planejados=True)
        db.collection(lc.COLECAO).dados["id1"]["isPurchased"] = True
        lc.mutar(db, "create", {"nome": "manteiga", "isPlanned": False, "isPurchased": False})
        item = lc.consultar(db)["itens"][0]
        self.assertEqual((item["isPlanned"], item["isPurchased"]), (True, True))

    def test_payload_do_card_da_web_nao_apaga_o_que_o_usuario_ajustou(self):
        """Regressao do que o card enviava: defaults de UI em todos os campos."""
        db = _db_com("manteiga")
        db.collection(lc.COLECAO).dados["id1"].update({
            "categoria": "Frios", "quantidade": "3", "unit": "kg", "isPlanned": True,
        })
        # O card so manda um campo quando o copiloto informou aquele campo.
        lc.mutar(db, "create", {"action": "create", "nome": "manteiga"})
        self.assertEqual(
            db.collection(lc.COLECAO).dados["id1"],
            {"nome": "manteiga", "categoria": "Frios", "quantidade": "3",
             "unit": "kg", "isPlanned": True, "isPurchased": False},
        )

    def test_campo_informado_de_fato_ainda_e_aplicado(self):
        db = _db_com("manteiga")
        db.collection(lc.COLECAO).dados["id1"]["quantidade"] = "3"
        r = lc.mutar(db, "create", {"nome": "manteiga", "quantidade": "5", "isPlanned": True})
        self.assertEqual(sorted(r["atualizado"]), ["isPlanned", "quantidade"])
        self.assertEqual(db.collection(lc.COLECAO).dados["id1"]["quantidade"], "5")

    def test_detalhe_nao_esconde_escrita_atras_do_planejamento(self):
        """Planejar e mudar quantidade na mesma chamada tem de aparecer inteiro."""
        db = _db_com("manteiga")
        db.collection(lc.COLECAO).dados["id1"]["quantidade"] = "3"
        r = lc.mutar(db, "create", {"nome": "manteiga", "quantidade": "5", "isPlanned": True})
        self.assertIn("entrou no planejamento", r["detalhe"])
        self.assertIn("quantidade", r["detalhe"])

    def test_detalhe_cita_todo_campo_de_updates(self):
        db = _db_com("manteiga")
        db.collection(lc.COLECAO).dados["id1"].update({"categoria": "Frios", "unit": "kg"})
        r = lc.mutar(db, "create", {
            "nome": "manteiga", "categoria": "Mercado", "unit": "un", "isPurchased": True,
        })
        for campo in r["atualizado"]:
            if campo in ("isPlanned", "isPurchased"):
                continue
            self.assertIn(campo, r["detalhe"], f"{campo} foi gravado mas nao aparece no detalhe")
        self.assertIn("comprado", r["detalhe"])

    def test_nome_vazio_continua_recusado(self):
        with self.assertRaises(lc.ListaComprasError) as ctx:
            lc.mutar(_db_com(), "create", {"nome": "   "})
        self.assertEqual(ctx.exception.code, "invalid_argument")


class TestTextoBateComOGravado(unittest.TestCase):
    """Varredura: nenhum `detalhe` pode afirmar o que o banco nao mostra.

    Tres passes de review acharam, um por vez, ramos em que o texto devolvido
    divergia da escrita — ora omitindo um campo, ora anunciando marcacao que nao
    houve. Em vez de tapar mais um buraco por vez, isto percorre as combinacoes e
    confere o texto contra o estado final. E a guarda que fecha a classe.
    """

    def _create(self, existente, pedido):
        db = _db_com() if existente is None else _db_com("manteiga")
        if existente:
            db.collection(lc.COLECAO).dados["id1"].update(existente)
        antes = dict(db.collection(lc.COLECAO).dados.get("id1") or {})
        r = lc.mutar(db, "create", {"nome": "manteiga", **pedido})
        depois = list(db.collection(lc.COLECAO).dados.values())[0]
        return antes, depois, r

    def test_create_descreve_toda_marca_que_passou_a_valer(self):
        existentes = (None, {}, {"isPlanned": True}, {"isPlanned": True, "isPurchased": True})
        pedidos = (
            {}, {"isPlanned": True}, {"isPurchased": True},
            {"isPlanned": False}, {"isPlanned": False, "isPurchased": True},
        )
        for existente in existentes:
            for pedido in pedidos:
                with self.subTest(existente=existente, pedido=pedido):
                    antes, depois, r = self._create(existente, pedido)
                    detalhe = r["detalhe"].lower()
                    if depois["isPurchased"] and not antes.get("isPurchased"):
                        self.assertIn("comprad", detalhe, r["detalhe"])
                    if depois["isPlanned"] and not antes.get("isPlanned"):
                        self.assertIn("planej", detalhe, r["detalhe"])
                    if antes and depois == antes:
                        self.assertIn("nada mudou", detalhe, r["detalhe"])

    def test_importacao_conta_planejados_igual_ao_banco(self):
        for is_planned in (True, False):
            with self.subTest(isPlanned=is_planned):
                db = _db_com("manteiga", "queijo")
                db.collection(lc.COLECAO).dados["id2"]["isPlanned"] = True
                r = lc.mutar(db, "import_batch", {
                    "importText": "manteiga\nqueijo\nleite", "isPlanned": is_planned,
                })
                planejados = {i["nome"] for i in lc.consultar(db, filtro="planejados")["itens"]}
                enviados = {"manteiga", "queijo", "leite"}
                self.assertEqual(r["planejados"], len(planejados & enviados))


class TestAtualizarERemover(unittest.TestCase):

    def test_update_sem_id_aponta_a_saida(self):
        with self.assertRaises(lc.ListaComprasError) as ctx:
            lc.mutar(_db_com("arroz"), "update", {"nome": "arroz integral"})
        self.assertIn("consultar_lista_compras", ctx.exception.message)

    def test_renomear_para_nome_existente_e_recusado_com_o_id_do_conflito(self):
        db = _db_com("queijo", "muçarela")
        with self.assertRaises(lc.ListaComprasError) as ctx:
            lc.mutar(db, "update", {"item_id": "id1", "nome": "muçarela"})
        self.assertEqual(ctx.exception.code, "already_exists")
        self.assertIn("id2", ctx.exception.message)

    def test_marcar_comprado_implica_planejado(self):
        db = _db_com("arroz")
        lc.mutar(db, "update", {"item_id": "id1", "isPurchased": True})
        item = lc.consultar(db)["itens"][0]
        self.assertEqual((item["isPlanned"], item["isPurchased"]), (True, True))

    def test_tirar_do_planejamento_tira_o_comprado(self):
        db = _db_com("arroz", planejados=True)
        db.collection(lc.COLECAO).dados["id1"]["isPurchased"] = True
        lc.mutar(db, "update", {"item_id": "id1", "isPlanned": False})
        item = lc.consultar(db)["itens"][0]
        self.assertEqual((item["isPlanned"], item["isPurchased"]), (False, False))

    def test_delete_de_id_inexistente_nao_devolve_sucesso(self):
        with self.assertRaises(lc.ListaComprasError) as ctx:
            lc.mutar(_db_com("arroz"), "delete", {"item_id": "nao-existe"})
        self.assertEqual(ctx.exception.code, "not_found")

    def test_delete_devolve_o_que_foi_removido(self):
        db = _db_com("arroz")
        r = lc.mutar(db, "delete", {"item_id": "id1"})
        self.assertEqual(r["removido"]["nome"], "arroz")
        self.assertEqual(lc.consultar(db)["total"], 0)

    def test_acao_invalida_lista_as_validas(self):
        with self.assertRaises(lc.ListaComprasError) as ctx:
            lc.mutar(_db_com(), "esvaziar_tudo", {})
        self.assertIn("import_batch", ctx.exception.message)


class TestConsulta(unittest.TestCase):

    def setUp(self):
        self.db = _db_com("arroz", "feijão", "queijo")
        col = self.db.collection(lc.COLECAO)
        col.dados["id1"].update({"isPlanned": True})
        col.dados["id2"].update({"isPlanned": True, "isPurchased": True})

    def test_contagens_descrevem_a_lista_inteira_e_nao_o_recorte(self):
        r = lc.consultar(self.db, filtro="pendentes")
        self.assertEqual((r["total"], r["planejados"], r["comprados"]), (3, 2, 1))
        self.assertEqual([i["nome"] for i in r["itens"]], ["arroz"])

    def test_filtros(self):
        def nomes(filtro):
            return sorted(i["nome"] for i in lc.consultar(self.db, filtro=filtro)["itens"])

        self.assertEqual(nomes("todos"), ["arroz", "feijão", "queijo"])
        self.assertEqual(nomes("planejados"), ["arroz", "feijão"])
        self.assertEqual(nomes("comprados"), ["feijão"])
        self.assertEqual(nomes("nao_planejados"), ["queijo"])

    def test_filtro_desconhecido_e_erro_e_nao_silencio(self):
        with self.assertRaises(lc.ListaComprasError):
            lc.consultar(self.db, filtro="planejadps")

    def test_busca_ignora_acento(self):
        r = lc.consultar(self.db, busca="feijao")
        self.assertEqual([i["nome"] for i in r["itens"]], ["feijão"])

    def test_limite_marca_truncado(self):
        r = lc.consultar(self.db, limite=2)
        self.assertEqual((r["encontrados"], r["retornados"], r["truncado"]), (3, 2, True))

    def test_sem_truncar_nao_mente_dizendo_que_truncou(self):
        self.assertNotIn("truncado", lc.consultar(self.db))

    def test_limite_nao_numerico_vira_erro_de_dominio(self):
        """A borda MCP so traduz ListaComprasError; ValueError cru vaza sem causa."""
        with self.assertRaises(lc.ListaComprasError) as ctx:
            lc.consultar(self.db, limite="dez")
        self.assertEqual(ctx.exception.code, "invalid_argument")

    def test_ordem_nao_numerica_vira_erro_de_dominio(self):
        with self.assertRaises(lc.ListaComprasError) as ctx:
            lc.mutar(self.db, "create", {"nome": "sal", "ordem": "primeiro"})
        self.assertEqual(ctx.exception.code, "invalid_argument")


class TestParidadeEntreCanais(unittest.TestCase):
    """Web manda `itemId`; o schema MCP manda `item_id`. Os dois chegam aqui."""

    def test_item_id_e_itemid_sao_o_mesmo_campo(self):
        for chave in ("item_id", "itemId"):
            db = _db_com("arroz")
            lc.mutar(db, "update", {chave: "id1", "nome": f"arroz {chave}"})
            self.assertEqual(lc.consultar(db)["itens"][0]["nome"], f"arroz {chave}")

    def test_import_text_aceita_os_dois_nomes(self):
        for chave in ("importText", "import_text"):
            db = _db_com()
            lc.mutar(db, "import_batch", {chave: "queijo"})
            self.assertEqual(lc.consultar(db)["total"], 1, f"{chave} nao foi lido")


if __name__ == "__main__":
    unittest.main()
