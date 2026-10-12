"""Testes para a mudança (ainda não aplicada) que faz
`knowledge_graph._dual_pass_find_or_create_node` gravar `origem_fato` ao
criar um Nó Conceitual inédito.

Mudança decidida (ver docstring de `functions/autonomy/context.py`, bloco
"NÃO tocado por esta sub-entrega, registrado como pendência" -- este é
exatamente o `knowledge_graph.py` lá citado como pendência, agora endereçado
numa sub-entrega própria): no bloco "── Cria nó inédito" de
`_dual_pass_find_or_create_node`, o dict passado a
`db.collection("knowledge_nodes").document(new_id).set({...})` ganha a chave
`"origem_fato": RESUMO_DERIVADO` (importado de `autonomy.context`). Nenhuma
outra linha da função muda -- em particular, o caminho de ANEXAR a um nó já
existente (decisão `"ANEXAR:<id>"` da LLM, nó validado com
`.get().exists`) continua retornando `(node_id, round(best_sim, 4))` sem
nenhuma escrita no Firestore, então não grava nem altera `origem_fato` do nó
anexado.

Mock de Firestore reaproveitado de `test_outbox_aprovacao._MockDb` -- mesmo
padrão já usado por `test_memoria_origem_fato.py` para testar proveniência
de fatos, sem reimplementar um segundo mock encadeado.

`_gemini_client`/`client.models.generate_content` (decisão ANEXAR vs.
CRIAR_NOVO) e `_derive_node_title` (título do nó novo) são mockados para
isolar a gravação de `origem_fato` do resto da lógica de embeddings/LLM, que
já tem seu próprio escopo e não é alterada por esta mudança.

Cobertura de `autonomy.context.origem_fato_de_leitura` para documento sem o
campo (item 3 do pedido original) é PULADA aqui de propósito: já existe em
`test_memoria_origem_fato.py::TestOrigemFatoDeLeitura` (ex.:
`test_documento_sem_campo_e_legado`, `test_documento_none_e_legado`,
`test_documento_vazio_e_legado`), que testa a função pura diretamente --
duplicar essa cobertura aqui não agregaria nada.
"""

import unittest
from unittest import mock

from test_outbox_aprovacao import _MockDb

import knowledge_graph as kg
from autonomy.context import RESUMO_DERIVADO


def _mock_decisao_llm(texto_decisao: str):
    """Monta um `client` fake cujo `models.generate_content(...)` devolve
    `texto_decisao` em `.text`, no formato que `_dual_pass_find_or_create_node`
    espera de `_gemini_client(api_key).models.generate_content(...)`."""
    resposta = mock.Mock()
    resposta.text = texto_decisao
    client = mock.Mock()
    client.models.generate_content.return_value = resposta
    return client


class TestCriaNoIneditoGravaOrigemFato(unittest.TestCase):
    """Bloco "── Cria nó inédito": o dict passado a `.set()` deve conter
    `origem_fato=RESUMO_DERIVADO`, tanto quando não há candidatos (pula a
    decisão da LLM) quanto quando há candidatos mas a LLM decide
    `CRIAR_NOVO`."""

    def setUp(self):
        self.db = _MockDb()

    def test_sem_candidatos_grava_origem_fato_resumo_derivado(self):
        """Sem nenhum nó existente na área temática, `top_candidates` fica
        vazio e a função vai direto para "Cria nó inédito" sem nunca chamar
        a LLM para decidir ANEXAR/CRIAR_NOVO."""
        with mock.patch.object(
            kg, "_derive_node_title", return_value="Título Mockado"
        ) as mock_title, mock.patch.object(
            kg, "_gemini_client"
        ) as mock_gemini_client:
            node_id, peso = kg._dual_pass_find_or_create_node(
                db=self.db,
                api_key="fake-key",
                summary="Resumo do procedimento executado na tarefa.",
                embedding=[0.1, 0.2, 0.3],
                area_tematica="GERAL",
                task_id="task-1",
            )

        # Caminho sem candidatos nunca deveria precisar decidir nada via LLM.
        mock_gemini_client.assert_not_called()
        mock_title.assert_called_once_with(
            "Resumo do procedimento executado na tarefa.", "GERAL", "fake-key"
        )

        self.assertEqual(peso, 1.0)
        doc = self.db.collection("knowledge_nodes")._docs[node_id]
        self.assertEqual(doc["origem_fato"], RESUMO_DERIVADO)
        self.assertEqual(doc["origem_fato"], "resumo_derivado")
        self.assertEqual(doc["titulo"], "Título Mockado")
        self.assertEqual(doc["area_tematica"], "GERAL")

    def test_com_candidatos_mas_decisao_criar_novo_grava_origem_fato_resumo_derivado(self):
        """Há um nó candidato na mesma área, mas a LLM decide que o
        procedimento é genuinamente diferente (`CRIAR_NOVO`) -- ainda assim
        cai no bloco "Cria nó inédito" e deve gravar `origem_fato`."""
        self.db.collection("knowledge_nodes").document("no-existente").set({
            "titulo": "Nó existente",
            "area_tematica": "GERAL",
            "embedding": [1.0, 0.0, 0.0],
            "resumo": "resumo antigo",
            # proveniência do nó existente -- não deve interferir no nó NOVO
            "origem_fato": "declaracao_humana",
        })

        with mock.patch.object(
            kg, "_gemini_client", return_value=_mock_decisao_llm("CRIAR_NOVO")
        ) as mock_gemini_client, mock.patch.object(
            kg, "_derive_node_title", return_value="Outro Título"
        ):
            node_id, peso = kg._dual_pass_find_or_create_node(
                db=self.db,
                api_key="fake-key",
                summary="Procedimento diferente de tudo que já existe.",
                embedding=[0.0, 1.0, 0.0],
                area_tematica="GERAL",
                task_id="task-2",
            )

        mock_gemini_client.assert_called_once_with("fake-key")
        self.assertNotEqual(node_id, "no-existente")

        docs = self.db.collection("knowledge_nodes")._docs
        self.assertEqual(len(docs), 2)  # nó antigo + nó novo
        novo_doc = docs[node_id]
        self.assertEqual(novo_doc["origem_fato"], RESUMO_DERIVADO)

        # O nó existente não foi tocado por esta chamada.
        self.assertEqual(docs["no-existente"]["origem_fato"], "declaracao_humana")


class TestAnexarNaoTocaOrigemFato(unittest.TestCase):
    """Caminho de ANEXAR (decisão `"ANEXAR:<id>"` com nó validado via
    `.get().exists`): a função só lê e retorna `(node_id, peso)`, sem
    escrever nada no Firestore -- então não grava, não adiciona e não
    sobrescreve `origem_fato` do nó anexado."""

    def setUp(self):
        self.db = _MockDb()

    def test_anexar_a_no_existente_nao_altera_origem_fato_ja_gravado(self):
        self.db.collection("knowledge_nodes").document("no-existente").set({
            "titulo": "Nó existente",
            "area_tematica": "GERAL",
            "embedding": [1.0, 0.0, 0.0],
            "resumo": "resumo antigo",
            "origem_fato": "declaracao_humana",
        })
        doc_original = dict(self.db.collection("knowledge_nodes")._docs["no-existente"])

        with mock.patch.object(
            kg, "_gemini_client",
            return_value=_mock_decisao_llm("ANEXAR:no-existente"),
        ), mock.patch.object(kg, "_derive_node_title") as mock_title:
            node_id, peso = kg._dual_pass_find_or_create_node(
                db=self.db,
                api_key="fake-key",
                summary="Procedimento que se encaixa no nó existente.",
                embedding=[1.0, 0.0, 0.0],
                area_tematica="GERAL",
                task_id="task-3",
            )

        self.assertEqual(node_id, "no-existente")
        # Caminho de ANEXAR não cria nó novo, então nunca deriva título.
        mock_title.assert_not_called()

        # Nenhuma escrita aconteceu: a coleção continua com o único doc
        # original, byte a byte -- em particular, origem_fato não mudou.
        docs = self.db.collection("knowledge_nodes")._docs
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs["no-existente"], doc_original)
        self.assertEqual(docs["no-existente"]["origem_fato"], "declaracao_humana")

    def test_anexar_a_no_existente_sem_origem_fato_nao_adiciona_o_campo(self):
        """Mesmo cenário, mas o nó existente nunca teve `origem_fato`
        gravado (nó antigo, de antes desta mudança) -- anexar não deve
        inserir o campo por baixo dos panos."""
        self.db.collection("knowledge_nodes").document("no-existente").set({
            "titulo": "Nó existente",
            "area_tematica": "GERAL",
            "embedding": [1.0, 0.0, 0.0],
            "resumo": "resumo antigo",
        })

        with mock.patch.object(
            kg, "_gemini_client",
            return_value=_mock_decisao_llm("ANEXAR:no-existente"),
        ):
            node_id, peso = kg._dual_pass_find_or_create_node(
                db=self.db,
                api_key="fake-key",
                summary="Procedimento que se encaixa no nó existente.",
                embedding=[1.0, 0.0, 0.0],
                area_tematica="GERAL",
                task_id="task-4",
            )

        self.assertEqual(node_id, "no-existente")
        doc = self.db.collection("knowledge_nodes")._docs["no-existente"]
        self.assertNotIn("origem_fato", doc)


if __name__ == "__main__":
    unittest.main()
