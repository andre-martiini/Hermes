"""Testes unitários para orchestrator.py (Voice Client)."""

import sys
import unittest
from unittest.mock import MagicMock

# Dependências nativas/opcionais do cliente local (keyring, faster_whisper)
# podem não estar no path em todos os ambientes de teste. Mock defensivo
# para permitir testar _build_gemini_tools em isolamento estrito.
for _mod in ("keyring", "faster_whisper", "piper"):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()

from orchestrator import _build_gemini_tools


class TestBuildGeminiTools(unittest.TestCase):
    def test_filtra_apenas_tools_com_voice_enabled_true(self):
        mcp_tools = [
            {
                "name": "calculadora",
                "description": "Calcula expressoes matematicas",
                "inputSchema": {
                    "type": "object",
                    "properties": {"expressao": {"type": "string"}},
                    "required": ["expressao"],
                },
                "_meta": {"voiceEnabled": True},
            },
            {
                "name": "gerar_relatorio",
                "description": "Gera relatorio em PDF",
                "inputSchema": {"type": "object", "properties": {}},
                "_meta": {"voiceEnabled": False},
            },
        ]

        tools = _build_gemini_tools(mcp_tools)
        self.assertEqual(len(tools), 1)
        declarations = tools[0].function_declarations
        self.assertEqual(len(declarations), 1)
        self.assertEqual(declarations[0].name, "calculadora")
        self.assertEqual(declarations[0].description, "Calcula expressoes matematicas")

    def test_retorna_vazio_se_nenhuma_tool_for_voice_enabled(self):
        mcp_tools = [
            {
                "name": "gerar_relatorio",
                "_meta": {"voiceEnabled": False},
            },
            {
                "name": "registrar_aporte_investimento",
                "_meta": {"voiceEnabled": False},
            },
        ]

        tools = _build_gemini_tools(mcp_tools)
        self.assertEqual(tools, [])

    def test_trata_tool_sem_meta_como_desabilitada_defensivamente(self):
        mcp_tools = [
            {
                "name": "tool_antiga_sem_meta",
                "description": "Servidor antigo sem _meta",
            },
            {
                "name": "obter_fila_atencao",
                "description": "Obtem itens prioritarios",
                "_meta": {"voiceEnabled": True},
            },
        ]

        tools = _build_gemini_tools(mcp_tools)
        self.assertEqual(len(tools), 1)
        declarations = tools[0].function_declarations
        self.assertEqual(len(declarations), 1)
        self.assertEqual(declarations[0].name, "obter_fila_atencao")

    def test_input_schema_ausente_usa_objeto_padrao(self):
        mcp_tools = [
            {
                "name": "obter_estado_atual",
                "description": "Obtem estado do sistema",
                "_meta": {"voiceEnabled": True},
            }
        ]

        tools = _build_gemini_tools(mcp_tools)
        self.assertEqual(len(tools), 1)
        declarations = tools[0].function_declarations
        self.assertEqual(len(declarations), 1)
        self.assertEqual(declarations[0].name, "obter_estado_atual")
        self.assertIsNotNone(declarations[0].parameters)


if __name__ == "__main__":
    unittest.main()
