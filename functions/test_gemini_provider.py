"""Loop de tool-calling sobre a Gemini API (llm_providers/gemini_provider.py)."""
import unittest
from unittest import mock

from google.genai import types

from llm_providers import gemini_provider as gp


class _ApiError(Exception):
    def __init__(self, code, message="erro"):
        super().__init__(message)
        self.code = code


def _resp(parts, prompt=10, out=5, thoughts=0):
    return types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(role="model", parts=parts))],
        usage_metadata=types.GenerateContentResponseUsageMetadata(
            prompt_token_count=prompt, candidates_token_count=out, thoughts_token_count=thoughts),
    )


def _call(name, **args):
    return types.Part(function_call=types.FunctionCall(name=name, args=args))


def _texto(t, thought=False):
    return types.Part(text=t, thought=True if thought else None)


class _Roteiro:
    """Substitui generate_content_logged: devolve (ou levanta) as respostas na ordem."""

    def __init__(self, *itens):
        self.itens = list(itens)
        self.chamadas = []

    def __call__(self, client, *, model, contents, feature, db=None, **kwargs):
        self.chamadas.append({"model": model, "feature": feature, "config": kwargs["config"], "n_contents": len(contents)})
        item = self.itens.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


TOOLS = [
    {"name": "consultar_agenda", "description": "agenda", "input_schema": {
        "type": "object", "properties": {"dia": {"type": "string"}}, "required": ["dia"]}},
    {"name": "finalizar_atendimento", "description": "fim", "input_schema": {
        "type": "object", "properties": {"resposta": {"type": "string"}}, "required": ["resposta"]}},
]


def _rodar(roteiro, function_map=None, **kw):
    args = dict(client=object(), model="gemini-3.8-flash", system_instruction="sys", tools=TOOLS,
                function_map=function_map or {}, history=[], user_message="oi", max_tokens=100,
                fallback_model="gemini-3.5-flash-lite", feature="teste")
    args.update(kw)
    with mock.patch.object(gp, "generate_content_logged", roteiro):
        return gp.run_tool_loop(**args)


class TestLoop(unittest.TestCase):
    def test_resposta_sem_ferramenta(self):
        r = _rodar(_Roteiro(_resp([_texto("Olá!")])))
        self.assertEqual(r["text"], "Olá!")
        self.assertEqual(r["tools_used"], [])
        self.assertEqual(r["usage"]["rounds"], 1)
        self.assertFalse(r["fallback_used"])

    def test_ferramenta_executada_e_resultado_volta_ao_modelo(self):
        vistos = []
        roteiro = _Roteiro(
            _resp([_call("consultar_agenda", dia="2026-09-22")]),
            _resp([_texto("Ocupado.")]),
        )
        r = _rodar(roteiro, {"consultar_agenda": lambda dia: vistos.append(dia) or {"eventos": ["reunião"]}})
        self.assertEqual(vistos, ["2026-09-22"])
        self.assertEqual(r["text"], "Ocupado.")
        self.assertEqual(r["tools_used"], ["consultar_agenda"])
        resposta = r["history"][-2].parts[0].function_response
        self.assertEqual(resposta.name, "consultar_agenda")
        self.assertEqual(resposta.response, {"eventos": ["reunião"]})

    def test_duas_ferramentas_na_mesma_rodada_voltam_juntas(self):
        roteiro = _Roteiro(
            _resp([_call("consultar_agenda", dia="a"), _call("consultar_agenda", dia="b")]),
            _resp([_texto("ok")]),
        )
        r = _rodar(roteiro, {"consultar_agenda": lambda dia: {"dia": dia}})
        volta = r["history"][-2]
        self.assertEqual([p.function_response.response["dia"] for p in volta.parts], ["a", "b"])

    def test_ferramenta_desconhecida_e_erro_da_ferramenta_nao_derrubam_o_turno(self):
        def quebra(dia):
            raise ValueError("falhou")
        roteiro = _Roteiro(
            _resp([_call("inexistente"), _call("consultar_agenda", dia="x")]),
            _resp([_texto("segui")]),
        )
        r = _rodar(roteiro, {"consultar_agenda": quebra})
        respostas = [p.function_response.response for p in r["history"][-2].parts]
        self.assertIn("desconhecida", respostas[0]["error"])
        self.assertEqual(respostas[1], {"error": "falhou"})
        self.assertEqual(r["text"], "segui")

    def test_stop_after_tools_encerra_sem_rodada_extra(self):
        roteiro = _Roteiro(_resp([_call("finalizar_atendimento", resposta="oi")]))
        r = _rodar(roteiro, {"finalizar_atendimento": lambda resposta: {"ok": True}},
                   stop_after_tools={"finalizar_atendimento"})
        self.assertEqual(len(roteiro.chamadas), 1)
        self.assertEqual(r["tools_used"], ["finalizar_atendimento"])

    def test_force_tools_configura_modo_any(self):
        roteiro = _Roteiro(_resp([_call("finalizar_atendimento", resposta="oi")]))
        _rodar(roteiro, {"finalizar_atendimento": lambda resposta: {}},
               force_tools=["finalizar_atendimento"], stop_after_tools={"finalizar_atendimento"})
        fc = roteiro.chamadas[0]["config"].tool_config.function_calling_config
        self.assertEqual(str(fc.mode).split(".")[-1], "ANY")
        self.assertEqual(fc.allowed_function_names, ["finalizar_atendimento"])

    def test_resultado_grande_e_cortado_e_sinalizado(self):
        roteiro = _Roteiro(_resp([_call("consultar_agenda", dia="x")]), _resp([_texto("ok")]))
        r = _rodar(roteiro, {"consultar_agenda": lambda dia: {"lixo": "x" * (gp.TOOL_RESULT_CHAR_LIMIT + 50)}})
        resposta = r["history"][-2].parts[0].function_response.response
        self.assertTrue(resposta["truncated"])
        self.assertEqual(len(resposta["result"]), gp.TOOL_RESULT_CHAR_LIMIT)

    def test_resultado_que_nao_e_dict_vira_objeto(self):
        roteiro = _Roteiro(_resp([_call("consultar_agenda", dia="x")]), _resp([_texto("ok")]))
        r = _rodar(roteiro, {"consultar_agenda": lambda dia: ["a", "b"]})
        self.assertEqual(r["history"][-2].parts[0].function_response.response, {"result": ["a", "b"]})

    def test_raciocinio_nao_entra_no_texto_final(self):
        r = _rodar(_Roteiro(_resp([_texto("pensando...", thought=True), _texto("Resposta.")])))
        self.assertEqual(r["text"], "Resposta.")

    def test_limite_de_rodadas_devolve_aviso(self):
        roteiro = _Roteiro(*[_resp([_call("consultar_agenda", dia="x")]) for _ in range(3)])
        r = _rodar(roteiro, {"consultar_agenda": lambda dia: {}}, max_rounds=3)
        self.assertIn("limite de rodadas", r["text"])
        self.assertEqual(r["usage"]["rounds"], 3)

    def test_uso_soma_raciocinio_na_saida(self):
        r = _rodar(_Roteiro(_resp([_texto("x")], prompt=100, out=20, thoughts=300)))
        self.assertEqual(r["usage"]["input_tokens"], 100)
        self.assertEqual(r["usage"]["output_tokens"], 320)


class TestConfiguracao(unittest.TestCase):
    def test_orcamento_de_saida_inclui_folga_do_raciocinio(self):
        roteiro = _Roteiro(_resp([_texto("x")]))
        _rodar(roteiro, max_tokens=100)
        self.assertEqual(roteiro.chamadas[0]["config"].max_output_tokens, 100 + gp.THINKING_HEADROOM_TOKENS)

    def test_historico_mapeia_papeis_e_ignora_vazios(self):
        roteiro = _Roteiro(_resp([_texto("x")]))
        _rodar(roteiro, history=[{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"},
                                 {"role": "user", "content": "  "}, {"role": "assistant", "content": ["bloco"]}])
        self.assertEqual(roteiro.chamadas[0]["n_contents"], 3)  # a, b e a mensagem nova

    def test_sem_ferramentas_nao_manda_tools(self):
        roteiro = _Roteiro(_resp([_texto("x")]))
        _rodar(roteiro, tools=[])
        self.assertIsNone(roteiro.chamadas[0]["config"].tools)

    def test_ferramenta_sem_parametros_nao_manda_schema(self):
        decls = gp._tool_declarations([{"name": "agora", "description": "hora", "input_schema": {"type": "object", "properties": {}}}])
        self.assertIsNone(decls[0].parameters_json_schema)

    def test_feature_padrao_vem_do_modulo_chamador(self):
        roteiro = _Roteiro(_resp([_texto("x")]))
        _rodar(roteiro, feature=None)
        self.assertTrue(roteiro.chamadas[0]["feature"].startswith("agent."))


class TestRecuperacao(unittest.TestCase):
    def test_modelo_indisponivel_troca_para_reserva_e_mantem_nas_proximas_rodadas(self):
        roteiro = _Roteiro(_ApiError(503, "UNAVAILABLE"),
                           _resp([_call("consultar_agenda", dia="x")]), _resp([_texto("ok")]))
        r = _rodar(roteiro, {"consultar_agenda": lambda dia: {}})
        self.assertTrue(r["fallback_used"])
        self.assertEqual(r["model_used"], "gemini-3.5-flash-lite")
        self.assertEqual([c["model"] for c in roteiro.chamadas],
                         ["gemini-3.8-flash", "gemini-3.5-flash-lite", "gemini-3.5-flash-lite"])

    def test_erro_de_raciocinio_refaz_sem_thinking(self):
        roteiro = _Roteiro(_ApiError(400, "Thinking level LOW is not supported"), _resp([_texto("ok")]))
        r = _rodar(roteiro)
        self.assertEqual(r["text"], "ok")
        self.assertIsNotNone(roteiro.chamadas[0]["config"].thinking_config)
        self.assertIsNone(roteiro.chamadas[1]["config"].thinking_config)

    def test_reserva_que_rejeita_raciocinio_tambem_recupera(self):
        roteiro = _Roteiro(_ApiError(503), _ApiError(400, "thinking not supported"), _resp([_texto("ok")]))
        r = _rodar(roteiro)
        self.assertEqual(r["text"], "ok")
        self.assertEqual(r["model_used"], "gemini-3.5-flash-lite")

    def test_erro_nao_recuperavel_sobe(self):
        with self.assertRaises(_ApiError):
            _rodar(_Roteiro(_ApiError(400, "argumento inválido")))

    def test_sem_reserva_o_erro_de_capacidade_sobe(self):
        with self.assertRaises(_ApiError):
            _rodar(_Roteiro(_ApiError(503)), fallback_model=None)

    def test_reserva_tambem_falhando_sobe(self):
        with self.assertRaises(_ApiError):
            _rodar(_Roteiro(_ApiError(503), _ApiError(503)))


if __name__ == "__main__":
    unittest.main()
