"""`registrar_observacao_externa` — P05 sub-entrega 16/N (passo 9 do pacote).

Três propriedades justificam estes testes acima das outras:

1. **Isolamento.** A garantia de "não virar preferência/autorização" nasce
   por omissão — nenhum outro módulo lê `observacoes_externas`. O teste que
   prova isto aqui é negativo: nenhuma OUTRA coleção (memória, política,
   autorização) é tocada por uma chamada desta tool.
2. **Grava e relê.** Igual ao critério de `registrar_saude`: a resposta usa
   o que foi relido do banco, nunca o argumento bruto.
3. **Recusa sem gravar.** Campo obrigatório ausente ou `nivel_verificacao`
   fora do enum não grava nada — igual ao padrão de `registrar_saude`.
"""

import unittest
from unittest import mock

from tools import registrar_observacao_externa as roe


class _Doc:
    def __init__(self, colecao, id_, dados=None):
        self._col = colecao
        self.id = id_
        self.exists = dados is not None
        self._d = dados

    def to_dict(self):
        return dict(self._d) if self._d else {}

    def get(self):
        return _Doc(self._col, self.id, self._col.dados.get(self.id))

    def set(self, valores, merge=False):
        atual = self._col.dados.get(self.id) if merge else None
        self._col.dados[self.id] = {**(atual or {}), **valores}


class _Colecao:
    def __init__(self):
        self.dados = {}
        self._seq = 0

    def document(self, doc_id=None):
        if doc_id is None:
            self._seq += 1
            doc_id = f"auto{self._seq}"
        return _Doc(self, doc_id, self.dados.get(doc_id))


class _Db:
    def __init__(self):
        self.cols: dict[str, _Colecao] = {}

    def collection(self, nome):
        return self.cols.setdefault(nome, _Colecao())


class _Ctx:
    def __init__(self, user_uid="uid-andre", canal="mcp", session_id="sess-1"):
        self.db = _Db()
        self.user_uid = user_uid
        self.canal = canal
        self.session_id = session_id


_ARGS_VALIDOS = {
    "fonte": "conector de e-mail do cliente",
    "assunto": "fatura de outubro foi paga em 2026-10-01",
    "horario": "2026-10-01T10:00:00-03:00",
}


class TestGravaERele(unittest.TestCase):
    def test_campos_obrigatorios_sao_relidos_do_banco(self):
        ctx = _Ctx()
        r = roe.registrar(ctx, dict(_ARGS_VALIDOS))
        self.assertEqual(r["status"], "completed")
        self.assertEqual(r["fonte"], _ARGS_VALIDOS["fonte"])
        self.assertEqual(r["assunto"], _ARGS_VALIDOS["assunto"])
        self.assertEqual(r["horario"], _ARGS_VALIDOS["horario"])

    def test_opcionais_ausentes_viram_none(self):
        r = roe.registrar(_Ctx(), dict(_ARGS_VALIDOS))
        self.assertIsNone(r["id_ou_url"])
        self.assertIsNone(r["artefato_hash"])

    def test_opcionais_presentes_sao_gravados(self):
        args = {**_ARGS_VALIDOS, "id_ou_url": "https://exemplo/doc/1", "artefato_hash": "sha256:abc"}
        r = roe.registrar(_Ctx(), args)
        self.assertEqual(r["id_ou_url"], "https://exemplo/doc/1")
        self.assertEqual(r["artefato_hash"], "sha256:abc")

    def test_opcional_so_com_espacos_vira_none_igual_ao_ausente(self):
        """Achado da revisão adversarial: antes da correção, `"   "` virava
        string vazia gravada, divergindo do tratamento dos obrigatórios."""
        r = roe.registrar(_Ctx(), {**_ARGS_VALIDOS, "id_ou_url": "   ", "artefato_hash": "\t"})
        self.assertIsNone(r["id_ou_url"])
        self.assertIsNone(r["artefato_hash"])

    def test_nivel_verificacao_padrao_e_nao_verificado(self):
        r = roe.registrar(_Ctx(), dict(_ARGS_VALIDOS))
        self.assertEqual(r["nivel_verificacao"], "nao_verificado")

    def test_nivel_verificacao_explicito_e_gravado(self):
        args = {**_ARGS_VALIDOS, "nivel_verificacao": "verificado_pelo_cliente"}
        r = roe.registrar(_Ctx(), args)
        self.assertEqual(r["nivel_verificacao"], "verificado_pelo_cliente")

    def test_registrado_por_reflete_o_contexto_do_canal(self):
        ctx = _Ctx(user_uid="uid-x", canal="telegram", session_id="s9")
        r = roe.registrar(ctx, dict(_ARGS_VALIDOS))
        self.assertEqual(
            r["registrado_por"],
            {"user_uid": "uid-x", "canal": "telegram", "session_id": "s9"},
        )

    def test_resposta_deixa_claro_que_nao_e_preferencia(self):
        r = roe.registrar(_Ctx(), dict(_ARGS_VALIDOS))
        self.assertIn("preferência", r["nota"])


class TestRecusaSemGravar(unittest.TestCase):
    def test_fonte_ausente_e_recusada(self):
        ctx = _Ctx()
        args = {k: v for k, v in _ARGS_VALIDOS.items() if k != "fonte"}
        r = roe.registrar(ctx, args)
        self.assertFalse(r["aplicado"])
        self.assertIn("fonte", r["erro"])
        self.assertEqual(ctx.db.cols, {})

    def test_assunto_ausente_e_recusado(self):
        ctx = _Ctx()
        args = {k: v for k, v in _ARGS_VALIDOS.items() if k != "assunto"}
        r = roe.registrar(ctx, args)
        self.assertFalse(r["aplicado"])
        self.assertIn("assunto", r["erro"])
        self.assertEqual(ctx.db.cols, {})

    def test_horario_ausente_e_recusado(self):
        ctx = _Ctx()
        args = {k: v for k, v in _ARGS_VALIDOS.items() if k != "horario"}
        r = roe.registrar(ctx, args)
        self.assertFalse(r["aplicado"])
        self.assertIn("horario", r["erro"])
        self.assertEqual(ctx.db.cols, {})

    def test_texto_so_com_espacos_e_tratado_como_ausente(self):
        ctx = _Ctx()
        r = roe.registrar(ctx, {**_ARGS_VALIDOS, "fonte": "   "})
        self.assertFalse(r["aplicado"])
        self.assertEqual(ctx.db.cols, {})

    def test_varios_campos_ausentes_sao_todos_citados(self):
        r = roe.registrar(_Ctx(), {})
        self.assertFalse(r["aplicado"])
        for campo in ("fonte", "assunto", "horario"):
            self.assertIn(campo, r["erro"])

    def test_nivel_verificacao_invalido_e_recusado(self):
        ctx = _Ctx()
        r = roe.registrar(ctx, {**_ARGS_VALIDOS, "nivel_verificacao": "confirmadissimo"})
        self.assertFalse(r["aplicado"])
        self.assertIn("nivel_verificacao", r["erro"])
        self.assertEqual(ctx.db.cols, {})


class TestNaoIdempotente(unittest.TestCase):
    """Cada chamada cria um documento novo -- mesmo com os MESMOS argumentos."""

    def test_duas_chamadas_iguais_criam_dois_documentos(self):
        ctx = _Ctx()
        roe.registrar(ctx, dict(_ARGS_VALIDOS))
        roe.registrar(ctx, dict(_ARGS_VALIDOS))
        self.assertEqual(len(ctx.db.cols[roe.COL_OBSERVACOES].dados), 2)

    def test_ids_das_duas_chamadas_sao_diferentes(self):
        ctx = _Ctx()
        r1 = roe.registrar(ctx, dict(_ARGS_VALIDOS))
        r2 = roe.registrar(ctx, dict(_ARGS_VALIDOS))
        self.assertNotEqual(r1["observacao_id"], r2["observacao_id"])


class TestFalhaNaReleitura(unittest.TestCase):
    """Achado da revisão adversarial: a escrita pode ter funcionado mesmo
    quando a releitura falha ou não enxerga o documento ainda -- o erro
    devolvido precisa deixar isso claro, nunca sugerir que nada foi gravado."""

    def test_excecao_ao_reler_preserva_aplicado_true_e_cita_o_id(self):
        ctx = _Ctx()
        with mock.patch.object(_Doc, "get", side_effect=RuntimeError("timeout")):
            r = roe.registrar(ctx, dict(_ARGS_VALIDOS))
        self.assertTrue(r["aplicado"])
        self.assertIn("FOI gravada", r["erro"])
        gravados = ctx.db.cols[roe.COL_OBSERVACOES].dados
        self.assertEqual(len(gravados), 1, "o documento deveria ter sido escrito mesmo com a releitura falhando")
        self.assertEqual(r["observacao_id"], next(iter(gravados)))

    def test_documento_nao_aparece_ao_reler_preserva_aplicado_true(self):
        ctx = _Ctx()
        with mock.patch.object(_Doc, "get", lambda self: _Doc(self._col, self.id, None)):
            r = roe.registrar(ctx, dict(_ARGS_VALIDOS))
        self.assertTrue(r["aplicado"])
        self.assertIn("FOI gravada", r["erro"])
        self.assertEqual(len(ctx.db.cols[roe.COL_OBSERVACOES].dados), 1)


class TestIsolamento(unittest.TestCase):
    """A garantia de não virar preferência/autorização é por isolamento:
    nenhuma outra coleção é tocada por esta tool."""

    def test_so_a_colecao_observacoes_externas_e_criada(self):
        ctx = _Ctx()
        roe.registrar(ctx, dict(_ARGS_VALIDOS))
        self.assertEqual(set(ctx.db.cols), {roe.COL_OBSERVACOES})

    def test_schema_version_gravado(self):
        r = roe.registrar(_Ctx(), dict(_ARGS_VALIDOS))
        self.assertEqual(r["schema_version"], 1)


if __name__ == "__main__":
    unittest.main()
