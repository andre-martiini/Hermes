"""Conciliacao de Pix com contas fixas.

Antes, a palavra-chave da conta era procurada no texto inteiro do e-mail, por
pedaco de palavra: "elo" (de "Fatura Elo") casava com "CIELO", a instituicao de
qualquer maquininha, e um Pix de R$ 29,04 para uma padaria virava a fatura do
cartao de setembro. E, quando casava, o valor da conta era trocado pelo do Pix.

Agora so o nome de quem recebeu o Pix conta, por palavra inteira, e a conta
so e baixada se o valor bater com o que ela ja tem.
"""
from __future__ import annotations

import re
import unicodedata

# Palavras que aparecem em nome de conta mas nao identificam o recebedor.
_GENERICAS = {
    "fatura", "conta", "contas", "mensal", "mensalidade", "pagamento", "plano",
    "celular", "energia", "agua", "luz", "coparticipacao", "saude", "taxa",
    "para", "com", "dos", "das", "del", "por", "geral", "fixa",
}

# PicPay: "Você fez um Pix para NOME Valor enviado..."
# XP: "O seu Pix enviado para NOME, descrito abaixo..."
_RECEBEDOR = re.compile(
    r"pix\s+(?:enviado\s+)?para\s+(.+?)(?:,|\s+(?:valor|cpf|cnpj|chave|institui|descrito))",
    re.IGNORECASE,
)

# Diferenca tolerada entre o Pix e o valor da conta (centavos de arredondamento,
# juros pequenos). Acima disso o Pix e outro pagamento, nao esta conta.
_TOLERANCIA_ABS = 1.0
_TOLERANCIA_REL = 0.05


def normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", str(texto or ""))
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", sem_acento.lower()).strip()


def palavras_chave(descricao: str) -> list[str]:
    return [p for p in normalizar(descricao).split()
            if len(p) > 2 and p not in _GENERICAS]


def nao_e_comprovante(remetente: str) -> bool:
    """Notificação do GitHub nunca é comprovante de Pix.

    A busca do Gmail pega todo e-mail com "Pix", e o primeiro "R$" do assunto vira o
    valor: o e-mail do PR #573 ("... causa do −R$ 6.277") virou um Pix de R$ 6.277.
    Encaminhamento ("Fwd: Pix realizado") NÃO entra aqui: é como o André registra
    comprovante de outro banco.
    """
    return "github.com" in str(remetente or "").lower()


def conta_do_email(remetente: str, conteudo: str) -> str | None:
    """De qual conta saiu o Pix do e-mail, só quando há sinal; senão None.

    Os e-mails "Seu Pix de R$ X no Google Pay..." batem um a um com o extrato do
    PicPay de 24 a 28/10/2026: o Google Pay do André está ligado ao PicPay. Os da
    XP já são descartados antes (são o extrato da conta XP).
    """
    if "picpay" in str(remetente or "").lower() or "google pay" in str(conteudo or "").lower():
        return "picpay"
    return None


def extrair_recebedor(texto: str) -> str | None:
    achado = _RECEBEDOR.search(str(texto or ""))
    if not achado:
        return None
    nome = achado.group(1).strip()
    return nome or None


def _recebedores_da_rubrica(rubrica: dict) -> list[str]:
    valor = rubrica.get("pix_recebedor")
    if not valor:
        return []
    return [valor] if isinstance(valor, str) else [str(v) for v in valor if v]


def _casa(rubrica: dict, palavras: set[str]) -> bool:
    # Conta paga a uma pessoa (a natacao, paga a quem cuida dela): o nome
    # completo cadastrado na rubrica tem que estar todo no recebedor.
    for nome in _recebedores_da_rubrica(rubrica):
        exigidas = set(normalizar(nome).split())
        if exigidas and exigidas <= palavras:
            return True
    chaves = palavras_chave(rubrica.get("full_desc") or rubrica.get("desc") or "")
    return any(p in palavras for p in chaves)


def rubrica_do_recebedor(recebedor: str | None, rubricas: list[dict]) -> dict | None:
    """Rubrica cujo nome (ou recebedor cadastrado) bate com quem recebeu o Pix.

    Ambiguidade (duas rubricas casando) nao concilia: errar a conta e pior que
    deixar o Pix como lancamento avulso.
    """
    if not recebedor:
        return None
    palavras = set(normalizar(recebedor).split())
    candidatas = [rb for rb in rubricas if _casa(rb, palavras)]
    return candidatas[0] if len(candidatas) == 1 else None


def valor_bate(valor_conta, valor_pix: float) -> bool:
    try:
        conta = float(valor_conta)
    except (TypeError, ValueError):
        return False
    return abs(conta - valor_pix) <= max(_TOLERANCIA_ABS, abs(conta) * _TOLERANCIA_REL)


def baixa_da_conta(conta: dict, valor_pix: float, *, data_iso: str, msg_id: str,
                   pix_id: str | None) -> dict | None:
    """Campos para marcar a conta como paga, ou None se o Pix nao e desta conta.

    Conta sem valor (0 ou vazio) recebe o valor do Pix. Conta com valor so e
    baixada se o Pix bater; o valor dela nunca e trocado.
    """
    if conta.get("isPaid"):
        return None
    atual = conta.get("amount")
    sem_valor = atual in (None, "", 0, 0.0)
    if not sem_valor and not valor_bate(atual, valor_pix):
        return None
    campos = {
        "isPaid": True,
        "valor_pago": valor_pix,
        "data_pagamento": data_iso,
        "google_message_id": msg_id,
        "pix_id": pix_id,
        "pago_via": "pix",
    }
    if sem_valor:
        campos["amount"] = valor_pix
    return campos


def id_da_conta(rubric_id: str, ano: int, mes: int) -> str:
    """Mesmo ID que a tela usa ao gerar a conta do mes (index.tsx)."""
    return f"{rubric_id}_{ano}_{mes}"
