"""P03 sub-entrega 22/N (idempotentHint por handler): prova por handler REAL,
não só por leitura de código, que `confirmar_edicao_acao` é NAO_IDEMPOTENTE
-- ver tools/inventory.py::Idempotencia e a nota da entrada
`confirmar_edicao_acao`.

Mesma técnica de test_confirmar_lote_nao_idempotente.py (P03 sub-entrega
21/N): `inspect.unwrap()` tira a decoração `@https_fn.on_call` (exige
contexto de app Flask ativo, indisponível fora do emulador/deploy) e chega
na função real de `main.py`. Diferença de FakeDB: `main.py::
confirmarEdicaoAcao` faz `task_ref.get()` ANTES de gravar (as callables em
lote da sub-entrega 21/N são grava-cega, sem leitura prévia) -- o FakeDB
aqui precisa de um snapshot de leitura que reflita a própria escrita
anterior, não só de captura passiva de update().

Dois cenários provados, correspondendo à nota do inventário:
1. Sem `snapshot_ts` (mesmo caminho de `editar_acao`, que nunca envia esse
   campo): repetir a MESMA chamada grava DUAS notas de diário -- a raiz de
   não-idempotência já estabelecida para todo o grupo edição/edição-em-lote
   (sub-entregas 16/N e 21/N).
2. Com `snapshot_ts` (fluxo normal desta tool -- é a contraparte de
   `preparar_edicao_acao`, que devolve esse valor especificamente para uso
   aqui): a PRIMEIRA chamada grava a nota e reescreve `data_atualizacao`; a
   SEGUNDA chamada, com o MESMO `snapshot_ts` (agora desatualizado), falha
   com `status: 'invalidated'` SEM gravar nada -- uma auto-limitação real
   que o grupo em lote da sub-entrega 21/N não tem. Isso não torna a tool
   idempotente de verdade: a segunda chamada devolve um resultado DIFERENTE
   da primeira (erro, não o mesmo sucesso) -- por isso a classificação
   continua NAO_IDEMPOTENTE, mesmo critério conservador já usado no resto
   deste inventário.
"""

from __future__ import annotations

import inspect
import unittest
from unittest.mock import patch


class _FakeTaskSnapshot:
    def __init__(self, exists, data):
        self.exists = exists
        self._data = data

    def to_dict(self):
        return dict(self._data)


class _FakeTaskRef:
    def __init__(self, store, task_id):
        self._store = store
        self._task_id = task_id

    def get(self):
        data = self._store.get(self._task_id)
        return _FakeTaskSnapshot(data is not None, data or {})

    def update(self, updates):
        current = dict(self._store.get(self._task_id) or {})
        for key, value in updates.items():
            if key == "acompanhamento":
                # firestore.ArrayUnion([diary_entry]) -- mesma semântica do
                # Firestore real: concatena na lista já existente.
                existente = list(current.get("acompanhamento") or [])
                current["acompanhamento"] = existente + list(value.values)
            else:
                current[key] = value
        self._store[self._task_id] = current


class _FakeCollection:
    def __init__(self, store):
        self._store = store

    def document(self, task_id):
        return _FakeTaskRef(self._store, task_id)


class _FakeDB:
    """Só `tarefas` -- suficiente porque o request de teste nunca envia
    `sessionId`/`messageId` (card do copiloto web, fora do escopo do MCP),
    então `_set_card_status` sai cedo sem tocar `sessoes_copiloto`."""

    def __init__(self, tarefas_iniciais):
        self._store = dict(tarefas_iniciais)

    def collection(self, name):
        assert name == "tarefas", f"FakeDB só cobre 'tarefas', pediu {name!r}"
        return _FakeCollection(self._store)

    def snapshot_de(self, task_id):
        return dict(self._store[task_id])


def _fake_request(data: dict):
    # `req.data` é tudo que `confirmarEdicaoAcao` lê de
    # `https_fn.CallableRequest` -- um objeto qualquer com esse atributo
    # basta, sem precisar do SDK real.
    return type("FakeCallableRequest", (), {"data": data})()


class TestConfirmarEdicaoAcaoNaoIdempotente(unittest.TestCase):
    def _handler_real(self):
        import main

        return inspect.unwrap(main.confirmarEdicaoAcao)

    def test_sem_snapshot_ts_repetir_a_mesma_chamada_acrescenta_segunda_nota(self):
        fn = self._handler_real()
        db = _FakeDB({
            "t1": {"status": "em andamento", "data_criacao": "2026-01-01T00:00:00+00:00"},
        })

        with patch("main.get_db", return_value=db):
            req = _fake_request({"taskId": "t1", "alteracoes": {"notas": "revisado"}})
            r1 = fn(req)
            r2 = fn(req)  # MESMA chamada, de novo, sem snapshot_ts

        snap = db.snapshot_de("t1")
        self.assertEqual(r1["status"], "completed")
        self.assertEqual(r2["status"], "completed")
        self.assertEqual(snap["notas"], "revisado")

        # O valor do campo converge ('notas' fica 'revisado' nas duas), mas
        # o diário cresce a cada chamada -- efeito adicional, não uma
        # convergência de estado. NAO_IDEMPOTENTE.
        self.assertEqual(len(snap["acompanhamento"]), 2)
        self.assertNotEqual(
            snap["acompanhamento"][0]["data"], snap["acompanhamento"][1]["data"],
            "as duas chamadas deveriam gravar timestamps diferentes -- se "
            "iguais, o teste não está de fato provando duas chamadas "
            "distintas",
        )

    def test_com_snapshot_ts_segunda_chamada_identica_falha_em_vez_de_duplicar(self):
        snapshot_ts_original = "2026-01-01T00:00:00+00:00"
        fn = self._handler_real()
        db = _FakeDB({"t1": {"status": "em andamento", "data_criacao": snapshot_ts_original}})

        with patch("main.get_db", return_value=db):
            req = _fake_request({
                "taskId": "t1",
                "alteracoes": {"notas": "revisado"},
                "snapshotTs": snapshot_ts_original,
            })
            r1 = fn(req)
            snap_depois_da_1a = db.snapshot_de("t1")
            r2 = fn(req)  # MESMA chamada, MESMO snapshot_ts (agora obsoleto)
            snap_depois_da_2a = db.snapshot_de("t1")

        self.assertEqual(r1["status"], "completed")
        self.assertEqual(r2["status"], "invalidated")

        # A segunda chamada não duplicou a nota -- ela não gravou nada, só
        # recusou. Prova que a auto-limitação é real (bloqueio antes da
        # escrita), não só um status de erro que a callable devolve depois
        # de já ter gravado mesmo assim.
        self.assertEqual(len(snap_depois_da_1a["acompanhamento"]), 1)
        self.assertEqual(snap_depois_da_2a, snap_depois_da_1a)

    def test_tool_mcp_repassa_snapshot_ts_opcional_para_a_callable(self):
        """Prova a delegação em si -- `tools/hermes_tools.py::_map_confirmar_
        edicao_acao` repassa `snapshot_ts` (nome do schema, snake_case) para
        `snapshotTs` (nome que a callable espera), inclusive quando omitido
        (vira string vazia, não None, mesmo comportamento de "sem
        snapshot_ts" provado no primeiro teste). O efeito colateral em si já
        está provado pelos dois testes de handler real acima; este só
        confere que a tool MCP não perde nem inventa esse parâmetro no
        caminho até lá."""
        from tools import hermes_tools

        capturado = []

        class _FalsoInvokeCallable:
            def __call__(self, callable_fn, data, uid=None, token=None):
                capturado.append(dict(data))
                return {"status": "completed", "campos_alterados": sorted((data.get("alteracoes") or {}).keys())}

        handler = hermes_tools._HANDLERS["confirmar_edicao_acao"]
        ctx = type("Ctx", (), {"user_uid": "uid", "session_id": "s1"})()

        with patch("tools.callable_bridge.invoke_callable", new=_FalsoInvokeCallable()):
            handler(ctx, {"task_id": "t1", "alteracoes": {"notas": "x"}, "snapshot_ts": "abc"})
            handler(ctx, {"task_id": "t1", "alteracoes": {"notas": "x"}})

        self.assertEqual(capturado[0]["snapshotTs"], "abc")
        self.assertEqual(capturado[1]["snapshotTs"], "")


if __name__ == "__main__":
    unittest.main()
