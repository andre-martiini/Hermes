"""P03 sub-entrega 21/N (idempotentHint por handler): prova por handler REAL,
não só por leitura de código, que o grupo edição/reagendamento em lote de
ações é NAO_IDEMPOTENTE -- ver tools/inventory.py::Idempotencia e a nota de
cada uma das 4 tools (`confirmar_edicao_em_lote`, `editar_acoes_em_lote`,
`confirmar_reagendamento_em_lote`, `reagendar_acoes_em_lote`).

`main.confirmarEdicaoEmLote`/`main.confirmarReagendamentoEmLote` importam
normalmente neste venv (mesmo precedente já usado em test_secretario_
whatsapp.py, `import main` dentro do teste) -- diferente do comentário em
test_hermes_tools.py sobre "main.py não importa fora do venv de deploy", que
é sobre RODAR os testes SEM o venv completo instalado, não sobre a
impossibilidade do import em si. Chamar a função diretamente, porém, esbarra
no decorador `@https_fn.on_call(cors=...)`: ele exige um contexto de app
Flask ativo (RuntimeError "Working outside of application context" fora do
emulador/deploy) -- `inspect.unwrap()` tira a decoração e chega na função
real, mesma técnica já usada em
test_secretario_whatsapp.py::TestAutomationSettingsCallable.

Estratégia: um FakeDB mínimo (só `collection().document()`, `.get()` do
documento e `batch()`) que grava cada `batch.update(ref, data)` numa lista,
para poder inspecionar quantas vezes e com que `acompanhamento` cada chamada
gravou. O `.get()` existe só porque `confirmarEdicaoEmLote` lê o status ATUAL
da ação antes de escrever, para pular item 'excluído' sem pedido de reabertura
(bloqueio que só o passo de propor tinha); o fake devolve uma ação existente e
ativa, para não alterar o caminho que este arquivo quer provar.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from tools import hermes_tools


class _FakeSnapshot:
    exists = True

    def to_dict(self):
        return {"status": "em andamento"}


class _FakeDocRef:
    def __init__(self, task_id):
        self.id = task_id

    def get(self):
        return _FakeSnapshot()


class _FakeCollection:
    def document(self, task_id):
        return _FakeDocRef(task_id)


class _FakeBatch:
    def __init__(self):
        self.updates = []

    def update(self, ref, data):
        self.updates.append((ref, data))

    def commit(self):
        pass


class _FakeDB:
    """Só o suficiente para as duas callables (ver docstring do módulo)."""

    def __init__(self):
        self.last_batch: _FakeBatch | None = None

    def collection(self, _name):
        return _FakeCollection()

    def batch(self):
        self.last_batch = _FakeBatch()
        return self.last_batch


def _fake_request(data: dict):
    # `req.data` é tudo que as duas callables leem de `https_fn.CallableRequest`
    # -- um objeto qualquer com esse atributo basta, sem precisar do SDK real.
    return type("FakeCallableRequest", (), {"data": data})()


class TestConfirmarEdicaoEmLoteNaoIdempotente(unittest.TestCase):
    """`main.py::confirmarEdicaoEmLote` -- usada tanto por `confirmar_edicao_
    em_lote` (chamada direta) quanto por `editar_acoes_em_lote` (mesma
    callable, só troca o nome do parâmetro de entrada)."""

    def test_repetir_a_mesma_chamada_acrescenta_segunda_nota_ao_diario(self):
        import inspect
        import main

        # `inspect.unwrap` tira a decoração `@https_fn.on_call` (que exige um
        # contexto de app Flask ativo, indisponível fora do emulador/deploy)
        # e chega na função real -- mesma técnica já usada em
        # test_secretario_whatsapp.py::TestAutomationSettingsCallable.
        fn = inspect.unwrap(main.confirmarEdicaoEmLote)

        db = _FakeDB()
        with patch("main.get_db", return_value=db):
            items = [{"task_id": "t1", "alteracoes": {"notas": "revisado"}}]
            req = _fake_request({"items": items, "justificativa": "teste"})

            r1 = fn(req)
            batch1 = db.last_batch
            r2 = fn(req)  # MESMA chamada, de novo
            batch2 = db.last_batch

        # O valor do campo em si converge -- 'notas' fica 'revisado' nas duas.
        self.assertEqual(r1["status"], "completed")
        self.assertEqual(r2["status"], "completed")
        self.assertEqual(batch1.updates[0][1]["notas"], "revisado")
        self.assertEqual(batch2.updates[0][1]["notas"], "revisado")

        # Mas cada chamada grava a SUA PRÓPRIA nota no diário (ArrayUnion com
        # um diary_entry novo, timestamp novo) -- efeito adicional a cada
        # repetição, não uma convergência de estado. NAO_IDEMPOTENTE.
        nota1 = batch1.updates[0][1]["acompanhamento"]
        nota2 = batch2.updates[0][1]["acompanhamento"]
        self.assertEqual(len(nota1.values), 1)
        self.assertEqual(len(nota2.values), 1)
        self.assertNotEqual(
            nota1.values[0]["data"], nota2.values[0]["data"],
            "as duas chamadas deveriam gravar timestamps diferentes -- se "
            "iguais, o teste não está de fato provando duas chamadas "
            "distintas",
        )
        # `data_atualizacao` também é reescrito, incondicionalmente, a cada
        # chamada bem-sucedida -- mais um campo que muda a cada repetição.
        self.assertNotEqual(
            batch1.updates[0][1]["data_atualizacao"],
            batch2.updates[0][1]["data_atualizacao"],
        )

    def test_editar_acoes_em_lote_delega_para_a_mesma_callable_nao_idempotente(self):
        """`tools/hermes_tools.py::editar_acoes_em_lote` não é uma implementação
        própria -- é `_via_callable("confirmarEdicaoEmLote", ...)`, a MESMA
        callable provada não-idempotente acima. Prova aqui só a delegação
        (o nome da callable e o remapeamento itens->items); o efeito
        colateral em si já está provado pelo teste anterior."""
        capturado = []

        class _FalsoInvokeCallable:
            def __call__(self, callable_fn, data, uid=None, token=None):
                capturado.append(dict(data))
                return {"status": "completed", "count": len(data.get("items") or [])}

        with patch("tools.callable_bridge.invoke_callable", new=_FalsoInvokeCallable()):
            ctx = type("Ctx", (), {"user_uid": "uid", "session_id": "s1"})()
            hermes_tools.editar_acoes_em_lote(ctx, {
                "itens": [{"task_id": "t1", "alteracoes": {"notas": "x"}}],
                "justificativa": "lote",
            })
            hermes_tools.editar_acoes_em_lote(ctx, {
                "itens": [{"task_id": "t1", "alteracoes": {"notas": "x"}}],
                "justificativa": "lote",
            })

        # Duas chamadas idênticas -> duas invocações da callable, sem
        # dedup nenhum no wrapper Python -- o wrapper não protege o que a
        # callable já não protege.
        self.assertEqual(len(capturado), 2)
        self.assertEqual(capturado[0]["items"], capturado[1]["items"])


class TestConfirmarReagendamentoEmLoteNaoIdempotente(unittest.TestCase):
    """`main.py::confirmarReagendamentoEmLote` -- usada tanto por `confirmar_
    reagendamento_em_lote` (chamada direta) quanto por `reagendar_acoes_
    em_lote` (via `preparar_reagendamento_em_lote` + esta mesma callable)."""

    def test_repetir_a_mesma_chamada_acrescenta_segunda_nota_ao_diario(self):
        import inspect
        import main

        fn = inspect.unwrap(main.confirmarReagendamentoEmLote)

        db = _FakeDB()
        with patch("main.get_db", return_value=db):
            items = [{"task_id": "t1", "nova_data_limite": "2026-10-01"}]
            req = _fake_request({"items": items, "justificativa": "teste"})

            fn(req)
            batch1 = db.last_batch
            fn(req)  # MESMA chamada, de novo
            batch2 = db.last_batch

        self.assertEqual(batch1.updates[0][1]["data_limite"], "2026-10-01")
        self.assertEqual(batch2.updates[0][1]["data_limite"], "2026-10-01")

        nota1 = batch1.updates[0][1]["acompanhamento"]
        nota2 = batch2.updates[0][1]["acompanhamento"]
        self.assertNotEqual(nota1.values[0]["data"], nota2.values[0]["data"])
        self.assertNotEqual(
            batch1.updates[0][1]["data_atualizacao"],
            batch2.updates[0][1]["data_atualizacao"],
        )

    def test_reagendar_acoes_em_lote_nao_pula_a_confirmacao_em_repeticao(self):
        """`tools/hermes_tools.py::reagendar_acoes_em_lote` chama de novo o
        passo de preparação a cada invocação (não é descartado, só a
        ida-e-volta ao cliente é) -- aqui a preparação é mockada para
        devolver sempre os MESMOS itens (simula seleção por `task_ids`
        explícito, onde o conjunto não muda entre chamadas), e o teste prova
        que a confirmação é acionada as DUAS vezes, sem nenhum atalho de
        'já apliquei isso'."""
        import json

        proposta = json.dumps({
            "items": [{"task_id": "t1", "nova_data_limite": "2026-10-01"}],
            "justificativa": "reagendamento",
        })
        chamadas_confirmar = []

        def _falso_via_callable(nome_callable, mapear=None):
            def handler(ctx, args):
                chamadas_confirmar.append((nome_callable, dict(args)))
                return {"status": "completed", "count": len(args.get("items") or [])}
            return handler

        with patch("tools.hermes_tools.execute", return_value=proposta), \
             patch.object(hermes_tools, "_via_callable", side_effect=_falso_via_callable):
            ctx = type("Ctx", (), {"user_uid": "uid", "session_id": "s1"})()
            hermes_tools.reagendar_acoes_em_lote(ctx, {"task_ids": ["t1"], "nova_data_inicio": "2026-10-01"})
            hermes_tools.reagendar_acoes_em_lote(ctx, {"task_ids": ["t1"], "nova_data_inicio": "2026-10-01"})

        self.assertEqual(len(chamadas_confirmar), 2)
        self.assertEqual(chamadas_confirmar[0][0], "confirmarReagendamentoEmLote")
        self.assertEqual(chamadas_confirmar[0][1]["items"], chamadas_confirmar[1][1]["items"])

    def test_filtro_data_apos_sucesso_tende_a_nao_encontrar_mais_nada(self):
        """Nuance documentada em tools/inventory.py: quando a seleção é por
        `filtro_data` (em vez de `task_ids`), a PREPARAÇÃO filtra por
        `data_limite == filtro_data` -- exatamente o campo que a confirmação
        muda. Aqui simulamos isso via `execute` devolvendo erro na segunda
        chamada (o efeito real de `_coletar_tarefas_lote` não achar mais
        nada) e provamos que `reagendar_acoes_em_lote` propaga esse erro sem
        chamar a confirmação de novo -- uma auto-limitação parcial, não uma
        proteção transacional."""
        respostas = iter([
            __import__("json").dumps({
                "items": [{"task_id": "t1", "nova_data_limite": "2026-10-01"}],
                "justificativa": "reagendamento",
            }),
            "ERRO|Nenhuma acao encontrada com os criterios informados.",
        ])
        chamadas_confirmar = []

        def _falso_execute(nome, args, ctx):
            return next(respostas)

        def _falso_via_callable(nome_callable, mapear=None):
            def handler(ctx, args):
                chamadas_confirmar.append(nome_callable)
                return {"status": "completed", "count": len(args.get("items") or [])}
            return handler

        with patch("tools.hermes_tools.execute", side_effect=_falso_execute), \
             patch.object(hermes_tools, "_via_callable", side_effect=_falso_via_callable):
            ctx = type("Ctx", (), {"user_uid": "uid", "session_id": "s1"})()
            r1 = hermes_tools.reagendar_acoes_em_lote(ctx, {"filtro_data": "2026-09-20", "nova_data_inicio": "2026-10-01"})
            r2 = hermes_tools.reagendar_acoes_em_lote(ctx, {"filtro_data": "2026-09-20", "nova_data_inicio": "2026-10-01"})

        self.assertEqual(len(chamadas_confirmar), 1, "a 2a chamada nao deveria ter confirmado nada")
        self.assertTrue(isinstance(r2, str) and r2.startswith("ERRO|"))


if __name__ == "__main__":
    unittest.main()
