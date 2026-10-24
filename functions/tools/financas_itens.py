"""Editar e excluir lancamentos do financeiro interno, e ajustar parcela de renda de servico.

Ate 24/10/2026 o catalogo so criava (`registrar_item_financeiro_v2`): um mes errado
ficava gravado para sempre, e "corrigir" passando o id criava OUTRO lancamento
(incidente de 23/10: remuneracao de novembro gravada em dezembro). Mesma semantica
da tela (index.tsx): renda e transacao saem com `status: 'deleted'` (reversivel);
conta fixa e apagada de vez, como o `deleteDoc` da tela.
"""
from __future__ import annotations

import unicodedata
from datetime import date

import competencia

COLECAO = {"renda": "income_entries", "obrigacao_fixa": "fixed_bills",
           "transacao_avulsa": "finance_transactions"}
_QUITADO = {"renda": "isReceived", "obrigacao_fixa": "isPaid"}


def _normal(texto) -> str:
    sem_acento = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode()
    return " ".join(sem_acento.lower().split())


def _item(db, tipo, item_id):
    if tipo not in COLECAO:
        return None, None, {"erro": "tipo deve ser 'renda', 'obrigacao_fixa' ou 'transacao_avulsa'."}
    if not str(item_id or "").strip():
        return None, None, {"erro": "Informe o id do lançamento (veja em consultar_financas_v2)."}
    ref = db.collection(COLECAO[tipo]).document(str(item_id).strip())
    snap = ref.get()
    dados = (snap.to_dict() or {}) if snap.exists else {}
    if not snap.exists or dados.get("status") == "deleted":
        return None, None, {"erro": f"{tipo} {item_id} não encontrado (ou já excluído)."}
    return ref, dados, None


def duplicatas(db, tipo: str, descricao: str, mes0: int, ano: int) -> list[dict]:
    """Lançamentos do mesmo tipo, mês e descrição (sem acento, maiúscula ou espaço extra)."""
    if tipo not in ("renda", "obrigacao_fixa"):
        return []
    alvo = _normal(descricao)
    achados = []
    for snap in (db.collection(COLECAO[tipo]).where("month", "==", int(mes0))
                 .where("year", "==", int(ano)).stream()):
        d = snap.to_dict() or {}
        if d.get("status") != "deleted" and _normal(d.get("description")) == alvo:
            achados.append({"id": snap.id, "descricao": d.get("description"), "valor": d.get("amount")})
    return achados


def editar(db, args: dict) -> dict:
    tipo = args.get("tipo")
    ref, atual, erro = _item(db, tipo, args.get("id"))
    if erro:
        return erro
    mudanca: dict = {}
    if args.get("descricao") is not None:
        mudanca["description"] = str(args["descricao"]).strip()
    if args.get("valor") is not None:
        mudanca["amount"] = float(args["valor"])
    if args.get("competencia"):
        if tipo == "transacao_avulsa":
            return {"erro": "transação avulsa não tem competência; mude a data pela tela."}
        try:
            mes0, ano = competencia.ler(args["competencia"])
        except ValueError as exc:
            return {"erro": str(exc)}
        mudanca.update(month=mes0, year=ano)
    if args.get("quitado") is not None:
        campo = _QUITADO.get(tipo)
        if not campo:
            return {"erro": "transação avulsa não tem recebido/pago."}
        mudanca[campo] = bool(args["quitado"])
    if not mudanca:
        return {"erro": "Nada para mudar: informe descricao, valor, competencia ou quitado."}
    ref.update(mudanca)
    saida = {"status": "ok", "tipo": tipo, "id": ref.id,
             "alterado": {k: [atual.get(k), v] for k, v in mudanca.items()}}
    if "month" in mudanca:
        saida["periodo"] = competencia.periodo(mudanca["month"], mudanca["year"])
    return saida


def excluir(db, args: dict) -> dict:
    tipo = args.get("tipo")
    ref, atual, erro = _item(db, tipo, args.get("id"))
    if erro:
        return erro
    if tipo == "obrigacao_fixa":
        ref.delete()
    else:
        ref.update({"status": "deleted"})
    return {"status": "excluido", "tipo": tipo, "id": ref.id, "descricao": atual.get("description"),
            "valor": atual.get("amount"), "reversivel": tipo != "obrigacao_fixa"}


def editar_parcela_servico(db, args: dict) -> dict:
    """Marca parcela como paga/pendente, adia (nova data prevista) ou corrige o valor.

    Atualiza tambem a renda ligada a parcela (`parcela_id` ou `rubricId`, os dois
    vinculos que a tela usa), para o financeiro do mes nao ficar defasado ate a tela
    sincronizar de novo.
    """
    service_id = str(args.get("service_id") or "").strip()
    parcela_id = str(args.get("parcela_id") or "").strip()
    if not service_id or not parcela_id:
        return {"erro": "Informe service_id e parcela_id (veja em consultar_rendas_servico)."}
    ref = db.collection("servicos").document(service_id)
    snap = ref.get()
    if not snap.exists:
        return {"erro": f"serviço {service_id} não encontrado."}
    parcelas = list((snap.to_dict() or {}).get("parcelas") or [])
    indice = next((i for i, p in enumerate(parcelas) if isinstance(p, dict) and p.get("id") == parcela_id), None)
    if indice is None:
        return {"erro": f"parcela {parcela_id} não existe no serviço {service_id}."}
    antes = dict(parcelas[indice])
    nova = dict(antes)
    if args.get("data_prevista"):
        try:
            nova["data_prevista"] = date.fromisoformat(str(args["data_prevista"])[:10]).isoformat()
        except ValueError:
            return {"erro": "data_prevista deve ser YYYY-MM-DD."}
    if args.get("status"):
        if args["status"] not in ("pago", "pendente"):
            return {"erro": "status deve ser 'pago' ou 'pendente'."}
        nova["status"] = args["status"]
    if args.get("valor") is not None:
        nova["valor"] = float(args["valor"])
    if nova == antes:
        return {"erro": "Nada para mudar: informe data_prevista, status ou valor."}
    parcelas[indice] = nova
    ref.update({"parcelas": parcelas})

    renda = {"amount": nova.get("valor"), "isReceived": nova.get("status") == "pago"}
    try:
        d = date.fromisoformat(str(nova.get("data_prevista") or "")[:10])
        renda.update(month=d.month - 1, year=d.year, day=d.day)
    except ValueError:
        pass
    rendas = []
    for campo in ("parcela_id", "rubricId"):
        for r in db.collection("income_entries").where(campo, "==", parcela_id).stream():
            if (r.to_dict() or {}).get("status") != "deleted" and r.id not in rendas:
                r.reference.update(renda)
                rendas.append(r.id)
    return {"status": "ok", "service_id": service_id, "parcela_id": parcela_id,
            "alterado": {k: [antes.get(k), nova.get(k)] for k in nova if antes.get(k) != nova.get(k)},
            "rendas_atualizadas": rendas}
