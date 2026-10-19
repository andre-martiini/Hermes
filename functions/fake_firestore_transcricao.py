"""Firestore em memória para os testes da transcrição ao vivo.

Cobre só o que `transcricao_ao_vivo.py` e as tools de leitura usam: documento,
subcoleção, transação (grava tudo no fim ou nada) e consulta com where,
order_by e limit. Não é um simulador geral do Firestore.
"""
from __future__ import annotations

import copy


class _Snap:
    def __init__(self, ref, dados):
        self.reference = ref
        self.id = ref.id
        self._dados = dados

    @property
    def exists(self):
        return self._dados is not None

    def to_dict(self):
        return copy.deepcopy(self._dados) if self._dados is not None else None

    def get(self, campo):
        return (self._dados or {}).get(campo)


class FakeDoc:
    def __init__(self, db, caminho: str):
        self._db = db
        self.path = caminho
        self.id = caminho.rsplit("/", 1)[-1]

    def get(self, transaction=None):
        self._db.leituras += 1
        return _Snap(self, copy.deepcopy(self._db.docs.get(self.path)))

    def set(self, dados, merge=False):
        if merge and self.path in self._db.docs:
            self._db.docs[self.path].update(copy.deepcopy(dados))
        else:
            self._db.docs[self.path] = copy.deepcopy(dados)

    def update(self, dados):
        if self.path not in self._db.docs:
            raise KeyError(f"documento inexistente: {self.path}")
        self._db.docs[self.path].update(copy.deepcopy(dados))

    def collection(self, nome):
        return FakeColecao(self._db, f"{self.path}/{nome}")


class FakeConsulta:
    def __init__(self, colecao, filtros=(), ordem=(), limite=None):
        self._col = colecao
        self._filtros = list(filtros)
        self._ordem = list(ordem)
        self._limite = limite

    def where(self, campo=None, op=None, valor=None, *, filter=None):
        if filter is not None:
            campo, op, valor = filter.field_path, filter.op_string, filter.value
        return FakeConsulta(self._col, self._filtros + [(campo, op, valor)], self._ordem, self._limite)

    def order_by(self, campo, direction="ASCENDING"):
        return FakeConsulta(self._col, self._filtros, self._ordem + [(campo, direction)], self._limite)

    def limit(self, n):
        return FakeConsulta(self._col, self._filtros, self._ordem, n)

    def stream(self):
        ops = {
            "==": lambda a, b: a == b, ">": lambda a, b: a is not None and a > b,
            ">=": lambda a, b: a is not None and a >= b, "<": lambda a, b: a is not None and a < b,
            "<=": lambda a, b: a is not None and a <= b,
        }
        itens = []
        for ref, dados in self._col._filhos():
            if all(ops[op](dados.get(campo), valor) for campo, op, valor in self._filtros):
                itens.append((ref, dados))
        for campo, direcao in reversed(self._ordem):
            itens.sort(key=lambda par: (par[1].get(campo) is None, par[1].get(campo)),
                       reverse=str(direcao).upper().startswith("DESC"))
        if self._limite is not None:
            itens = itens[: self._limite]
        self._col._db.leituras += max(1, len(itens))
        return iter([_Snap(ref, copy.deepcopy(dados)) for ref, dados in itens])

    def get(self):
        return list(self.stream())


class FakeColecao(FakeConsulta):
    def __init__(self, db, caminho: str):
        self._db = db
        self.path = caminho
        super().__init__(self)

    def document(self, doc_id):
        if "/" in str(doc_id):  # como o Firestore: id com barra vira outro caminho e é recusado
            raise ValueError("id de documento com barra")
        return FakeDoc(self._db, f"{self.path}/{doc_id}")

    def _filhos(self):
        prefixo = self.path + "/"
        for caminho, dados in sorted(self._db.docs.items()):
            resto = caminho[len(prefixo):] if caminho.startswith(prefixo) else None
            if resto and "/" not in resto:
                yield FakeDoc(self._db, caminho), dados


class FakeTx:
    """Guarda as escritas e só aplica no commit: exceção no meio não grava nada."""

    def __init__(self):
        self._escritas = []

    def set(self, ref, dados, merge=False):
        self._escritas.append(("set", ref, dados))

    def update(self, ref, dados):
        self._escritas.append(("update", ref, dados))

    def commit(self):
        for tipo, ref, dados in self._escritas:
            getattr(ref, tipo)(dados)


class FakeDb:
    def __init__(self):
        self.docs: dict[str, dict] = {}
        self.leituras = 0

    def collection(self, nome):
        return FakeColecao(self, nome)


def em_transacao_falsa(db, corpo):
    """Substitui `transcricao_ao_vivo._em_transacao` nos testes."""
    tx = FakeTx()
    resultado = corpo(tx)
    tx.commit()
    return resultado
