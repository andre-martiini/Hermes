"""Contracheque do Ifes por rubrica (item 13 do prompt de ajustes financeiros).

O Gaspar guardava so a "Remuneracao IFES" liquida. Com as rubricas da para
separar o per capita de saude suplementar (que paga parte do plano: o custo
liquido do plano de saude e Allcare menos o per capita) e explicar a diferenca
entre o liquido do contracheque e a renda lancada (R$ 64,87 em set/2026).

O PDF do Sigepe traz nome, CPF, matricula e conta bancaria. Nada disso e
extraido nem gravado: so competencia, rubricas e totais.
"""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, timezone

import competencia as comp

COLECAO = "contracheques"
_MESES = {"JAN": 1, "FEV": 2, "MAR": 3, "ABR": 4, "MAI": 5, "JUN": 6,
          "JUL": 7, "AGO": 8, "SET": 9, "OUT": 10, "NOV": 11, "DEZ": 12}

_PROMPT = """Você recebe um contracheque (comprovante de rendimentos do Sigepe). Transcreva
em JSON, sem interpretar:
- mes_ano: o MÊS/ANO do contracheque como aparece (ex.: "JAN 2026")
- rendimentos: lista de {"descricao": texto da rubrica, "valor": número}
- descontos: lista de {"descricao": texto da rubrica, "valor": número positivo}
- bruto, desconto, liquido: os totais impressos (números)

NÃO transcreva nome, CPF, matrícula, identificação, banco, agência nem conta.
Valores em formato brasileiro (5.372,35) viram número (5372.35).
Responda APENAS o JSON:
{"mes_ano": "", "rendimentos": [], "descontos": [], "bruto": 0, "desconto": 0, "liquido": 0}"""


def _num(valor) -> float:
    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        return round(float(valor), 2)
    texto = re.sub(r"[^\d,.\-]", "", str(valor or ""))
    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")
    try:
        return round(float(texto), 2)
    except ValueError:
        return 0.0


def _normalizar(texto) -> str:
    sem_acento = unicodedata.normalize("NFKD", str(texto or ""))
    return "".join(c for c in sem_acento if not unicodedata.combining(c)).upper()


def competencia_do_mes_ano(mes_ano: str) -> str:
    """"JAN 2026" -> "2026-01"."""
    achado = re.search(r"([A-Z]{3})\D*(\d{4})", _normalizar(mes_ano))
    if not achado or achado.group(1) not in _MESES:
        raise ValueError(f"Mes/ano do contracheque ilegivel: {mes_ano!r}.")
    return f"{int(achado.group(2)):04d}-{_MESES[achado.group(1)]:02d}"


def e_per_capita_saude(descricao: str) -> bool:
    texto = _normalizar(descricao)
    return "PER CAPITA" in texto and "SAUDE" in texto


def normalizar(dados: dict) -> dict:
    """Transcricao do modelo -> registro conferido (soma das rubricas x totais impressos)."""
    rendimentos = [{"descricao": str(r.get("descricao") or "").strip(), "valor": _num(r.get("valor"))}
                   for r in dados.get("rendimentos") or [] if isinstance(r, dict)]
    descontos = [{"descricao": str(d.get("descricao") or "").strip(), "valor": abs(_num(d.get("valor")))}
                 for d in dados.get("descontos") or [] if isinstance(d, dict)]
    bruto, desconto, liquido = _num(dados.get("bruto")), _num(dados.get("desconto")), _num(dados.get("liquido"))
    soma_rend = round(sum(r["valor"] for r in rendimentos), 2)
    soma_desc = round(sum(d["valor"] for d in descontos), 2)
    divergencias = []
    if abs(soma_rend - bruto) > 0.05:
        divergencias.append(f"rendimentos somam R$ {soma_rend:.2f}, bruto impresso R$ {bruto:.2f}")
    if abs(soma_desc - desconto) > 0.05:
        divergencias.append(f"descontos somam R$ {soma_desc:.2f}, desconto impresso R$ {desconto:.2f}")
    if abs(bruto - desconto - liquido) > 0.05:
        divergencias.append(f"bruto - desconto = R$ {bruto - desconto:.2f}, liquido impresso R$ {liquido:.2f}")
    return {
        "competencia": competencia_do_mes_ano(dados.get("mes_ano") or ""),
        "rendimentos": rendimentos,
        "descontos": descontos,
        "bruto": bruto,
        "desconto": desconto,
        "liquido": liquido,
        "per_capita_saude": round(sum(r["valor"] for r in rendimentos if e_per_capita_saude(r["descricao"])), 2),
        "confere": not divergencias,
        "divergencias": divergencias,
    }


def extrair(client, types, pdf: bytes) -> dict:
    from gemini_cost_controls import GEMINI_DOCUMENT_MODEL

    resposta = client.models.generate_content(
        model=GEMINI_DOCUMENT_MODEL,
        contents=[_PROMPT, types.Part.from_bytes(data=pdf, mime_type="application/pdf")])
    bruto = re.sub(r"^```(?:json)?|```$", "", (resposta.text or "").strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(bruto)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Leitura do contracheque nao devolveu JSON: {bruto[:200]}") from exc


def renda_lancada(db, competencia: str) -> tuple[float | None, str]:
    """"Remuneracao IFES" lancada no mes seguinte ao do contracheque (quando o salario cai)."""
    mes0, ano = comp.ler(competencia)
    mes0, ano = (0, ano + 1) if mes0 == 11 else (mes0 + 1, ano)
    import fontes_renda

    total = None
    for snap in (db.collection("income_entries").where("month", "==", mes0)
                 .where("year", "==", ano).stream()):
        d = snap.to_dict() or {}
        if d.get("status") == "deleted" or not fontes_renda.e_salario_ifes(d):
            continue
        total = round((total or 0.0) + _num(d.get("amount")), 2)
    return total, comp.periodo(mes0, ano)["competencia"]


def gravar(db, registro: dict, origem: dict | None = None) -> dict:
    """Grava (substitui o mesmo mes), rele e compara com a renda lancada."""
    ref = db.collection(COLECAO).document(registro["competencia"])
    ref.set({**registro, **(origem or {}), "importado_em": datetime.now(timezone.utc).isoformat()})
    relido = ref.get().to_dict() or {}
    gravou = relido.get("liquido") == registro["liquido"] and len(relido.get("rendimentos") or []) == len(
        registro["rendimentos"])
    renda, mes_renda = renda_lancada(db, registro["competencia"])
    return {
        "estado": "verificado" if gravou else "falhou",
        "competencia": registro["competencia"],
        "bruto": relido.get("bruto"), "desconto": relido.get("desconto"), "liquido": relido.get("liquido"),
        "per_capita_saude": relido.get("per_capita_saude"),
        "confere": relido.get("confere"), "divergencias": relido.get("divergencias"),
        "renda_lancada": {"mes": mes_renda, "valor": renda,
                          "diferenca_para_o_liquido": None if renda is None else round(renda - registro["liquido"], 2)},
        "motivo": None if gravou else "a releitura nao bateu com o que foi gravado",
    }


def saude_liquida(db, competencia: str) -> dict | None:
    """Custo do plano de saude no mes: contas Allcare menos o per capita do contracheque."""
    contracheque = db.collection(COLECAO).document(competencia).get().to_dict()
    if not contracheque:
        return None
    mes0, ano = comp.ler(competencia)
    allcare = round(sum(_num((s.to_dict() or {}).get("amount")) for s in db.collection("fixed_bills")
                        .where("month", "==", mes0).where("year", "==", ano).stream()
                        if "ALLCARE" in _normalizar((s.to_dict() or {}).get("description"))), 2)
    per_capita = _num(contracheque.get("per_capita_saude"))
    return {"plano_e_coparticipacao": allcare, "per_capita": per_capita,
            "custo_liquido": round(allcare - per_capita, 2)}
