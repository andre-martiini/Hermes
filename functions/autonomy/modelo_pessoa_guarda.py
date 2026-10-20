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
        r"doenc\w*", r"doente\w*", r"deprim\w*", r"depress\w*", r"cancer",
        r"oncologic\w*", r"quimioterapia", r"diagnosticad\w*",
        r"diagnostico (?:de|medico)", r"tratamento (?:medico|psiquiatrico|oncologico)",
        r"psiquiatr\w*", r"gravidez", r"gravida", r"gestante\w*", r"hiv",
        r"transtorno\w*", r"crise de ansiedade", r"bipolar\w*", r"autis\w*",
        r"tdah", r"diabet\w*", r"hipertens\w*", r"epilep\w*",
        r"licenca medica", r"atestado medico", r"vicio\w*", r"dependente quimic\w*",
    ),
    "deficiencia": (
        r"deficien\w*", r"cadeirante\w*", r"surd[oa]s?", r"surdez", r"cego", r"cega",
        r"cegueira", r"pcd",
    ),
    "religiao": (
        r"religi\w*", r"evangelic\w*", r"catolic\w*", r"cristao", r"crista\w*",
        r"espirita\w*", r"ateu\w*", r"ateia\w*", r"mu[cç]?ulman\w*", r"muculman\w*",
        r"islam\w*", r"judeu\w*", r"judia\w*", r"budis\w*", r"hindu\w*",
        r"umbanda", r"candomble", r"pastor\w*", r"igreja",
    ),
    "politica": (
        r"partido politico", r"filiad[oa] ao? partido", r"petista\w*", r"bolsonar\w*",
        r"lulis\w*", r"esquerdista\w*", r"direitista\w*", r"ideologia politica",
        r"vot(?:o|a|ou|a?ria)\s+(?:em|no|na)\b", r"eleitor\w*",
    ),
    "orientacao_sexual": (
        r"homossexual\w*", r"homossexuais", r"gays?", r"lesbica\w*", r"bissexual\w*",
        r"bissexuais", r"transgenero\w*", r"transexual\w*", r"transexuais", r"trans",
        r"orientacao sexual", r"lgbt\w*",
    ),
    "origem_etnica": (r"racial", r"etnia\w*", r"etnico\w*", r"negr[oa]s?", r"indigena\w*"),
    "sindical": (r"sindicalizad\w*", r"sindicato\w*", r"filiacao sindical"),
    "financeiro_judicial": (
        r"endividad\w*", r"divida\w*", r"devedor\w*", r"inadimplen\w*", r"falido\w*",
        r"falencia", r"processo criminal", r"antecedentes criminais", r"condena\w*",
    ),
    "acesso_por_perfil": (
        r"pode(?:m|ra|rao)? (?:aprovar|acessar|decidir|receber)", r"tem permissao",
        r"tem acesso", r"possui acesso", r"acesso (?:total|irrestrito)",
        r"autorizad[oa] a (?:aprovar|acessar|decidir)", r"confiavel para",
        r"pode ser confiad\w*", r"nivel de acesso",
    ),
}

_PADROES = {
    cat: re.compile(r"(?<![a-z0-9])(?:" + "|".join(termos) + r")(?![a-z0-9])")
    for cat, termos in _CATEGORIAS.items()
}


def _normalizar(texto: str) -> str:
    decomposto = unicodedata.normalize("NFKD", texto)
    # Remove acentos (Mn) e caracteres de formato invisíveis (Cf: zero-width etc.).
    limpo = "".join(
        c for c in decomposto if unicodedata.category(c) not in ("Mn", "Cf")
    )
    return limpo.lower()


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
        valor = saneado.get(campo)
        if valor is not None and not isinstance(valor, str):
            saneado[campo] = None
            descartes.append({"campo": campo, "categorias": ["tipo_invalido"]})
            continue
        cats = categorias_proibidas(valor)
        if cats:
            saneado[campo] = None
            descartes.append({"campo": campo, "categorias": cats})
    acoes = saneado.get("acoes_recentes")
    if isinstance(acoes, list):
        mantidas = []
        for i, item in enumerate(acoes):
            if not isinstance(item, str):
                descartes.append({"campo": "acoes_recentes", "indice": i, "categorias": ["tipo_invalido"]})
                continue
            cats = categorias_proibidas(item)
            if cats:
                descartes.append({"campo": "acoes_recentes", "indice": i, "categorias": cats})
            else:
                mantidas.append(item)
        saneado["acoes_recentes"] = mantidas
    return saneado, descartes
