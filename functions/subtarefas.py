"""O contrato da subtarefa: um lugar so.

A unidade mental de trabalho do dono do sistema e **macroacao dividida em
subtarefas** (`plano_acao`). Isso nao muda. O que muda aqui e a resolucao: ate
2026-08-26 todo o controle vivia na macroacao — data, estado, faixa de execucao
e contador de adiamento — e a subtarefa era texto com um marcador de concluida.

A consequencia era diagnostico grosso. "Adiada 33 vezes" informa que algo esta
parado, nao **o que** esta parado. E uma macroacao so podia estar numa faixa por
vez, quando na pratica se trabalha numa etapa e se espera terceiro em outra.

## Por que este modulo existe

O merge de plano de acao estava escrito duas vezes — `main.py` (copiloto web) e
`tools/telegram_extended.py` (Telegram e MCP) — e as duas remontavam cada etapa
como `{id, text, completed}` literal. Qualquer campo novo seria apagado no
primeiro reordenamento de plano, sem erro nenhum. Com duas copias, seria apagado
em dois lugares diferentes por motivos identicos.

Aqui o formato da subtarefa e definido uma vez, e `mesclar_plano` preserva o que
nao conhece. Campo novo que apareca amanha sobrevive sem ninguem lembrar dele.

## Compatibilidade

`completed` continua sendo gravado sempre, espelhando `estado == "feito"`. Ha
leitores que so entendem ele (`UIComponents.tsx`, `TaskExecutionView.tsx`,
`morning_summary`), e nenhum precisa mudar ao mesmo tempo que isto. Subtarefa
sem `estado` tem o estado deduzido de `completed` — as 226 etapas existentes
entram nesse caminho e nao precisam de migracao.
"""

from __future__ import annotations

import difflib
import json
import uuid
from dataclasses import dataclass, field

PENDENTE = "pendente"
EM_ANDAMENTO = "em_andamento"
AGUARDANDO_TERCEIRO = "aguardando_terceiro"
FEITO = "feito"

ESTADOS = (PENDENTE, EM_ANDAMENTO, AGUARDANDO_TERCEIRO, FEITO)

# Campos que este modulo governa. Serve para `mesclar_plano` saber o que e dele
# e o que e de outra pessoa — tudo o que nao estiver aqui e preservado intacto.
_CAMPOS_CONHECIDOS = frozenset(
    {"id", "text", "texto", "completed", "estado", "aguardando_de",
     "data_prevista", "degradation_count",
     # Instrucao de quem edita, nao dado da etapa: nunca e gravada.
     "remover"}
)

# Campos que quem edita pode APAGAR mandando `null` ou "". Nos outros, vazio
# continua significando "nao mexa": sem data nem espera a etapa ainda faz
# sentido, sem texto ou estado nao.
_CAMPOS_APAGAVEIS = frozenset({"data_prevista", "aguardando_de"})


# ---------------------------------------------------------------------------
# Leitura
# ---------------------------------------------------------------------------

def estado_de(item: dict) -> str:
    """Estado da subtarefa, deduzido de `completed` quando ainda nao existir.

    A deducao e o que dispensa migracao: etapa antiga com `completed: true` le
    como `feito`, com `completed: false` le como `pendente`.
    """
    bruto = str(item.get("estado") or "").strip().lower()
    if bruto in ESTADOS:
        return bruto
    return FEITO if item.get("completed") else PENDENTE


def esta_feita(item: dict) -> bool:
    return estado_de(item) == FEITO


def texto_de(item) -> str:
    if isinstance(item, dict):
        return str(item.get("text") or item.get("texto") or "").strip()
    return str(item or "").strip()


def contar(plano) -> tuple[int, int]:
    """(feitas, totais) — o agregado que `etapas_feitas`/`etapas_totais` usam."""
    itens = [i for i in (plano or []) if isinstance(i, dict) and texto_de(i)]
    return sum(1 for i in itens if esta_feita(i)), len(itens)


def plano_tem_datas(plano) -> bool:
    """Se alguma etapa marcou data propria — o que muda o sentido das outras."""
    return any(str(i.get("data_prevista") or "").strip()
               for i in (plano or []) if isinstance(i, dict))


def data_prevista_de(item: dict, data_limite_acao: str | None,
                     plano=None) -> str:
    """Data da subtarefa, herdando a da macroacao quando cabe.

    A heranca preserva o comportamento atual: plano onde ninguem marcou data —
    todos os 34 planos existentes — se comporta exatamente como antes, com
    todas as etapas no dia da acao.

    **Num plano misto ela nao se aplica.** Quando algumas etapas tem data e
    outras nao, a etapa sem data e a que nao tem dia marcado ainda; herdar a
    data da macroacao a jogaria para o dia mais cedo do plano. No caso real de
    `Revisar Questoes do Mago`, "apos o retorno: retomar a fila" nao tem data
    justamente por ser a ultima, e a heranca pura a colocava na frente de
    "publicar a versao", marcada para o dia seguinte.

    Passe `plano` para que a distincao seja possivel; sem ele, herda (o
    comportamento antigo, correto para plano sem datas).
    """
    propria = str(item.get("data_prevista") or "").strip()
    if propria:
        return propria
    if plano is not None and plano_tem_datas(plano):
        return ""
    return str(data_limite_acao or "").strip()


def subtarefa_corrente(plano, data_limite_acao: str | None) -> dict | None:
    """A subtarefa que esta valendo agora: a de menor data ainda nao concluida.

    Etapa sem dia marcado num plano que tem datas vai para o fim da fila, nao
    para o comeco. Empate resolve pela ordem do plano, que e a ordem em que o
    dono escreveu — numa sequencia real ela costuma ser a ordem de execucao.

    Devolve `None` quando todas estao concluidas. Isso acontece de verdade: ha
    acao ativa com 12/12 etapas feitas e contador em 26. Quem chama precisa
    decidir o que fazer nesse caso, em vez de receber uma etapa arbitraria.
    """
    itens = plano or []
    candidatas = [
        (data_prevista_de(i, data_limite_acao, itens) or "9999-12-31", ordem, i)
        for ordem, i in enumerate(itens)
        if isinstance(i, dict) and texto_de(i) and not esta_feita(i)
    ]
    if not candidatas:
        return None
    return min(candidatas, key=lambda c: (c[0], c[1]))[2]


def aguardando_terceiros(plano) -> list[dict]:
    """Subtarefas paradas em terceiro, mesmo quando a acao esta em avanco.

    Existe porque essa e a lista que some hoje: a macroacao aparece em `avanco`
    por causa de uma etapa em andamento, e a espera fica invisivel.
    """
    return [i for i in (plano or [])
            if isinstance(i, dict) and texto_de(i)
            and estado_de(i) == AGUARDANDO_TERCEIRO]


def derivar_lane(plano, lane_gravada: str | None = None) -> str:
    """Faixa de execucao da macroacao, a partir do estado das subtarefas.

    Ate aqui `execution_lane` nao tinha quem escrevesse: das 43 acoes ativas em
    2026-08-26, 43 estavam em `avanco`, e o unico write existente no sistema
    inteiro era o reset para `avanco` na virada do dia. Derivar e o que da um
    produtor ao campo pela primeira vez.

    `continuo` fica de fora da derivacao de proposito — nao ha estado de
    subtarefa que o expresse, entao um valor gravado desses e respeitado como
    escolha de quem gravou, em vez de ser sobrescrito por deducao.
    """
    if str(lane_gravada or "").strip() == "continuo":
        return "continuo"

    itens = [i for i in (plano or []) if isinstance(i, dict) and texto_de(i)]
    abertas = [i for i in itens if not esta_feita(i)]
    if not abertas:
        # Sem etapa aberta (ou sem plano) nao ha o que deduzir: mantem o que
        # estava, e na ausencia disso o padrao historico.
        return str(lane_gravada or "").strip() or "avanco"

    if any(estado_de(i) == EM_ANDAMENTO for i in abertas):
        return "avanco"
    if all(estado_de(i) == AGUARDANDO_TERCEIRO for i in abertas):
        return AGUARDANDO_TERCEIRO
    # Todas pendentes e o caso esmagadoramente comum hoje — nenhuma interface
    # marca estado ainda. Cair em `avanco` preserva o comportamento atual.
    return "avanco"


def degradacao_da_acao(plano, gravado) -> int:
    """Contador da macroacao: o maior entre o gravado e os das subtarefas.

    Espelha, nao move. Se a macroacao passasse a ser puramente derivada, as 30
    acoes que hoje tem contador maior que zero e nenhum historico por subtarefa
    zerariam de uma vez — regressao exatamente onde o objetivo era nao ter.
    """
    por_subtarefa = [int(i.get("degradation_count") or 0)
                     for i in (plano or []) if isinstance(i, dict)]
    return max([int(gravado or 0), *por_subtarefa]) if por_subtarefa else int(gravado or 0)


def inconsistencias(plano, prazo_final: str | None) -> list[str]:
    """Sinaliza subtarefa prevista depois do prazo final da macroacao.

    Sinaliza, nao bloqueia: o dono pode estar registrando uma realidade que ele
    ja sabe que fura o prazo, e recusar a gravacao apagaria a informacao em vez
    de expor o problema.
    """
    limite = str(prazo_final or "").strip()
    if not limite:
        return []
    fora = []
    for i in (plano or []):
        if not isinstance(i, dict):
            continue
        prevista = str(i.get("data_prevista") or "").strip()
        if prevista and prevista > limite:
            fora.append(f"'{texto_de(i)[:60]}' prevista para {prevista}, "
                        f"depois do prazo final {limite}")
    return fora


# ---------------------------------------------------------------------------
# Escrita
# ---------------------------------------------------------------------------

def normalizar(item, *, id_existente: str | None = None) -> dict | None:
    """Uma subtarefa no formato canonico, aceitando texto puro ou objeto.

    Aceitar string mantem funcionando todo mundo que ja chamava
    `criar_acao_no_sistema(plano_acao=["passo 1", "passo 2"])`.
    """
    if isinstance(item, str):
        item = {"text": item}
    if not isinstance(item, dict):
        return None

    texto = texto_de(item)
    if not texto:
        return None

    estado = str(item.get("estado") or "").strip().lower()
    if estado not in ESTADOS:
        estado = FEITO if item.get("completed") else PENDENTE

    saida = {
        "id": id_existente or str(item.get("id") or "").strip() or str(uuid.uuid4())[:8],
        "text": texto,
        # Espelho do estado, para os leitores que so conhecem `completed`.
        "completed": estado == FEITO,
        "estado": estado,
    }

    aguardando_de = str(item.get("aguardando_de") or "").strip()
    if aguardando_de:
        saida["aguardando_de"] = aguardando_de[:200]

    prevista = str(item.get("data_prevista") or "").strip()
    if prevista:
        saida["data_prevista"] = prevista

    contador = int(item.get("degradation_count") or 0)
    if contador:
        saida["degradation_count"] = contador

    # Tudo o que este modulo nao governa viaja junto. E o que impede a proxima
    # feature de ser apagada por um merge que nao sabia dela.
    for chave, valor in item.items():
        if chave not in _CAMPOS_CONHECIDOS and chave not in saida:
            saida[chave] = valor

    return saida


def converter_plano(plano) -> list[dict]:
    """Plano recem-criado: lista de strings ou de objetos vira lista canonica."""
    saida = []
    for item in normalizar_entrada_plano(plano):
        norm = normalizar(item)
        if norm:
            saida.append(norm)
    return saida


MODO_PARCIAL = "parcial"
MODO_SUBSTITUIR = "substituir"
MODOS = (MODO_PARCIAL, MODO_SUBSTITUIR)

# Quantas etapas removidas ficam guardadas na acao para poderem voltar. O
# campo vive no proprio documento da tarefa, entao precisa de teto; as mais
# antigas saem primeiro.
LIMITE_ETAPAS_REMOVIDAS = 30


@dataclass
class EdicaoPlano:
    """O resultado de aplicar uma edicao: o plano novo e o que saiu dele.

    `removidas` guarda a etapa **inteira** (com id, contador, historico), para
    que a remocao possa ser desfeita. `explicita` distingue quem pediu
    (`remover: true`) de quem so deixou de citar a etapa no modo `substituir`
    — esse segundo caso e o que exige `confirmar_remocao`.
    """

    plano: list
    removidas: list = field(default_factory=list)
    restauradas: list = field(default_factory=list)

    @property
    def removidas_sem_pedido(self) -> list:
        return [r for r in self.removidas if not r["explicita"]]


def _pede_remocao(item: dict) -> bool:
    valor = item.get("remover")
    if isinstance(valor, str):
        return valor.strip().lower() in ("true", "1", "sim", "yes")
    return valor is True or valor == 1


def _mesclar_item(original: dict, item: dict, id_fallback: str | None = None) -> dict | None:
    """Herda o original inteiro e deixa o item novo sobrepor o que trouxer.

    Campo ausente preserva o herdado; `data_prevista`/`aguardando_de` com
    `null` ou "" apagam. Texto ausente (edicao so de estado, por exemplo)
    mantem o texto que a etapa ja tinha.
    """
    mesclado = {**original}
    for chave, valor in item.items():
        if chave in ("id", "remover"):
            continue
        if chave in _CAMPOS_APAGAVEIS and (valor is None or str(valor).strip() == ""):
            mesclado.pop(chave, None)
        elif valor is not None and valor != "":
            mesclado[chave] = valor
    texto = texto_de(item) or texto_de(original)
    mesclado.pop("texto", None)
    mesclado["text"] = texto
    return normalizar(mesclado, id_existente=original.get("id") or id_fallback or None)


def _parecido(texto: str, candidatos: list[tuple[int, str]]) -> int | None:
    """Indice da etapa com texto >=85% parecido, ou None."""
    textos = [t for _, t in candidatos]
    achados = difflib.get_close_matches(texto, textos, n=1, cutoff=0.85)
    if not achados:
        return None
    return candidatos[textos.index(achados[0])][0]


def _descrever(item: dict) -> str:
    eid = str(item.get("id") or "").strip()
    texto = texto_de(item)
    if eid and texto:
        return f"{eid} ({texto[:60]!r})"
    return eid or repr(texto[:60])


def editar_plano(plano_atual, novo_plano, *, modo: str = MODO_PARCIAL,
                 etapas_removidas=None) -> EdicaoPlano:
    """Aplica uma edicao ao plano, no modo pedido.

    **`parcial` (padrao).** So as etapas citadas mudam; as outras ficam
    intactas, na posicao em que estavam. Ate 27/09/2026 o unico modo era o de
    substituicao, e a descricao da tool dizia que "campos omitidos preservam o
    valor atual da etapa" — quem chamava lia isso como "mande so a etapa que
    mudou", mandava uma, e as outras quatro sumiam com retorno OK. Aconteceu
    com o dono e com o proprio Claude. Etapa citada casa por id, depois por
    texto parecido (>=85%); sem casar, e anexada ao fim. `{"id": ...,
    "remover": true}` e a unica forma de tirar uma etapa neste modo.

    **`substituir`.** A lista enviada passa a ser o plano inteiro, na ordem
    enviada — e o modo de reordenar. Etapa existente que nao aparecer sai do
    plano; quem chama (o handler) decide se isso exige confirmacao, olhando
    `removidas_sem_pedido`.

    Nos dois modos, um id que esteja em `etapas_removidas` (a lixeira da acao)
    traz a etapa de volta com o id e os campos originais — contador de
    adiamento e historico inclusos — em vez de criar uma etapa nova.

    Levanta `PlanoInvalido` quando a edicao cita uma etapa que nao existe de um
    jeito que nao da para interpretar como etapa nova (remover id
    desconhecido, ou id desconhecido sem texto).
    """
    modo = str(modo or MODO_PARCIAL).strip().lower()
    if modo not in MODOS:
        raise PlanoInvalido(f"modo {modo!r} invalido; use 'parcial' ou 'substituir'.")

    entrada = normalizar_entrada_plano(novo_plano)
    atual = list(plano_atual or [])
    idx_por_id = {p.get("id"): i for i, p in enumerate(atual)
                  if isinstance(p, dict) and p.get("id")}
    candidatos = [(i, texto_de(p)) for i, p in enumerate(atual)
                  if isinstance(p, dict) and texto_de(p)]
    lixeira = {str(e.get("id")): e for e in (etapas_removidas or [])
               if isinstance(e, dict) and e.get("id") and isinstance(e.get("etapa"), dict)}

    # Posicao i do plano atual -> etapa mesclada (quando citada).
    atualizadas: dict[int, dict] = {}
    remover_idx: set[int] = set()
    # (posicao_de_insercao, etapa) no parcial; no substituir tudo vai em `ordem`.
    restauradas: list[tuple[int, dict]] = []
    novas: list[dict] = []
    ordem: list = []  # substituir: ("atual", i) | ("etapa", dict)

    for item in entrada:
        if isinstance(item, str):
            item = {"text": item}
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id") or "").strip()
        texto = texto_de(item)

        if _pede_remocao(item):
            idx = idx_por_id.get(item_id) if item_id else None
            if idx is None and not item_id and texto:
                idx = next((i for i, t in candidatos if t.casefold() == texto.casefold()), None)
            if idx is None:
                raise PlanoInvalido(
                    f"Etapa a remover nao encontrada no plano: {_descrever(item)}. "
                    "Use o id exato da etapa (veja obter_acao).")
            remover_idx.add(idx)
            continue

        if item_id and item_id in idx_por_id:
            idx = idx_por_id[item_id]
            base = atualizadas.get(idx, atual[idx])
            atualizadas[idx] = _mesclar_item(base, item)
            if modo == MODO_SUBSTITUIR:
                ordem.append(("atual", idx))
            continue

        if item_id and item_id in lixeira:
            entrada_lixeira = lixeira.pop(item_id)
            etapa = _mesclar_item(entrada_lixeira["etapa"], item, id_fallback=item_id)
            if etapa:
                if modo == MODO_SUBSTITUIR:
                    ordem.append(("etapa", etapa))
                else:
                    restauradas.append((int(entrada_lixeira.get("posicao") or 0), etapa))
            continue

        if not texto:
            if item_id:
                raise PlanoInvalido(
                    f"Etapa {item_id!r} nao existe no plano e veio sem texto — nao da para "
                    "saber se e uma etapa nova. Confira o id (obter_acao) ou envie 'text'.")
            continue

        # Etapa ja citada nesta mesma chamada nao e candidata de novo: duas
        # etapas novas parecidas com a mesma antiga virariam uma so (ou, antes
        # disto, duas com o mesmo id).
        idx = _parecido(texto, [c for c in candidatos
                                if c[0] not in remover_idx and c[0] not in atualizadas])
        if idx is not None:
            base = atualizadas.get(idx, atual[idx])
            atualizadas[idx] = _mesclar_item(base, item, id_fallback=item_id)
            if modo == MODO_SUBSTITUIR:
                ordem.append(("atual", idx))
            continue

        nova = normalizar(item)
        if nova:
            if modo == MODO_SUBSTITUIR:
                ordem.append(("etapa", nova))
            else:
                novas.append(nova)

    if modo == MODO_PARCIAL:
        plano = [atualizadas.get(i, p) for i, p in enumerate(atual) if i not in remover_idx]
        plano = [p for p in plano if p]
        for posicao, etapa in sorted(restauradas, key=lambda r: r[0]):
            plano.insert(min(max(posicao, 0), len(plano)), etapa)
        plano.extend(novas)
        mantidos = set(range(len(atual))) - remover_idx
    else:
        plano = []
        mantidos = set()
        for tipo, valor in ordem:
            if tipo == "atual":
                if valor in remover_idx or valor in mantidos:
                    continue
                mantidos.add(valor)
                etapa = atualizadas.get(valor)
            else:
                etapa = valor
            if etapa:
                plano.append(etapa)

    removidas = []
    for i, p in enumerate(atual):
        if i in mantidos or not isinstance(p, dict) or not texto_de(p):
            continue
        removidas.append({
            "id": str(p.get("id") or ""),
            "etapa": dict(p),
            "posicao": i,
            "explicita": i in remover_idx,
        })

    restauradas_ids = [e["id"] for e in (etapas_removidas or [])
                       if isinstance(e, dict) and e.get("id")
                       and str(e.get("id")) not in lixeira and isinstance(e.get("etapa"), dict)]
    return EdicaoPlano(plano=plano, removidas=removidas, restauradas=restauradas_ids)


def mesclar_plano(plano_atual, novo_plano, modo: str = MODO_PARCIAL) -> list[dict]:
    """O plano resultante de `editar_plano` — atalho para quem so quer a lista.

    Desde 27/09/2026 o padrao e o modo `parcial`: etapa nao citada fica. Quem
    manda a lista inteira para reordenar passa `modo="substituir"`.
    """
    return editar_plano(plano_atual, novo_plano, modo=modo).plano


def atualizar_lixeira(etapas_removidas, edicao: EdicaoPlano, agora_iso: str) -> list[dict]:
    """A lixeira da acao depois da edicao: sai o que voltou, entra o que saiu.

    Cada entrada guarda a etapa inteira, a posicao que ela ocupava e quando
    saiu. Teto em `LIMITE_ETAPAS_REMOVIDAS`, descartando as mais antigas.
    """
    restauradas = set(edicao.restauradas)
    saida = [e for e in (etapas_removidas or [])
             if isinstance(e, dict) and str(e.get("id") or "") not in restauradas]
    for r in edicao.removidas:
        eid = r["id"] or str(uuid.uuid4())[:8]
        etapa = {**r["etapa"], "id": eid}
        saida = [e for e in saida if str(e.get("id") or "") != eid]
        saida.append({"id": eid, "etapa": etapa, "posicao": r["posicao"],
                      "removida_em": agora_iso})
    return saida[-LIMITE_ETAPAS_REMOVIDAS:]


def _resumo_valor(valor):
    if isinstance(valor, str) and len(valor) > 80:
        return valor[:77] + "..."
    return valor


def diferencas(plano_antes, plano_depois) -> dict:
    """O que de fato mudou entre dois planos, por etapa.

    Existe para o retorno de quem edita: sem ele, um campo que o merge ignorou
    respondia o mesmo "OK" de uma edicao que gravou. `completed` fica de fora
    por espelhar `estado`; estado e texto sao comparados pela leitura canonica,
    para que etapa antiga normalizada nao apareca como alterada.
    """
    antes = {p["id"]: p for p in (plano_antes or []) if isinstance(p, dict) and p.get("id")}
    depois = {p["id"]: p for p in (plano_depois or []) if isinstance(p, dict) and p.get("id")}

    alteradas = {}
    for eid, novo in depois.items():
        velho = antes.get(eid)
        if velho is None:
            continue
        campos = {}
        for chave in sorted((set(velho) | set(novo)) - {"id", "completed", "texto"}):
            if chave == "text":
                a, b = texto_de(velho), texto_de(novo)
            elif chave == "estado":
                a, b = estado_de(velho), estado_de(novo)
            else:
                a, b = velho.get(chave), novo.get(chave)
            if a != b:
                campos[chave] = [_resumo_valor(a), _resumo_valor(b)]
        if campos:
            alteradas[eid] = campos

    saida = {}
    if alteradas:
        saida["alteradas"] = alteradas
    adicionadas = [eid for eid in depois if eid not in antes]
    if adicionadas:
        saida["adicionadas"] = adicionadas
    removidas = [eid for eid in antes if eid not in depois]
    if removidas:
        saida["removidas"] = removidas
    comuns_antes = [eid for eid in antes if eid in depois]
    comuns_depois = [eid for eid in depois if eid in antes]
    if comuns_antes != comuns_depois:
        saida["ordem_alterada"] = True
    return saida


def aplicar_degradacao(plano, data_limite_acao: str | None) -> tuple[list[dict], dict | None, bool]:
    """Incrementa o contador da subtarefa corrente, se ela puder degradar.

    Devolve `(plano, subtarefa_degradada, macroacao_degrada)`. Os tres saem
    juntos porque sao a mesma decisao, e separa-los foi o que deixou a regra
    inconsistente antes: quem chama nao precisa reconstituir o motivo de
    ninguem ter degradado.

    **Esperar terceiro nao e procrastinar.** Subtarefa em `aguardando_terceiro`
    nao degrada — e como e ela que segura a acao, a macroacao tambem nao. Essa
    e a correcao central. Ate aqui a espera escapava so no primeiro dia: junto
    com o `[COBRAR]`, a virada do dia devolvia a faixa para `avanco`, e do
    segundo dia em diante a acao degradava como qualquer outra.

    Quando nao ha etapa aberta a macroacao **degrada assim mesmo** — nao ha a
    quem atribuir, mas o adiamento aconteceu. Isso e real, nao hipotetico: ha
    acao ativa com 12/12 etapas feitas e contador em 26.
    """
    itens = list(plano or [])
    alvo = subtarefa_corrente(itens, data_limite_acao)
    if alvo is None:
        return itens, None, True
    if estado_de(alvo) == AGUARDANDO_TERCEIRO:
        return itens, None, False

    saida = []
    degradada = None
    for item in itens:
        if isinstance(item, dict) and item is alvo:
            novo = {**item, "degradation_count": int(item.get("degradation_count") or 0) + 1}
            degradada = novo
            saida.append(novo)
        else:
            saida.append(item)
    return saida, degradada, True

def esvaziaria_o_plano(plano_atual, plano_final) -> bool:
    """Se aplicar `plano_final` apagaria um plano que existia.

    Em 28/08/2026 uma chamada de `editar_plano_acao` com o nome de parametro
    errado (`plano_acao` em vez de `novo_plano`) chegou com a lista nova vazia.
    O merge fez o que foi mandado — devolveu `[]` — e seis etapas sumiram, com
    retorno "OK". Apagar tudo por engano e barato de causar e caro de desfazer,
    entao passa a exigir intencao explicita.
    """
    tinha = any(isinstance(p, dict) and texto_de(p) for p in (plano_atual or []))
    ficaria = any(isinstance(p, dict) and texto_de(p) for p in (plano_final or []))
    return tinha and not ficaria

class PlanoInvalido(ValueError):
    """Entrada que nao descreve um plano. Recusar e melhor que gravar o que der."""


# Etapa de 1 ou 2 caracteres nunca e conteudo real; e o sintoma de uma string
# iterada como lista. Acima desta proporcao, o plano inteiro e recusado.
_PROPORCAO_DEGENERADA = 0.5


def normalizar_entrada_plano(valor):
    """Aceita lista, ou o JSON de uma lista, e recusa o resto.

    Em 28/08/2026 um plano chegou como a **string** `'["Baixar as propostas", ...]'`.
    `mesclar_plano` iterava sobre ela, e em Python iterar uma string percorre
    caracteres: a acao terminou com ~800 etapas de um caractere — `"["`, `'"'`,
    `"B"`, `"a"`... A escrita respondeu OK.

    Uma etapa de um caractere nao tem caso legitimo, entao o erro certo aqui e
    recusar, nao adivinhar.
    """
    if valor is None:
        return []
    if isinstance(valor, str):
        texto = valor.strip()
        if not texto:
            return []
        try:
            valor = json.loads(texto)
        except (ValueError, TypeError) as exc:
            raise PlanoInvalido(
                "O plano veio como texto e nao e JSON valido. Envie uma LISTA de "
                "etapas (ex.: novo_plano=[{\"text\": \"primeira etapa\"}]), nao "
                f"uma string. Recebido: {texto[:80]!r}") from exc
    if isinstance(valor, dict):
        valor = [valor]
    if not isinstance(valor, (list, tuple)):
        raise PlanoInvalido(
            f"O plano precisa ser uma lista de etapas; veio {type(valor).__name__}.")
    return list(valor)


def parece_degenerado(plano) -> str | None:
    """Descreve por que um plano e obviamente lixo, ou `None` se estiver bom.

    Serve de ultima barreira: mesmo que o parse passe, um plano majoritariamente
    feito de etapas de um caractere so pode ter vindo de uma string iterada.
    """
    itens = [texto_de(i) for i in (plano or []) if isinstance(i, dict)]
    itens = [x for x in itens if x]
    if not itens:
        return None
    curtas = sum(1 for x in itens if len(x) <= 2)
    if curtas / len(itens) > _PROPORCAO_DEGENERADA:
        return (f"{curtas} de {len(itens)} etapas tem 1 ou 2 caracteres — isso e o "
                "sintoma de uma string iterada como lista, nao um plano.")
    return None
