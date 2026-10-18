"""P06 sub-entrega -- corrige a seção "Memory context" de
`telegram_handlers_core.py::_process_telegram_message`.

Achado real do Codex (revisão automática da PR #434, comentário P1,
confirmado lendo o código): esta seção lia `knowledge_nodes` direto pelos
campos antigos `fato`/`categoria`, mas `main._save_memory_node` -- o
escritor compartilhado por MCP, pelo copiloto web e, desde a P06
sub-entrega 2/N, também pelo motor Telegram legado -- grava o fato em
`texto_memoria`/`tipo`, nunca em `fato`/`categoria` (confirmado lendo
`main.py::_save_memory_node`, linhas ~7446-7548: todo `.set()` daquela
função usa só `texto_memoria`/`tipo`). Resultado: nenhum fato gravado por
NENHUM canal aparecia neste bloco de contexto -- e, a partir da PR #434,
isso passou a valer até para fatos de origem Telegram (que antes usavam o
esquema antigo e portanto apareciam), tornando o bloco "MEMÓRIA GLOBAL
ATIVA" deste motor efetivamente morto para qualquer escrita nova.

A correção usa o mesmo fallback já estabelecido em dois outros lugares do
próprio repositório para esta exata divergência de esquema --
`copilot_context.py::_format_recent_memories` (`data.get("texto_memoria")
or data.get("fato")`) e `verificadores_escrita.py::salvar_memoria`
(`doc.get("texto_memoria") or doc.get("fato")`) -- então os primeiros três
testes abaixo cobrem exatamente essa regra: um documento no esquema NOVO
(`texto_memoria`/`tipo`, como `_save_memory_node` grava hoje, para os 3
canais) e um documento no esquema LEGADO (`fato`/`categoria`, como
`telegram_message_tools.py::salvar_memoria_global` gravava antes da P06
sub-entrega 2/N, e como qualquer nó antigo já existente em produção
continua gravado, sem migração retroativa).

COMPOSIÇÃO com a P06 sub-entrega 4/N (PR #451, `autonomy/temporal.py`,
já mesclada em main antes desta correção ser publicada): aquela
sub-entrega adicionou, na MESMA seção, um filtro que pula qualquer
documento com `memoria_status == "superada"` (fato substituído por uma
resolução de conflito) antes mesmo de olhar seu texto -- e seu próprio
diário (`test_memoria_supersedes.py`, docstring do módulo) registrou
explicitamente que esse filtro, dentro de `telegram_handlers_core.py`,
ficava SEM teste dedicado "por desproporção de custo", já que exigiria
mockar boa parte do pipeline Gemini/Telegram só para isso -- exatamente o
fake que este arquivo já constrói para testar o fallback de esquema.
`TestMemoriaContextoFiltraSuperadaComEsquemaNovo` fecha essa lacuna
(aproveitando a infraestrutura já presente aqui) ao mesmo tempo em que
prova que a ORDEM de composição é a correta: um fato no esquema NOVO
(`texto_memoria`/`tipo`) mas com `memoria_status="superada"` precisa
continuar fora do contexto -- o fallback de esquema é aditivo e nunca deve
reviver um fato que o filtro de proveniência temporal já descartou.

Fake de Firestore local (não reaproveita `test_outbox_aprovacao._MockDb`
porque esse mock não implementa `order_by`, usado por este bloco; segue o
mesmo padrão de `_Query`/`_Colecao` com `order_by`/`limit`/`stream` já
usado em `test_whatsapp_tools.py`, só o necessário para esta seção).
`_patches_do_handler` é uma cópia do helper homônimo de
`test_telegram_peso.py::TestCaminhosDoTelegram` -- mesmo conjunto mínimo de
mocks para `_process_telegram_message` alcançar o bloco de memória sem
precisar simular o motor Gemini/copiloto web inteiro (a tentativa real de
`_run_web_copilot_engine` contra este fake lança, é capturada pelo
`except Exception` do próprio `_process_telegram_message`, e o fluxo cai
para o caminho determinístico/Gemini -- mesmo comportamento já exercitado
por aqueles testes).
"""

import unittest
from unittest import mock


class _Snap:
    def __init__(self, id_, dados):
        self.id = id_
        self._d = dados

    def to_dict(self):
        return dict(self._d) if self._d is not None else {}


class _DocRef:
    def __init__(self, colecao, id_):
        self._col = colecao
        self.id = id_

    def set(self, valores, merge=False):
        if merge and self.id in self._col.dados:
            self._col.dados[self.id].update(valores)
        else:
            self._col.dados[self.id] = dict(valores)


class _Query:
    def __init__(self, colecao, docs):
        self._col = colecao
        self._docs = docs

    def order_by(self, campo, direction=None):
        ordenados = sorted(
            self._docs, key=lambda p: str(p[1].get(campo) or ""),
            reverse=str(direction or "").upper().startswith("DESC"),
        )
        return _Query(self._col, ordenados)

    def limit(self, n):
        return _Query(self._col, self._docs[:n])

    def stream(self):
        return [_Snap(i, d) for i, d in self._docs]


class _Colecao:
    def __init__(self):
        self.dados = {}
        self._seq = 0

    def order_by(self, *a, **k):
        return _Query(self, list(self.dados.items())).order_by(*a, **k)

    def document(self, doc_id=None):
        if doc_id is None:
            self._seq += 1
            doc_id = f"auto{self._seq}"
        return _DocRef(self, doc_id)


class _Db:
    def __init__(self):
        self._cols: dict[str, _Colecao] = {}

    def collection(self, nome):
        return self._cols.setdefault(nome, _Colecao())


def _patches_do_handler(**extras):
    patches = {
        "_get_api_keys": mock.Mock(return_value={"gemini_api_key": "gk", "telegram_bot_token": "tok"}),
        "_get_session": mock.Mock(return_value={}),
        "_ensure_copilot_session": mock.Mock(return_value="sessao"),
        "_save_session": mock.Mock(),
        "try_deterministic_reply": mock.Mock(return_value=False),
        "_cached_doc_get": mock.Mock(return_value=mock.Mock(exists=False)),
        "carregar_areas_tematicas_validas": mock.Mock(return_value=["GERAL"]),
        "_load_copilot_session_history": mock.Mock(return_value=[]),
        "_send_telegram_typing": mock.Mock(),
        "_send_telegram_session_message": mock.Mock(return_value=None),
        "_delete_telegram_message": mock.Mock(),
        "_persist_copilot_message": mock.Mock(),
    }
    patches.update(extras)
    return patches


# Mensagem com >= 4 palavras significativas (nenhuma stopword, todas com
# mais de 2 letras) -- é o que faz `_process_telegram_message` disparar a
# leitura de `knowledge_nodes` para montar o contexto de memória.
_TEXTO_COM_CONTEXTO = "preciso lembrar da viagem marcada semana"


class TestMemoriaContextoEsquemaNovo(unittest.TestCase):
    """Fato gravado por `_save_memory_node` (esquema atual, os 3 canais)."""

    def test_fato_em_texto_memoria_aparece_no_contexto(self):
        import telegram_handlers_core as thc

        db = _Db()
        db.collection("knowledge_nodes").document("mem-1").set({
            "texto_memoria": "André prefere reuniões pela manhã",
            "tipo": "preferencia",
            "data_criacao": "2026-10-10T10:00:00+00:00",
        })
        run_gemini = mock.Mock(return_value="ok")
        patches = _patches_do_handler(_run_gemini_turn=run_gemini)
        with mock.patch.multiple(thc, **patches):
            thc._process_telegram_message(db, {"chat_id": "123", "text": _TEXTO_COM_CONTEXTO})

        system_instruction = run_gemini.call_args.kwargs["system_instruction"]
        self.assertIn("MEMÓRIA GLOBAL ATIVA", system_instruction)
        self.assertIn("[preferencia] André prefere reuniões pela manhã", system_instruction)

    def test_fato_sem_texto_memoria_nem_fato_e_ignorado_sem_quebrar(self):
        """Nó de procedimento (knowledge_graph.py, forma diferente de
        documento, sem `texto_memoria`/`fato`) não deve aparecer no
        contexto nem lançar excecao -- comportamento já existente,
        preservado pela correção (fallback só adiciona uma 2a opção, nunca
        remove a checagem `if fato` que já existia)."""
        import telegram_handlers_core as thc

        db = _Db()
        db.collection("knowledge_nodes").document("proc-1").set({
            "nome_procedimento": "Fechar mês financeiro",
            "data_criacao": "2026-10-10T10:00:00+00:00",
        })
        run_gemini = mock.Mock(return_value="ok")
        patches = _patches_do_handler(_run_gemini_turn=run_gemini)
        with mock.patch.multiple(thc, **patches):
            thc._process_telegram_message(db, {"chat_id": "123", "text": _TEXTO_COM_CONTEXTO})

        system_instruction = run_gemini.call_args.kwargs["system_instruction"]
        self.assertNotIn("MEMÓRIA GLOBAL ATIVA", system_instruction)


class TestMemoriaContextoEsquemaLegado(unittest.TestCase):
    """Fato gravado no esquema ANTIGO (fato/categoria) -- qualquer nó já
    existente em produção antes da P06 sub-entrega 2/N, ou de um canal que
    um dia volte a gravar assim. Precisa continuar aparecendo: a correção é
    aditiva (fallback), nunca troca um esquema pelo outro."""

    def test_fato_no_esquema_antigo_continua_aparecendo(self):
        import telegram_handlers_core as thc

        db = _Db()
        db.collection("knowledge_nodes").document("mem-legado").set({
            "fato": "André mora em Vitória",
            "categoria": "fato_isolado",
            "data_criacao": "2026-09-01T10:00:00+00:00",
        })
        run_gemini = mock.Mock(return_value="ok")
        patches = _patches_do_handler(_run_gemini_turn=run_gemini)
        with mock.patch.multiple(thc, **patches):
            thc._process_telegram_message(db, {"chat_id": "123", "text": _TEXTO_COM_CONTEXTO})

        system_instruction = run_gemini.call_args.kwargs["system_instruction"]
        self.assertIn("MEMÓRIA GLOBAL ATIVA", system_instruction)
        self.assertIn("[fato_isolado] André mora em Vitória", system_instruction)


class TestMemoriaContextoOrdenacaoELimite(unittest.TestCase):
    """A 1a rodada de revisão adversarial desta sub-entrega notou que os
    testes acima inserem só 1 documento cada -- a interação real do código
    de produção, `.order_by("data_criacao", direction=DESCENDING).limit(4)`,
    nunca era exercitada com mais de um documento (qualquer corte/ordenação
    "funciona" trivialmente com 1 só). Este teste cobre isso: 6 documentos
    (mais que o `limit(4)`), misturando os dois esquemas (novo e legado), e
    confirma que só os 4 mais recentes por `data_criacao` aparecem, na
    ordem certa (mais recente primeiro) -- e que o mais antigo de todos
    (fora do corte) não aparece."""

    def test_so_os_4_mais_recentes_aparecem_na_ordem_certa(self):
        import telegram_handlers_core as thc

        db = _Db()
        docs = [
            ("mem-1", {"texto_memoria": "fato 1 (mais antigo, fora do limite)", "tipo": "x",
                       "data_criacao": "2026-10-01T10:00:00+00:00"}),
            ("mem-2", {"fato": "fato 2 (esquema legado)", "categoria": "y",
                       "data_criacao": "2026-10-02T10:00:00+00:00"}),
            ("mem-3", {"texto_memoria": "fato 3", "tipo": "z",
                       "data_criacao": "2026-10-03T10:00:00+00:00"}),
            ("mem-4", {"texto_memoria": "fato 4", "tipo": "w",
                       "data_criacao": "2026-10-04T10:00:00+00:00"}),
            ("mem-5", {"fato": "fato 5 (esquema legado)", "categoria": "v",
                       "data_criacao": "2026-10-05T10:00:00+00:00"}),
            ("mem-6", {"texto_memoria": "fato 6 (mais recente)", "tipo": "u",
                       "data_criacao": "2026-10-06T10:00:00+00:00"}),
        ]
        for doc_id, dados in docs:
            db.collection("knowledge_nodes").document(doc_id).set(dados)

        run_gemini = mock.Mock(return_value="ok")
        patches = _patches_do_handler(_run_gemini_turn=run_gemini)
        with mock.patch.multiple(thc, **patches):
            thc._process_telegram_message(db, {"chat_id": "123", "text": _TEXTO_COM_CONTEXTO})

        system_instruction = run_gemini.call_args.kwargs["system_instruction"]
        bloco = system_instruction.split("## MEMÓRIA GLOBAL ATIVA\n", 1)[1]
        linhas_memoria = [l for l in bloco.splitlines() if l.startswith("- [")]

        self.assertEqual(linhas_memoria, [
            "- [u] fato 6 (mais recente)",
            "- [v] fato 5 (esquema legado)",
            "- [w] fato 4",
            "- [z] fato 3",
        ])
        self.assertNotIn("fato 1", system_instruction)
        self.assertNotIn("fato 2", system_instruction)


class TestMemoriaContextoFiltraSuperadaComEsquemaNovo(unittest.TestCase):
    """Composição com a P06 sub-entrega 4/N (PR #451, já mesclada em main):
    o filtro `memoria_status_de_leitura(m) == STATUS_SUPERADA` precisa
    continuar descartando um fato ANTES do fallback de esquema entrar em
    ação -- um documento no esquema NOVO (`texto_memoria`/`tipo`) mas
    marcado `superada` não deve reaparecer no contexto só porque agora
    também lemos `texto_memoria`. Lacuna de teste registrada explicitamente
    (não escondida) na docstring de `test_memoria_supersedes.py` como
    "desproporcional" de cobrir ali, por exigir este mesmo fake de
    Telegram -- fechada aqui, que já o constrói."""

    def test_fato_superado_no_esquema_novo_nao_aparece(self):
        import telegram_handlers_core as thc

        db = _Db()
        db.collection("knowledge_nodes").document("mem-superado").set({
            "texto_memoria": "André trabalha de São Paulo (fato antigo, já substituído)",
            "tipo": "fato_isolado",
            "memoria_status": "superada",
            "data_criacao": "2026-10-09T10:00:00+00:00",
        })
        db.collection("knowledge_nodes").document("mem-vigente").set({
            "texto_memoria": "André trabalha de Vitória",
            "tipo": "fato_isolado",
            "memoria_status": "ativa",
            "data_criacao": "2026-10-10T10:00:00+00:00",
        })
        run_gemini = mock.Mock(return_value="ok")
        patches = _patches_do_handler(_run_gemini_turn=run_gemini)
        with mock.patch.multiple(thc, **patches):
            thc._process_telegram_message(db, {"chat_id": "123", "text": _TEXTO_COM_CONTEXTO})

        system_instruction = run_gemini.call_args.kwargs["system_instruction"]
        self.assertIn("MEMÓRIA GLOBAL ATIVA", system_instruction)
        self.assertIn("[fato_isolado] André trabalha de Vitória", system_instruction)
        self.assertNotIn("já substituído", system_instruction)
        self.assertNotIn("São Paulo", system_instruction)


if __name__ == "__main__":
    unittest.main()
