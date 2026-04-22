import json
import os

_SCHEMA_DIR = os.path.join(os.path.dirname(__file__), "schemas")

# Catálogo resumido: nome → descrição de uma linha (Stage 1)
_CATALOG: dict[str, str] = {
    "consultar_historico_acoes": "Busca ações, tarefas e projetos no Hermes por texto, status, área ou prazo",
    "buscar_arquivos_acervo": "Busca documentos, manuais e arquivos no Acervo Global do Hermes",
    "pesquisar_internet": "Busca informações recentes e atuais na internet (notícias, preços, dados externos)",
    "ler_pagina_web": "Lê e extrai o conteúdo completo de uma URL",
    "consultar_agenda": "Consulta eventos e compromissos na agenda do Google Calendar em um período",
    "encontrar_slot_livre": "Encontra o próximo horário livre disponível na agenda",
    "criar_acao_no_sistema": "Cria uma nova ação ou tarefa no Hermes com título, área, prazo e plano",
    "salvar_memoria_global": "Salva um fato durável ou preferência permanente na memória global",
    "registrar_correcao_procedimento": "Registra uma correção ou melhoria em um procedimento existente",
    "buscar_e_analisar_email": "Busca e analisa e-mails no Gmail usando query padrão (ex: 'from:x@y.com')",
}

# Tools que requerem confirmação explícita antes de executar
_NEEDS_CONFIRMATION: set[str] = {"criar_acao_no_sistema"}

# Tools assíncronas (futuramente via Pub/Sub — por ora executam síncronas)
_ASYNC_TOOLS: set[str] = {"buscar_e_analisar_email"}

_schema_cache: dict[str, dict] = {}


def get_short_catalog() -> str:
    return "\n".join(f"- {name}: {desc}" for name, desc in _CATALOG.items())


def list_tool_names() -> set[str]:
    return set(_CATALOG.keys())


def get_schema(tool_name: str) -> dict:
    if tool_name not in _schema_cache:
        path = os.path.join(_SCHEMA_DIR, f"{tool_name}.json")
        with open(path, "r", encoding="utf-8") as f:
            _schema_cache[tool_name] = json.load(f)
    return _schema_cache[tool_name]


def needs_confirmation(tool_name: str) -> bool:
    return tool_name in _NEEDS_CONFIRMATION


def is_async(tool_name: str) -> bool:
    return tool_name in _ASYNC_TOOLS


def get_required_params(tool_name: str) -> list[str]:
    schema = get_schema(tool_name)
    return schema.get("parameters", {}).get("required", [])
