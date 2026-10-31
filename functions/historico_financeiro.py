"""Historico mensal do financeiro (item 4 do prompt de ajustes financeiros).

Cada mes vira um retrato: renda por fonte (Ifes, servicos, outras), contas,
aportes, cartao por categoria, saldo, reserva e metas. Mes fechado e congelado
em `financeiro_historico/{YYYY-MM}`; corrigir um mes ja fechado e uma
retificacao explicita, que guarda os totais da versao anterior e o motivo.

Mes sem retrato e calculado na hora a partir dos dados de agora, entao a
consulta de 12 meses funciona desde o primeiro dia, e os meses antigos refletem
as correcoes de dados feitas depois (como as de 11/10/2026).

Os numeros de renda e contas sao os mesmos de `consultar_financas_v2`; o cartao
e o detalhamento das faturas daquele mes (competencia = mes do vencimento), que
ja estao dentro das contas como "Fatura Elo"/"Fatura XP" — nao se soma de novo.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from firebase_functions import options, scheduler_fn

import competencia as comp
import fontes_renda
from agent_runs import instrumentada

COLECAO = "financeiro_historico"
MAX_MESES = 24
CATEGORIAS_APORTE = ("Poupança", "Investimento")

# Custo de IA e nuvem (item 14): o dono espera a API do Gaspar (Google Cloud)
# abaixo de R$ 100/mes depois das correcoes de set-out/2026 (R$ 276,83 na fatura
# de 05/09 e R$ 466,35 na de 05/10).
META_GOOGLE_CLOUD = 100.0
_FORNECEDORES_IA = (
    ("google cloud", "Google Cloud"), ("anthropic", "Anthropic (Claude)"), ("claude", "Anthropic (Claude)"),
    ("openai", "OpenAI (ChatGPT)"), ("chatgpt", "OpenAI (ChatGPT)"), ("elevenlabs", "ElevenLabs"),
    ("aqua voice", "Aqua Voice"), ("typesafe", "Typesafe AI"), ("microsoft", "Microsoft"), ("kling", "Kling"),
)


def _fornecedor(estabelecimento: str) -> str:
    import categorias_cartao

    texto = f" {categorias_cartao.normalizar(estabelecimento)} "
    for chave, nome in _FORNECEDORES_IA:
        if f" {chave} " in texto:
            return nome
    return str(estabelecimento or "outro").strip()


def custo_ia(db, competencia: str) -> dict:
    """Gasto do mes em IA e software no cartao, por fornecedor, com a meta do Google Cloud."""
    import fatura_cartao

    fatura = fatura_cartao.consultar(db, competencia=competencia, categoria="IA e software", limite=2000)
    por_fornecedor: dict[str, float] = {}
    for item in fatura.get("lancamentos") or []:
        nome = _fornecedor(item.get("estabelecimento", ""))
        por_fornecedor[nome] = round(por_fornecedor.get(nome, 0.0) + _num(item.get("valor")), 2)
    google = por_fornecedor.get("Google Cloud", 0.0)
    return {
        "total": round(sum(por_fornecedor.values()), 2),
        "por_fornecedor": dict(sorted(por_fornecedor.items(), key=lambda kv: -kv[1])),
        "google_cloud": {"valor": google, "meta": META_GOOGLE_CLOUD, "acima_da_meta": google > META_GOOGLE_CLOUD},
    }


def _num(valor) -> float:
    try:
        return round(float(valor or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def meses_entre(inicio: str, fim: str) -> list[str]:
    m0, a0 = comp.ler(inicio)
    m1, a1 = comp.ler(fim)
    if (a1, m1) < (a0, m0):
        raise ValueError("mes_fim e anterior a mes_inicio.")
    meses = []
    ano, mes = a0, m0
    while (ano, mes) <= (a1, m1):
        meses.append(comp.periodo(mes, ano)["competencia"])
        if len(meses) > MAX_MESES:
            raise ValueError(f"No maximo {MAX_MESES} meses por consulta.")
        mes += 1
        if mes > 11:
            ano, mes = ano + 1, 0
    return meses


def avulsas_do_mes(db, competencia: str) -> list[dict]:
    """Transacoes avulsas do mes (finance_transactions nao tem month/year: vale o prefixo de `date`)."""
    # So `>=` no servidor (indice de campo unico); o teto do mes sai no filtro abaixo.
    docs = (s.to_dict() or {} for s in db.collection("finance_transactions").where("date", ">=", competencia).stream())
    return [d for d in docs if str(d.get("date") or "")[:7] == competencia and d.get("status") != "deleted"]


def montar_mes(db, competencia: str) -> dict:
    """Retrato do mes a partir dos dados de agora."""
    import fatura_cartao

    mes0, ano = comp.ler(competencia)
    contas = [s.to_dict() or {} for s in db.collection("fixed_bills")
              .where("month", "==", mes0).where("year", "==", ano).stream()]
    # Mesma regra da tela e de consultar_financas_v2: so a renda excluida sai.
    rendas = [d for d in (s.to_dict() or {} for s in db.collection("income_entries")
                          .where("month", "==", mes0).where("year", "==", ano).stream())
              if d.get("status") != "deleted"]

    por_fonte = {"ifes": 0.0, "servicos": 0.0, "outras": 0.0}
    for r in rendas:
        fonte = fontes_renda.fonte(r)
        por_fonte[fonte] = round(por_fonte[fonte] + _num(r.get("amount")), 2)
    renda_total = round(sum(_num(r.get("amount")) for r in rendas), 2)
    renda_recebida = round(sum(_num(r.get("amount")) for r in rendas if r.get("isReceived")), 2)
    contas_total = round(sum(_num(c.get("amount")) for c in contas), 2)
    contas_pagas = round(sum(_num(c.get("amount")) for c in contas if c.get("isPaid")), 2)
    aportes = round(sum(_num(c.get("amount")) for c in contas
                        if c.get("category") in CATEGORIAS_APORTE), 2)
    avulsas = avulsas_do_mes(db, competencia)
    avulsas_total = round(sum(_num(a.get("amount")) for a in avulsas), 2)

    fatura = fatura_cartao.consultar(db, competencia=competencia, limite=0)
    config = db.collection("finance_settings").document("config").get().to_dict() or {}
    metas = [{"nome": d.get("name"), "alvo": _num(d.get("targetAmount")), "status": d.get("status")}
             for d in (s.to_dict() or {} for s in db.collection("finance_goals").stream())]

    return {
        "periodo": comp.periodo(mes0, ano),
        "renda": {"total": renda_total, "recebida": renda_recebida, "por_fonte": por_fonte},
        "contas": {"total": contas_total, "pagas": contas_pagas, "quantidade": len(contas), "aportes": aportes},
        "avulsas": {"total": avulsas_total, "quantidade": len(avulsas)},
        "saldo": {"previsto": round(renda_total - contas_total - avulsas_total, 2),
                  "realizado": round(renda_recebida - contas_pagas - avulsas_total, 2)},
        "cartao": {
            "total_gasto": fatura.get("total_gasto"),
            "total_encargos": fatura.get("total_encargos"),
            "por_cartao": fatura.get("por_cartao"),
            "por_categoria": [{"categoria": c["categoria"], "total": c["total"]}
                              for c in fatura.get("por_categoria") or []],
            "por_natureza": fatura.get("por_natureza"),
        },
        "custo_ia": custo_ia(db, competencia),
        "contracheque": _contracheque_do_mes(db, competencia),
        "saude": _saude(db, competencia),
        "reserva_emergencia": {"atual": _num(config.get("emergencyReserveCurrent")),
                               "alvo": _num(config.get("emergencyReserveTarget"))},
        "metas": metas,
    }


def _contracheque_do_mes(db, competencia: str) -> dict | None:
    """Totais do contracheque deste mes (o salario cai no mes seguinte)."""
    registro = db.collection("contracheques").document(competencia).get().to_dict()
    if not registro:
        return None
    return {k: registro.get(k) for k in ("bruto", "desconto", "liquido", "per_capita_saude", "confere")}


def _saude(db, competencia: str) -> dict | None:
    import contracheque

    return contracheque.saude_liquida(db, competencia)


def _resumo_versao(retrato: dict) -> dict:
    return {"renda": retrato["renda"]["total"], "contas": retrato["contas"]["total"],
            "saldo": retrato["saldo"]["previsto"], "cartao": retrato["cartao"]["total_gasto"],
            "fechado_em": retrato.get("fechado_em")}


def fechar_mes(db, competencia: str, *, hoje: date, retificar: bool = False, motivo: str = "",
               canal: str = "mcp") -> dict:
    """Congela o retrato de um mes ja encerrado. Refazer exige `retificar` e um motivo."""
    mes0, ano = comp.ler(competencia)
    if (ano, mes0) >= (hoje.year, hoje.month - 1):
        raise ValueError(f"{competencia} ainda nao terminou; so se fecha mes encerrado.")
    if retificar and not str(motivo or "").strip():
        raise ValueError("Retificar um mes fechado exige o motivo.")

    ref = db.collection(COLECAO).document(competencia)
    anterior = ref.get().to_dict()
    if anterior and not retificar:
        return {"estado": "ja_fechado", "retrato": anterior,
                "observacao": "Mes ja fechado; para refazer, use retificar=true com o motivo."}

    retrato = montar_mes(db, competencia)
    agora = datetime.now(timezone.utc).isoformat()
    retrato.update({"fechado_em": agora, "canal": canal, "versao": 1, "retificacoes": []})
    if anterior:
        retrato["versao"] = int(anterior.get("versao") or 1) + 1
        retrato["retificacoes"] = (list(anterior.get("retificacoes") or [])
                                   + [{"em": agora, "motivo": str(motivo).strip()[:300],
                                       "anterior": _resumo_versao(anterior)}])[-10:]
    ref.set(retrato)

    relido = ref.get().to_dict() or {}
    gravou = relido.get("versao") == retrato["versao"] and relido.get("fechado_em") == agora
    return {"estado": "verificado" if gravou else "falhou",
            "competencia": competencia, "versao": retrato["versao"],
            "resumo": _resumo_versao(relido or retrato),
            "motivo": None if gravou else "a releitura nao bateu com o retrato gravado"}


def consultar(db, mes_inicio: str, mes_fim: str, *, hoje: date) -> dict:
    """Retrato de cada mes do intervalo: o congelado, se houver; senao, calculado agora."""
    meses = []
    for competencia in meses_entre(mes_inicio, mes_fim):
        congelado = db.collection(COLECAO).document(competencia).get().to_dict()
        if congelado:
            retrato = dict(congelado)
            retrato["situacao"] = "fechado"
        else:
            retrato = montar_mes(db, competencia)
            mes0, ano = comp.ler(competencia)
            em_curso = (ano, mes0) >= (hoje.year, hoje.month - 1)
            retrato["situacao"] = "em curso" if em_curso else "calculado agora (nao fechado)"
        meses.append(retrato)

    comparativo = [{"competencia": m["periodo"]["competencia"], "mes_nome": m["periodo"]["mes_nome"],
                    "renda": m["renda"]["total"], "contas": m["contas"]["total"],
                    "saldo": m["saldo"]["previsto"], "cartao": m["cartao"]["total_gasto"],
                    # Retrato congelado antes do item 14 nao tem custo_ia.
                    "custo_ia": (m.get("custo_ia") or {}).get("total"),
                    "situacao": m["situacao"]} for m in meses]
    return {"comparativo": comparativo, "meses": meses}


def mes_anterior(hoje: date) -> str:
    if hoje.month == 1:
        return f"{hoje.year - 1:04d}-12"
    return f"{hoje.year:04d}-{hoje.month - 1:02d}"


@scheduler_fn.on_schedule(
    schedule="0 6 10 * *",  # dia 10, 06:00: faturas e contas do mes anterior ja chegaram
    timezone="America/Sao_Paulo",
    memory=options.MemoryOption.MB_256,
    timeout_sec=120,
)
@instrumentada("fechar_mes_financeiro")
def fechar_mes_financeiro(event: scheduler_fn.ScheduledEvent):
    from zoneinfo import ZoneInfo

    from main import get_db

    hoje = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    competencia = mes_anterior(hoje)
    resultado = fechar_mes(get_db(), competencia, hoje=hoje, canal="agendado")
    print(f"[HistoricoFinanceiro] {competencia}: {resultado['estado']}")
