"""Motor de política de autonomia (P02 do plano de autonomia, passos 4, 7, 9).

Implementa a matriz de efeito e a decisão de política da seção 5 do plano
(docs/plano-hermes-autonomo-2026-09-06.md, PR #184 — ainda não mergeado em
`main`), a partir dos tipos de `autonomy/contracts.py`.

Sub-entrega 1/N do P02: só o motor de decisão (função pura, sem I/O) e as
funções de consulta/simulação/preparação de política, MAIS a gravação de
decisões — NENHUM canal foi religado a isto ainda. `mcp_server.py` continua
usando seu próprio `_CONFIRMACAO_OBRIGATORIA` hoje; uma sub-entrega seguinte
troca essa fonte por `FLOOR_CONFIRMACAO_OBRIGATORIA` daqui (fonte única, sem
duplicação) e chama `avaliar()` como preflight antes de cada tool. Ver
docs/autonomia/execucao.md para o registro completo desta divisão.

Design deliberado: `avaliar()` é uma função PURA — recebe um `PolicyRequest`
já com `classe_efeito` resolvida pelo chamador (que tem acesso a
`tools/registry.py`; este módulo propositalmente não importa `tools.*` nem
`firebase_admin`, para não criar dependência circular com o pacote de tools
e para ficar testável sem Firestore/emulador, mesmo padrão de
`core/idempotency.py::_txn` e do conjunto de fakes de `test_hermes_tools.py`
descrito no achado de investigação desta sub-entrega). As funções que TÊM
I/O real (`estado_autonomia_atual`, `registrar_decisao`,
`preparar_politica_persistida`) ficam claramente separadas no fim do arquivo
e recebem `db` explicitamente — nunca leem Firestore por conta própria de
dentro da decisão.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from autonomy.contracts import (
    ClasseEfeito,
    Decisao,
    EstadoAutonomia,
    Mandato,
    Principal,
    PolicyDecision,
    PolicyRequest,
    TipoPrincipal,
)

# ---------------------------------------------------------------------------
# Piso de confirmação obrigatória — fonte única (P02 passo 5: preservar as
# cinco confirmações atuais durante a migração; não ampliar por analogia nem
# remover por conveniência).
#
# Espelha EXATAMENTE `mcp_server._CONFIRMACAO_OBRIGATORIA` hoje (2026-09-07,
# antes desta sub-entrega religar o canal MCP a este módulo) — mesmos cinco
# nomes, mesmo motivo por trás de cada um (ver o comentário completo em
# mcp_server.py:53-85, preservado ali). Depois que uma sub-entrega seguinte
# trocar `mcp_server.py` para consultar este conjunto em vez de manter o seu
# próprio, ele deixa de existir duplicado — até lá, os dois precisam
# permanecer idênticos; um teste de regressão nesta sub-entrega
# (test_policy.py) documenta isso e falha se divergirem.
#
# ESTE CONJUNTO NÃO CRESCE POR HÁBITO (condição do dono, 02/09/2026, herdada
# de mcp_server.py) — uma candidata nova exige decisão explícita, registrada
# aqui e em mcp_server.py, não "parece do mesmo tipo".
FLOOR_CONFIRMACAO_OBRIGATORIA: frozenset[str] = frozenset({
    "schedule_whatsapp_message", "pausar_conversa", "criar_rascunho_email",
    "registrar_aporte_investimento", "registrar_execucao_investimento",
})

# Classificação por convenção das ferramentas do piso, na matriz de efeito da
# seção 5.1 — exposta via `consultar_politica("mcp")` para quem quiser saber
# "por que este tool está no piso"; a decisão em si (`avaliar()`, abaixo) não
# depende desta tabela, depende de `classe_efeito` vir corretamente
# preenchido pelo chamador em cada `PolicyRequest`.
CLASSE_EFEITO_PISO: dict[str, ClasseEfeito] = {
    "schedule_whatsapp_message": ClasseEfeito.COMPROMISSO_TERCEIROS,
    "criar_rascunho_email": ClasseEfeito.COMPROMISSO_TERCEIROS,
    "pausar_conversa": ClasseEfeito.COMPROMISSO_TERCEIROS,
    "registrar_aporte_investimento": ClasseEfeito.EFEITO_FINANCEIRO_DESTRUTIVO_INSTITUCIONAL,
    "registrar_execucao_investimento": ClasseEfeito.EFEITO_FINANCEIRO_DESTRUTIVO_INSTITUCIONAL,
}

_POLICY_ID_PADRAO = "matriz-efeito-secao-5.1"
_POLICY_VERSION_PADRAO = 1


# ---------------------------------------------------------------------------
# Decisão — função pura (P02 passo 4, 6, 8)
# ---------------------------------------------------------------------------

def avaliar(request: PolicyRequest, *, agora: datetime | None = None) -> PolicyDecision:
    """Decide allow/prepare_only/require_approval/defer/deny para um pedido.

    Ordem de checagem (a primeira que decidir e retornar, decide — nenhuma
    checagem posterior pode afrouxar uma decisão anterior mais restritiva):

    1. Piso de confirmação obrigatória (nunca contornável por política nem
       por mandato — P02 passo 5): fixa a decisão CANDIDATA em
       require_approval e pula os passos 2-5 (nenhum mandato nem tipo de
       principal muda isso). A candidata ainda passa pelo aperto de estado
       do passo 6 — ver a nota nesse passo.
    2. Estado "pausado" (seção 5.4): bloqueia tudo que não seja leitura.
       Decide e retorna imediatamente — nenhum mandato o contorna. (Só se
       aplica quando o passo 1 não decidiu — ferramentas do piso são
       apertadas pelo mesmo estado no passo 6, não aqui.)
    3. Tipo de principal vs. classe de efeito — um `runner_servico` nunca
       decide sozinho um efeito de "compromisso com terceiros" ou
       "financeiro/destrutivo/institucional" (aceite do P02: "o agente não
       consegue conceder a si mesmo permissão"), A MENOS que um mandato
       explícito cubra o pedido. Só decide (DENY) quando NÃO há mandato
       cobrindo; caso contrário passa adiante.
    4/5. Mandato aplicável (rebaixa para allow, seção 5.3: "não exige um
       segundo botão") OU, na ausência de mandato, a matriz de efeito
       padrão (seção 5.1). As duas alimentam a MESMA decisão candidata.
    6. Por fim, o estado "somente_preparação"/"pausado" (seção 5.4) aperta
       a decisão candidata por igual — venha ela do piso (passo 1), de
       mandato ou da matriz padrão (passo 4/5). Um mandato vigente nunca
       faz o sistema agir além do que "somente_preparação" permite, e uma
       ferramenta do piso nunca fica "aguardando aprovação" enquanto a
       autonomia está pausada (achado P1 da revisão do Codex, PR #191: a
       versão original retornava o piso direto no passo 1, sem nunca
       consultar o estado — um humano aprovando essa pendência ainda
       executaria o efeito apesar da pausa). Isto é deliberado: mandato/
       piso respondem "o dono já autorizou isto" (uma vez, ou como regra
       permanente), estado de autonomia responde "o dono quer isto
       pausado/restrito AGORA" — a pergunta mais recente (estado) vence.

    Não confia em `sensibilidade`/confiança autodeclarada do modelo para
    autorizar efeito (seção 5.2, última frase) — este parâmetro só entra no
    log, nunca relaxa uma decisão.
    """
    agora = agora or datetime.now(timezone.utc)
    checks: list[str] = []
    op_hash = _hash_operacao(request)

    checks.append("floor_confirmacao_obrigatoria")
    veio_do_piso = request.ferramenta in FLOOR_CONFIRMACAO_OBRIGATORIA

    if veio_do_piso:
        # 1. Piso — decisão candidata fixa, passos 2-5 não se aplicam. Ainda
        #    passa pelo aperto de estado do passo 6, abaixo. `policy_id`
        #    próprio (não o padrão da matriz) enquanto a decisão continuar
        #    vindo do piso — o passo 6 troca para `_POLICY_ID_PADRAO` se e
        #    quando o estado efetivamente apertar a decisão (achado da
        #    revisão adversarial desta correção: a refatoração abaixo tinha
        #    deixado o `return` final usar `_POLICY_ID_PADRAO`
        #    incondicionalmente, fazendo uma decisão do piso se identificar
        #    como se tivesse vindo da matriz de efeito da seção 5.1).
        decisao_padrao, reason_code, aprovacao = Decisao.REQUIRE_APPROVAL, "floor_nao_contornavel", True
        policy_id = "floor-confirmacao-obrigatoria"
        # O passo 6 sempre consulta o estado para decidir se aperta o piso —
        # registra isso na trilha de auditoria mesmo quando o estado é ATIVO
        # e nada muda, espelhando o que o passo 2 já faz no ramo não-piso.
        checks.append("estado_autonomia")
    else:
        # 2. Estado de autonomia — só pode apertar, nunca afrouxar (checado
        #    nos dois extremos primeiro: pausado bloqueia tudo que não seja
        #    leitura).
        if request.estado_autonomia == EstadoAutonomia.PAUSADO:
            checks.append("estado_autonomia")
            if request.classe_efeito == ClasseEfeito.OBSERVACAO_AUTORIZADA:
                pass  # leitura continua permitida mesmo pausado (seção 5.4)
            else:
                return PolicyDecision(
                    decision=Decisao.DENY,
                    policy_id=_POLICY_ID_PADRAO,
                    policy_version=_POLICY_VERSION_PADRAO,
                    reason_code="autonomia_pausada",
                    constraints_checked=tuple(checks),
                    operation_hash=op_hash,
                    motivo_legivel="Autonomia pausada: nenhum efeito além de leitura é permitido agora.",
                )
        else:
            checks.append("estado_autonomia")

        # 3. Tipo de principal vs. classe de efeito — o agente não pode se
        #    autoconceder um efeito de compromisso com terceiros ou
        #    financeiro/destrutivo/institucional. Calcula a cobertura de
        #    mandato UMA vez aqui e reusa no passo 4 (evita computar duas
        #    vezes e, mais importante, garante que os dois passos vejam
        #    exatamente a mesma resposta).
        checks.append("tipo_principal_vs_classe_efeito")
        cobre_por_mandato = _mandato_cobre_algum(request, agora)
        classes_restritas_a_dono = (
            ClasseEfeito.COMPROMISSO_TERCEIROS,
            ClasseEfeito.EFEITO_FINANCEIRO_DESTRUTIVO_INSTITUCIONAL,
        )
        if (
            request.classe_efeito in classes_restritas_a_dono
            and not request.principal.eh_dono()
            and not cobre_por_mandato
        ):
            return PolicyDecision(
                decision=Decisao.DENY,
                policy_id=_POLICY_ID_PADRAO,
                policy_version=_POLICY_VERSION_PADRAO,
                reason_code="principal_nao_pode_autoconceder",
                constraints_checked=tuple(checks),
                operation_hash=op_hash,
                motivo_legivel=(
                    f"Principal do tipo '{request.principal.tipo.value}' não pode "
                    f"decidir sozinho um efeito '{request.classe_efeito.value}' sem "
                    "mandato explícito que cubra este pedido."
                ),
            )

        # 4/5. Mandato aplicável (rebaixa para allow) OU matriz de efeito
        #    padrão (seção 5.1) para o que sobrar — as DUAS fontes
        #    alimentam a MESMA variável de decisão, para que o passo 6
        #    (estado) aperte de forma uniforme independentemente de onde a
        #    decisão veio. Antes desta correção, uma decisão vinda de
        #    mandato retornava direto e escapava do aperto de
        #    "somente_preparação" — corrigido após revisão adversarial
        #    (sub-entrega 1/N, ver docs/autonomia/execucao.md): um runner de
        #    serviço com mandato vigente NÃO pode mais enviar um compromisso
        #    a terceiros enquanto o dono colocou a autonomia em
        #    "somente_preparação".
        checks.append("mandato_aplicavel")
        if cobre_por_mandato:
            decisao_padrao, reason_code, aprovacao = Decisao.ALLOW, "dentro_de_mandato_vigente", False
        else:
            checks.append("matriz_efeito_padrao")
            decisao_padrao, reason_code, aprovacao = _decisao_padrao_por_classe(
                request.classe_efeito, request.principal
            )
        policy_id = _POLICY_ID_PADRAO

    # 6. Estado "pausado"/"somente_preparação" aperta a decisão candidata —
    #    inclusive uma vinda do piso (achado P1 da revisão do Codex, PR
    #    #191, ver docstring acima). O ramo do piso nunca passa por aqui com
    #    OBSERVACAO_AUTORIZADA (nenhuma ferramenta do piso é classificada
    #    como leitura), então "pausado" sempre aperta para deny quando
    #    veio_do_piso — sem precisar repetir a exceção de leitura do passo 2.
    #    Quando o estado efetivamente aperta uma decisão do piso, o
    #    `policy_id` muda para o padrão — a decisão final não é mais "o piso
    #    decidiu", é "o estado de autonomia decidiu apertar o piso".
    if veio_do_piso and request.estado_autonomia == EstadoAutonomia.PAUSADO:
        decisao_padrao, reason_code, aprovacao = Decisao.DENY, "autonomia_pausada", False
        policy_id = _POLICY_ID_PADRAO
    elif request.estado_autonomia == EstadoAutonomia.SOMENTE_PREPARACAO and decisao_padrao not in (
        Decisao.DENY, Decisao.PREPARE_ONLY,
    ) and request.classe_efeito != ClasseEfeito.OBSERVACAO_AUTORIZADA:
        decisao_padrao = Decisao.PREPARE_ONLY
        reason_code = "autonomia_somente_preparacao"
        aprovacao = False
        policy_id = _POLICY_ID_PADRAO

    return PolicyDecision(
        decision=decisao_padrao,
        policy_id=policy_id,
        policy_version=_POLICY_VERSION_PADRAO,
        reason_code=reason_code,
        constraints_checked=tuple(checks),
        approval_required=aprovacao,
        operation_hash=op_hash,
        motivo_legivel=f"Classificado como '{request.classe_efeito.value}' ({reason_code}).",
    )


def _decisao_padrao_por_classe(
    classe: ClasseEfeito, principal: Principal,
) -> tuple[Decisao, str, bool]:
    """A matriz de efeito da seção 5.1, traduzida em decisão. Retorna
    (decisão, reason_code, approval_required)."""
    if classe == ClasseEfeito.OBSERVACAO_AUTORIZADA:
        return Decisao.ALLOW, "observacao_autorizada", False
    if classe == ClasseEfeito.PREPARACAO_INTERNA:
        # Correção pós-revisão do Codex (PR #191, segunda rodada): este é o
        # ramo da matriz PADRÃO — chamado só quando NÃO há mandato cobrindo
        # (ver `avaliar()`, passo 4/5). O reason_code antigo
        # ("...com_mandato_valido") mentia sobre a origem da decisão e
        # corrompia a trilha de auditoria (`registrar_decisao` grava
        # exatamente este texto).
        #
        # Gate por `origem_humana` (correção pós-revisão do Codex, terceira
        # rodada): a matriz de efeito (seção 5.1 do plano) define, para
        # "Preparação interna", a regra "Executar com mandato e orçamento
        # válidos" — ou seja, SEM mandato vigente, o padrão não é ALLOW
        # incondicional. A exceção que preserva a "pouca fricção" prometida
        # na seção 5 é quando um humano está de fato presente/dirigindo o
        # pedido agora (`origem_humana=True` — dono interativo ou cliente
        # assistido em tempo real, que já é a própria confirmação); sem essa
        # presença (rotina do Cowork ou runner de serviço agindo sozinho,
        # sem mandato), preparar internamente ainda é seguro por ser
        # reversível/observável, mas não deve fechar o ciclo sozinho —
        # rebaixa para PREPARE_ONLY em vez de ALLOW.
        #
        # Exige também `eh_dono()` (achado do Codex sobre a PR #192): o
        # comentário acima já dizia que a exceção é para "dono interativo ou
        # cliente assistido", mas o código só checava a flag booleana
        # `origem_humana` — nada no sistema de tipos impede um
        # `ROTINA_COWORK`/`RUNNER_SERVICO`/`TERCEIRO_PORTAL` de ser
        # construído com `origem_humana=True` (o próprio default do
        # contrato). Sem essa checagem extra, um terceiro num portal
        # público com "humano presente" (ele mesmo, não o dono) recebia o
        # mesmo ALLOW que o dono interativo — a garantia de que é o DONO
        # presente, não qualquer humano, é o que preserva a baixa fricção
        # da seção 5 sem abrir mão da restrição de autoconcessão do passo 3
        # de `avaliar()`.
        if principal.origem_humana and principal.eh_dono():
            return Decisao.ALLOW, "preparacao_interna_permitida_por_padrao", False
        return (
            Decisao.PREPARE_ONLY,
            "preparacao_interna_requer_mandato_ou_humano_presente",
            False,
        )
    if classe == ClasseEfeito.ESCRITA_INTERNA_REVERSIVEL:
        # Mesma correção — nenhum mandato foi consultado para chegar aqui. A
        # seção 5.1 define, para "Escrita interna reversível", a regra
        # "Executar dentro do mandato": sem mandato vigente, mesmo raciocínio
        # de `origem_humana` acima — inclusive o `eh_dono()` adicional
        # (achado do Codex sobre a PR #192, mesmo raciocínio do ramo
        # PREPARACAO_INTERNA logo acima).
        if principal.origem_humana and principal.eh_dono():
            return Decisao.ALLOW, "escrita_interna_reversivel_permitida_por_padrao", False
        return (
            Decisao.PREPARE_ONLY,
            "escrita_interna_reversivel_requer_mandato_ou_humano_presente",
            False,
        )
    if classe == ClasseEfeito.COORDENACAO_LIMITADA:
        # "Exigir política específica previamente aprovada" — sem mandato
        # explícito cobrindo (já checado antes de chegar aqui), decide-se
        # como require_approval, nunca allow direto.
        return Decisao.REQUIRE_APPROVAL, "coordenacao_limitada_exige_politica_previa", True
    if classe == ClasseEfeito.COMPROMISSO_TERCEIROS:
        return Decisao.REQUIRE_APPROVAL, "compromisso_terceiros_exige_decisao_concreta", True
    if classe == ClasseEfeito.EFEITO_FINANCEIRO_DESTRUTIVO_INSTITUCIONAL:
        return Decisao.DENY, "efeito_financeiro_destrutivo_exige_autorizacao_especifica", False
    # Classe desconhecida: fail closed, nunca fail open.
    return Decisao.DENY, "classe_efeito_desconhecida_fail_closed", False


def _mandato_cobre_algum(request: PolicyRequest, agora: datetime) -> bool:
    return any(
        mandato_cobre(m, request, agora)
        for m in request.mandatos_aplicaveis
    )


def _destino_coberto(destino_mandato: str, destinatario_pedido: str) -> bool:
    """Compara um destino do mandato com o destinatário resolvido do pedido.

    Correção pós-revisão adversarial (sub-entrega 1/N): a versão original
    usava `destino in destinatario` (substring cru), o que deixava um
    mandato para "@empresa.com" cobrir por engano
    "chefe@empresa.com.malicioso.net" (a string "@empresa.com" está contida
    ali, mas o domínio real é outro). Regra agora: igualdade exata, OU — só
    para o padrão explícito de domínio "@dominio" — o destinatário deve
    TERMINAR EXATAMENTE com esse sufixo (`str.endswith`, não `in`), o que
    ancora o `@` real e não é enganado por texto extra colado depois do
    domínio.
    """
    if destino_mandato == destinatario_pedido:
        return True
    if destino_mandato.startswith("@") and destinatario_pedido.endswith(destino_mandato):
        return True
    return False


def mandato_cobre(mandato: Mandato, request: PolicyRequest, agora: datetime) -> bool:
    """Um mandato cobre um pedido se: não revogado, ainda válido, dentro do
    limite de uso da janela (falha fechada quando a contagem é desconhecida
    e há limite declarado), a finalidade bate exatamente com a missão do
    pedido (falha fechada quando a missão não foi informada), o destino está
    entre os cobertos, a classe de conteúdo está entre as permitidas, e o
    horário (se restrito) bate.

    Orçamento (fechado na sub-entrega 4/N do P02, docs/autonomia/execucao.md
    — antes disso, `PolicyRequest.orcamento_restante` não era lido em nenhum
    ponto desta função nem de `avaliar()`, apesar de a matriz de efeito
    (seção 5.1 do plano) exigir "mandato e orçamento válidos" para
    preparação interna): quando `Mandato.orcamento_maximo` está declarado, o
    mandato só cobre se `orcamento_restante` tiver sido RESOLVIDO (mesmo
    raciocínio fail-closed de `usos_na_janela_atual`, logo abaixo — saldo
    desconhecido contra um teto declarado não passa) e ainda restar
    orçamento positivo. Mandatos sem `orcamento_maximo` declarado (o
    default, `None`) não são afetados — nem toda finalidade tem dimensão
    financeira. Resolver o saldo real (consumo até agora vs. teto) continua
    sendo responsabilidade de um wrapper com I/O ainda não implementado,
    mesma divisão já descrita para `usos_na_janela_atual`. Gap ainda aberto,
    categoria diferente: `classes_conteudo_permitidas` continua texto livre,
    não enum fechado (ver comentário mais abaixo, na checagem de
    `sensibilidade`).

    Limite por janela (correção pós-revisão do Codex, PR #191): esta função
    é pura e não tem acesso a histórico de uso — `mandato.usos_na_janela_atual`
    é o dado JÁ RESOLVIDO que o chamador (thin wrapper com I/O, análogo a
    `estado_autonomia_atual` no fim deste arquivo — ainda não implementado
    nesta sub-entrega) precisa preencher antes de incluir o mandato em
    `mandatos_aplicaveis`. Terceira rodada da revisão do Codex: quando há
    `limite_por_janela` declarado mas a contagem ainda é `None` (nada
    resolveu ainda), o mandato NÃO cobre — contagem desconhecida contra um
    limite declarado falha fechado, não é tratada como "sem limite". O campo
    existe desde já para que o wrapper futuro tenha onde escrever, em vez de
    o limite ficar "documentado mas sem lugar nenhum para ser checado" (era
    assim que o Codex encontrou o gap original: nada no repositório populava
    ou lia essa contagem).
    """
    if mandato.revogado:
        return False
    # Validade (correção pós-revisão do Codex, PR #191, quarta rodada): a
    # versão anterior só rejeitava quando `valido_ate` estava PREENCHIDO e no
    # passado — um mandato sem `valido_ate` (o default do contrato) cobria
    # indefinidamente, apesar de "validade" ser uma das condições mínimas do
    # mandato (seção 5.3 do plano) e de cada outro campo opcional desta
    # função já ter sido fechado no mesmo sentido (limite por janela,
    # finalidade/missão, destinos, classes — todos falham fechado quando o
    # dado não foi resolvido, em vez de tratar ausência como "sem
    # restrição"). Agora: sem `valido_ate` resolvido, o mandato não cobre.
    if mandato.valido_ate is None:
        return False
    if agora > mandato.valido_ate:
        return False
    if mandato.limite_por_janela is not None:
        # Correção pós-revisão do Codex (PR #191, terceira rodada): a versão
        # anterior só rejeitava quando `usos_na_janela_atual` já estava
        # PREENCHIDO e no limite — quando o chamador ainda não tinha
        # resolvido a contagem (`None`, o padrão do contrato), o limite era
        # simplesmente ignorado e o mandato cobria como se não houvesse
        # limite nenhum. Um mandato com `limite_por_janela` declarado exige
        # que a contagem tenha sido resolvida para contar como coberto —
        # contagem desconhecida não passa por um limite declarado (falha
        # fechada, mesmo raciocínio já aplicado a `sensibilidade=None`
        # contra um mandato que declara `classes_conteudo_permitidas`).
        if mandato.usos_na_janela_atual is None:
            return False
        if mandato.usos_na_janela_atual >= mandato.limite_por_janela:
            return False

    # Orçamento (P02 passo 8, sub-entrega 4/N — ver docstring desta função
    # acima para o histórico do gap): mesmo raciocínio fail-closed do limite
    # por janela, logo acima — um teto DECLARADO exige saldo RESOLVIDO.
    if mandato.orcamento_maximo is not None:
        if request.orcamento_restante is None:
            return False
        # `not (> 0)`, não `<= 0` (achado da revisão adversarial desta
        # sub-entrega): `orcamento_restante = float('nan')` faz TODAS as
        # comparações (`<=`, `<`, `>`, `>=`, `==`) retornarem `False` — um
        # saldo NaN não é "None" nem "<= 0", então a checagem `<= 0` deixava
        # passar como se fosse um saldo positivo válido, exatamente o
        # oposto do fail-closed que esta checagem existe para garantir.
        # `not (x > 0)` rejeita NaN corretamente (`nan > 0` já é `False`,
        # então a negação vira `True` e a função retorna `False` abaixo).
        if not (request.orcamento_restante > 0):
            return False

    # Finalidade do mandato vs. missão do pedido (correção pós-revisão do
    # Codex, terceira rodada): a versão anterior só comparava quando AMBOS
    # `missao` e `finalidade` vinham preenchidos — como `Mandato.finalidade`
    # é campo obrigatório (`str`, sem default — seção 5.3: "condições
    # mínimas" inclui finalidade), todo mandato real já declara uma; a
    # checagem antiga então nunca disparava quando o chamador simplesmente
    # não preenchia `missao` (`None`, o default de `PolicyRequest`),
    # deixando QUALQUER mandato cobrir pedidos sem missão declarada — o
    # mesmo padrão de fail-open já fechado para `sensibilidade`/
    # `destinatarios_recursos`/`classes_conteudo_permitidas`. Agora a
    # comparação é incondicional: `missao` ausente nunca bate com a
    # `finalidade` (sempre presente) do mandato.
    if request.missao != mandato.finalidade:
        return False

    destinos = set(mandato.destinatarios_recursos)
    if not destinos:
        # Achado P1 da revisão do Codex (PR #191): `destinos and not (...)`
        # pulava a checagem inteira quando `destinatarios_recursos` vinha
        # vazio (`set()` é falso), tratando um mandato SEM escopo de destino
        # como se cobrisse QUALQUER destinatário — o oposto do que o
        # contrato pede ("destinatários/recursos" é uma das condições
        # mínimas do mandato, não algo que possa ficar implícito como "*").
        # Falha fechada: destino vazio nunca cobre nada.
        return False
    if not (
        "*" in destinos
        or any(
            _destino_coberto(d, request.argumentos_resolvidos.get("destinatario", ""))
            for d in destinos
        )
        or any(d == request.ferramenta for d in destinos)
    ):
        return False

    classes = set(mandato.classes_conteudo_permitidas)
    if not classes:
        # Mesmo achado, mesmo raciocínio, para `classes_conteudo_permitidas`
        # vazio: sem classe declarada, o mandato não cobre nada — não é
        # "unrestricted" por omissão.
        return False
    if request.sensibilidade not in classes:
        # Correção pós-revisão do Codex (PR #191, primeira rodada): a versão
        # original só rejeitava quando `sensibilidade` estava PREENCHIDA e
        # fora da lista — como o contrato permite `sensibilidade=None` por
        # padrão, um mandato restrito a ("geral",) cobria qualquer pedido
        # cujo chamador simplesmente não preenchesse o campo, inclusive um
        # efeito financeiro/destrutivo. Agora: ausência de classificação
        # NÃO passa por um mandato que declara classes — falha fechado, não
        # aberto (`None not in {"geral"}` é True, então isto também barra
        # o caso ausente, não só o caso "fora da lista").
        #
        # Limitação documentada (segunda rodada da revisão do Codex, PR
        # #191): `classes_conteudo_permitidas` continua sendo texto livre
        # (`tuple[str, ...]`), não um conjunto fechado/enum — nada aqui
        # impede um mandato com um rótulo como "outro" de cobrir um pedido
        # cujo `sensibilidade` resolvido seja também "outro". O plano
        # (seção 5.3) exige que "tipos 'outro' e rótulos livres não podem
        # habilitar envio autônomo", mas essa é uma responsabilidade de QUEM
        # RESOLVE `sensibilidade` a partir de um vocabulário controlado
        # (ainda não implementado — nenhum chamador popula este campo nesta
        # sub-entrega) ou de uma sub-entrega futura que troque este campo
        # por um enum fechado; esta função só compara os valores que recebe.
        return False

    # Janela de horário parcialmente configurada (correção pós-revisão do
    # Codex, PR #191, quarta rodada): a versão anterior só aplicava a
    # restrição quando os DOIS extremos vinham preenchidos (`and`) — um
    # mandato com só `horario_permitido_inicio` OU só `horario_permitido_fim`
    # (dado parcial/malformado; os dois campos são independentemente
    # opcionais no contrato) pulava a checagem inteira, cobrindo qualquer
    # horário como se não houvesse restrição nenhuma. Mesmo raciocínio já
    # aplicado aos outros campos desta função: um dado parcialmente resolvido
    # não é "sem restrição", é "não resolvido" — falha fechada.
    # `is not None` na checagem externa, não truthiness (achado da revisão
    # adversarial desta própria correção): `"" or ""` é falsy, então um
    # mandato com os dois campos presentes mas vazios (`""`) escapava até
    # da checagem de configuração parcial logo abaixo — o mesmo padrão de
    # bug que esta rodada fechou em `estado_autonomia_atual`, reintroduzido
    # aqui por usar `or`/`and` sobre o valor em vez de identidade com None.
    if mandato.horario_permitido_inicio is not None or mandato.horario_permitido_fim is not None:
        if not (mandato.horario_permitido_inicio and mandato.horario_permitido_fim):
            return False
        inicio, fim = mandato.horario_permitido_inicio, mandato.horario_permitido_fim
        hora_atual = agora.strftime("%H:%M")
        if inicio <= fim:
            dentro_da_janela = inicio <= hora_atual <= fim
        else:
            # Janela cruza a meia-noite (ex.: 22:00-06:00) — correção
            # pós-revisão adversarial: a comparação simples `inicio <= hora
            # <= fim` é insatisfazível quando fim < inicio, o que tornava
            # qualquer mandato noturno permanentemente inutilizável (sempre
            # False, em qualquer horário) sem nenhum erro visível.
            dentro_da_janela = hora_atual >= inicio or hora_atual <= fim
        if not dentro_da_janela:
            return False

    return True


def _hash_operacao(request: PolicyRequest) -> str:
    """sha256 do payload canônico (ferramenta + argumentos ordenados) — para
    correlacionar a decisão com a operação exata, sem guardar os argumentos
    em si na decisão (ver `registrar_decisao`)."""
    payload = json.dumps(
        {"ferramenta": request.ferramenta, "argumentos": request.argumentos_resolvidos},
        sort_keys=True, ensure_ascii=False, default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Consultar / simular / preparar política — P02 passo 7
# ---------------------------------------------------------------------------

def consultar_politica(escopo: str) -> dict:
    """Permissões, limites, versão e origem para um escopo — leitura pura,
    sem mutação (linha 412 do plano). `escopo` hoje só reconhece "mcp"
    (o piso de confirmação); escopos por-ferramenta/por-mandato ficam para
    quando houver fonte de mandatos persistida (sub-entrega seguinte)."""
    if escopo == "mcp":
        return {
            "escopo": "mcp",
            "policy_id": "floor-confirmacao-obrigatoria",
            "policy_version": _POLICY_VERSION_PADRAO,
            "ferramentas_com_confirmacao_obrigatoria": sorted(FLOOR_CONFIRMACAO_OBRIGATORIA),
            "classe_efeito_por_ferramenta": {
                nome: CLASSE_EFEITO_PISO[nome].value for nome in sorted(CLASSE_EFEITO_PISO)
            },
            "origem": "condição do dono, 02/09/2026 — não cresce por hábito",
        }
    return {
        "escopo": escopo,
        "policy_id": _POLICY_ID_PADRAO,
        "policy_version": _POLICY_VERSION_PADRAO,
        "origem": "matriz de efeito padrão, seção 5.1 do plano",
    }


def simular_politica(pedidos: list[PolicyRequest], *, agora: datetime | None = None) -> dict:
    """Avalia um lote de pedidos hipotéticos SEM aplicar nada — proposta e
    exemplos → efeitos permitidos/bloqueados (linha 413 do plano). Usado
    para conferir o efeito de uma mudança de mandato/estado antes de
    ativá-la de verdade.

    Correção pós-revisão do Codex (PR #191): a versão original computava
    `requer_aprovacao` por subtração (`total - permitidos - bloqueados`),
    o que misturava `PREPARE_ONLY` e `DEFER` dentro de "requer aprovação" —
    um resultado `PREPARE_ONLY` (por exemplo, autonomia em
    "somente_preparação") tem `approval_required=False` no `to_dict()`, mas
    aparecia contado como se exigisse aprovação. Agora cada decisão é
    contada pelo seu próprio valor, sem inferência por subtração.
    """
    agora = agora or datetime.now(timezone.utc)
    resultados = []
    for pedido in pedidos:
        decisao = avaliar(pedido, agora=agora)
        resultados.append({
            "ferramenta": pedido.ferramenta,
            "principal_tipo": pedido.principal.tipo.value,
            "decisao": decisao.to_dict(),
        })
    contagem = {d.value: 0 for d in Decisao}
    for r in resultados:
        contagem[r["decisao"]["decision"]] += 1
    return {
        "total": len(resultados),
        "permitidos": contagem[Decisao.ALLOW.value],
        "bloqueados": contagem[Decisao.DENY.value],
        "requer_aprovacao": contagem[Decisao.REQUIRE_APPROVAL.value],
        "somente_preparacao": contagem[Decisao.PREPARE_ONLY.value],
        "adiados": contagem[Decisao.DEFER.value],
        "resultados": resultados,
    }


def preparar_politica(politica_proposta: dict, *, base_version: int) -> dict:
    """Política proposta + versão base → diff explícito e decisão concreta a
    tomar (linha 414 do plano). Só PREPARA — não aplica. A aplicação
    acontece pelo fluxo autenticado de confirmação existente (mesmo padrão
    de `mcp_server._criar_confirmacao`/`confirmar_acao`), fora deste módulo
    nesta sub-entrega — quem chamar isto ainda precisa levar o diff por um
    caminho de confirmação real antes de qualquer escrita, e este módulo não
    persiste nada sozinho.
    """
    if base_version != _POLICY_VERSION_PADRAO:
        return {
            "diff": None,
            "erro": (
                f"base_version={base_version} não bate com a versão vigente "
                f"({_POLICY_VERSION_PADRAO}) — releia a política antes de propor "
                "mudança, para não sobrescrever uma versão que você não viu."
            ),
        }

    atual = set(FLOOR_CONFIRMACAO_OBRIGATORIA)
    proposto = set(politica_proposta.get("ferramentas_com_confirmacao_obrigatoria", atual))
    adicionadas = sorted(proposto - atual)
    removidas = sorted(atual - proposto)

    exige_justificativa = bool(removidas)
    return {
        "diff": {
            "adicionadas": adicionadas,
            "removidas": removidas,
            "inalteradas": sorted(atual & proposto),
        },
        "versao_base": base_version,
        "versao_proposta": base_version + 1,
        "exige_justificativa_explicita": exige_justificativa,
        "aviso": (
            "Remover uma ferramenta do piso de confirmação obrigatória exige "
            "decisão explícita e individual do dono, registrada com motivo — "
            "nunca aplicada automaticamente por este diff."
            if exige_justificativa else None
        ),
    }


# ---------------------------------------------------------------------------
# Funções com I/O real (Firestore) — thin wrappers em torno do que é puro
# acima. Nenhuma delas é chamada por nenhum canal ainda nesta sub-entrega.
# ---------------------------------------------------------------------------

_ESTADO_DOC = ("system", "autonomy_state")
_AUSENTE = object()  # sentinela: distingue "chave ausente" de "valor presente e falsy"


def estado_autonomia_atual(db, dominio: str = "global") -> EstadoAutonomia:
    """Lê `system/autonomy_state.{dominio}` (novo documento; ainda não
    escrito por nada em produção — lido aqui defensivamente).

    Duas falhas diferentes, duas respostas diferentes (correção pós-revisão
    adversarial da sub-entrega 1/N — a versão original colapsava as duas no
    mesmo ATIVO, o que seria fail-open no dia em que esta função passar a
    ser consultada de verdade):

    - Documento AUSENTE (nada foi configurado ainda) → ATIVO. Este é o
      comportamento de hoje, sem esta sub-entrega — não muda nada para
      canais que ainda não consultam este módulo.
    - Leitura FALHOU (Firestore indisponível, permissão negada, valor
      corrompido no documento) → SOMENTE_PREPARACAO. Um erro real não é a
      mesma coisa que "nada configurado": não sabemos qual era o estado
      verdadeiro, então não cai nem no mais aberto (ATIVO, abriria
      autonomia sem confirmação de que é seguro) nem no mais fechado
      (PAUSADO, que é uma decisão exclusiva do dono, não uma inferência de
      erro de leitura) — cai no meio-termo mais restrito que ainda não
      requer decisão do dono para ser aplicado.
    """
    try:
        snap = db.collection(_ESTADO_DOC[0]).document(_ESTADO_DOC[1]).get()
    except Exception:
        return EstadoAutonomia.SOMENTE_PREPARACAO

    if not snap.exists:
        return EstadoAutonomia.ATIVO

    dados = snap.to_dict() or {}
    # Correção pós-revisão do Codex (PR #191, quarta rodada): a versão
    # anterior usava `dados.get(dominio) or dados.get("global") or ATIVO`,
    # que trata um valor PRESENTE MAS FALSY (`""`, `None` gravado
    # explicitamente — por exemplo um documento em escrita parcial) do
    # mesmo jeito que uma chave AUSENTE, caindo direto em ATIVO sem nunca
    # passar pelo `except ValueError` abaixo. O docstring desta função
    # promete SOMENTE_PREPARACAO para "valor gravado que não é um dos três
    # esperados" — um valor falsy presente é exatamente esse caso, não o
    # de "nada configurado". Agora a chave é procurada por AUSÊNCIA
    # (`dict.get(..., _AUSENTE)`), não por truthiness: só cai em ATIVO
    # quando nem `dominio` nem "global" existem no documento; um valor
    # presente e falsy segue para `EstadoAutonomia(valor)`, que lança
    # `ValueError` e cai no fail-closed de baixo, como qualquer outro valor
    # gravado inválido.
    valor = dados.get(dominio, _AUSENTE)
    if valor is _AUSENTE:
        valor = dados.get("global", _AUSENTE)
    if valor is _AUSENTE:
        valor = EstadoAutonomia.ATIVO.value
    try:
        return EstadoAutonomia(valor)
    except ValueError:
        # Documento existe mas o valor gravado não é um dos três esperados
        # — dado corrompido/versão futura desconhecida, mesmo raciocínio de
        # falha de leitura acima: não presume ATIVO nem PAUSADO.
        return EstadoAutonomia.SOMENTE_PREPARACAO


def registrar_decisao(db, request: PolicyRequest, decision: PolicyDecision) -> None:
    """Registra a decisão com motivo, sem copiar conteúdo sensível integral
    (P02 passo 9) — grava só as CHAVES dos argumentos (não os valores), o
    hash da operação, e o resultado. Coleção nova (`policy_decisions`),
    distinta de `mcp_audit_log` (que já grava argumentos completos hoje —
    ver mcp_server.py:856-863 — e continua existindo para esse propósito;
    este log é sobre a DECISÃO de política, não sobre a chamada em si)."""
    try:
        db.collection("policy_decisions").add({
            "uid": request.principal.uid,
            "principal_tipo": request.principal.tipo.value,
            "canal": request.principal.canal,
            "ferramenta": request.ferramenta,
            "argumentos_chaves": sorted(request.argumentos_resolvidos.keys()),
            "operation_hash": decision.operation_hash,
            "decision": decision.decision.value,
            "policy_id": decision.policy_id,
            "policy_version": decision.policy_version,
            "reason_code": decision.reason_code,
            "constraints_checked": list(decision.constraints_checked),
            "timestamp": _server_timestamp(),
        })
    except Exception as exc:  # noqa: BLE001 — telemetria nunca derruba a decisão
        print(f"[autonomy.policy] Falha ao registrar decisão (tool={request.ferramenta}): {exc}")


def _server_timestamp():
    from firebase_admin import firestore

    return firestore.SERVER_TIMESTAMP
