import json

from core import tracing

_ROUTING_MODEL = "gemini-2.0-flash-lite"

_MISSING_PARAM_PROMPTS: dict[str, str] = {
    "query": "O que você quer buscar?",
    "url": "Qual é a URL que devo acessar?",
    "titulo": "Qual será o título da ação?",
    "area_tematica": "Qual é a área temática? (ex: GERAL, FINANCEIRO, TI, RH)",
    "data_limite": "Qual é a data limite? (ex: 30/04/2026)",
    "fato": "Qual é o fato que devo memorizar?",
    "categoria": "Qual é a categoria? (ex: PREFERÊNCIA, REGRA, CONTATO)",
    "data_inicio": "A partir de qual data? (ex: 22/04/2026)",
    "data_fim": "Até qual data? (ex: 30/04/2026)",
    "a_partir_de": "A partir de qual data? (ex: 22/04/2026)",
    "titulo_procedimento": "Qual é o título do procedimento a corrigir?",
    "correcao_descrita": "Descreva a correção necessária.",
    "novo_conteudo_proposto": "Qual seria o novo conteúdo proposto?",
    "justificativa": "Qual é a justificativa para a correção?",
}

_CONFIRMATION_WORDS = {"sim", "confirma", "confirmo", "ok", "pode", "vai", "yes", "certo", "correto", "tá", "ta"}
_CANCELLATION_WORDS = {"não", "nao", "cancela", "cancelar", "desistir", "para", "abort", "no"}


def classify_tool(gemini_key: str, message: str, catalog: str) -> str | None:
    """Estágio 1: Flash Lite escolhe entre nomes e descrições curtas. Retorna tool_name ou None."""
    from google import genai
    from google.genai import types

    prompt = (
        f"Ferramentas disponíveis:\n{catalog}\n\n"
        f"Mensagem do usuário: {message}\n\n"
        "Retorne APENAS o nome exato de uma ferramenta da lista, ou a palavra NONE."
    )

    client = genai.Client(api_key=gemini_key)
    try:
        response = client.models.generate_content(
            model=_ROUTING_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=(
                    "Você é um classificador de intenção. "
                    "Retorne APENAS o nome da ferramenta ou NONE. Sem explicações."
                ),
                max_output_tokens=30,
                temperature=0.0,
            ),
        )
        raw = (response.text or "").strip()
    except Exception as e:
        tracing.log("ERROR", "classify_tool_failed", error=str(e))
        return None

    from tools.registry import list_tool_names
    tool_names = list_tool_names()
    for name in tool_names:
        if name in raw:
            tracing.log("INFO", "tool_classified", tool=name)
            return name
    return None


def extract_slots(gemini_key: str, tool_name: str, message: str, current_slots: dict, schema: dict) -> dict:
    """Estágio 2: Flash Lite extrai parâmetros da mensagem e mescla com slots existentes."""
    from google import genai
    from google.genai import types

    prompt = (
        f"Schema:\n{json.dumps(schema.get('parameters', schema), ensure_ascii=False, indent=2)}\n\n"
        f"Parâmetros já coletados:\n{json.dumps(current_slots, ensure_ascii=False)}\n\n"
        f"Mensagem do usuário: {message}\n\n"
        "Retorne um JSON com todos os parâmetros coletados (incluindo os anteriores mais os novos). "
        "Não invente valores. Use null para campos não informados."
    )

    client = genai.Client(api_key=gemini_key)
    try:
        response = client.models.generate_content(
            model=_ROUTING_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction="Extraia parâmetros. Retorne APENAS JSON válido.",
                response_mime_type="application/json",
                temperature=0.0,
            ),
        )
        new_slots = json.loads(response.text or "{}")
    except Exception as e:
        tracing.log("ERROR", "extract_slots_failed", error=str(e))
        new_slots = {}

    merged = {**current_slots, **{k: v for k, v in new_slots.items() if v is not None}}
    tracing.log("INFO", "slots_extracted", tool=tool_name, filled=list(merged.keys()))
    return merged


def get_missing_params(required_params: list, slots: dict) -> list[str]:
    return [p for p in required_params if not slots.get(p)]


def get_missing_param_prompt(missing: list[str]) -> str:
    first = missing[0]
    msg = _MISSING_PARAM_PROMPTS.get(first, f"Por favor, informe: <b>{first}</b>.")
    if len(missing) > 1:
        rest = ", ".join(f"<code>{p}</code>" for p in missing[1:])
        msg += f" (Também precisarei de: {rest})"
    return msg


def is_confirmation(text: str) -> bool:
    return _normalize(text) in _CONFIRMATION_WORDS


def is_cancellation(text: str) -> bool:
    return _normalize(text) in _CANCELLATION_WORDS


def _normalize(text: str) -> str:
    import unicodedata
    t = unicodedata.normalize("NFKD", (text or "").lower().strip())
    return "".join(ch for ch in t if not unicodedata.combining(ch))
