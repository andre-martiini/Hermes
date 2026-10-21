"""Avaliador de cumprimento de compromisso (P07 do plano de autonomia,
passo 6: cumprimento parcial/completo e tratamento de negação).

Lógica pura -- sem I/O e sem wiring; `atencao_whatsapp.mensagem_cumpre_promessa`
(A06, fechamento por comprimento) NÃO foi alterado. Reaproveita o vocabulário
e o classificador de `autonomy/commitments.py`.

Princípio: precisão sobre revocação. `CUMPRIDO` com `incerta=False` exige
marca de entrega + objeto prometido casando com o texto/nome do anexo, sem
negação, pergunta, hedge ou promessa nova. Mídia sozinha, texto longo sobre
outro assunto e objeto diferente do prometido nunca fecham: viram `INCERTO`
ou `NAO_CUMPRE`, e quem consome mantém o compromisso pendente.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from autonomy.commitments import (
    CANCELAMENTO,
    ENTREGA_PARCIAL,
    INTENCAO_VAGA,
    PERGUNTA,
    PROMESSA,
    _NEGACAO,
    _normalizar,
    classificar_mensagem,
)

CUMPRIDO = "cumprido"
PARCIAL = "parcial"
NAO_CUMPRE = "nao_cumpre"
INCERTO = "incerto"

ESTADOS = (CUMPRIDO, PARCIAL, NAO_CUMPRE, INCERTO)

_OBJETOS = (
    "planilha", "arquivo", "documento", "relatorio", "email", "contrato", "oficio",
    "ata", "minuta", "proposta", "orcamento", "resumo", "link", "foto", "print",
    "pdf", "anexo", "lista", "modelo", "versao", "parecer", "tabela",
    "planejamento", "esboco",
)
_RE_OBJETO = re.compile(r"\b(" + "|".join(_OBJETOS) + r")s?\b")

_ENTREGA = re.compile(
    r"\b(segue|seguem|em anexo|anexei|enviei|mandei|encaminhei|entreguei|"
    r"aqui esta|aqui estao|ta ai|esta ai)\b"
)
_HEDGE = re.compile(
    r"\b(acho que|talvez|quase|tentei|tentando|nao sei se|sera que|parece que|"
    r"se (?:nao )?(?:chegou|recebeu)|deve ter|devo ter)\b"
)
# Marca de dúvida/cancelamento sobre a própria entrega.
_FUTURO = re.compile(r"\b(vou|vai|irei|mando|envio|encaminho|entrego) (?!em anexo)")


@dataclass(frozen=True)
class Cumprimento:
    estado: str
    evidencia: str
    incerta: bool


def _combinante_estranha(texto) -> bool:
    """Marca combinante fora dos acentos do português (grave, agudo, circunflexo, til, trema, cedilha), p.ex. tachado."""
    return isinstance(texto, str) and any(
        unicodedata.category(c) in ("Mn", "Me") and c not in "\u0300\u0301\u0302\u0303\u0308\u0327"
        for c in texto
    )


def _objetos(n: str) -> set[str]:
    return {m.group(1) for m in _RE_OBJETO.finditer(n)}


def avaliar_cumprimento(
    promessa, mensagem, tem_midia: bool = False, nome_anexo: str = ""
) -> Cumprimento:
    """Avalia se `mensagem` (from_me, posterior à `promessa`) cumpre a promessa.

    Só `estado == CUMPRIDO and not incerta` pode encerrar compromisso."""
    if _combinante_estranha(promessa) or _combinante_estranha(mensagem) or _combinante_estranha(nome_anexo):
        # Texto riscado/anulado por marcas combinantes: nunca firme.
        return Cumprimento(INCERTO, "marcas_combinantes", True)
    prom = _normalizar(promessa)
    msg = _normalizar(mensagem)
    anexo = re.sub(r"[_.\-]+", " ", _normalizar(nome_anexo))
    if not msg and not tem_midia:
        return Cumprimento(NAO_CUMPRE, "", False)

    objetos_prometidos = _objetos(prom)
    objetos_msg = _objetos(msg) | _objetos(anexo)

    if msg:
        classe = classificar_mensagem(mensagem)
        if classe.classe == ENTREGA_PARCIAL:
            return Cumprimento(PARCIAL, classe.evidencia, True)
        if classe.classe == CANCELAMENTO:
            return Cumprimento(NAO_CUMPRE, classe.evidencia, classe.incerta)
        if classe.classe in (PROMESSA, PERGUNTA, INTENCAO_VAGA):
            # Nova promessa/pergunta/vaga não cumpre a anterior (substitui).
            return Cumprimento(NAO_CUMPRE, classe.evidencia, classe.incerta)
        if _NEGACAO.search(msg):
            # "ainda não enviei o relatório": negação vence a marca de entrega.
            return Cumprimento(NAO_CUMPRE, "negacao", False)

    entrega = bool(_ENTREGA.search(msg))
    if not entrega and not tem_midia:
        # Texto sem marca de entrega (mesmo longo) não comprova cumprimento.
        return Cumprimento(NAO_CUMPRE, "sem_marca_de_entrega", False)

    if _HEDGE.search(msg) or _FUTURO.search(msg) or re.search(r"[?？¿]", str(mensagem or "")):
        return Cumprimento(INCERTO, "hedge", True)
    if not objetos_prometidos:
        # Promessa sem objeto documental ("te retorno amanhã"): nada a casar.
        return Cumprimento(INCERTO, "promessa_sem_objeto", True)
    # Lista branca (mesma decisão de P07 sub 1): só é firme a mensagem que é
    # inteira uma fórmula de entrega + exatamente os objetos prometidos, sem
    # nenhuma palavra de conteúdo (qualificador, destinatário, data, resto).
    # Qualquer outra coisa com marca de entrega fica INCERTO.
    if _promessa_qualificada(prom):
        return Cumprimento(INCERTO, "promessa_qualificada", True)
    if _formula_de_entrega(msg, objetos_prometidos):
        if tem_midia and not _anexo_confere(nome_anexo, objetos_prometidos):
            # Mídia exige que o NOME do anexo case com todos os objetos
            # prometidos; foto/arquivo sem nome conferível nunca fecha.
            return Cumprimento(INCERTO, "anexo_nao_confere", True)
        return Cumprimento(CUMPRIDO, sorted(objetos_prometidos)[0], False)
    if objetos_msg and not (objetos_prometidos <= objetos_msg):
        return Cumprimento(INCERTO, "objeto_diferente_ou_incompleto", True)
    return Cumprimento(INCERTO, "entrega_nao_inequivoca", True)


_RE_QUALIFICA = re.compile(
    r"\b(?:" + "|".join(_OBJETOS) + r")s?\b (?:de|do|da|dos|das|final|para|pro|pra|ao|aos|\d)|\d{4}|\bate\b"
)


_OBJ = "(?:" + "|".join(_OBJETOS) + ")"
_ART = r"(?:(?:o|a|os|as|um|uma) )?"
_ITEM_P = _ART + _OBJ
_PROMESSA_LIMPA = re.compile(
    r"(?:vou (?:te )?(?:enviar|mandar|encaminhar|entregar|passar)|"
    r"(?:te )?(?:envio|mando|encaminho|entrego))"
    r" " + _ITEM_P + r"(?: e " + _ITEM_P + r")*"
    r"(?: (?:hoje|amanha|ainda hoje|logo|depois))?"
)


def _promessa_qualificada(prom: str) -> bool:
    """Lista branca (gramática fechada) também na promessa: só é "limpa" a
    promessa que é inteira verbo de envio + objetos documentais no singular
    + prazo simples. Qualquer outra palavra ou fim truncado (qualificador,
    destinatário, condição, exclusão, alternativa, número, plural, negação,
    objeto fora do vocabulário) a torna qualificada e a entrega só pode ser
    INCERTO."""
    n = re.sub(r"[,.!;:\-]+", " ", prom)
    n = re.sub(r"\s+", " ", n).strip()
    return _PROMESSA_LIMPA.fullmatch(n) is None


def _anexo_confere(nome: str, prometidos: set[str]) -> bool:
    """Nome do arquivo = só os objetos prometidos + uma extensão simples."""
    n = _normalizar(nome)
    m = re.fullmatch(r"([a-z0-9 _.\-]+?)\.(pdf|docx?|xlsx?|odt|ods|csv|txt|png|jpe?g)", n)
    if not m:
        return False
    tokens = re.findall(r"[a-z0-9]+", m.group(1))
    achados = set()
    tokens_obj = []
    for t in tokens:
        if t == "e":
            continue
        if t not in _OBJETOS:
            return False
        achados.add(t)
        tokens_obj.append(t)
    return len(tokens_obj) == len(achados) and achados == prometidos


_FORMULA_MSG = re.compile(
    r"(?:segue|seguem|enviei|mandei|encaminhei|anexei|aqui esta|aqui estao)"
    r" (?P<itens>" + _ART + _OBJ + r"s?(?: e " + _ART + _OBJ + r"s?)*)"
)


def _formula_de_entrega(msg: str, prometidos: set[str]) -> bool:
    """msg inteira = marca de entrega + (somente) todos os objetos prometidos,
    uma vez cada, em gramática fechada (sem tokens soltos nem repetidos)."""
    # Pontuação só como um único "." ou "!" final (ou vírgula entre palavras).
    if not re.fullmatch(r"[a-z0-9 ,]*[.!]?", msg) or ",," in msg:
        return False
    n = re.sub(r"\bem anexo\b", " ", msg)
    n = re.sub(r"[,.!;:\-()]+", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    m = _FORMULA_MSG.fullmatch(n)
    if not m:
        return False
    achados = [t[:-1] if t.endswith("s") and t[:-1] in _OBJETOS else t
               for t in re.findall(r"[a-z0-9]+", m.group("itens")) if t.rstrip("s") in _OBJETOS or t in _OBJETOS]
    return len(achados) == len(set(achados)) and set(achados) == prometidos
