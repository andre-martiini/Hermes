"""Testes do cache em memória de perfil_pessoas em knowledge_graph.

Contexto (DEV-2026-0003 / Issue #203, docs/okf/operacoes/custos.md):
``on_tarefa_written_extract_people`` fazia um ``.limit(200).stream()``
completo em ``perfil_pessoas`` a cada nome não encontrado por match exato —
medido em 314.845 leituras/dia (38,6% do total) em 13/09/2026. Este cache
reduz isso a no máximo 1 leitura da coleção por instância quente a cada
``_PERFIL_PESSOAS_CACHE_TTL_S`` segundos.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

import knowledge_graph as kg


class _FakeDoc:
    def __init__(self, doc_id: str, nome: str):
        self.id = doc_id
        self._nome = nome

    def to_dict(self):
        return {"nome": self._nome}


def _fake_db(docs):
    db = MagicMock()
    db.collection.return_value.stream.return_value = iter(docs)
    return db


class PerfilPessoasCacheTest(unittest.TestCase):
    def setUp(self):
        kg._perfil_pessoas_cache["pessoas"] = []
        kg._perfil_pessoas_cache["loaded_at"] = None

    def test_carrega_uma_vez_e_reusa_dentro_do_ttl(self):
        db = _fake_db([_FakeDoc("1", "João Silva")])
        result1 = kg._get_perfil_pessoas_cache(db)
        result2 = kg._get_perfil_pessoas_cache(db)
        self.assertEqual(result1, [("1", "joão silva")])
        self.assertEqual(result2, result1)
        db.collection.return_value.stream.assert_called_once()

    def test_recarrega_apos_ttl_expirar(self):
        db = _fake_db([_FakeDoc("1", "João Silva")])
        kg._get_perfil_pessoas_cache(db)
        kg._perfil_pessoas_cache["loaded_at"] -= kg._PERFIL_PESSOAS_CACHE_TTL_S + 1
        db.collection.return_value.stream.return_value = iter(
            [_FakeDoc("1", "João Silva"), _FakeDoc("2", "Maria")]
        )
        result = kg._get_perfil_pessoas_cache(db)
        self.assertEqual(len(result), 2)
        self.assertEqual(db.collection.return_value.stream.call_count, 2)

    def test_force_reload_ignora_ttl(self):
        db = _fake_db([_FakeDoc("1", "João Silva")])
        kg._get_perfil_pessoas_cache(db)
        kg._get_perfil_pessoas_cache(db, force_reload=True)
        self.assertEqual(db.collection.return_value.stream.call_count, 2)

    def test_add_atualiza_cache_sem_consultar_banco_de_novo(self):
        db = _fake_db([])
        kg._get_perfil_pessoas_cache(db)
        kg._perfil_pessoas_cache_add("novo-id", "Carlos Pereira")
        result = kg._get_perfil_pessoas_cache(db)
        self.assertIn(("novo-id", "carlos pereira"), result)
        db.collection.return_value.stream.assert_called_once()

    def test_cacheia_colecao_vazia_dentro_do_ttl(self):
        db = _fake_db([])
        kg._get_perfil_pessoas_cache(db)
        kg._get_perfil_pessoas_cache(db)
        db.collection.return_value.stream.assert_called_once()


if __name__ == "__main__":
    unittest.main()
