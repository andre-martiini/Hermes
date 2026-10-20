"""Guarda do modelo por pessoa (P06 do plano de autonomia,
docs/plano-hermes-autonomo-2026-09-06.md, passo 9 do pacote: "Integrar modelo
por pessoa apenas para tom, vínculos e comportamento observado; não inferir
traços sensíveis ou conceder acesso por perfil.").

Lógica pura -- sem I/O. O `modelo_interacao` de `perfil_pessoas` é gerado por
LLM (`main.parse_resposta_modelo_pessoa`) e só deve descrever tom
(`registro`), tempo de resposta observado (`tempo_resposta_tipico`) e ações
citadas (`acoes_recentes`). Este módulo descarta, campo a campo, texto que
infere traço sensível (saúde, religião, política, orientação sexual, origem
étnica, filiação sindical, situação financeira/judicial, deficiência) ou que
sugere permissão/acesso por perfil, e devolve o motivo para auditoria. É
descarte, nunca reescrita: o campo vira None / sai da lista.

O modelo é só contexto de leitura; nenhum código usa `modelo_interacao` para
conceder acesso (a autorização continua vindo de política/mandato).
"""

from __future__ import annotations

import re
import unicodedata

_CAMPOS_TEXTO = ("registro", "tempo_resposta_tipico")

_CATEGORIAS: dict[str, tuple[str, ...]] = {
    "saude": (
        r"doenc\w*", r"depress\w*", r"ansiedade", r"cancer", r"diagnostic\w*",
        r"tratamento medic\w*", r"psiquiatr\w*", r"psicolog\w*", r"terapia",
        r"gravidez", r"gravida", r"hiv", r"transtorno\w*", r"bipolar",
        r"autis\w*", r"vicio\w*", r"dependente quimic\w*",
    ),
    "deficiencia": (r"deficien\w*", r"cadeirante", r"surd[oa]", r"cego", r"cega"),
    "religiao": (
        r"religi\w*", r"evangelic\w*", r"catolic\w*", r"espirita", r"ateu",
        r"ateia", r"muculman\w*", r"judeu", r"judia", r"umbanda", r"candomble",
    ),
    "politica": (
        r"partido", r"petista", r"bolsonarista", r"esquerdista", r"direitista",
        r"ideologia politica", r"voto em", r"eleitor\w*",
    ),
    "orientacao_sexual": (
        r"homossexual\w*", r"gay", r"lesbica", r"bissexual\w*", r"transgenero",
        r"orientacao sexual", r"lgbt\w*",
    ),
    "origem_etnica": (r"raca", r"racial", r"etnia", r"negro", r"negra", r"indigena"),
    "sindical": (r"sindicalizad\w*", r"filiad[oa] a sindicato", r"filiacao sindical"),
    "financeiro_judicial": (
        r"endividad\w*", r"inadimplente", r"falido", r"falencia", r"processo criminal",
        r"antecedentes", r"condenad\w*",
    ),
    "acesso_por_perfil": (
        r"autoriz\w* (?:a|para)", r"pode (?:aprovar|acessar|decidir|receber)",
        r"tem permissao", r"acesso (?:total|irrestrito|a)", r"confiavel para",
        r"pode ser confiad\w*", r"nivel de acesso",
    ),
}

_PADROES = {
    cat: re.compile(r"(?<![a-z0-9])(?:" + "|".join(termos) + r")(?![a-z0-9])")
    for cat, termos in _CATEGORIAS.items()
}


def _normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto)
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    return sem_acento.lower()


def categorias_proibidas(texto) -> list[str]:
    """Categorias proibidas detectadas em `texto` (vazio se limpo ou não-string)."""
    if not isinstance(texto, str) or not texto.strip():
        return []
    norm = _normalizar(texto)
    return [cat for cat, padrao in _PADROES.items() if padrao.search(norm)]


def sanear_modelo_interacao(modelo):
    """Devolve (modelo_saneado, descartes).

    `descartes` é lista de {"campo": ..., "categorias": [...]} (para
    `acoes_recentes`, também "indice" do item original). Não muta a entrada;
    entrada não-dict volta como está, sem descartes.
    """
    if not isinstance(modelo, dict):
        return modelo, []
    saneado = dict(modelo)
    descartes: list[dict] = []
    for campo in _CAMPOS_TEXTO:
        cats = categorias_proibidas(saneado.get(campo))
        if cats:
            saneado[campo] = None
            descartes.append({"campo": campo, "categorias": cats})
    acoes = saneado.get("acoes_recentes")
    if isinstance(acoes, list):
        mantidas = []
        for i, item in enumerate(acoes):
            cats = categorias_proibidas(item)
            if cats:
                descartes.append({"campo": "acoes_recentes", "indice": i, "categorias": cats})
            else:
                mantidas.append(item)
        saneado["acoes_recentes"] = mantidas
    return saneado, descartes
