"""Testes do wiring em sombra da extração estruturada (functions/extracao_compromissos_sombra.py)."""

import unittest
from datetime import datetime, timezone
from unittest import mock

import extracao_compromissos_sombra as ecs
from autonomy.extracao_estruturada import CompromissoExtraido

AGORA = datetime(2026, 10, 23, 15, 0, tzinfo=timezone.utc)
TEXTO = "Vou te enviar a planilha amanhã"


class _Snap:
    def __init__(self, dados):
        self._dados = dados
        self.exists = dados is not None

    def to_dict(self):
        return dict(self._dados or {})


class _Doc:
    def __init__(self, db, colecao, doc_id):
        self.db, self.colecao, self.id = db, colecao, doc_id

    def get(self):
        return _Snap(self.db.dados.get((self.colecao, self.id)))

    def set(self, dados, merge=False):
        self.db.escritas.append((self.colecao, self.id, dados, merge))
        if merge:
            atual = self.db.dados.setdefault((self.colecao, self.id), {})
            for k, v in dados.items():
                atual[k] = atual.get(k, 0) + v.value if hasattr(v, "value") else v
        else:
            self.db.dados[(self.colecao, self.id)] = dados


class _Colecao:
    def __init__(self, db, nome):
        self.db, self.nome = db, nome

    def document(self, doc_id):
        return _Doc(self.db, self.nome, doc_id)


class _DB:
    def __init__(self, cfg=None):
        self.dados, self.escritas = {}, []
        if cfg is not None:
            self.dados[("system", "settings")] = {"atencao": {"extracao_estruturada": cfg}}

    def collection(self, nome):
        return _Colecao(self, nome)

    def em(self, colecao):
        return [e for e in self.escritas if e[0] == colecao]


def _msg(**campos):
    base = {"id": "chat_m1", "chat_id": "111@lid", "is_group": False, "from_me": True,
            "message_type": "chat", "content": TEXTO,
            "timestamp": datetime(2026, 10, 23, 14, 50, tzinfo=timezone.utc)}
    base.update(campos)
    return base


SAIDA_OK = {"compromissos": [{"classe": "promessa", "objeto": "planilha", "evidencia": "Vou te enviar a planilha"}]}


def _rodar(db, msg, modelo, bot=False):
    with mock.patch("secretario_whatsapp.eh_mensagem_do_bot", return_value=bot):
        return ecs.processar_mensagem(db, msg, AGORA, chamar_modelo=modelo)


class TestSombra(unittest.TestCase):
    def test_desligada_por_padrao_nao_chama_modelo(self):
        modelo = mock.Mock(return_value=SAIDA_OK)
        self.assertIsNone(_rodar(_DB(None), _msg(), modelo))
        self.assertIsNone(_rodar(_DB({}), _msg(), modelo))
        modelo.assert_not_called()

    def test_grava_so_concordancia_sem_texto(self):
        db = _DB({"enabled": True})
        r = _rodar(db, _msg(), lambda d, t: SAIDA_OK)
        self.assertEqual(r["modo"], "sombra")
        self.assertIn("concorda", r)
        gravados = db.em(ecs.SOMBRA_COLLECTION)
        self.assertEqual(len(gravados), 1)
        self.assertNotIn("planilha", repr(gravados[0][2]))

    def test_filtros_nao_chamam_modelo(self):
        modelo = mock.Mock(return_value=SAIDA_OK)
        db = _DB({"enabled": True})
        for m in (_msg(from_me=False), _msg(is_group=True), _msg(message_type="ptt"),
                  _msg(content="bom dia"), _msg(content="")):
            self.assertIsNone(_rodar(db, m, modelo))
        self.assertIsNone(_rodar(db, _msg(), modelo, bot=True))
        modelo.assert_not_called()

    def test_mensagem_antiga_ou_sem_data_nao_chama_modelo(self):
        modelo = mock.Mock(return_value=SAIDA_OK)
        db = _DB({"enabled": True})
        antiga = datetime(2026, 10, 23, 8, 0, tzinfo=timezone.utc)
        futura = datetime(2026, 10, 23, 18, 0, tzinfo=timezone.utc)
        for ts in (antiga, futura, None, "lixo"):
            self.assertIsNone(_rodar(db, _msg(timestamp=ts), modelo))
        self.assertIsNone(_rodar(db, {k: v for k, v in _msg().items() if k != "timestamp"}, modelo))
        modelo.assert_not_called()

    def test_limite_diario(self):
        db = _DB({"enabled": True, "max_por_dia": 1})
        modelo = mock.Mock(return_value=SAIDA_OK)
        self.assertIsNotNone(_rodar(db, _msg(), modelo))
        self.assertIsNone(_rodar(db, _msg(id="chat_m2"), modelo))
        self.assertEqual(modelo.call_count, 1)

    def test_reentrega_nao_chama_nem_conta_de_novo(self):
        db = _DB({"enabled": True})
        modelo = mock.Mock(return_value=SAIDA_OK)
        self.assertIsNotNone(_rodar(db, _msg(), modelo))
        self.assertIsNone(_rodar(db, _msg(), modelo))
        self.assertEqual(modelo.call_count, 1)
        self.assertEqual(db.dados[(ecs.CONTADORES_COLLECTION, "2026-10-23")]["avaliadas"], 1)

    def test_saida_invalida_e_erro_do_modelo_nao_gravam_nem_propagam(self):
        db = _DB({"enabled": True})
        self.assertIsNone(_rodar(db, _msg(), lambda d, t: {"compromissos": "x"}))
        self.assertIsNone(_rodar(db, _msg(), lambda d, t: None))

        def falha(d, t):
            raise RuntimeError("429")

        self.assertIsNone(_rodar(db, _msg(), falha))
        self.assertEqual(db.em(ecs.SOMBRA_COLLECTION), [])

    def test_duas_promessas_firmes_viram_dois_compromissos_independentes(self):
        firme = lambda o: CompromissoExtraido("promessa", o, "evidencia", False)  # noqa: E731
        extraidos = (firme("planilha"), CompromissoExtraido("promessa", "x", "e", True),
                     CompromissoExtraido("intencao_vaga", "y", "e", False), firme("contrato"))
        r = ecs._compromissos_independentes("111@lid", "chat_m1", extraidos)
        self.assertEqual(r["n_compromissos"], 2)
        self.assertEqual(r["chaves_compromissos"], ["111@lid__chat_m1__0", "111@lid__chat_m1__3"])

    def test_resumo_traz_compromissos_sem_texto(self):
        db = _DB({"enabled": True})
        r = _rodar(db, _msg(), lambda d, t: SAIDA_OK)
        self.assertEqual(r["n_compromissos"], len(r["chaves_compromissos"]))
        self.assertNotIn("planilha", repr(db.em(ecs.SOMBRA_COLLECTION)))

    def test_objeto_com_quebra_de_linha_nao_descarta_os_outros(self):
        f = lambda o: CompromissoExtraido("promessa", o, "ev", False)  # noqa: E731
        r = ecs._compromissos_independentes("1@lid", "m1", (f("enviar\nplanilha"), f("con\u200btrato"), f("ok")))
        self.assertEqual(r["chaves_compromissos"], ["1@lid__m1__0", "1@lid__m1__2"])
        self.assertEqual(r["compromissos_chat_erro"], 1)

    def test_id_invalido_para_chave_nao_derruba_a_sombra(self):
        db = _DB({"enabled": True})
        r = _rodar(db, _msg(id="chat__m1"), lambda d, t: SAIDA_OK)
        self.assertEqual(r["compromissos_chat_erro"], 1)
        self.assertIn("concorda", r)
        self.assertEqual(len(db.em(ecs.SOMBRA_COLLECTION)), 1)


if __name__ == "__main__":
    unittest.main()
