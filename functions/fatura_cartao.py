"""Fatura de cartao de credito: extracao dos lancamentos e projecao de parcelas.

O `sync_boletos_gmail` ja acha a fatura no Gmail, destrava o PDF com a senha do
Secret Manager e extrai valor, vencimento e codigo de barras. Isso trata a fatura
como **boleto**: uma linha a pagar.

Fatura de cartao e outra coisa. O que permite direcionamento financeiro sao os
**lancamentos** — e, dentro deles, as **parcelas**. Uma fatura diz quanto voce
gastou; as parcelas dizem quanto do mes que vem ja esta comprometido antes de
voce gastar qualquer coisa. Sem os itens, nenhum raciocinio sobre a fatura passa
de "voce gastou R$ X", que o usuario ja sabe olhando o e-mail.

Este modulo faz a aquisicao e o armazenamento. **Analise nao mora aqui**: quem
raciocina sobre esses dados e o cliente MCP, com as tools de consulta no fim do
arquivo. Extracao de PDF e trabalho mecanico e barato, roda sozinha e cabe num
modelo leve; conselho financeiro nao.

Colecoes:
  fatura_cartao        cabecalho, um doc por competencia (`elo-caixa-2026-09`)
  fatura_cartao_itens  um doc por lancamento, com `competencia` para consulta
                       cruzando meses (necessario para projetar parcelas)

O PDF nao e guardado em lugar nenhum: e buscado, lido e descartado, como ja
acontece hoje. Fatura de cartao em Storage e dado sensivel sem necessidade, e o
proprio Gmail ja e o arquivo de onde se pode reextrair.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone

COL_FATURAS = "fatura_cartao"
COL_ITENS = "fatura_cartao_itens"

# Remetentes cuja fatura recebe o tratamento de cartao. A senha do PDF ja vem de
# `bill_pdf_password_configs` / Secret Manager, configurada como "Fatura Elo".
REMETENTES_CARTAO: dict[str, str] = {
    "cartoescaixa@aplicacao.caixa.gov.br": "elo-caixa",
}

# A partir de quando a extracao pode corrigir o total em `fixed_bills`.
#
# Ate agosto/2026 os valores foram lancados a mao pelo dono do sistema e ja estao
# pagos e conferidos; sobrescrever apagaria trabalho manual correto. Os itens sao
# extraidos de qualquer competencia — sao dados novos, nao sobrescrevem nada.
CORRIGIR_FIXED_BILLS_A_PARTIR_DE = (2026, 9)


def e_fatura_de_cartao(remetente: str | None) -> str | None:
    """Identificador do cartao se o remetente for de fatura; senao None."""
    if not remetente:
        return None
    alvo = str(remetente).strip().lower()
    for endereco, cartao in REMETENTES_CARTAO.items():
        if endereco in alvo:
            return cartao
    return None


def pode_corrigir_fixed_bill(mes: int | None, ano: int | None) -> bool:
    if not mes or not ano:
        return False
    return (int(ano), int(mes)) >= CORRIGIR_FIXED_BILLS_A_PARTIR_DE


# --------------------------------------------------------------------------
# Extracao
# --------------------------------------------------------------------------

_PROMPT = """Você recebe a fatura de um cartão de crédito em PDF. Extraia os dados
estruturados abaixo. Não interprete, não aconselhe, não resuma: transcreva.

CABEÇALHO:
- total: valor total da fatura (número)
- vencimento: data de vencimento (YYYY-MM-DD)
- competencia: mês de referência da fatura (YYYY-MM)
- limite_total, limite_disponivel: se aparecerem (número ou null)
- total_anterior, pagamentos, juros_encargos: se aparecerem (número ou null)

LANÇAMENTOS: todos os itens da fatura, um por linha do extrato.
- data: data da compra (YYYY-MM-DD). Se só houver dia/mês, use o ano da competência.
- estabelecimento: nome como aparece, sem normalizar
- valor: número. Estornos e créditos vêm NEGATIVOS.
- parcela_atual e parcela_total: quando a linha indicar parcelamento
  (ex.: "PARCELA 03/12", "03/12", "3 DE 12"), extraia os dois números.
  Compra à vista: ambos null.
- cartao_final: 4 últimos dígitos, se a fatura separar por cartão

Regras:
- Não invente lançamento que não esteja no documento.
- Não agrupe nem some itens: uma linha do extrato é um item.
- Ignore linhas de saldo, subtotal e propaganda.

Responda APENAS o JSON:
{
  "cabecalho": {"total": 0, "vencimento": "YYYY-MM-DD", "competencia": "YYYY-MM",
                "limite_total": null, "limite_disponivel": null,
                "total_anterior": null, "pagamentos": null, "juros_encargos": null},
  "itens": [{"data": "YYYY-MM-DD", "estabelecimento": "", "valor": 0,
             "parcela_atual": null, "parcela_total": null, "cartao_final": null}]
}
Se o documento não for uma fatura de cartão, responda {"error": "nao_e_fatura"}."""


def extrair(client, types, pdf_bytes: bytes, contexto_email: str = "") -> dict:
    """Roda a extracao no PDF. Levanta ValueError se o documento nao servir."""
    from gemini_cost_controls import GEMINI_DOCUMENT_MODEL

    partes = [_PROMPT]
    if contexto_email:
        partes.append(contexto_email)
    partes.append(types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"))

    resposta = client.models.generate_content(model=GEMINI_DOCUMENT_MODEL, contents=partes)
    bruto = (resposta.text or "").strip()
    bruto = re.sub(r"^```(?:json)?|```$", "", bruto, flags=re.MULTILINE).strip()

    try:
        dados = json.loads(bruto)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Resposta da extracao nao e JSON: {bruto[:200]}") from exc

    if dados.get("error"):
        raise ValueError(f"Documento recusado pela extracao: {dados['error']}")
    if not isinstance(dados.get("itens"), list):
        raise ValueError("Extracao nao devolveu lista de itens.")
    return dados


# --------------------------------------------------------------------------
# Normalizacao e gravacao
# --------------------------------------------------------------------------

# A fatura tem tres naturezas de linha, e confundi-las distorce numeros
# diferentes:
#
#   compra   gasto num estabelecimento — e o que responde "onde foi o dinheiro"
#   encargo  IOF, juros, anuidade, multa. Custo REAL, mas nao e estabelecimento.
#            Classificar como ajuste subestimava o gasto do mes; como compra,
#            "IOF COMPRA INTERNACIONAL" viraria um dos maiores "estabelecimentos".
#   ajuste   saldo anterior e pagamento recebido. Somam zero entre si e existem
#            so para o total da fatura fechar.
#
# O prompt manda ignorar as duas ultimas e o modelo nao obedece de forma
# confiavel, entao a classificacao e deterministica. Nada e descartado: as tres
# somadas tem que reproduzir o total impresso, e e assim que se confere a
# extracao.
_PADROES_AJUSTE = re.compile(
    r"total\s+da\s+fatura|fatura\s+anterior|saldo\s+anterior|obrigado\s+pelo\s+pagamento"
    r"|pagamento\s+(efetuado|recebido)|pgto\s+|subtotal|total\s+a\s+pagar|limite\s+"
    r"|ajuste\s+cred",
    re.IGNORECASE,
)
_PADROES_ENCARGO = re.compile(
    r"\biof\b|juros|encargos?\b|multa|anuidade|tarifa|mora|rotativ|parcelamento\s+de\s+fatura",
    re.IGNORECASE,
)


def classificar(estabelecimento: str) -> str:
    texto = estabelecimento or ""
    if _PADROES_AJUSTE.search(texto):
        return "ajuste"
    if _PADROES_ENCARGO.search(texto):
        return "encargo"
    return "compra"


def _num(valor) -> float | None:
    if valor is None or valor == "":
        return None
    try:
        return round(float(str(valor).replace(".", "").replace(",", ".")
                          if isinstance(valor, str) and "," in str(valor) else valor), 2)
    except (TypeError, ValueError):
        return None


def _inteiro(valor) -> int | None:
    try:
        n = int(valor)
        return n if n > 0 else None
    except (TypeError, ValueError):
        return None


def _competencia_valida(valor, vencimento: str | None) -> str:
    """Competencia derivada do VENCIMENTO, nao do que o modelo disser.

    O modelo alterna entre o mes de referencia e o mes de fechamento, e o mesmo
    e-mail chega as vezes duas vezes (fatura fechada e fatura disponivel). Com a
    competencia vindo do modelo, a mesma fatura virava dois documentos com meses
    diferentes — foi o que aconteceu com 2025-08 e 2025-09, identicas nos 77
    lancamentos. O vencimento e um dado impresso, nao inferido.
    """
    if vencimento and re.match(r"\d{4}-\d{2}", str(vencimento)):
        return str(vencimento)[:7]
    texto = str(valor or "").strip()
    if re.fullmatch(r"\d{4}-\d{2}", texto):
        return texto
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _id_do_item(competencia: str, item: dict, indice: int) -> str:
    """Id deterministico: reextrair a mesma fatura atualiza, nao duplica.

    O indice entra na chave porque a mesma compra pode aparecer duas vezes na
    fatura legitimamente (dois cafes no mesmo lugar, no mesmo dia, mesmo valor).
    """
    semente = "|".join([
        competencia, str(item.get("data")), str(item.get("estabelecimento")),
        str(item.get("valor")), str(indice),
    ])
    return hashlib.sha256(semente.encode("utf-8")).hexdigest()[:24]


def salvar(db, cartao: str, dados: dict, *, google_message_id: str | None = None) -> dict:
    """Grava cabecalho e itens. Idempotente por competencia."""
    cabecalho = dados.get("cabecalho") or {}
    vencimento = str(cabecalho.get("vencimento") or "").strip() or None
    competencia = _competencia_valida(cabecalho.get("competencia"), vencimento)
    fatura_id = f"{cartao}-{competencia}"

    ano, mes = int(competencia[:4]), int(competencia[5:7])
    itens = dados.get("itens") or []

    doc_cabecalho = {
        "fatura_id": fatura_id,
        "cartao": cartao,
        "competencia": competencia,
        "ano": ano,
        "mes": mes,
        "vencimento": vencimento,
        "total": _num(cabecalho.get("total")),
        "limite_total": _num(cabecalho.get("limite_total")),
        "limite_disponivel": _num(cabecalho.get("limite_disponivel")),
        "total_anterior": _num(cabecalho.get("total_anterior")),
        "pagamentos": _num(cabecalho.get("pagamentos")),
        "juros_encargos": _num(cabecalho.get("juros_encargos")),
        "total_itens": len(itens),
        "google_message_id": google_message_id,
        "extraido_em": datetime.now(timezone.utc).isoformat(),
    }
    db.collection(COL_FATURAS).document(fatura_id).set(doc_cabecalho, merge=True)

    # Apaga os lancamentos desta competencia antes de regravar.
    #
    # O id deterministico por si so nao basta: a mesma fatura chega em dois
    # e-mails (fechada e disponivel) e a extracao pode devolver os itens em ordem
    # ou quantidade um pouco diferentes. Como o indice entra na chave, os ids nao
    # coincidem e os itens ACUMULAM em vez de substituir — foi o que aconteceu com
    # 2025-10, que ficou com 221 lancamentos para uma fatura de 114, dobrando o
    # gasto do mes e inflando a projecao de parcelas.
    antigos = list(db.collection(COL_ITENS).where("fatura_id", "==", fatura_id).stream())
    for inicio in range(0, len(antigos), 400):
        limpeza = db.batch()
        for doc in antigos[inicio:inicio + 400]:
            limpeza.delete(doc.reference)
        limpeza.commit()

    lote = db.batch()
    gravados = 0
    soma_compras = 0.0
    soma_encargos = 0.0
    soma_total = 0.0
    for indice, item in enumerate(itens):
        valor = _num(item.get("valor"))
        estabelecimento = str(item.get("estabelecimento") or "").strip()
        if valor is None or not estabelecimento:
            continue
        parcela_total = _inteiro(item.get("parcela_total"))
        tipo = classificar(estabelecimento)
        soma_total += valor
        if tipo == "compra":
            soma_compras += valor
        elif tipo == "encargo":
            soma_encargos += valor
        ref = db.collection(COL_ITENS).document(_id_do_item(competencia, item, indice))
        lote.set(ref, {
            "tipo": tipo,
            "fatura_id": fatura_id,
            "cartao": cartao,
            "competencia": competencia,
            "ano": ano,
            "mes": mes,
            "data": str(item.get("data") or "").strip() or None,
            "estabelecimento": estabelecimento,
            "valor": valor,
            "parcela_atual": _inteiro(item.get("parcela_atual")),
            "parcela_total": parcela_total,
            "parcelado": bool(parcela_total and parcela_total > 1),
            "cartao_final": str(item.get("cartao_final") or "").strip() or None,
        }, merge=True)
        gravados += 1
    lote.commit()

    soma_compras = round(soma_compras, 2)
    soma_encargos = round(soma_encargos, 2)
    soma_total = round(soma_total, 2)
    total_cabecalho = doc_cabecalho["total"]
    # O total impresso e a soma das compras deveriam bater. Quando nao batem, o
    # mais provavel e o modelo ter lido o saldo anterior como total da fatura —
    # foi o caso de 2026-06. Registrar a divergencia deixa isso visivel em vez de
    # virar um numero errado com cara de certo.
    # Confere contra a soma de TODAS as linhas, nao so das compras: IOF e juros
    # entram no total impresso. Comparar so com as compras marcava como suspeita
    # uma fatura perfeitamente extraida — foi o que aconteceu com 2026-06, cujos
    # R$ 389 de "divergencia" eram exatamente o IOF da compra internacional.
    divergencia = (None if total_cabecalho is None
                   else round(abs(total_cabecalho - soma_total), 2))
    db.collection(COL_FATURAS).document(fatura_id).set({
        "soma_compras": soma_compras,
        "soma_encargos": soma_encargos,
        "soma_total": soma_total,
        "divergencia_total": divergencia,
        "confiavel": divergencia is not None and divergencia < max(1.0, abs(soma_total) * 0.01),
    }, merge=True)

    return {
        "fatura_id": fatura_id,
        "competencia": competencia,
        "ano": ano,
        "mes": mes,
        "total": total_cabecalho,
        "soma_compras": soma_compras,
        "soma_encargos": soma_encargos,
        "soma_total": soma_total,
        "divergencia_total": divergencia,
        "vencimento": vencimento,
        "itens_gravados": gravados,
        "itens_ignorados": len(itens) - gravados,
    }


# --------------------------------------------------------------------------
# Consulta
# --------------------------------------------------------------------------

def consultar(db, *, competencia: str | None = None, desde: str | None = None,
              estabelecimento: str | None = None, apenas_parceladas: bool = False,
              limite: int = 200) -> dict:
    """Lancamentos por periodo e/ou estabelecimento, com totais por estabelecimento.

    Devolve dado agregado junto com a lista porque o agregado e o que quase sempre
    responde a pergunta, e a lista crua de uma fatura passa de 200 linhas — o
    cliente MCP corta resultado grande e a resposta chegaria truncada no meio.
    """
    consulta = db.collection(COL_ITENS)
    if competencia:
        consulta = consulta.where("competencia", "==", str(competencia))
    elif desde:
        consulta = consulta.where("competencia", ">=", str(desde))

    itens = []
    alvo = (estabelecimento or "").strip().lower()
    for snap in consulta.limit(2000).stream():
        item = snap.to_dict() or {}
        if item.get("tipo") == "ajuste":
            continue   # saldo e pagamento somam zero e nao sao gasto
        if apenas_parceladas and not item.get("parcelado"):
            continue
        if alvo and alvo not in str(item.get("estabelecimento", "")).lower():
            continue
        itens.append(item)

    itens.sort(key=lambda i: (str(i.get("competencia") or ""), str(i.get("data") or "")))

    encargos = [i for i in itens if i.get("tipo") == "encargo"]
    itens = [i for i in itens if i.get("tipo") != "encargo"]

    por_estabelecimento: dict[str, dict] = {}
    for item in itens:
        nome = item["estabelecimento"]
        acumulado = por_estabelecimento.setdefault(nome, {"estabelecimento": nome, "total": 0.0, "lancamentos": 0})
        acumulado["total"] = round(acumulado["total"] + item["valor"], 2)
        acumulado["lancamentos"] += 1

    ranking = sorted(por_estabelecimento.values(), key=lambda x: -x["total"])

    total_encargos = round(sum(i["valor"] for i in encargos), 2)
    return {
        "total_lancamentos": len(itens),
        "total_gasto": round(sum(i["valor"] for i in itens), 2),
        # Separado de proposito: IOF e juros sao custo real, mas nao sao gasto
        # num estabelecimento — misturar esconde os dois.
        "total_encargos": total_encargos,
        "encargos": [{"descricao": e["estabelecimento"], "valor": e["valor"],
                      "competencia": e["competencia"]} for e in encargos[:20]],
        "por_estabelecimento": ranking[:40],
        "lancamentos": itens[:limite],
        "truncado": len(itens) > limite,
        "filtros": {
            "competencia": competencia, "desde": desde,
            "estabelecimento": estabelecimento, "apenas_parceladas": apenas_parceladas,
        },
    }


def projetar_parcelas(db, *, meses: int = 12) -> dict:
    """Quanto de cada mes futuro ja esta comprometido por compras parceladas.

    Este e o numero que a fatura sozinha nao da. Ela diz o que foi gasto; a
    projecao diz quanto do mes que vem ja esta gasto antes de comecar. Cada
    parcela `atual/total` de uma competencia implica `total - atual` parcelas
    ainda por vir, uma por mes seguinte.
    """
    hoje = datetime.now(timezone.utc)
    futuro: dict[str, dict] = {}

    for snap in db.collection(COL_ITENS).where("parcelado", "==", True).limit(3000).stream():
        item = snap.to_dict() or {}
        atual, total = item.get("parcela_atual"), item.get("parcela_total")
        competencia = str(item.get("competencia") or "")
        if not (atual and total and total > atual and re.fullmatch(r"\d{4}-\d{2}", competencia)):
            continue

        ano, mes = int(competencia[:4]), int(competencia[5:7])
        for adiante in range(1, (total - atual) + 1):
            m = mes + adiante
            chave = f"{ano + (m - 1) // 12:04d}-{((m - 1) % 12) + 1:02d}"
            if chave <= hoje.strftime("%Y-%m"):
                continue
            bucket = futuro.setdefault(chave, {"competencia": chave, "total": 0.0, "parcelas": []})
            bucket["total"] = round(bucket["total"] + item["valor"], 2)
            bucket["parcelas"].append({
                "estabelecimento": item["estabelecimento"],
                "valor": item["valor"],
                "parcela": f"{atual + adiante}/{total}",
            })

    meses_ordenados = [futuro[k] for k in sorted(futuro)][:meses]
    for m in meses_ordenados:
        m["parcelas"].sort(key=lambda p: -p["valor"])
        m["qtd_parcelas"] = len(m["parcelas"])
        m["parcelas"] = m["parcelas"][:25]

    return {
        "meses": meses_ordenados,
        "total_comprometido": round(sum(m["total"] for m in meses_ordenados), 2),
        "gerado_em": hoje.strftime("%Y-%m-%d"),
    }


# --------------------------------------------------------------------------
# Correcao do lado "conta a pagar"
# --------------------------------------------------------------------------

# Como achar o card de `fixed_bills` que corresponde a cada cartao.
_DESCRICAO_DO_CARTAO = {"elo-caixa": "elo"}


def corrigir_fixed_bill(db, cartao: str, resumo: dict) -> dict:
    """Acerta o total em `fixed_bills` com o valor real extraido da fatura.

    So age da competencia de corte em diante — antes disso os valores foram
    lancados a mao e ja estao pagos e conferidos. O valor anterior fica guardado
    em `amount_anterior`, para o acerto ser auditavel e reversivel: sobrescrever
    numero de financeiro sem deixar rastro e pior do que nao corrigir.
    """
    mes, ano, total = resumo.get("mes"), resumo.get("ano"), resumo.get("total")
    if total is None:
        return {"corrigido": False, "motivo": "extracao nao trouxe total"}
    if not pode_corrigir_fixed_bill(mes, ano):
        return {"corrigido": False, "motivo": f"{mes}/{ano} e anterior ao corte (lancado a mao)"}
    divergencia = resumo.get("divergencia_total")
    if divergencia is not None and divergencia >= max(1.0, abs(resumo.get("soma_total") or 0) * 0.01):
        # Total impresso nao bate com a soma das compras: provavelmente o modelo
        # leu outra linha como total. Nao vale sobrescrever o financeiro com isso.
        return {"corrigido": False,
                "motivo": f"extracao pouco confiavel (divergencia de R$ {divergencia})"}

    marcador = _DESCRICAO_DO_CARTAO.get(cartao, cartao)
    alterados = []
    for snap in (db.collection("fixed_bills")
                 .where("month", "==", mes).where("year", "==", ano).stream()):
        dados = snap.to_dict() or {}
        if marcador not in str(dados.get("description", "")).lower():
            continue
        anterior = dados.get("amount")
        if anterior == total:
            continue
        snap.reference.update({
            "amount": total,
            "amount_anterior": anterior,
            "amount_origem": "fatura_cartao",
            "amount_corrigido_em": datetime.now(timezone.utc).isoformat(),
            "fatura_id": resumo.get("fatura_id"),
        })
        alterados.append({"doc": snap.id, "de": anterior, "para": total})

    return {"corrigido": bool(alterados), "alteracoes": alterados,
            "motivo": None if alterados else "nenhum card correspondente ou ja estava certo"}
