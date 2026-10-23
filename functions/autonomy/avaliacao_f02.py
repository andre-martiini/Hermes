"""Suíte de avaliação F02 -- precisão de cumprimento (P07 do plano de autonomia).

Lógica pura -- sem I/O e sem wiring. Mede, sobre um corpus sintético em
português, a métrica "Precisão de cumprimento" da seção 11 do plano: dos
compromissos que o avaliador FECHARIA sozinho (`cumprido` firme), quantos
foram de fato cumpridos. Abaixo do limiar, o consumidor só pode sugerir o
fechamento. Casos incertos ficam pendentes e não entram no denominador.
"""

from __future__ import annotations

from collections import namedtuple

from autonomy.cumprimento import CUMPRIDO, avaliar_cumprimento

# Seção 11: >= 98% em avaliação; abaixo disso, sugerir fechamento.
LIMIAR_PRECISAO = 0.98

# Amostra mínima de fechamentos para a precisão valer como evidência.
MIN_FECHADOS = 3

CasoF02 = namedtuple("CasoF02", "promessa mensagem cumpre tem_midia nome_anexo")


def _c(promessa, mensagem, cumpre, midia=False, anexo=""):
    return CasoF02(promessa, mensagem, cumpre, midia, anexo)


P_REL = "Te envio o relatório amanhã"
P_PLAN = "Mando a planilha"

CASOS_F02 = (
    # Cumprimento real.
    _c(P_REL, "Segue o relatório", True),
    _c(P_REL, "Enviei o relatório em anexo", True, True, "relatorio.pdf"),
    _c(P_PLAN, "Segue a planilha", True),
    _c(P_PLAN, "segue em anexo a planilha!", True, True, "planilha.xlsx"),
    # Não cumpre: mensagem longa e não relacionada (aceite F02).
    _c(P_REL, "Ontem almocei com a turma e foi ótimo, depois fui ao mercado comprar frutas e "
              "acabei encontrando um velho amigo da faculdade que não via há anos, ficamos "
              "conversando sobre tudo o que aconteceu desde então e perdi a hora", False),
    _c(P_REL, "Bom dia, tudo bem? Vamos marcar um café esta semana?", False),
    # Negação vence a marca de entrega.
    _c(P_REL, "Ainda não enviei o relatório", False),
    # Objeto diferente ou incompleto.
    _c(P_REL, "Segue a planilha", False),
    _c("Mando o relatório e a planilha", "Segue o relatório", False),
    # Mídia sem nome conferível, anexo prometido sem mídia, hedge e futuro.
    _c(P_REL, "Segue o relatório", False, True, "IMG_2231.jpg"),
    _c(P_REL, "Enviei o relatório em anexo", False),
    _c(P_REL, "Acho que enviei o relatório, confere aí?", False),
    _c(P_REL, "Vou enviar o relatório amanhã cedo", False),
    # Nova promessa não cumpre a anterior.
    _c(P_REL, "Te mando o relatório na segunda", False),
    # Cancelamento e entrega parcial.
    _c(P_REL, "Não vou conseguir mandar o relatório", False),
    _c(P_REL, "Segue a primeira parte do relatório", False),
)


def medir_precisao_cumprimento(casos=CASOS_F02, limiar: float = LIMIAR_PRECISAO) -> dict:
    """Roda `avaliar_cumprimento` sobre `casos` e mede a precisão de fechamento.

    `fechados` = casos em que o avaliador fecharia sozinho (cumprido, não
    incerto); `corretos` = desses, os realmente cumpridos. `falsos_fechamentos`
    lista os erros graves. `precisao` é None sem nenhum fechamento; `aprovado` exige
    `MIN_FECHADOS` fechamentos, ao menos um caso negativo e precisão >= limiar: sem amostra não se libera
    fechamento automático. Entradas inválidas levantam ValueError. `revocacao` é informativa (cumpridos que o avaliador fechou)."""
    if isinstance(limiar, bool) or not isinstance(limiar, (int, float)) or not LIMIAR_PRECISAO <= limiar <= 1:
        raise ValueError("limiar deve estar entre o limiar da seção 11 e 1")
    if isinstance(casos, (dict, str, bytes)):
        raise ValueError("casos deve ser sequência de CasoF02")
    try:
        casos = tuple(casos)
    except Exception:
        raise ValueError("casos deve ser iterável de CasoF02") from None
    for caso in casos:
        if (
            type(caso) is not CasoF02
            or type(caso.cumpre) is not bool
            or type(caso.tem_midia) is not bool
            or type(caso.promessa) is not str
            or type(caso.mensagem) is not str
            or type(caso.nome_anexo) is not str
        ):
            raise ValueError("cada caso deve ser CasoF02 com campos de tipo exato")
    negativos = sum(1 for c in casos if not c.cumpre)
    fechados = corretos = reais = reais_fechados = 0
    falsos = []
    for caso in casos:
        r = avaliar_cumprimento(caso.promessa, caso.mensagem, caso.tem_midia, caso.nome_anexo)
        fecha = r.estado == CUMPRIDO and not r.incerta
        if caso.cumpre:
            reais += 1
            reais_fechados += fecha
        if fecha:
            fechados += 1
            if caso.cumpre:
                corretos += 1
            else:
                falsos.append(caso)
    precisao = (corretos / fechados) if fechados else None
    return {
        "total": len(casos),
        "fechados": fechados,
        "corretos": corretos,
        "precisao": precisao,
        "revocacao": (reais_fechados / reais) if reais else None,
        "falsos_fechamentos": falsos,
        "limiar": limiar,
        "aprovado": negativos > 0 and fechados >= MIN_FECHADOS and precisao >= limiar,
    }
