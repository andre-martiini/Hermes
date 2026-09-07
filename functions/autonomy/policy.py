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
       por mandato — P02 passo 5). Decide e retorna imediatamente.
    2. Estado "pausado" (seção 5.4): bloqueia tudo que não seja leitura.
       Decide e retorna imediatamente — nenhum mandato o contorna.
    3. Tipo de principal vs. classe de efeito — um `runner_servico` nunca
       decide sozinho um efeito de "compromisso com terceiros" ou
       "financeiro/destrutivo/institucional" (aceite do P02: "o agente não
       consegue conceder a si mesmo permissão"), A MENOS que um mandato
       explícito cubra o pedido. Só decide (DENY) quando NÃO há mandato
       cobrindo; caso contrário passa adiante.
    4/5. Mandato aplicável (rebaixa para allow, seção 5.3: "não exige um
       segundo botão") OU, na ausência de mandato, a matriz de efeito
       padrão (seção 5.1). As duas alimentam a MESMA decisão candidata.
       Por fim, o estado "somente_preparação" (seção 5.4) aperta essa
       decisão candidata por igual — inclusive uma vinda de mandato: um
       mandato vigente nunca faz o sistema agir além do que
       "somente_preparação" permite. Isto é deliberado: mandato responde
       "o dono já autorizou isto uma vez", estado de autonomia responde "o
       dono quer isto pausado/restrito AGORA" — a pergunta mais recente
       (estado) vence sobre a mais antiga (mandato).

    Não confia em `sensibilidade`/confiança autodeclarada do modelo para
    autorizar efeito (seção 5.2, última frase) — este parâmetro só entra no
    log, nunca relaxa uma decisão.
    """
    agora = agora or datetime.now(timezone.utc)
    checks: list[str] = []
    op_hash = _hash_operacao(request)

    # 1. Piso de confirmação obrigatória — decide e para, sempre.
    if request.ferramenta in FLOOR_CONFIRMACAO_OBRIGATORIA:
        checks.append("floor_confirmacao_obrigatoria")
        return PolicyDecision(
            decision=Decisao.REQUIRE_APPROVAL,
            policy_id="floor-confirmacao-obrigatoria",
            policy_version=_POLICY_VERSION_PADRAO,
            reason_code="floor_nao_contornavel",
            constraints_checked=tuple(checks),
            approval_required=True,
            operation_hash=op_hash,
            motivo_legivel=(
                f"'{request.ferramenta}' está no piso de confirmação obrigatória "
                "(decisão do dono, não amplia nem reduz por política ou mandato)."
            ),
        )

    checks.append("floor_confirmacao_obrigatoria")

    # 2. Estado de autonomia — só pode apertar, nunca afrouxar (checado nos
    #    dois extremos primeiro: pausado bloqueia tudo que não seja leitura).
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
    #    autoconceder um efeito de compromisso com terceiros ou financeiro/
    #    destrutivo/institucional. Calcula a cobertura de mandato UMA vez
    #    aqui e reusa no passo 4 (evita computar duas vezes e, mais
    #    importante, garante que os dois passos vejam exatamente a mesma
    #    resposta).
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

    # 4/5. Mandato aplicável (rebaixa para allow) OU matriz de efeito padrão
    #    (seção 5.1) para o que sobrar — as DUAS fontes alimentam a MESMA
    #    variável de decisão, para que o passo seguinte (estado
    #    "somente_preparação") aperte de forma uniforme independentemente de
    #    onde a decisão veio. Antes desta correção, uma decisão vinda de
    #    mandato retornava direto e escapava do aperto de
    #    "somente_preparação" — corrigido após revisão adversarial
    #    (sub-entrega 1/N, ver docs/autonomia/execucao.md): um runner de
    #    serviço com mandato vigente NÃO pode mais enviar um compromisso a
    #    terceiros enquanto o dono colocou a autonomia em "somente_preparação".
    checks.append("mandato_aplicavel")
    if cobre_por_mandato:
        decisao_padrao, reason_code, aprovacao = Decisao.ALLOW, "dentro_de_mandato_vigente", False
    else:
        checks.append("matriz_efeito_padrao")
        decisao_padrao, reason_code, aprovacao = _decisao_padrao_por_classe(
            request.classe_efeito, request.principal
        )

    # Estado "somente_preparação" aperta qualquer coisa mais forte que
    # preparação interna — inclusive uma decisão que veio de mandato.
    if request.estado_autonomia == EstadoAutonomia.SOMENTE_PREPARACAO and decisao_padrao not in (
        Decisao.DENY, Decisao.PREPARE_ONLY,
    ) and request.classe_efeito != ClasseEfeito.OBSERVACAO_AUTORIZADA:
        decisao_padrao = Decisao.PREPARE_ONLY
        reason_code = "autonomia_somente_preparacao"
        aprovacao = False

    return PolicyDecision(
        decision=decisao_padrao,
        policy_id=_POLICY_ID_PADRAO,
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
        return Decisao.ALLOW, "preparacao_interna_com_mandato_valido", False
    if classe == ClasseEfeito.ESCRITA_INTERNA_REVERSIVEL:
        return Decisao.ALLOW, "escrita_interna_reversivel_dentro_do_mandato", False
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
    """Um mandato cobre um pedido se: não revogado, ainda válido, o destino
    está entre os cobertos, a classe de conteúdo está entre as permitidas, o
    horário (se restrito) bate, e o limite por janela não foi excedido.

    O limite por janela (contagem de uso recente) não é verificado aqui —
    esta função é pura e não tem acesso a histórico de uso; o chamador que
    monta `mandatos_aplicaveis` já deve excluir um mandato cujo limite da
    janela atual foi atingido (thin wrapper com I/O, análogo a
    `estado_autonomia_atual` no fim deste arquivo). Documentado explicitamente
    para não ser lido como "limite não implementado" — é implementado fora
    desta função pura de propósito.
    """
    if mandato.revogado:
        return False
    if mandato.valido_ate is not None and agora > mandato.valido_ate:
        return False

    destinos = set(mandato.destinatarios_recursos)
    if destinos and not (
        "*" in destinos
        or any(
            _destino_coberto(d, request.argumentos_resolvidos.get("destinatario", ""))
            for d in destinos
        )
        or any(d == request.ferramenta for d in destinos)
    ):
        return False

    classes = set(mandato.classes_conteudo_permitidas)
    if classes and request.sensibilidade is not None and request.sensibilidade not in classes:
        return False

    if mandato.horario_permitido_inicio and mandato.horario_permitido_fim:
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
    ativá-la de verdade."""
    agora = agora or datetime.now(timezone.utc)
    resultados = []
    for pedido in pedidos:
        decisao = avaliar(pedido, agora=agora)
        resultados.append({
            "ferramenta": pedido.ferramenta,
            "principal_tipo": pedido.principal.tipo.value,
            "decisao": decisao.to_dict(),
        })
    permitidos = sum(1 for r in resultados if r["decisao"]["decision"] == Decisao.ALLOW.value)
    bloqueados = sum(1 for r in resultados if r["decisao"]["decision"] == Decisao.DENY.value)
    return {
        "total": len(resultados),
        "permitidos": permitidos,
        "bloqueados": bloqueados,
        "requer_aprovacao": len(resultados) - permitidos - bloqueados,
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
    valor = dados.get(dominio) or dados.get("global") or EstadoAutonomia.ATIVO.value
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
