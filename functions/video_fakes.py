"""Firestore em memória para os testes do Hermes Vídeo (test_video_*.py).

Diferente dos mocks de outros testes, suporta subcoleções (`cenas`, `clipes`),
`batch()` e uma transação compatível com o `@firestore.transactional` real —
o decorador chama `_begin`/`_commit`/`_clean_up`, então a transação precisa
existir de verdade para o teste exercitar o mesmo caminho da produção.
"""
from __future__ import annotations

import copy


class Snap:
    def __init__(self, ref, data):
        self.reference = ref
        self.id = ref.id
        self._data = copy.deepcopy(data) if data is not None else None
        self.exists = data is not None

    def to_dict(self):
        return copy.deepcopy(self._data) if self._data is not None else None


class DocRef:
    def __init__(self, db, caminho: str):
        self._db = db
        self.path = caminho
        self.id = caminho.rsplit("/", 1)[-1]

    def get(self, transaction=None):
        return Snap(self, self._db.docs.get(self.path))

    def set(self, data, merge=False):
        if merge and self.path in self._db.docs:
            self._db.docs[self.path].update(copy.deepcopy(data))
        else:
            self._db.docs[self.path] = copy.deepcopy(data)
        self._db.escritas += 1

    def update(self, data):
        if self.path not in self._db.docs:
            raise KeyError(f"{self.path} não existe")
        self._db.docs[self.path].update(copy.deepcopy(data))
        self._db.escritas += 1

    def collection(self, nome):
        return Colecao(self._db, f"{self.path}/{nome}")


class Colecao:
    def __init__(self, db, caminho: str):
        self._db = db
        self.path = caminho

    def document(self, doc_id: str | None = None):
        if not doc_id:
            self._db.contador += 1
            doc_id = f"auto{self._db.contador:04d}"
        return DocRef(self._db, f"{self.path}/{doc_id}")

    def stream(self):
        prefixo = self.path + "/"
        for caminho in sorted(self._db.docs):
            resto = caminho[len(prefixo):] if caminho.startswith(prefixo) else None
            if resto and "/" not in resto:
                yield Snap(DocRef(self._db, caminho), self._db.docs[caminho])


class Batch:
    def __init__(self, db):
        self._db = db
        self._ops = []

    def set(self, ref, data, merge=False):
        self._ops.append((ref, data, merge))

    def commit(self):
        if self._db.falhar_commit:
            raise RuntimeError("commit falhou")
        for ref, data, merge in self._ops:
            ref.set(data, merge=merge)


class Transacao:
    """Como no Firestore real, as escritas ficam no buffer e só valem no commit;
    se a função levantar, o decorador faz rollback e nada é gravado."""

    def __init__(self, db):
        self._db = db
        self._read_only = False
        self._id = None
        self._max_attempts = 5
        self._ops = []

    def get(self, ref):
        return ref.get(transaction=self)

    def update(self, ref, data):
        self._ops.append(("update", ref, data, False))

    def set(self, ref, data, merge=False):
        self._ops.append(("set", ref, data, merge))

    def _begin(self, retry_id=None):
        self._id = retry_id or b"tx"
        self._ops = []

    def _commit(self):
        for op, ref, data, merge in self._ops:
            ref.update(data) if op == "update" else ref.set(data, merge=merge)
        self._ops = []
        return []

    def _rollback(self):
        self._ops = []
        self._id = None

    def _clean_up(self):
        self._id = None


class FakeDb:
    def __init__(self):
        self.docs: dict[str, dict] = {}
        self.contador = 0
        self.escritas = 0
        self.falhar_commit = False

    def collection(self, nome):
        return Colecao(self, nome)

    def batch(self):
        return Batch(self)

    def transaction(self):
        return Transacao(self)
