"""Testes diretos de `main.py::claim_action_dedup_slot`/`store_action_dedup_result`/
`release_action_dedup_slot` -- P03 sub-entrega 16/N.

A classificação IDEMPOTENTE de `criar_acao_no_sistema` (ver `tools/inventory.py`,
`idempotencia`) depende inteiramente deste mecanismo de dedup. Achado da 2ª rodada
de revisão adversarial desta sub-entrega: `claim_action_dedup_slot` não tinha
NENHUM teste dedicado em toda a suíte antes deste arquivo -- a classificação
estava apoiada só em leitura de código, não em comportamento executado. Este
arquivo prova as duas metades da nota da classificação: (1) repetir a MESMA
chamada (titulo/data_limite/horario_inicio) DENTRO da janela de
`ttl_minutes=15` devolve o `task_id` já criado, sem reivindicar um novo slot;
(2) repetir a MESMA chamada DEPOIS dessa janela não é mais deduplicada -- a
classificação é honesta sobre esse limite, não um "idempotente" incondicional.

Fake Firestore mínimo: só o que `claim_action_dedup_slot` de fato usa
(`collection().document().create()/.get()/.set()/.delete()`), com `create()`
levantando (capturado por `except Exception` na função real) quando a chave já
existe -- mesma semântica de exclusão mútua do Firestore real que a função
depende para ser atômica.
"""

from __future__ import annotations

import hashlib
import unittest
from datetime import datetime, timedelta, timezone

from main import claim_action_dedup_slot, release_action_dedup_slot, store_action_dedup_result


class _Snap:
    def __init__(self, data):
        self._data = data
        self.exists = data is not None

    def to_dict(self):
        return dict(self._data) if self._data is not None else None


class _DocRef:
    def __init__(self, store, key):
        self._store = store
        self._key = key

    def create(self, data):
        if self._key in self._store:
            raise RuntimeError("already exists")
        self._store[self._key] = dict(data)

    def get(self):
        return _Snap(self._store.get(self._key))

    def set(self, data, merge=False):
        if merge and self._key in self._store:
            self._store[self._key].update(data)
        else:
            self._store[self._key] = dict(data)

    def delete(self):
        self._store.pop(self._key, None)


class _Collection:
    def __init__(self, store):
        self._store = store

    def document(self, key):
        return _DocRef(self._store, key)


class _Db:
    def __init__(self):
        self._collections: dict[str, dict] = {}

    def collection(self, name):
        return _Collection(self._collections.setdefault(name, {}))


def _chave(titulo: str, data_limite: str, horario_inicio: str | None) -> str:
    # Mesma derivação de tools/inventory.py's contraparte documentada na nota
    # -- ver main.py::claim_action_dedup_slot.
    key_raw = f"{(titulo or '').strip().lower()}|{data_limite}|{horario_inicio}"
    return "aclock_" + hashlib.sha1(key_raw.encode("utf-8")).hexdigest()[:24]


class ClaimActionDedupSlotTest(unittest.TestCase):
    def test_primeira_chamada_reivindica_e_devolve_proceed(self):
        db = _Db()
        status, task_id = claim_action_dedup_slot(db, "Enviar declaracao", "2026-09-14", "10:00")
        self.assertEqual(status, "proceed")
        self.assertIsNone(task_id)

    def test_repetir_apos_store_devolve_duplicate_com_o_mesmo_task_id(self):
        # Sequência real: proceed -> cria a ação -> store_action_dedup_result
        # grava o task_id -> uma SEGUNDA chamada com os MESMOS
        # titulo/data_limite/horario_inicio tem que devolver
        # ("duplicate", task_id), sem reivindicar um novo slot nem criar uma
        # segunda ação -- é isso que sustenta idempotentHint=True.
        db = _Db()
        status, _ = claim_action_dedup_slot(db, "Enviar declaracao", "2026-09-14", "10:00")
        self.assertEqual(status, "proceed")
        store_action_dedup_result(db, "Enviar declaracao", "2026-09-14", "10:00", "task-abc123")

        status2, task_id2 = claim_action_dedup_slot(db, "Enviar declaracao", "2026-09-14", "10:00")
        self.assertEqual(status2, "duplicate")
        self.assertEqual(task_id2, "task-abc123")

    def test_titulo_com_variacao_de_maiuscula_e_espacos_ainda_dedupla(self):
        # A chave usa (titulo or "").strip().lower() -- variação de
        # maiúsculas/espaços do MESMO título não deveria escapar do dedup.
        db = _Db()
        claim_action_dedup_slot(db, "Enviar Declaracao", "2026-09-14", "10:00")
        store_action_dedup_result(db, "Enviar Declaracao", "2026-09-14", "10:00", "task-abc123")

        status, task_id = claim_action_dedup_slot(db, "  enviar declaracao  ", "2026-09-14", "10:00")
        self.assertEqual(status, "duplicate")
        self.assertEqual(task_id, "task-abc123")

    def test_titulo_diferente_nao_e_deduplicado(self):
        db = _Db()
        claim_action_dedup_slot(db, "Enviar declaracao", "2026-09-14", "10:00")
        store_action_dedup_result(db, "Enviar declaracao", "2026-09-14", "10:00", "task-abc123")

        status, task_id = claim_action_dedup_slot(db, "Outra acao", "2026-09-14", "10:00")
        self.assertEqual(status, "proceed")
        self.assertIsNone(task_id)

    def test_apos_ttl_expirado_a_mesma_chamada_nao_e_mais_deduplicada(self):
        # P03 sub-entrega 16/N: a classificação IDEMPOTENTE de
        # criar_acao_no_sistema, na nota do inventário, é explícita que o
        # dedup só vale DENTRO da janela de ttl_minutes=15 (padrão) -- este
        # teste prova a outra metade dessa nota: uma reivindicação já
        # expirada não impede uma nova (repetir a MESMA chamada depois do
        # TTL cria uma ação nova, não é idempotente sem limite de tempo).
        db = _Db()
        claim_antigo = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()
        chave = _chave("Enviar declaracao", "2026-09-14", "10:00")
        db.collection("action_creation_claims").document(chave).create(
            {"claimed_at": claim_antigo, "task_id": "task-velho"}
        )

        status, task_id = claim_action_dedup_slot(db, "Enviar declaracao", "2026-09-14", "10:00")
        self.assertEqual(status, "proceed")
        self.assertIsNone(task_id)

    def test_reivindicacao_concorrente_ainda_sem_task_id_devolve_pending(self):
        # Uma segunda chamada que chega enquanto a primeira ainda está
        # criando a ação (task_id ainda None) não deve prosseguir nem
        # devolver "duplicate" -- devolve "pending", para o chamador recusar
        # em vez de arriscar duplicata.
        db = _Db()
        status, _ = claim_action_dedup_slot(db, "Enviar declaracao", "2026-09-14", "10:00")
        self.assertEqual(status, "proceed")
        # Sem store_action_dedup_result -- task_id continua None no claim.

        status2, task_id2 = claim_action_dedup_slot(db, "Enviar declaracao", "2026-09-14", "10:00")
        self.assertEqual(status2, "pending")
        self.assertIsNone(task_id2)


class ReleaseActionDedupSlotTest(unittest.TestCase):
    def test_release_libera_o_slot_para_nova_reivindicacao(self):
        db = _Db()
        claim_action_dedup_slot(db, "Enviar declaracao", "2026-09-14", "10:00")
        release_action_dedup_slot(db, "Enviar declaracao", "2026-09-14", "10:00")

        status, task_id = claim_action_dedup_slot(db, "Enviar declaracao", "2026-09-14", "10:00")
        self.assertEqual(status, "proceed")
        self.assertIsNone(task_id)


if __name__ == "__main__":
    unittest.main()
