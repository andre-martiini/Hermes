"""Importa a fatura de cartao a partir de um arquivo, em vez do e-mail.

A Caixa parou de mandar a fatura do Elo por e-mail em agosto/2026, e a XP nunca
mandou. O dono baixa o arquivo (PDF da Caixa, CSV exportado do app da XP) e o
deixa no Drive; esta importacao grava pelo mesmo caminho da sincronizacao por
e-mail (`fatura_cartao.salvar` + `corrigir_fixed_bill`), entao reimportar a
mesma fatura substitui, nao duplica.
"""
from __future__ import annotations

import csv
import io
import os
import re

import fatura_cartao

# Cartao padrao por formato de arquivo: so a XP exporta CSV, e o PDF que se
# extrai hoje e o da Caixa.
CARTAO_DO_CSV = "xp"
CARTAO_DO_PDF = "elo-caixa"
CARTOES = ("elo-caixa", "xp")

_CABECALHO_XP = ("data", "estabelecimento", "portador", "valor", "parcela")
_PAGAMENTO = re.compile(r"pagamento", re.IGNORECASE)
_DATA_NO_NOME = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_DATA_BR = re.compile(r"^(\d{2})/(\d{2})/(\d{4})$")
_PARCELA = re.compile(r"(\d+)\s*(?:/|de)\s*(\d+)", re.IGNORECASE)


def vencimento_do_nome(nome: str | None) -> str | None:
    """`Fatura2026-10-05.csv` -> `2026-10-05` (o app da XP nomeia pelo vencimento)."""
    achado = _DATA_NO_NOME.search(str(nome or ""))
    return "-".join(achado.groups()) if achado else None


def _valor_br(texto: str) -> float:
    limpo = re.sub(r"[^\d,.\-]", "", str(texto or ""))
    if "," in limpo:
        limpo = limpo.replace(".", "").replace(",", ".")
    return round(float(limpo), 2)


def _data_iso(texto: str) -> str | None:
    achado = _DATA_BR.match(str(texto or "").strip())
    if not achado:
        return None
    dia, mes, ano = achado.groups()
    return f"{ano}-{mes}-{dia}"


def _parcela(texto: str) -> tuple[int | None, int | None]:
    achado = _PARCELA.search(str(texto or ""))
    if not achado:
        return None, None
    atual, total = int(achado.group(1)), int(achado.group(2))
    return (atual, total) if total > 1 else (None, None)


def e_csv_da_xp(texto: str) -> bool:
    primeira = texto.lstrip("﻿").splitlines()[0] if texto.strip() else ""
    colunas = tuple(c.strip().lower() for c in primeira.split(";"))
    return colunas[:len(_CABECALHO_XP)] == _CABECALHO_XP


def ler_csv_xp(texto: str, vencimento: str) -> dict:
    """CSV do app da XP no formato que `fatura_cartao.salvar` espera.

    O pagamento da fatura anterior vem como uma linha negativa ("Pagamentos
    Validos Normais"). Ele vai para o cabecalho, nao para os lancamentos: o
    CSV nao traz o saldo anterior que o anularia, e com ele a soma das linhas
    nao fecharia com o total (a conferencia de `salvar` marcaria a fatura como
    nao confiavel).
    """
    leitor = csv.reader(io.StringIO(texto.lstrip("﻿")), delimiter=";")
    linhas = [linha for linha in leitor if any(c.strip() for c in linha)]
    if not linhas or not e_csv_da_xp(";".join(linhas[0])):
        raise ValueError("O CSV nao esta no formato do app da XP "
                         "(Data;Estabelecimento;Portador;Valor;Parcela).")

    itens, pagamentos = [], 0.0
    for numero, linha in enumerate(linhas[1:], start=2):
        if len(linha) < 4:
            raise ValueError(f"Linha {numero} do CSV incompleta: {';'.join(linha)!r}")
        data, estabelecimento, valor = linha[0], linha[1].strip(), _valor_br(linha[3])
        if valor < 0 and _PAGAMENTO.search(estabelecimento):
            pagamentos += -valor
            continue
        atual, total = _parcela(linha[4] if len(linha) > 4 else "")
        itens.append({"data": _data_iso(data), "estabelecimento": estabelecimento, "valor": valor,
                      "parcela_atual": atual, "parcela_total": total, "cartao_final": None})

    return {
        "cabecalho": {
            "total": round(sum(i["valor"] for i in itens), 2),
            "vencimento": vencimento,
            "competencia": vencimento[:7],
            "pagamentos": round(pagamentos, 2) if pagamentos else None,
        },
        "itens": itens,
    }


def _senhas_do_cartao(db, cartao: str) -> list[str]:
    from bill_pdf_passwords import find_password_config, read_password_secret

    projeto = os.environ.get("GCLOUD_PROJECT") or "gestao-hermes"
    senhas = []
    for remetente, nome in fatura_cartao.REMETENTES_CARTAO.items():
        if nome != cartao:
            continue
        config = find_password_config(db, remetente)
        if config:
            senha = read_password_secret(projeto, config["secret_id"])
            if senha:
                senhas.append(senha)
    return senhas


def extrair_pdf(db, client, types, pdf: bytes, cartao: str) -> dict:
    from gmail_bill_pdf import prepare_pdf_for_gemini

    pronto, motivo = prepare_pdf_for_gemini(pdf, passwords=_senhas_do_cartao(db, cartao))
    if pronto is None:
        raise ValueError(f"Nao consegui abrir o PDF ({motivo}). Se ele tiver senha, "
                         "confira a senha cadastrada para a fatura do cartao.")
    return fatura_cartao.extrair(client, types, pronto, contexto_email=f"Fatura do cartao {cartao}")


def reler(db, fatura_id: str) -> dict:
    """O que ficou gravado, relido do banco: e isso que a resposta confirma."""
    cabecalho = db.collection(fatura_cartao.COL_FATURAS).document(fatura_id).get().to_dict() or {}
    itens = list(db.collection(fatura_cartao.COL_ITENS).where("fatura_id", "==", fatura_id).stream())
    return {
        "total": cabecalho.get("total"),
        "vencimento": cabecalho.get("vencimento"),
        "confiavel": cabecalho.get("confiavel"),
        "lancamentos": len(itens),
    }


def importar(db, dados: bytes, nome: str, *, cartao: str | None = None,
             vencimento: str | None = None, extrair_pdf_fn=None, origem: dict | None = None) -> dict:
    """Le o arquivo, grava a fatura e acerta a conta do mes. Devolve o que foi relido."""
    if cartao and cartao not in CARTOES:
        raise ValueError(f"Cartao desconhecido: {cartao!r}. Use um de {', '.join(CARTOES)}.")

    if dados.lstrip().startswith(b"%PDF-"):
        cartao = cartao or CARTAO_DO_PDF
        if extrair_pdf_fn is None:
            raise ValueError("Leitura de PDF indisponivel neste contexto.")
        extraido = extrair_pdf_fn(dados, cartao)
        if vencimento:
            extraido.setdefault("cabecalho", {})["vencimento"] = vencimento
    else:
        texto = dados.decode("utf-8-sig", errors="replace")
        if not e_csv_da_xp(texto):
            raise ValueError(f"'{nome}' nao e PDF de fatura nem CSV do app da XP.")
        cartao = cartao or CARTAO_DO_CSV
        vencimento = vencimento or vencimento_do_nome(nome)
        if not vencimento:
            raise ValueError("Informe o vencimento (YYYY-MM-DD): o nome do arquivo nao traz a data.")
        extraido = ler_csv_xp(texto, vencimento)

    resumo = fatura_cartao.salvar(db, cartao, extraido)
    if origem:
        db.collection(fatura_cartao.COL_FATURAS).document(resumo["fatura_id"]).set(
            {"origem": "arquivo", **origem}, merge=True)
    correcao = fatura_cartao.corrigir_fixed_bill(db, cartao, resumo)
    relido = reler(db, resumo["fatura_id"])

    gravou = relido["lancamentos"] == resumo["itens_gravados"] and relido["total"] == resumo["total"]
    return {
        "estado": "verificado" if gravou else "falhou",
        "fatura_id": resumo["fatura_id"],
        "cartao": cartao,
        "competencia": resumo["competencia"],
        "vencimento": relido["vencimento"],
        "total": relido["total"],
        "lancamentos": relido["lancamentos"],
        "confere_com_a_soma": relido["confiavel"],
        "divergencia": resumo["divergencia_total"],
        "conta_do_mes": (
            {"corrigida": True, "alteracoes": correcao.get("alteracoes")}
            if correcao.get("corrigido") else {"corrigida": False, "motivo": correcao.get("motivo")}
        ),
        "motivo": None if gravou else "a releitura nao bateu com o que foi gravado",
    }
