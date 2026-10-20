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

É defesa em profundidade por lista de termos (melhor esforço, não
exaustiva): a barreira primária é a regra 3 do prompt de geração. Termos
ambíguos com uso administrativo comum (voto em colegiado, vício de forma,
dívida ativa, sindicato como entidade, igreja/pastoral como endereço) ficam
de fora de propósito para não apagar conteúdo legítimo.

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
        r"psiquiatr\w*", r"gravidez", r"gravida", r"hiv",
        r"transtorno\w*", r"crise de ansiedade", r"bipolar\w*", r"autis\w*",
        r"tdah", r"diabet\w*", r"hipertens\w*", r"epilep\w*",
        r"licenca medica", r"atestado medico", r"dependente quimic\w*", r"aids", r"(?:tem|teve) covid",
        r"burnout", r"internad[oa] (?:no|em) hospital", r"problemas? de saude", r"faz terapia", r"toma (?:remedio|medicamento)\w*",
        r"tem ansiedade", r"engravidou", r"invalidez",
    ),
    "deficiencia": (
        r"pessoa com deficiencia", r"deficiente\w*", r"cadeirante\w*", r"paraplegic\w*", r"surd[oa]s?", r"surdez", r"cego", r"cega",
        r"cegueira", r"pcd",
    ),
    "religiao": (
        r"religi\w*", r"evangelic\w*", r"catolic\w*", r"cristao", r"crista\w*",
        r"espirita\w*", r"ateu\w*", r"ateia\w*", r"mu[cç]?ulman\w*", r"muculman\w*",
        r"islam\w*", r"judeu\w*", r"judia\w*", r"budis\w*", r"hindu\w*",
        r"umbanda", r"candomble", r"e crente", r"protestante\w*", r"mormon\w*", r"testemunha de jeova", r"macumba", r"espiritismo", r"ateismo", r"agnostic\w*", r"mulcumano\w*", r"mussulman\w*",
    ),
    "politica": (
        r"partido politico", r"filiad[oa] ao? partido", r"petista\w*", r"bolsonar\w*",
        r"lulis\w*", r"esquerdista\w*", r"direitista\w*", r"ideologia politica",
        r"vot(?:o|a|ou)\s+(?:no|na|em)\s+(?:pt|psol|psdb|pl|mdb|psb|novo|lula|bolsonaro)\b", r"comunista\w*",
    ),
    "orientacao_sexual": (
        r"homossexual\w*", r"homossexuais", r"gays?", r"lesbica\w*", r"bissexual\w*",
        r"bissexuais", r"transgenero\w*", r"transexual\w*", r"transsexual\w*", r"transexuais", r"(?:pessoa|homem|mulher|e) trans", r"travesti\w*", r"nao binari\w*", r"homoafetiv\w*",
        r"orientacao sexual", r"lgbt\w*",
    ),
    "origem_etnica": (r"racial", r"etnia\w*", r"etnico\w*", r"(?:pessoas?|homem|homens|mulher|mulheres|rapaz(?:es)?|moca\w*|senhor\w*) (?:negr|pard)[oa]s?", r"quilombola\w*", r"indigena\w*"),
    "sindical": (r"sindicalizad\w*", r"sindicalista\w*", r"filiad[oa] ao sindicato", r"grevista\w*", r"filiacao sindical"),
    "financeiro_judicial": (
        r"endividad\w*", r"esta devendo", r"nome sujo", r"nome no (?:spc|serasa)", r"devedor\w*", r"inadimplen\w*", r"falido\w*",
        r"falencia", r"ficha criminal", r"antecedentes criminais", r"foi preso", r"e reu",
    ),
    "acesso_por_perfil": (
        r"pode(?:m|ra|rao|ria)? (?:aprovar|acessar|liberar|assinar|autorizar) (?:o |a |os |as |um |uma )?(?:pagamento|folha|transferencia|contrato|sistema financeiro)\w*",
        r"autorizad[oa] a (?:aprovar|acessar|liberar|assinar|decidir) (?:o |a |os |as |um |uma )?(?:pagamento|folha|transferencia|contrato)\w*",
        r"tem permissao",
        r"acessos? (?:total|irrestrito)\w*", r"tem autorizacao para (?:aprovar|acessar|decidir|liberar)",
        r"pode(?:m|ra|rao|ria)? (?:autorizar|liberar|assinar) (?:pagamento|transferencia)\w*",
        r"autorizad[oa] a (?:aprovar|acessar|decidir)", r"confiavel para", r"e de confianca",
        r"pode ser confiad\w*", r"nivel de acesso",
    ),
}

_PADROES = {
    cat: re.compile(r"(?<![a-z0-9])(?:" + "|".join(termos) + r")(?![a-z0-9])")
    for cat, termos in _CATEGORIAS.items()
}


_HOMOGLIFOS = str.maketrans({
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x", "г": "r",
    "і": "i", "ѕ": "s", "ј": "j", "ο": "o", "α": "a", "ε": "e", "ι": "i", "ν": "v",
})


def _normalizar(texto: str) -> str:
    decomposto = unicodedata.normalize("NFKD", texto)
    # Remove acentos (Mn) e caracteres de formato invisíveis (Cf: zero-width etc.).
    limpo = "".join(
        c for c in decomposto if unicodedata.category(c) not in ("Mn", "Cf")
    )
    return limpo.lower().translate(_HOMOGLIFOS)


_PADRAO_ETNIA_COM_ACENTO = re.compile(r"(?<!\w)\u00e9 (?:negr|pard)[oa]s?(?!\w)")


def categorias_proibidas(texto) -> list[str]:
    """Categorias proibidas detectadas em `texto` (vazio se limpo ou não-string)."""
    if not isinstance(texto, str) or not texto.strip():
        return []
    norm = _normalizar(texto)
    cats = [cat for cat, padrao in _PADROES.items() if padrao.search(norm)]
    if "origem_etnica" not in cats and _PADRAO_ETNIA_COM_ACENTO.search(
        unicodedata.normalize("NFC", texto).lower()
    ):
        cats.append("origem_etnica")
    return cats


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
