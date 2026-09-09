"""Testes para autonomy/mandatos_io.py -- wrapper de I/O que resolve
`autonomy.contracts.Mandato` a partir de `system/mcp_access.tipos_promovidos`
(P02 sub-entrega 17/N; ver docs/autonomia/proposta-p02-mandato-io-wrapper.md).
"""

from __future__ import annotations

import datetime
from datetime import timezone
import unittest

from autonomy import mandatos_io


class _MockDocSnap:
    def __init__(self, doc_id: str, data: dict | None):
        self.id = doc_id
        self._data = dict(data) if data is not None else None
        self.exists = data is not None

    def to_dict(self):
        return dict(self._data) if self._data is not None else {}


class _MockDocRef:
    def __init__(self, col, doc_id: str):
        self.col = col
        self.id = doc_id

    def get(self, transaction=None):
        return _MockDocSnap(self.id, self.col._docs.get(self.id))


class _MockCollection:
    def __init__(self, name: str):
        self.name = name
        self._docs: dict[str, dict] = {}

    def document(self, doc_id: str):
        return _MockDocRef(self, doc_id)


class _MockDb:
    def __init__(self):
        self._cols: dict[str, _MockCollection] = {}

    def collection(self, name: str):
        if name not in self._cols:
            self._cols[name] = _MockCollection(name)
        return self._cols[name]


class _DbQuebrado:
    """Simula Firestore indisponível -- toda leitura levanta."""

    def collection(self, name):
        raise RuntimeError("Firestore indisponível (simulado)")


class TestMandatoTipoPromovido(unittest.TestCase):
    def setUp(self):
        self.db = _MockDb()
        self.agora = datetime.datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)

    def _set_tipos_promovidos(self, *tipos):
        self.db.collection("system")._docs["mcp_access"] = {"tipos_promovidos": list(tipos)}

    def test_tipo_promovido_retorna_mandato_com_campos_esperados(self):
        self._set_tipos_promovidos("confirmacao_reuniao")
        mandato = mandatos_io.mandato_tipo_promovido(self.db, "confirmacao_reuniao", agora=self.agora)

        self.assertIsNotNone(mandato)
        self.assertEqual(mandato.mandato_id, "tipo_promovido:confirmacao_reuniao")
        self.assertEqual(mandato.finalidade, "envio_promovido:confirmacao_reuniao")
        self.assertEqual(mandato.destinatarios_recursos, ("*",))
        self.assertEqual(mandato.classes_conteudo_permitidas, ("confirmacao_reuniao",))
        self.assertFalse(mandato.revogado)
        self.assertIsNone(mandato.limite_por_janela)
        self.assertIsNone(mandato.orcamento_maximo)
        self.assertIsNone(mandato.horario_permitido_inicio)
        self.assertIsNone(mandato.horario_permitido_fim)

    def test_valido_ate_e_janela_rolante_a_partir_de_agora(self):
        self._set_tipos_promovidos("confirmacao_reuniao")
        mandato = mandatos_io.mandato_tipo_promovido(
            self.db, "confirmacao_reuniao", agora=self.agora, janela_validade_dias=30,
        )
        self.assertEqual(mandato.valido_ate, self.agora + datetime.timedelta(days=30))

    def test_normaliza_tipo_por_strip_e_lower(self):
        self._set_tipos_promovidos("confirmacao_reuniao")
        mandato = mandatos_io.mandato_tipo_promovido(self.db, "  Confirmacao_Reuniao  ", agora=self.agora)
        self.assertIsNotNone(mandato)
        self.assertEqual(mandato.classes_conteudo_permitidas, ("confirmacao_reuniao",))

    def test_tipo_nao_promovido_retorna_none(self):
        self._set_tipos_promovidos("confirmacao_reuniao")
        mandato = mandatos_io.mandato_tipo_promovido(self.db, "cobranca_terceiro", agora=self.agora)
        self.assertIsNone(mandato)

    def test_nenhum_tipo_promovido_ainda_retorna_none(self):
        # system/mcp_access nem existe -- mesmo comportamento de
        # outbox_aprovacao._tipos_promovidos quando nada foi configurado.
        mandato = mandatos_io.mandato_tipo_promovido(self.db, "confirmacao_reuniao", agora=self.agora)
        self.assertIsNone(mandato)

    def test_tipo_vazio_retorna_none_sem_ler_o_banco(self):
        self.assertIsNone(mandatos_io.mandato_tipo_promovido(self.db, "", agora=self.agora))
        self.assertIsNone(mandatos_io.mandato_tipo_promovido(self.db, "   ", agora=self.agora))
        self.assertIsNone(mandatos_io.mandato_tipo_promovido(self.db, None, agora=self.agora))

    def test_falha_ao_ler_tipos_promovidos_cai_fail_closed(self):
        # Diferente de uma leitura que responde "não promovido": uma
        # FALHA de leitura nunca deve ser tratada como "está promovido".
        mandato = mandatos_io.mandato_tipo_promovido(_DbQuebrado(), "confirmacao_reuniao", agora=self.agora)
        self.assertIsNone(mandato)

    def test_origem_autorizacao_usa_data_quando_promocao_aceita_disponivel(self):
        self._set_tipos_promovidos("confirmacao_reuniao")
        decidida_em = datetime.datetime(2026, 8, 20, 9, 30, tzinfo=timezone.utc)
        self.db.collection("promocoes_autonomia_sugeridas")._docs["confirmacao_reuniao"] = {
            "status": "aceita",
            "decidida_em": decidida_em,
        }
        mandato = mandatos_io.mandato_tipo_promovido(self.db, "confirmacao_reuniao", agora=self.agora)
        self.assertIn("confirmacao_reuniao", mandato.origem_autorizacao)
        self.assertIn(decidida_em.isoformat(), mandato.origem_autorizacao)

    def test_origem_autorizacao_generica_quando_sugestao_nao_encontrada(self):
        self._set_tipos_promovidos("confirmacao_reuniao")
        mandato = mandatos_io.mandato_tipo_promovido(self.db, "confirmacao_reuniao", agora=self.agora)
        self.assertIn("data não disponível", mandato.origem_autorizacao)

    def test_origem_autorizacao_generica_quando_status_sugestao_nao_e_aceita(self):
        # Cenário defensivo: não deveria acontecer (só entra em
        # tipos_promovidos via decisão "aceitar"), mas o mandato não deve
        # quebrar nem inventar uma data se o status divergir.
        self._set_tipos_promovidos("confirmacao_reuniao")
        self.db.collection("promocoes_autonomia_sugeridas")._docs["confirmacao_reuniao"] = {
            "status": "adiada",
        }
        mandato = mandatos_io.mandato_tipo_promovido(self.db, "confirmacao_reuniao", agora=self.agora)
        self.assertIn("data não disponível", mandato.origem_autorizacao)

    def test_falha_ao_ler_origem_autorizacao_nao_impede_construcao_do_mandato(self):
        # Não-crítico: só rastreabilidade extra, nunca deve derrubar a
        # resolução do mandato em si.
        self._set_tipos_promovidos("confirmacao_reuniao")

        class _DbSoPromovidosOk:
            def __init__(self, mcp_snap):
                self._mcp_snap = mcp_snap

            def collection(self, name):
                if name == "system":
                    col = _MockCollection("system")
                    col._docs["mcp_access"] = self._mcp_snap
                    return col
                raise RuntimeError("Firestore indisponível (simulado) para " + name)

        db_parcial = _DbSoPromovidosOk({"tipos_promovidos": ["confirmacao_reuniao"]})
        mandato = mandatos_io.mandato_tipo_promovido(db_parcial, "confirmacao_reuniao", agora=self.agora)
        self.assertIsNotNone(mandato)
        self.assertIn("data não disponível", mandato.origem_autorizacao)

    def test_tipo_outro_promovido_retorna_none_em_vez_de_levantar(self):
        # Achado BLOQUEANTE da revisão adversarial (P02 sub-entrega 17/N):
        # "outro" é o default de `tipo` em outbox_aprovacao.criar_rascunho
        # para todo rascunho sem tipo explícito, e
        # promocao_autonomia.tipos_elegiveis_para_promocao() não o exclui da
        # varredura -- um humano pode legitimamente aceitar essa promoção
        # via decidir_promocao_autonomia(db, "outro", "aceitar"). Sem este
        # guard, Mandato.__post_init__ levantaria ValueError sem ninguém
        # capturar no chamador de liberar_rascunhos_promovidos, derrubando o
        # lote inteiro (inclusive rascunhos de outros tipos, válidos).
        self._set_tipos_promovidos("outro")
        mandato = mandatos_io.mandato_tipo_promovido(self.db, "outro", agora=self.agora)
        self.assertIsNone(mandato)

    def test_tipo_outro_maiuscula_promovido_tambem_retorna_none(self):
        self._set_tipos_promovidos("Outro")
        mandato = mandatos_io.mandato_tipo_promovido(self.db, "Outro", agora=self.agora)
        self.assertIsNone(mandato)

    def test_mandato_resolvido_cobre_via_mandato_cobre_real(self):
        # Integração com autonomy.policy.mandato_cobre -- não reimplementa a
        # lógica de cobertura aqui, só confirma que o Mandato produzido é
        # aceito pelo motor real com sensibilidade/missão derivados do
        # mesmo tipo (contrato que outbox_aprovacao.liberar_rascunhos_
        # promovidos depende).
        from autonomy import policy as autonomy_policy
        from autonomy.contracts import ClasseEfeito, Principal, PolicyRequest, TipoPrincipal

        self._set_tipos_promovidos("confirmacao_reuniao")
        mandato = mandatos_io.mandato_tipo_promovido(self.db, "confirmacao_reuniao", agora=self.agora)

        request = PolicyRequest(
            principal=Principal(uid=None, tipo=TipoPrincipal.RUNNER_SERVICO, canal="outbox_worker"),
            ferramenta="liberar_rascunhos_promovidos",
            classe_efeito=ClasseEfeito.COMPROMISSO_TERCEIROS,
            missao="envio_promovido:confirmacao_reuniao",
            sensibilidade="confirmacao_reuniao",
            mandatos_aplicaveis=(mandato,),
        )
        self.assertTrue(autonomy_policy.mandato_cobre(mandato, request, self.agora))

        decisao = autonomy_policy.avaliar(request, agora=self.agora)
        self.assertEqual(decisao.decision.value, "allow")
        self.assertEqual(decisao.reason_code, "dentro_de_mandato_vigente")


if __name__ == "__main__":
    unittest.main()
