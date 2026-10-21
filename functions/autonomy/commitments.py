"""Compromissos semânticos -- base de vocabulário e seleção barata (P07 do
plano de autonomia, docs/plano-hermes-autonomo-2026-09-06.md, passos 1, 2 e 4
do pacote: conjunto inicial de exemplos sintéticos em português; regras
baratas como seleção; prazo expresso separado de estimativa).

Lógica pura -- sem I/O, mesmo padrão incremental de `autonomy/pops_mapa.py`
e `autonomy/context.py`. Não liga nada em `atencao_whatsapp.py` nem altera o
fechamento por comprimento (A06): esta sub-entrega só entrega o vocabulário,
o classificador barato e o corpus de avaliação (F02) que as próximas
sub-entregas (extração estruturada, avaliador de cumprimento) usarão.

Princípio de segurança: o classificador nunca afirma certeza onde há dúvida.
Intenção vaga ("vou tentar", "talvez") vence a promessa; negação vence a
promessa; texto que não casa com nada é `nao_relacionada` -- e quem consome
este módulo NÃO pode tratar `nao_relacionada` como cumprimento. Só
`promessa` com `incerta=False` seleciona candidato a compromisso firme.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, datetime, timedelta

PROMESSA = "promessa"
INTENCAO_VAGA = "intencao_vaga"
PERGUNTA = "pergunta"
CANCELAMENTO = "cancelamento"
ENTREGA_PARCIAL = "entrega_parcial"
NAO_RELACIONADA = "nao_relacionada"

CLASSES = (
    PROMESSA,
    INTENCAO_VAGA,
    PERGUNTA,
    CANCELAMENTO,
    ENTREGA_PARCIAL,
    NAO_RELACIONADA,
)

# Natureza do prazo (passo 4): o que a pessoa disse versus o que o sistema
# estima para acompanhar. Estimativa nunca vira prazo contratual.
PRAZO_EXPRESSO = "expresso"
PRAZO_ESTIMADO = "estimado"

_DIAS_SEMANA = {
    "segunda": 0, "terca": 1, "quarta": 2, "quinta": 3,
    "sexta": 4, "sabado": 5, "domingo": 6,
}


def _normalizar(texto) -> str:
    if not isinstance(texto, str):
        return ""
    base = unicodedata.normalize("NFD", texto)
    sem_acento = "".join(c for c in base if unicodedata.category(c) not in ("Mn", "Cf"))
    return re.sub(r"\s+", " ", sem_acento.lower()).strip()


_VAGA = [re.compile(p) for p in (
    r"\bvou tentar\b", r"\btalvez\b", r"\bquem sabe\b", r"\bse der\b",
    r"\bse conseguir\b", r"\bse sobrar\b", r"\bsem promessa\b",
    r"\bvou ver se\b", r"\bpode ser que\b", r"\bacho que (vou|consigo)\b",
    r"\bnao prometo\b", r"\bdepois a gente (ve|ve isso)\b",
    r"\bnao sei\b", r"\bacho que\b", r"\bso se\b",
    r"\bcaso (queira|precise|seja|contrario|haja|nao|ele|ela|voce)\b",
    r"\bse (possivel|deus quiser|eu nao|nao)\b", r"\ba menos que\b",
    r"\bdesde que\b", r"\bdepende\b", r"\ba depender\b", r"\btomara\b",
    r"\bespero\b", r"\bprovavelmente\b", r"\bsera que\b", r"\bou melhor\b",
    r"\bou depois\b", r"\bvou ter que\b", r"\bpreciso (confirmar|ver|checar)\b",
    r"\bprecisa (aprovar|aprovacao|confirmar)\b", r"\bconfirmo com\b",
    r"\bmais ou menos\b",
    r"\bporem\b", r"\bmas\b", r"\bse\b", r"\bcaso\b", r"\bquando\b",
    r"\bassim que\b", r"\bou\b", r"\bapos\b", r"\buma vez\b", r"\bexceto\b",
    r"\bsalvo\b", r"\bcontanto\b", r"\bsupondo\b", r"\bassumindo\b",
    r"\bdependendo\b", r"\b(imagino|creio|suponho|calculo|devo)\b", r"\beu acho\b",
    r"\bkkk+\b", r"\bbrincadeira\b", r"\bhipotetic", r"\bem tese\b",
    r"\bem principio\b", r"\bgarantia\b", r"\bna medida\b", r"\bdeve dar\b",
    r"\bpelo visto\b", r"\bimagina\b", r"\b(ele|ela|eles|elas|disse|falou)\b",
    r"\bso que\b", r"\be eu\b", r"\bacho\b", r"\ba principio\b",
    r"\bpossivelmente\b", r"\bo possivel\b", r"\ba gente ve\b", r"\bvamos ver\b",
    r"\bsujeito a\b", r"\bsem previsao\b", r"\bpode ser\b",
    r"\b(falei|disse|falaram|disseram)\b",
    r"\bse (voce|vc|ele|ela|for|quiser|precisar|pagar|me|nao|houver|tiver)\b",
)]

_CANCEL = [re.compile(p) for p in (
    r"\b(nao|n|num|naum|nunca|jamais) (vou |vai |posso |consigo |da pra |precisa )*(poder |conseguir )?(te |lhe |mais )*"
    r"(enviar|mandar|fazer|ir|entregar|ver|passar|encaminhar)\b",
    r"\b(nao|n|num|naum|nunca|jamais) (te |lhe )(envio|mando|passo|encaminho|entrego|retorno)\b",
    r"\bpode deixar (quieto|pra la|de lado)\b",
    r"\b(cancela|cancelei|cancelado|cancelada)\b",
    r"^esquece\b", r"\besquece (isso|tudo|o pedido|esse)\b", r"\bdesconsidere\b", r"\bnao precisa mais\b",
    r"\bdeixa (pra la|quieto)\b", r"\bdesisti\b",
)]

_PARCIAL = [re.compile(p) for p in (
    r"\bsegue (a )?(primeira|1a|1) parte\b", r"\bsegue parte\b",
    r"\bso (o|a|os|as) [a-z0-9 ]{1,30} por enquanto\b",
    r"\bfalta (o|a|os|as|ainda)\b", r"\bo resto (te )?(mando|envio|passo)\b",
    r"\b(entrega|versao|resultado) parcial\b",
)]

_COMPL = r"(?:o|a|os|as|isso|tudo|ainda|hoje|amanha|ate|logo|depois|mais tarde|ja|agora)\b(?! (?:que|abraco|seguinte|meu|minha)\b)"
_PROMESSA = [re.compile(p) for p in (
    r"\bvou (te )?(enviar|mandar|encaminhar) " + _COMPL,
    r"\bvou te (retornar|responder|entregar|passar)\b " + _COMPL,
    r"\bte (envio|mando|encaminho|entrego|retorno|aviso|respondo) " + _COMPL
    ,
    r"\b(envio|mando|encaminho|entrego) (hoje|amanha|ate|ainda|logo)\b",
    r"\bvou (ver|verificar|checar|conferir|olhar) e (te )?(retorno|aviso|falo)\b",
    r"^deixa comigo[.!]*$", r"\bdeixa comigo que eu\b",
    r"\bpode deixar(?: que eu\b| comigo\b|,? eu\b)",
    r"\bfico de (te )?(enviar|mandar|retornar|avisar)\b",
)]

_INTERROGATIVAS = re.compile(
    r"^(quando|como|onde|qual|quais|quem(?! sabe)|quanto|quantos|por que|porque|o que|"
    r"voce (pode|consegue|poderia)|pode (me|nos)|consegue (me|nos)|poderia (me|nos)|tem como|"
    r"voces (podem|conseguem))\b"
)

# Pergunta que contém promessa ("posso te mandar amanhã?") continua pergunta.


@dataclass(frozen=True)
class Prazo:
    natureza: str
    texto: str
    data: date | None = None


@dataclass(frozen=True)
class Classificacao:
    # `incerta=False` só significa "sem dúvida detectada" para a classe dada;
    # firme = classe == PROMESSA e incerta == False. Quem consome deve checar
    # a classe, nunca só o campo.
    classe: str
    evidencia: str
    incerta: bool
    prazo: Prazo | None = None


def extrair_prazo_expresso(texto, hoje: date | None = None) -> Prazo | None:
    """Prazo dito pela pessoa. `data` só é preenchida quando `hoje` é dado e
    a expressão é inequívoca (hoje, amanhã, depois de amanhã, dia da semana
    com 'até/na/no', dd/mm). Horário solto e 'em breve' ficam sem data."""
    if isinstance(hoje, datetime):
        hoje = hoje.date()
    elif not isinstance(hoje, date):
        hoje = None
    n = _normalizar(texto)
    if not n or _NEGACAO.search(n):
        return None  # "hoje não, amanhã" é ambíguo: não inventar prazo
    termos = set(re.findall(r"\b(hoje|amanha|segunda|terca|quarta|quinta|sexta|sabado|domingo)\b", n))
    if re.search(r"\b(semana|proxim[ao]s?|passad[ao]s?|que vem|que tirei|(?<!depois )de (hoje|amanha))\b", n):
        # referência relativa composta ou ao objeto/evento, não ao prazo da entrega
        return Prazo(PRAZO_EXPRESSO, "relativo", None) if termos else None
    if len(termos) > 1:
        return Prazo(PRAZO_EXPRESSO, "multiplo", None)
    try:
        return _prazo(n, hoje)
    except (OverflowError, ValueError):
        return None


def _prazo(n: str, hoje: date | None) -> Prazo | None:
    m = re.search(r"\bdepois de amanha\b", n)
    if m:
        return Prazo(PRAZO_EXPRESSO, m.group(0), hoje + timedelta(days=2) if hoje else None)
    m = re.search(r"\b(antes de )?amanha\b", n)
    if m:
        # "antes de amanhã" vence hoje: sem data para não errar o dia.
        data = None if m.group(1) or not hoje else hoje + timedelta(days=1)
        return Prazo(PRAZO_EXPRESSO, m.group(0), data)
    m = re.search(r"\b(ainda )?hoje\b", n)
    if m:
        return Prazo(PRAZO_EXPRESSO, m.group(0), hoje)
    m = re.search(r"\b(ate|na|no|pra|para) (a |o )?(segunda|terca|quarta|quinta|sexta|sabado|domingo)\b", n)
    if m:
        alvo = _DIAS_SEMANA[m.group(3)]
        data = None
        if hoje is not None:
            delta = (alvo - hoje.weekday()) % 7 or 7
            data = hoje + timedelta(days=delta)
        return Prazo(PRAZO_EXPRESSO, m.group(0), data)
    m = re.search(r"\b(dia|ate|para|pra|em) (\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?(?![\d/])", n)
    if m and hoje is not None:
        dia, mes = int(m.group(2)), int(m.group(3))
        if m.group(4):
            ano = int(m.group(4))
            if 100 <= ano < 1000:
                return None
            anos = (ano + 2000 if ano < 100 else ano,)
        else:
            anos = range(hoje.year, hoje.year + 9)
        for ano in anos:
            try:
                data = date(ano, mes, dia)
            except ValueError:
                return None  # ex.: 29/02 em ano não bissexto: não inventar data
            # data já passada no ano corrente é ambígua (erro de digitação ou
            # prazo vencido): sem data, nunca empurrada para o ano seguinte.
            return Prazo(PRAZO_EXPRESSO, m.group(0), data) if data >= hoje else None
        return None
    m = re.search(r"\b(em|dentro de) \d{1,2} (hora|horas|dia|dias|minutos)\b|\bas (?:[01]?\d|2[0-3])(?:h|:[0-5]\d)\b", n)
    if m:
        return Prazo(PRAZO_EXPRESSO, m.group(0), None)
    return None


_NEGACAO = re.compile(r"\b(nao|n|num|naum|nunca|jamais|nem)\b")


def _primeira(padroes, n: str) -> str | None:
    for p in padroes:
        m = p.search(n)
        if m:
            return m.group(0)
    return None


def classificar_mensagem(texto, hoje: date | None = None) -> Classificacao:
    """Seleção barata de candidatos, em ordem de cautela: cancelamento >
    intenção vaga > pergunta > entrega parcial > promessa. Sem casamento,
    `nao_relacionada` (que nunca comprova cumprimento)."""
    n = _normalizar(texto)
    if not n:
        return Classificacao(NAO_RELACIONADA, "", False)
    prazo = extrair_prazo_expresso(texto, hoje)  # tolera `hoje` inválido
    ev_promessa = _primeira(_PROMESSA, n)
    if not ev_promessa and not _primeira(_CANCEL, n) and (
        n.endswith("?") or _INTERROGATIVAS.search(n)
    ):
        return Classificacao(PERGUNTA, n[:80], False, None)
    if re.search(r"\bse (eu )?nao\b", n):
        return Classificacao(INTENCAO_VAGA, "se nao", True, prazo)
    ev = _primeira(_CANCEL, n)
    if ev:
        return Classificacao(CANCELAMENTO, ev, False, None)
    ev = _primeira(_VAGA, n)
    if ev:
        return Classificacao(INTENCAO_VAGA, ev, True, prazo)
    if ev_promessa and re.search(r"\bquando (voce|vc|ele|ela|eles|elas) \w+\b", n):
        return Classificacao(INTENCAO_VAGA, "quando <outro>", True, prazo)
    if n.endswith("?") or (_INTERROGATIVAS.search(n) and not ev_promessa):
        # Promessa que pede confirmação ("te envio amanhã, ok?") continua
        # pergunta, mas nunca firme.
        return Classificacao(PERGUNTA, n[:80], bool(ev_promessa), None)
    ev_parcial = _primeira(_PARCIAL, n)
    if (ev_parcial or ev_promessa) and _NEGACAO.search(n):
        # Negação que não casou com recusa clara: ambíguo, nunca firme.
        return Classificacao(INTENCAO_VAGA, ev_parcial or ev_promessa, True, prazo)
    if ev_parcial:
        return Classificacao(ENTREGA_PARCIAL, ev_parcial, True, prazo)
    if ev_promessa:
        # data mencionada mas ilegível/inválida: não é firme.
        data_ilegivel = prazo is None and re.search(r"\b\d{1,2}/\d{1,2}\b", n)
        return Classificacao(PROMESSA, ev_promessa, bool(data_ilegivel), prazo)
    return Classificacao(NAO_RELACIONADA, "", False)


def chave_compromisso(chat_id: str, mensagem_id: str, indice: int = 0) -> str:
    """Chave estável por compromisso (vários por chat/mensagem, passo 3).
    '__' é o separador e por isso proibido nos ids (evita colisão)."""
    if not isinstance(chat_id, str) or not isinstance(mensagem_id, str):
        raise ValueError("chat_id e mensagem_id devem ser texto")
    if chat_id != chat_id.strip() or mensagem_id != mensagem_id.strip():
        raise ValueError("ids não podem ter espaço nas pontas")
    partes = [chat_id, mensagem_id]
    if (
        not all(partes)
        or any("__" in p or p.startswith("_") or p.endswith("_") for p in partes)
        or isinstance(indice, bool)
        or not isinstance(indice, int)
        or indice < 0
    ):
        raise ValueError("chat_id, mensagem_id (sem '__') e indice >= 0 são obrigatórios")
    return f"{partes[0]}__{partes[1]}__{indice}"


# Corpus sintético inicial (passo 1). (texto, classe esperada). Nada real.
CASOS_SINTETICOS: tuple[tuple[str, str], ...] = (
    ("Te envio o relatório amanhã", PROMESSA),
    ("Vou te mandar a planilha ainda hoje", PROMESSA),
    ("Pode deixar, eu resolvo", PROMESSA),
    ("Vou ver e te retorno", PROMESSA),
    ("Fico de te avisar até sexta", PROMESSA),
    ("Vou tentar enviar amanhã", INTENCAO_VAGA),
    ("Talvez eu consiga olhar isso", INTENCAO_VAGA),
    ("Se der eu mando hoje", INTENCAO_VAGA),
    ("Quem sabe na semana que vem", INTENCAO_VAGA),
    ("Quando você consegue me mandar o contrato?", PERGUNTA),
    ("Pode me enviar a ata?", PERGUNTA),
    ("Qual o prazo do edital", PERGUNTA),
    ("Posso te mandar amanhã?", PERGUNTA),
    ("Não vou mais enviar, esquece", CANCELAMENTO),
    ("Pode cancelar, não precisa mais", CANCELAMENTO),
    ("Desconsidere o pedido anterior", CANCELAMENTO),
    ("Segue a primeira parte, o resto te mando amanhã", ENTREGA_PARCIAL),
    ("Falta ainda a assinatura do diretor", ENTREGA_PARCIAL),
    ("Só a planilha por enquanto", ENTREGA_PARCIAL),
    ("Não te envio hoje", CANCELAMENTO),
    ("Não posso te enviar amanhã", CANCELAMENTO),
    ("Não vou conseguir mandar", CANCELAMENTO),
    ("Nunca te mando nada", CANCELAMENTO),
    ("Pode deixar quieto", CANCELAMENTO),
    ("Não sei se vou te enviar", INTENCAO_VAGA),
    ("Acho que te envio amanhã", INTENCAO_VAGA),
    ("Se você me mandar eu te envio", INTENCAO_VAGA),
    ("Só se você pedir te envio", INTENCAO_VAGA),
    ("Vou te enviar amanhã, ok?", PERGUNTA),
    ("Não falta nada, te mando amanhã", INTENCAO_VAGA),
    ("Pode deixar de lado esse assunto", CANCELAMENTO),
    ("Concordo parcialmente com você", NAO_RELACIONADA),
    ("Ontem almocei com a turma e foi ótimo, depois fui ao mercado comprar frutas", NAO_RELACIONADA),
    ("ok", NAO_RELACIONADA),
    ("Bom dia!", NAO_RELACIONADA),
)


def avaliar(casos=CASOS_SINTETICOS, hoje: date | None = None) -> dict:
    """Precisão/revocação por classe sobre o corpus. `precisao_promessa` é a
    métrica de segurança: quanto do que o classificador chama de promessa
    firme é de fato promessa."""
    por_classe = {c: {"tp": 0, "fp": 0, "fn": 0} for c in CLASSES}
    erros = []
    for texto, esperado in casos:
        obtido = classificar_mensagem(texto, hoje).classe
        if obtido == esperado:
            por_classe[esperado]["tp"] += 1
        else:
            por_classe[esperado]["fn"] += 1
            por_classe[obtido]["fp"] += 1
            erros.append((texto, esperado, obtido))
    resumo = {}
    for c, v in por_classe.items():
        pred = v["tp"] + v["fp"]
        real = v["tp"] + v["fn"]
        resumo[c] = {
            "precisao": (v["tp"] / pred) if pred else None,
            "revocacao": (v["tp"] / real) if real else None,
            **v,
        }
    return {"total": len(casos), "por_classe": resumo, "erros": erros}
