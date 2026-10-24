"""Rendas de servico: quanto falta de cada contrato, quando acaba, e a renda dos proximos meses.

Item 8 do prompt de ajustes financeiros (out/2026): os servicos eram 46,8% da
renda de setembro e nada no Gaspar dizia quando cada um acaba. O dado ja existe
em `servicos/{id}.parcelas` (valor, data prevista, pendente/pago); este modulo
so o le e resume, sem gravar nada.

A projecao separa o Ifes dos servicos: o Ifes e a ultima "Renda Principal"
recebida (sem o 13o), os servicos sao as parcelas pendentes pela data prevista.
"""
from __future__ import annotations

from datetime import date, timedelta

STATUS_ATIVOS = ("Ativo", "Em Pausa")
LIMITE_ACABANDO = 2
# O mes trabalhado e pago no mes seguinte: o PLS MEC, prorrogado ate dezembro/2026,
# tem a ultima parcela em 08/01/2027. So passa disso e erro de cadastro.
DEFASAGEM_PAGAMENTO = timedelta(days=45)


def _data(valor) -> date | None:
    try:
        return date.fromisoformat(str(valor or "")[:10])
    except ValueError:
        return None


def _num(valor) -> float:
    try:
        return round(float(valor or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def _mes(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def resumir_contrato(servico: dict, hoje: date) -> dict:
    parcelas = sorted((p for p in servico.get("parcelas") or [] if isinstance(p, dict)),
                      key=lambda p: str(p.get("data_prevista") or ""))
    pagas = [p for p in parcelas if p.get("status") == "pago"]
    pendentes = [p for p in parcelas if p.get("status") != "pago"]
    datas = [d for d in (_data(p.get("data_prevista")) for p in parcelas) if d]
    ultima = max(datas) if datas else None
    proxima = next((p for p in pendentes if (_data(p.get("data_prevista")) or hoje) >= hoje), None)
    atrasadas = [p for p in pendentes if (_data(p.get("data_prevista")) or hoje) < hoje]

    # So o contrato de mensalidade "acaba" e tem prazo que as parcelas devam
    # respeitar; o pacote fechado e pago de uma vez, em geral depois da entrega.
    mensal = servico.get("tipo_contrato") == "Mensalidade"
    inconsistencias = []
    if parcelas and not pendentes and servico.get("status") in STATUS_ATIVOS:
        inconsistencias.append("todas as parcelas pagas, mas o contrato continua ativo")
    termino = _data(servico.get("data_termino"))
    if mensal and termino and ultima and ultima > termino + DEFASAGEM_PAGAMENTO:
        inconsistencias.append(f"parcela em {ultima.isoformat()} depois do término do contrato ({termino.isoformat()})")
    total = _num(servico.get("valor_total"))
    soma = round(sum(_num(p.get("valor")) for p in parcelas), 2)
    if total and parcelas and abs(soma - total) > 1:
        inconsistencias.append(f"parcelas somam R$ {soma:.2f}, o contrato diz R$ {total:.2f}")
    for anterior, seguinte in zip(datas, datas[1:]):
        if (seguinte - anterior).days > 90:
            inconsistencias.append(f"intervalo de {(seguinte - anterior).days} dias entre "
                                   f"{anterior.isoformat()} e {seguinte.isoformat()} (data digitada errada?)")

    return {
        "service_id": servico.get("id"),
        "titulo": servico.get("titulo"),
        "cliente": servico.get("cliente"),
        "status": servico.get("status"),
        "parcelas_total": len(parcelas),
        "parcelas_pagas": len(pagas),
        "parcelas_restantes": len(pendentes),
        "valor_restante": round(sum(_num(p.get("valor")) for p in pendentes), 2),
        "proxima": ({"id": proxima.get("id"), "data": str(proxima.get("data_prevista"))[:10],
                     "valor": _num(proxima.get("valor")), "descricao": proxima.get("descricao")} if proxima else None),
        "atrasadas": [{"id": p.get("id"), "data": str(p.get("data_prevista"))[:10], "valor": _num(p.get("valor")),
                       "descricao": p.get("descricao")} for p in atrasadas],
        # ids para editar_parcela_servico (adiar, marcar paga/pendente).
        "pendentes": [{"id": p.get("id"), "data": str(p.get("data_prevista"))[:10], "valor": _num(p.get("valor"))}
                      for p in pendentes],
        "termina_em": ultima.isoformat() if ultima else None,
        "tipo_contrato": servico.get("tipo_contrato"),
        "acabando": mensal and 0 < len(pendentes) <= LIMITE_ACABANDO,
        "inconsistencias": inconsistencias,
    }


def projetar(contratos_brutos: list[dict], renda_ifes: float, hoje: date, meses: int = 6) -> list[dict]:
    """Renda prevista por mes: Ifes fixo + parcelas pendentes. Parcela atrasada cai no mes atual."""
    chaves = []
    ano, mes = hoje.year, hoje.month
    for _ in range(meses):
        chaves.append(f"{ano:04d}-{mes:02d}")
        mes += 1
        if mes > 12:
            ano, mes = ano + 1, 1
    meses_proj = {c: {"mes": c, "ifes": round(renda_ifes, 2), "servicos": 0.0, "detalhe": []} for c in chaves}
    for servico in contratos_brutos:
        for parcela in servico.get("parcelas") or []:
            if not isinstance(parcela, dict) or parcela.get("status") == "pago":
                continue
            quando = _data(parcela.get("data_prevista"))
            if quando is None:
                continue
            chave = max(_mes(quando), chaves[0])
            if chave not in meses_proj:
                continue
            valor = _num(parcela.get("valor"))
            meses_proj[chave]["servicos"] = round(meses_proj[chave]["servicos"] + valor, 2)
            meses_proj[chave]["detalhe"].append({
                "titulo": servico.get("titulo"), "valor": valor,
                "parcela": parcela.get("descricao"), "atrasada": quando < hoje})
    for item in meses_proj.values():
        item["total"] = round(item["ifes"] + item["servicos"], 2)
    return list(meses_proj.values())


def renda_ifes_atual(db) -> tuple[float, str | None]:
    """Ultimo salario do Ifes recebido (valor, competencia YYYY-MM).

    Pelo nome do lancamento, nao pela categoria: "Renda Principal" tambem tem
    diarias, reembolsos e restituicao (ver fontes_renda).
    """
    import fontes_renda

    melhor = None
    for snap in db.collection("income_entries").stream():
        d = snap.to_dict() or {}
        if not d.get("isReceived") or d.get("status") == "deleted" or not fontes_renda.e_salario_ifes(d):
            continue
        chave = (int(d.get("year") or 0), int(d.get("month") or 0))
        if melhor is None or chave > melhor[0]:
            melhor = (chave, _num(d.get("amount")))
    if melhor is None:
        return 0.0, None
    (ano, mes0), valor = melhor
    return valor, f"{ano:04d}-{mes0 + 1:02d}"


def contratos_ativos(db) -> list[dict]:
    ativos = []
    for snap in db.collection("servicos").stream():
        d = snap.to_dict() or {}
        if d.get("status") in STATUS_ATIVOS:
            ativos.append({**d, "id": snap.id})
    return ativos


def resumo(db, hoje: date, meses: int = 6) -> dict:
    contratos = contratos_ativos(db)
    resumos = sorted((resumir_contrato(c, hoje) for c in contratos),
                     key=lambda r: (r["parcelas_restantes"] == 0, r["termina_em"] or "9999"))
    ifes, competencia = renda_ifes_atual(db)
    return {
        "contratos": resumos,
        "acabando": [r["titulo"] for r in resumos if r["acabando"]],
        "projecao": projetar(contratos, ifes, hoje, meses),
        "base_ifes": {"valor": ifes, "competencia": competencia,
                      "observacao": "ultima Renda Principal recebida; nao inclui 13o nem reajuste"},
    }


def posicao_da_parcela(servico: dict, parcela_id: str) -> dict | None:
    """'Parcela 7' vira 'parcela 7 de 12, faltam 5' — o que a renda sozinha nao diz."""
    parcelas = sorted((p for p in servico.get("parcelas") or [] if isinstance(p, dict)),
                      key=lambda p: str(p.get("data_prevista") or ""))
    for indice, parcela in enumerate(parcelas, start=1):
        if parcela.get("id") == parcela_id:
            pendentes = sum(1 for p in parcelas if p.get("status") != "pago")
            datas = [d for d in (_data(p.get("data_prevista")) for p in parcelas) if d]
            return {"parcela": f"{indice}/{len(parcelas)}", "parcelas_restantes": pendentes,
                    "termina_em": max(datas).isoformat() if datas else None}
    return None


def itens_atencao(resumos: list[dict], hoje: date) -> list[dict]:
    """Item da fila de atencao para cada contrato com 2 parcelas ou menos a receber."""
    itens = []
    for r in resumos:
        if not r["acabando"]:
            continue
        restantes = r["parcelas_restantes"]
        itens.append({
            "origem": "financeiro",
            "tipo": "renda_servico_acabando",
            "prioridade": "media",
            "titulo": f"Renda de '{r['titulo']}' acaba em {restantes} parcela(s)",
            "resumo": (f"Faltam {restantes} parcela(s) de '{r['titulo']}' (R$ {r['valor_restante']:.2f}); "
                       f"a última está prevista para {r['termina_em']}."),
            "acao_id": None, "etapa_id": None, "pessoa": r.get("cliente"),
            "prazo": r["termina_em"],
            "evidencia": {"service_id": r["service_id"], "parcelas_restantes": restantes,
                          "valor_restante": r["valor_restante"], "termina_em": r["termina_em"]},
            "sugestao": "Renovar, substituir essa renda ou ajustar o orçamento dos meses seguintes.",
            "chave_dedupe": f"renda_servico_acabando:{r['service_id']}:{r['termina_em']}",
        })
    return itens
