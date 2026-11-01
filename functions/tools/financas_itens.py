"""Editar e excluir lancamentos do financeiro interno, ajustar parcela de renda de servico e deduplicar rendas.

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
import rendas_servico
from rendas_servico import STATUS_SEM_PREVISAO

COLECAO = {"renda": "income_entries", "obrigacao_fixa": "fixed_bills",
           "transacao_avulsa": "finance_transactions"}
_QUITADO = {"renda": "isReceived", "obrigacao_fixa": "isPaid"}
# Dia do mes em que a renda e esperada ou a conta fixa vence (ex.: pedido do
# Andre em 01/11/2026 para mudar o dia da Natacao). transacao_avulsa tem data
# completa, nao dia fixo -- fica de fora, como competencia.
_DIA = {"renda": "day", "obrigacao_fixa": "dueDay"}
# Marca em `income_entries.retirada_por` de quem tirou a renda (status 'deleted'): a
# previsao (parcela fora dela) pode ser desfeita pela previsao; a duplicata, nunca.
RETIRADA_PREVISAO = "previsao"
RETIRADA_DUPLICATA = "duplicata"


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
    if args.get("dia") is not None:
        campo = _DIA.get(tipo)
        if not campo:
            return {"erro": "transação avulsa não tem dia fixo; mude a data pela tela."}
        try:
            dia = int(args["dia"])
        except (TypeError, ValueError):
            return {"erro": "dia deve ser um número entre 1 e 31."}
        if not 1 <= dia <= 31:
            return {"erro": "dia deve ser um número entre 1 e 31."}
        mudanca[campo] = dia
    if not mudanca:
        return {"erro": "Nada para mudar: informe descricao, valor, competencia, quitado ou dia."}
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
    saida = {"status": "excluido", "tipo": tipo, "id": ref.id, "descricao": atual.get("description"),
             "valor": atual.get("amount"), "reversivel": tipo != "obrigacao_fixa"}
    if tipo == "renda" and _parcela_segue_prevista(db, atual, ref.id):
        saida["aviso"] = ("A renda saiu do mês e a tela não a recria, mas a parcela continua pendente na projeção de "
                          "consultar_rendas_servico. Para tirá-la de lá também: editar_parcela_servico com "
                          "status='sem_previsao'.")
    return saida


def _parcela_segue_prevista(db, renda: dict, renda_id: str) -> bool:
    """Renda de servico excluida cuja parcela segue pendente, com data, e sem outra renda ativa."""
    service_id, parcela_id = renda.get("service_id"), renda.get("parcela_id")
    if not (service_id and parcela_id):
        return False
    snap = db.collection("servicos").document(str(service_id)).get()
    parcela = next((p for p in ((snap.to_dict() or {}).get("parcelas") or [])
                    if isinstance(p, dict) and p.get("id") == parcela_id), None) if snap.exists else None
    if not parcela or parcela.get("status") == "pago" or rendas_servico.fora_da_previsao(parcela):
        return False
    return not any(r.id != renda_id and (r.to_dict() or {}).get("status") != "deleted"
                   for r in db.collection("income_entries").where("parcela_id", "==", parcela_id).stream())


def _rendas_ligadas(db, parcela_id: str) -> list:
    """Rendas (de qualquer status) ligadas a parcela por `parcela_id` ou `rubricId`, sem repetir."""
    achadas: dict = {}
    for campo in ("parcela_id", "rubricId"):
        for r in db.collection("income_entries").where(campo, "==", parcela_id).stream():
            achadas.setdefault(r.id, r)
    return list(achadas.values())


def editar_parcela_servico(db, args: dict) -> dict:
    """Marca parcela como paga/pendente/sem_previsao, adia, limpa a data ou corrige o valor.

    Atualiza tambem a renda ligada a parcela (`parcela_id` ou `rubricId`, os dois
    vinculos que a tela usa), para o financeiro do mes nao ficar defasado ate a tela
    sincronizar de novo. Parcela fora da previsao (`sem_previsao`, ou pendente sem
    data) tira a renda do mes e sai da projecao; voltar a pendente com data a devolve.
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
    if args.get("limpar_data_prevista"):
        if args.get("data_prevista"):
            return {"erro": "Informe data_prevista OU limpar_data_prevista, não os dois."}
        nova["data_prevista"] = ""
    elif args.get("data_prevista"):
        try:
            nova["data_prevista"] = date.fromisoformat(str(args["data_prevista"])[:10]).isoformat()
        except ValueError:
            return {"erro": "data_prevista deve ser YYYY-MM-DD."}
    if args.get("status"):
        if args["status"] not in ("pago", "pendente", STATUS_SEM_PREVISAO):
            return {"erro": "status deve ser 'pago', 'pendente' ou 'sem_previsao'."}
        if args["status"] == STATUS_SEM_PREVISAO and antes.get("status") == "pago":
            return {"erro": "Parcela paga não sai da previsão: volte para 'pendente' antes."}
        nova["status"] = args["status"]
    if args.get("valor") is not None:
        nova["valor"] = float(args["valor"])
    if nova == antes:
        return {"erro": "Nada para mudar: informe data_prevista, limpar_data_prevista, status ou valor."}
    parcelas[indice] = nova
    ref.update({"parcelas": parcelas})

    ligadas = _rendas_ligadas(db, parcela_id)
    ativas = [r for r in ligadas if (r.to_dict() or {}).get("status") != "deleted"]
    atualizadas, retiradas, reativadas = [], [], []
    if rendas_servico.fora_da_previsao(nova):
        for r in ativas:
            r.reference.update({"status": "deleted", "retirada_por": RETIRADA_PREVISAO})
            retiradas.append(r.id)
    else:
        renda = {"amount": nova.get("valor"), "isReceived": nova.get("status") == "pago"}
        try:
            d = date.fromisoformat(str(nova.get("data_prevista") or "")[:10])
            renda.update(month=d.month - 1, year=d.year, day=d.day)
        except ValueError:
            pass
        for r in ativas:
            r.reference.update(renda)
            atualizadas.append(r.id)
        if not ativas and rendas_servico.fora_da_previsao(antes):
            # Reativar e pedido explicito: traz de volta a renda excluida mais recente (menos a de duplicata).
            candidatas = [r for r in ligadas if (r.to_dict() or {}).get("retirada_por") != RETIRADA_DUPLICATA]
            if candidatas:
                volta = max(candidatas, key=lambda r: (r.to_dict() or {}).get("data_criacao") or "")
                volta.reference.update({**renda, "status": "active", "retirada_por": None})
                reativadas.append(volta.id)
    saida = {"status": "ok", "service_id": service_id, "parcela_id": parcela_id,
             "alterado": {k: [antes.get(k), nova.get(k)] for k in nova if antes.get(k) != nova.get(k)},
             "rendas_atualizadas": atualizadas, "rendas_retiradas": retiradas, "rendas_reativadas": reativadas}
    if nova.get("status") == "pendente" and rendas_servico.fora_da_previsao(nova):
        saida["aviso"] = "Parcela pendente sem data_prevista: fica fora da renda do mês e da projeção até definir a data."
    return saida


def _competencia_da_renda(d: dict) -> str | None:
    try:
        return f"{int(d['year']):04d}-{int(d['month']) + 1:02d}"
    except (KeyError, TypeError, ValueError):
        return None


def _resumo_renda(snap, d: dict) -> dict:
    return {"id": snap.id, "descricao": d.get("description"), "valor": d.get("amount"),
            "recebida": bool(d.get("isReceived")), "data_criacao": d.get("data_criacao")}


def deduplicar_rendas_servico(db, args: dict) -> dict:
    """Rendas ativas repetidas para a mesma parcela e competencia: mantem uma, marca as extras como deleted.

    Roda em simulacao por padrao (`simular` omitido = true): so lista o que mudaria.
    Mantem a ja recebida; entre iguais, a mais antiga. As extras ficam recuperaveis
    (status 'deleted', `retirada_por: 'duplicata'`, `duplicata_de` com o id mantido).
    """
    simular = args.get("simular") is not False
    grupos: dict = {}
    for snap in db.collection("income_entries").stream():
        d = snap.to_dict() or {}
        comp = _competencia_da_renda(d)
        if d.get("status") == "deleted" or comp is None or not (d.get("service_id") and d.get("parcela_id")):
            continue
        grupos.setdefault((d["service_id"], d["parcela_id"], comp), []).append((snap, d))

    mudancas, extras_total = [], 0
    for (service_id, parcela_id, comp), itens in grupos.items():
        if len(itens) < 2:
            continue
        itens.sort(key=lambda sd: (not sd[1].get("isReceived"), sd[1].get("data_criacao") or "", sd[0].id))
        (mantida, d_mantida), extras = itens[0], itens[1:]
        mudancas.append({"service_id": service_id, "parcela_id": parcela_id, "competencia": comp,
                         "mantida": _resumo_renda(mantida, d_mantida),
                         "extras": [_resumo_renda(s, d) for s, d in extras]})
        extras_total += len(extras)
        if not simular:
            for s, _ in extras:
                s.reference.update({"status": "deleted", "retirada_por": RETIRADA_DUPLICATA,
                                    "duplicata_de": mantida.id})
    saida = {"modo": "simulacao" if simular else "aplicado", "grupos_duplicados": len(mudancas),
             "rendas_extras": extras_total, "mudancas": mudancas}
    if simular and mudancas:
        saida["como_aplicar"] = "Confira a lista e repita com simular=false."
    return saida
