"""Orquestração pura de pedido durável (P04 do plano de autonomia,
docs/plano-hermes-autonomo-2026-09-06.md, passo 4 do pacote: "Implementar
assumir, renovar, registrar progresso e registrar resultado observado").

Costura quatro peças já existentes, cada uma construída numa sub-entrega
anterior como lógica pura e sem I/O:

- `autonomy.requests` (sub-entrega 1/N): estados (`RequestStatus`), lease e
  geração -- seção 4.4 "Pedido" e seção 4.5, itens 1-5.
- `autonomy.ledger` (sub-entrega 2/N): idempotência por chave/hash,
  checkpoints e resultado observado -- seção 4.5, itens 6/9/10.
- `autonomy.runs` (sub-entrega 4/N): ciclo verificado de UMA tentativa de
  execução (`AgentRun`) -- seção 1.3, achado A02; costurado em
  `PedidoDuravel` nesta sub-entrega (5/N), ver `run` abaixo.

Nenhum destes três módulos sabia dos outros. `PedidoDuravel`, abaixo, é o
agregado que representa "um pedido com sua reserva, seu ledger de operação e
o registro verificado da tentativa de execução em curso" -- o mesmo tipo de
objeto que o wiring real (Firestore, `agent_requests.py`) vai precisar
montar a partir de um documento, mas ainda sem nenhum I/O aqui: só o que as
quatro operações do MCP propostas na seção 6.2 (`assumir_pedido_agente`,
`renovar_pedido_agente`, `registrar_progresso_agente`,
`registrar_resultado_observado`) precisam decidir, dado o estado atual e uma
ação de um consumidor.

Mesmo padrão incremental das sub-entregas anteriores de P04: quem persiste
o `PedidoDuravel` (lê o documento, monta o objeto, chama a função aqui,
grava o resultado de volta) fica para a sub-entrega de wiring (passo 5/6 do
pacote) -- ver `proximo_pacote` do bloco desta sub-entrega em
docs/autonomia/execucao.md.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from autonomy.ledger import (
    LedgerEntry,
    adicionar_checkpoint,
    criar_ou_reusar_entrada,
)
from autonomy.ledger import registrar_resultado as _ledger_registrar_resultado
from autonomy.requests import (
    DEFAULT_LEASE_SEGUNDOS,
    ESTADOS_TERMINAIS,
    Lease,
    RequestStatus,
    lease_expirada,
    lease_pertence_ao_apresentante,
    lease_valida_para_acao,
    nova_lease,
    renovar_lease,
    validar_transicao,
)
from autonomy.runs import AgentRun, AgentRunStatus
from autonomy.runs import concluir_run as _run_concluir
from autonomy.runs import criar_run as _run_criar
from autonomy.runs import marcar_em_andamento as _run_marcar_em_andamento

#: Para qual `AgentRunStatus` mapear cada `RequestStatus` TERMINAL aceito por
#: `registrar_resultado_observado`. `autonomy.runs.AgentRun` só tem dois
#: desfechos possíveis por `concluir_run` (`CONCLUIDO`/`FALHA` -- `TIMEOUT` é
#: exclusivo de `expirar_por_timeout`, uma ação de sistema, ver docstring de
#: `autonomy.runs`), então `CANCELADO` (cancelamento do PEDIDO, não uma
#: escolha do executor) mapeia para `FALHA`: a tentativa em curso não produziu
#: um resultado bem-sucedido, mesmo que o motivo seja cancelamento externo em
#: vez de um erro. `ERRO_LEGADO` fica de fora deliberadamente -- nenhum
#: caminho de `registrar_resultado_observado` consegue alcançá-lo (ver
#: docstring de `autonomy.requests.RequestStatus`), então não precisa de
#: mapeamento.
_REQUEST_STATUS_PARA_AGENT_RUN_STATUS: dict[RequestStatus, AgentRunStatus] = {
    RequestStatus.CONCLUIDO: AgentRunStatus.CONCLUIDO,
    RequestStatus.FALHA_FINAL: AgentRunStatus.FALHA,
    RequestStatus.CANCELADO: AgentRunStatus.FALHA,
}

#: Estados em que renovar a lease faz sentido -- o executor ainda está
#: ativamente trabalhando (ou aguardando algo enquanto SEGURA a reserva)
#: neste pedido. Deliberadamente MENOR que "não terminal"
#: (`ESTADOS_TERMINAIS`): `RETENTATIVA_AGENDADA` e `RESULTADO_DESCONHECIDO`
#: também não entram aqui, mesmo sendo não-terminais -- achado de revisão
#: adversarial (Codex, PR #330, P1): ambos sinalizam que a posse ATUAL está
#: sendo reconsiderada (agendar nova tentativa / reconciliar um efeito
#: incerto), não que o mesmo executor continua com a reserva. Deixar
#: renovar nesses dois estados permitiria a um executor "zumbi" continuar
#: dando heartbeat indefinidamente e impedir para sempre que a retentativa
#: fosse reivindicada (por `assumir_pedido`, que corretamente recusa
#: reassumir enquanto a lease anterior ainda não expirou)."""
_STATUS_PERMITE_RENOVACAO_DE_LEASE: frozenset[RequestStatus] = frozenset({
    RequestStatus.RESERVADO,
    RequestStatus.EM_ANDAMENTO,
    RequestStatus.VERIFICANDO,
    RequestStatus.AGUARDANDO_APROVACAO,
    RequestStatus.AGUARDANDO_EXTERNO,
})


class LeaseInvalida(Exception):
    """Fencing falhou -- seção 4.5, item 5: "consumidor anterior perde
    direito de concluir ou produzir nova operação depois de perder a
    reserva." `motivo` é o texto devolvido por
    `autonomy.requests.lease_valida_para_acao`, já pensado para ser
    apresentável (não vaza detalhe interno, só "lease expirada", "geração
    não confere" etc.)."""

    def __init__(self, motivo: str) -> None:
        self.motivo = motivo
        super().__init__(f"lease inválida: {motivo}")


@dataclass(frozen=True)
class PedidoDuravel:
    """Agregado: um pedido durável, sua reserva atual (se houver) e o
    ledger da operação associada (se já foi aberto). Imutável, como `Lease`
    e `LedgerEntry` -- toda função abaixo devolve uma instância NOVA.

    `ledger_entry` começa `None`: um pedido recém-criado ainda não tem
    nenhuma operação em curso. `registrar_progresso` é o primeiro ponto em
    que um ledger é aberto (via `criar_ou_reusar_entrada`) -- seção 4.5,
    item 6: "antes de qualquer efeito, criar/reusar operation_ledger".

    `run` (sub-entrega 5/N) começa `None` pelo mesmo motivo -- só existe a
    partir do primeiro `assumir_pedido`, que sempre cria um `AgentRun` novo
    junto com a lease nova (seção 1.3, A02: "servidor cria agent_run ao
    reservar"). Um `PedidoDuravel` construído diretamente (sem passar por
    `assumir_pedido` -- ex.: um pedido legado ainda não migrado, ou um caso
    de teste) pode legitimamente não ter `run`: `registrar_progresso` e
    `registrar_resultado_observado` toleram isso e simplesmente não tocam o
    ciclo do run nesse caso, sem erro -- só a peça de ledger/status do pedido
    continua funcionando (mesmo espírito de tolerância a dados legados já
    usado nos módulos irmãos)."""

    request_id: str
    status: RequestStatus
    lease: Lease | None = None
    ledger_entry: LedgerEntry | None = None
    run: AgentRun | None = None

    def __post_init__(self) -> None:
        request_id_limpo = str(self.request_id or "").strip()
        if not request_id_limpo:
            raise ValueError("request_id é obrigatório.")
        object.__setattr__(self, "request_id", request_id_limpo)


def _validar_fencing(pedido: PedidoDuravel, lease_token: str, generation: int, agora: datetime | None) -> None:
    ok, motivo = lease_valida_para_acao(pedido.lease, lease_token, generation, agora=agora)
    if not ok:
        raise LeaseInvalida(motivo)


def _transicionar(pedido: PedidoDuravel, novo_status: RequestStatus) -> None:
    """Levanta `ValueError` (mensagem de `validar_transicao`) se
    `pedido.status -> novo_status` não for uma transição permitida.

    Sempre delega a `validar_transicao`, inclusive quando
    `novo_status == pedido.status` -- essa função já reprova esse caso
    ("pedido já está em ..."), o que é o comportamento certo aqui: chamar
    `assumir_pedido` de novo sobre um pedido já `RESERVADO` não é uma
    reentrega inofensiva, é uma segunda reserva que precisaria passar pela
    lease/geração corretas, não por um atalho de "mesmo estado, então
    tudo bem" (achado de teste desta sub-entrega -- um atalho assim aqui
    deixaria um segundo executor "assumir" um pedido já reservado sem
    checar lease nenhuma). Reentregas legítimas de MESMO estado (ex.:
    `registrar_progresso` chamado de novo enquanto já `EM_ANDAMENTO`) são
    tratadas no chamador, pulando esta função quando o estado já é o
    esperado -- não aqui, de forma genérica."""
    ok, motivo = validar_transicao(pedido.status, novo_status)
    if not ok:
        raise ValueError(motivo)


def _transicionar_para_resultado(pedido: PedidoDuravel, novo_status: RequestStatus) -> None:
    """Mesma validação de `_transicionar`, mas para `registrar_resultado_observado`
    especificamente, com duas diferenças deliberadas:

    1. `novo_status == pedido.status` É um no-op permitido aqui (ao
       contrário de `_transicionar`) -- reenviar o MESMO resultado para um
       pedido já `CONCLUIDO`/`FALHA_FINAL` é a reentrega idempotente que a
       seção 4.5, item 9 descreve; `autonomy.ledger.registrar_resultado`
       (chamado logo depois) é quem de fato garante que só um resultado
       IGUAL passa aqui sem erro -- um resultado diferente ainda levanta
       `ValueError` lá, mesmo com o status batendo.
    2. Quando a transição direta `pedido.status -> novo_status` não é
       permitida, tenta o caminho implícito por `VERIFICANDO` (seção 4.4:
       "em_andamento → verificando → concluido") antes de desistir --
       `registrar_resultado_observado` registra evidência e decide o
       desfecho na MESMA chamada (ainda não há `autonomy/verifiers.py`,
       passo 8 do pacote, para separar isso em duas chamadas distintas),
       então `EM_ANDAMENTO -> CONCLUIDO` precisa ser aceito aqui mesmo sem
       ser uma aresta direta no grafo."""
    if novo_status == pedido.status:
        return
    ok, motivo = validar_transicao(pedido.status, novo_status)
    if ok:
        return
    ok_intermediario, _ = validar_transicao(pedido.status, RequestStatus.VERIFICANDO)
    if ok_intermediario:
        ok_final, _ = validar_transicao(RequestStatus.VERIFICANDO, novo_status)
        if ok_final:
            return
    raise ValueError(motivo)


def assumir_pedido(
    pedido: PedidoDuravel,
    executor_id: str,
    run_id: str,
    agora: datetime | None = None,
    duracao_segundos: float = DEFAULT_LEASE_SEGUNDOS,
) -> PedidoDuravel:
    """Seção 6.2, `assumir_pedido_agente`: "request_id opcional,
    executor_capabilities → pedido reservado, lease_token, generation."

    Só aceita pedidos em estado que permite ir para `RESERVADO`
    (`PENDENTE` ou `RETENTATIVA_AGENDADA`, hoje -- ver
    `autonomy.requests._TRANSICOES_PERMITIDAS`); `validar_transicao`
    decide isso, não esta função.

    Além disso, se `pedido.lease` já existir (reassumindo depois de
    `RETENTATIVA_AGENDADA`, por exemplo), ela precisa estar EXPIRADA --
    levanta `LeaseInvalida` caso contrário. Achado de revisão adversarial
    (P04 sub-entrega 3/N): sem esta checagem, um segundo executor podia
    "assumir" um pedido cuja lease anterior ainda tinha minutos de validade
    sempre que o `status` permitisse a transição para `RESERVADO`, tornando
    o token/geração do executor original silenciosamente inúteis mesmo
    antes de expirar -- exatamente o cenário que o fencing por geração
    (seção 4.5, item 5) existe para impedir. Esta função tem toda a
    informação necessária (`pedido.lease.expires_at`, `agora`) para
    recusar isso sozinha, sem depender só do wiring de armazenamento.

    `run_id` (sub-entrega 5/N) é OBRIGATÓRIO, sem valor padrão -- mesma
    escolha deliberada de `autonomy.runs.concluir_run.lease_ainda_valida`:
    omitir silenciosamente a criação do `AgentRun` reproduziria exatamente o
    achado A02 que este módulo existe para corrigir ("uma execução que nunca
    é registrada pode desaparecer das métricas"). Esta função não decide
    COMO gerar esse identificador (Firestore auto-ID ou
    `secrets.token_urlsafe`, à escolha de quem fizer o wiring real) -- só
    que ele precisa existir a cada `assumir_pedido`, exatamente como
    `autonomy.runs.criar_run` já documenta. Cada reassumir (nova geração de
    lease) cria um `AgentRun` NOVO com o `lease_token`/`generation` recém-
    emitidos -- nunca reaproveita `pedido.run` antigo, mesmo espírito de
    "múltiplas tentativas do mesmo pedido produzem múltiplos `AgentRun`"
    já descrito na docstring de `autonomy.runs`.

    Resolve `agora` UMA vez (mesmo `datetime.now(timezone.utc)`, se não
    informado) e passa o mesmo valor para `nova_lease` e `criar_run` -- sem
    isso, cada função resolveria seu próprio "agora" independentemente,
    deixando `lease.expires_at` e `run.iniciado_em` calculados a partir de
    dois instantes reais ligeiramente diferentes (só relevante quando
    `agora` não é informado; produção sempre informa)."""
    _transicionar(pedido, RequestStatus.RESERVADO)
    if pedido.lease is not None and not lease_expirada(pedido.lease, agora=agora):
        raise LeaseInvalida(
            f"lease anterior de '{pedido.lease.executor_id}' ainda válida "
            f"(expira em {pedido.lease.expires_at.isoformat()}) -- não é possível "
            "reassumir antes de expirar."
        )
    agora_resolvida = agora if agora is not None else datetime.now(timezone.utc)
    generation_anterior = pedido.lease.generation if pedido.lease is not None else 0
    lease_nova = nova_lease(
        executor_id, generation_anterior, agora=agora_resolvida, duracao_segundos=duracao_segundos
    )
    run_novo = _run_criar(
        run_id=run_id,
        request_id=pedido.request_id,
        executor_id=executor_id,
        lease_token=lease_nova.lease_token,
        generation=lease_nova.generation,
        agora=agora_resolvida,
    )
    return dataclasses.replace(pedido, status=RequestStatus.RESERVADO, lease=lease_nova, run=run_novo)


def renovar_pedido(
    pedido: PedidoDuravel,
    lease_token: str,
    generation: int,
    agora: datetime | None = None,
    duracao_segundos: float = DEFAULT_LEASE_SEGUNDOS,
) -> PedidoDuravel:
    """Seção 6.2, `renovar_pedido_agente`: "request_id, lease_token,
    generation → novo vencimento."

    Estende `expires_at` MANTENDO o mesmo `lease_token`/`generation` --
    renovação não é uma nova reserva (não incrementa geração; um executor
    que já detém a lease continua sendo o mesmo executor, não uma disputa
    nova). Não muda `status`: renovar é só heartbeat, seção 4.5 item 4
    ("início, heartbeat, checkpoint e conclusão exigem o mesmo
    token/geração ainda válidos").

    Só aceita renovar quando `pedido.status` está em
    `_STATUS_PERMITE_RENOVACAO_DE_LEASE` -- ou seja, quando o mesmo
    executor ainda está ativamente trabalhando (ou aguardando algo
    enquanto segura a reserva) neste pedido. Isto exclui não só
    `ESTADOS_TERMINAIS` (achado de revisão adversarial, P04 sub-entrega
    3/N, 1a rodada: nenhuma função deste módulo limpa `pedido.lease` ao
    transicionar para um terminal, e `_validar_fencing` sozinha não olha
    `status` -- sem checar isso, uma lease emitida antes da conclusão
    continuava "renovável" até seu próprio `expires_at` original mesmo com
    o pedido já `CONCLUIDO`), como também `RETENTATIVA_AGENDADA` e
    `RESULTADO_DESCONHECIDO` (achado de revisão adversarial, Codex, PR
    #330, P1: ambos sinalizam que a posse atual está sendo reconsiderada,
    não que o mesmo executor continua com a reserva -- permitir renovar
    aqui deixaria um executor "zumbi" bloquear para sempre a reivindicação
    da retentativa por `assumir_pedido`, que corretamente recusa reassumir
    enquanto a lease anterior não expira)."""
    _validar_fencing(pedido, lease_token, generation, agora)
    if pedido.status not in _STATUS_PERMITE_RENOVACAO_DE_LEASE:
        raise ValueError(
            f"pedido '{pedido.request_id}' está em '{pedido.status.value}', que não "
            "renova lease -- só pedidos ativamente trabalhados pelo mesmo executor "
            f"({sorted(s.value for s in _STATUS_PERMITE_RENOVACAO_DE_LEASE)}) podem."
        )
    assert pedido.lease is not None  # garantido por _validar_fencing (motivo != "nenhuma reserva ativa")
    lease_renovada = renovar_lease(pedido.lease, agora=agora, duracao_segundos=duracao_segundos)
    return dataclasses.replace(pedido, lease=lease_renovada)


def registrar_progresso(
    pedido: PedidoDuravel,
    lease_token: str,
    generation: int,
    idempotency_key: str,
    payload: dict[str, Any],
    checkpoint_dados: dict[str, Any],
    agora: datetime | None = None,
) -> PedidoDuravel:
    """Seção 6.2, `registrar_progresso_agente`: "request_id, lease_token,
    checkpoint, evidence_refs → checkpoint aceito."

    Abre o ledger da operação na primeira chamada (`criar_ou_reusar_entrada`
    -- item 6) e acrescenta um checkpoint (`adicionar_checkpoint` -- item 8:
    "após queda, recuperar checkpoint"). Chamadas seguintes com o MESMO
    `idempotency_key`/`payload` reusam a mesma entrada; payload DIFERENTE
    para a mesma chave levanta `ConflitoIdempotencia` (propagada de
    `autonomy.ledger`, item 10 -- nunca sobrescreve).

    Move o pedido para `EM_ANDAMENTO` na primeira chamada (a partir de
    `RESERVADO`, `AGUARDANDO_APROVACAO` ou `AGUARDANDO_EXTERNO`); chamadas
    seguintes enquanto já `EM_ANDAMENTO` pulam a validação de transição
    (reentrega legítima de checkpoint, não uma segunda "entrada" no
    estado -- `_transicionar` propositalmente NÃO trata
    `novo_status == pedido.status` como no-op genérico, ver sua docstring;
    aqui o no-op é decidido pelo chamador, restrito a este caso
    específico).

    Espelha a mesma transição em `pedido.run`, se houver
    (`autonomy.runs.marcar_em_andamento` -- `INICIADO -> EM_ANDAMENTO`, sub-
    entrega 5/N): o fencing já validado acima contra `pedido.lease` sempre
    confere também contra `pedido.run` -- `assumir_pedido` cria os dois a
    partir do MESMO `lease_token`/`generation` recém-emitidos, e nenhuma
    outra função deste módulo muda um sem o outro. `pedido.run is None` é
    tolerado (pedido construído sem passar por `assumir_pedido`, ver
    docstring de `PedidoDuravel`) -- só a peça de ledger/status continua
    funcionando nesse caso.

    A chamada a `marcar_em_andamento` roda em TODA chamada com `pedido.run`
    presente, não só na primeira (achado de revisão do Codex, PR #339):
    um wiring futuro que persista `pedido`/`run` como dois documentos
    separados pode, entre uma queda e uma retentativa, deixar o PEDIDO já
    `EM_ANDAMENTO` mas o `run` ainda `INICIADO` (a escrita do pedido
    terminou, a do run não). Se a chamada ao run ficasse restrita ao
    `if pedido.status != EM_ANDAMENTO` (só a "primeira" transição do
    pedido), uma retentativa que chega com o pedido JÁ `EM_ANDAMENTO`
    nunca repararia esse run atrasado -- ele ficaria `INICIADO` para
    sempre, incompleto nas métricas (exatamente o defeito que A02, e este
    módulo, existem para evitar). `marcar_em_andamento` já é idempotente
    (no-op, mesmo objeto devolvido, quando o run já está `EM_ANDAMENTO`),
    então chamá-la sempre que houver run é seguro e repara esse caso sem
    custo extra no caminho normal."""
    _validar_fencing(pedido, lease_token, generation, agora)
    if pedido.status != RequestStatus.EM_ANDAMENTO:
        _transicionar(pedido, RequestStatus.EM_ANDAMENTO)
    run_atualizado = pedido.run
    if run_atualizado is not None:
        run_atualizado = _run_marcar_em_andamento(run_atualizado, lease_token, generation)
    entrada = criar_ou_reusar_entrada(idempotency_key, payload, pedido.ledger_entry, agora=agora)
    entrada = adicionar_checkpoint(entrada, checkpoint_dados, agora=agora)
    return dataclasses.replace(
        pedido, status=RequestStatus.EM_ANDAMENTO, ledger_entry=entrada, run=run_atualizado
    )


def registrar_resultado_observado(
    pedido: PedidoDuravel,
    lease_token: str,
    generation: int,
    resultado: Any,
    novo_status: RequestStatus,
    agora: datetime | None = None,
) -> PedidoDuravel:
    """Seção 6.2, `registrar_resultado_observado`: "operation/request_id,
    evidência tipada → resultado aceito, refutado ou pendente. Servidor
    valida evidência antes de concluir."

    Esta função NÃO valida a evidência em si (isso é `autonomy/verifiers.py`,
    passo 8 do pacote, ainda não implementado) -- só garante o que já é
    responsabilidade desta camada: fencing válido e ledger aberto (não dá
    para registrar resultado de uma operação que nunca teve
    `registrar_progresso` chamado -- `pedido.ledger_entry is None` levanta
    `ValueError`).

    `novo_status` só aceita um estado TERMINAL do pedido
    (`autonomy.requests.ESTADOS_TERMINAIS` -- hoje `CONCLUIDO`,
    `FALHA_FINAL` ou `CANCELADO`; `ERRO_LEGADO` nunca é alcançável por
    `validar_transicao`). `autonomy.ledger.registrar_resultado` sela a
    entrada do ledger PERMANENTEMENTE (item 10: nunca sobrescreve) e
    `adicionar_checkpoint` recusa checkpoint novo numa entrada selada --
    aceitar aqui um `novo_status` não-terminal (`RETENTATIVA_AGENDADA`,
    `RESULTADO_DESCONHECIDO`, `AGUARDANDO_APROVACAO`,
    `AGUARDANDO_EXTERNO`) seria um beco sem saída: o pedido continuaria
    "ativo" (`pedido_esta_ativo` verdadeiro) mas nunca mais poderia chamar
    `registrar_progresso` de novo -- nem reusando o mesmo
    `idempotency_key` (ledger já selado) nem usando um novo (a entrada
    existente pertence à chave antiga, `criar_ou_reusar_entrada` rejeita
    trocar de chave). Esses estados intermediários -- retentativa
    agendada, aguardando aprovação/terceiro, resultado ainda desconhecido
    -- não representam um resultado definitivo desta OPERAÇÃO e ficam para
    outro mecanismo (o sweep do passo 7 do pacote, ou uma função de
    transição de status que não toque o ledger), fora do escopo desta
    fatia. Achado de revisão adversarial (P04 sub-entrega 3/N): reproduzido
    concretamente com `RETENTATIVA_AGENDADA` selando o ledger e travando
    toda tentativa seguinte, mesma classe de problema para os demais
    estados não-terminais listados.

    Reentrega do MESMO resultado é idempotente (herdado de
    `autonomy.ledger.registrar_resultado`); resultado DIFERENTE para uma
    operação já concluída levanta `ValueError`, nunca sobrescreve. Essa
    reentrega idempotente é aceita mesmo com a lease ORIGINAL já expirada
    -- achado de revisão adversarial (Codex, PR #330, P2): se a resposta da
    1a chamada se perdeu (ex.: timeout de rede) e o consumidor tenta de
    novo depois do vencimento natural da lease (5 minutos por padrão), a
    fatia normal desta função exigiria uma lease ainda válida para uma
    operação cujo resultado JÁ está definitivamente registrado -- o que
    contradiz a própria garantia de reentrega idempotente do item 9. Neste
    caminho especial, ainda EXIGE identidade de token/geração
    (`lease_pertence_ao_apresentante`, sem checar expiração) -- não abre
    mão de autenticar quem está lendo, só da exigência de lease
    NÃO-vencida; `autonomy.ledger.registrar_resultado` continua sendo o
    árbitro final de "idêntico" (levanta `ValueError` para um resultado
    diferente, mesmo aqui).

    Fecha `pedido.run` (se houver, sub-entrega 5/N) na MESMA chamada, via
    `autonomy.runs.concluir_run` -- `CONCLUIDO`/`FALHA_FINAL` mapeiam
    diretamente para `AgentRunStatus.CONCLUIDO`/`FALHA`; `CANCELADO` também
    mapeia para `FALHA` (`AgentRun` não tem desfecho próprio de
    cancelamento -- ver `_REQUEST_STATUS_PARA_AGENT_RUN_STATUS`, no topo do
    módulo, para a justificativa completa).

    `lease_ainda_valida` é sempre CALCULADA a partir da lease REAL do
    pedido (`not lease_expirada(pedido.lease, agora=agora)`), nos dois
    caminhos -- nunca assumida como `True`. Achado de revisão adversarial:
    uma versão anterior desta função passava `lease_ainda_valida=True`
    fixo no caminho de reentrega, sob a justificativa de que
    `concluir_run` "ignora esse parâmetro de qualquer forma (run já
    terminal)" -- mas isso só é verdade quando `pedido.run` JÁ está
    terminal, algo que esta função nunca conferia antes de chamar. Um
    `PedidoDuravel` construído com `pedido.run` ainda ATIVO (ex.:
    `INICIADO`/`EM_ANDAMENTO`) ao lado de um ledger já selado -- uma
    inconsistência que só um wiring futuro com escrita não-atômica de
    pedido/run poderia produzir, já que os quatro caminhos deste módulo
    sempre fecham os dois juntos -- forçaria `concluir_run` a fechar esse
    run com uma lease já expirada há muito tempo, só porque a alegação era
    aceita sem verificação. Calcular o valor de verdade em vez de assumir
    corrige isso nos dois caminhos: no caminho de nova conclusão, o
    resultado é sempre `True` (o `_validar_fencing` logo abaixo já exige
    lease não expirada antes de chegar aqui, então o cálculo só confirma o
    que já foi validado); no caminho de reentrega, se `pedido.run` por
    acaso não estivesse terminal, `concluir_run` corretamente levantaria
    `RunLeaseInvalida` em vez de fechá-lo às escuras.

    Se `_ledger_registrar_resultado` levantar (resultado diferente do já
    selado), a função inteira propaga a exceção SEM chegar a tocar
    `pedido.run` -- mesma garantia de "nunca sobrescreve" que já vale para
    o ledger, agora também para o run."""
    reentrega_de_terminal_ja_selado = (
        pedido.status in ESTADOS_TERMINAIS
        and novo_status == pedido.status
        and pedido.ledger_entry is not None
        and pedido.ledger_entry.resultado_registrado_em is not None
    )
    if reentrega_de_terminal_ja_selado:
        ok, motivo = lease_pertence_ao_apresentante(pedido.lease, lease_token, generation)
        if not ok:
            raise LeaseInvalida(motivo)
        entrada = _ledger_registrar_resultado(pedido.ledger_entry, resultado, agora=agora)
        run_atualizado = _fechar_run_se_houver(
            pedido.run, lease_token, generation, novo_status, resultado,
            lease_ainda_valida=not lease_expirada(pedido.lease, agora=agora),
            agora=agora,
        )
        return dataclasses.replace(pedido, ledger_entry=entrada, run=run_atualizado)
    _validar_fencing(pedido, lease_token, generation, agora)
    if pedido.ledger_entry is None:
        raise ValueError(
            f"pedido '{pedido.request_id}' não tem operação aberta no ledger -- "
            "chame registrar_progresso ao menos uma vez antes de registrar um "
            "resultado observado."
        )
    if novo_status not in ESTADOS_TERMINAIS:
        raise ValueError(
            f"registrar_resultado_observado só aceita um estado terminal do "
            f"pedido como novo_status ({sorted(s.value for s in ESTADOS_TERMINAIS)}) "
            f"-- '{novo_status.value}' não é terminal e seria um beco sem saída "
            "(o ledger da operação ficaria selado para sempre, mas o pedido "
            "continuaria esperando retomar a MESMA operação)."
        )
    _transicionar_para_resultado(pedido, novo_status)
    entrada = _ledger_registrar_resultado(pedido.ledger_entry, resultado, agora=agora)
    run_atualizado = _fechar_run_se_houver(
        pedido.run, lease_token, generation, novo_status, resultado,
        lease_ainda_valida=not lease_expirada(pedido.lease, agora=agora),
        agora=agora,
    )
    return dataclasses.replace(pedido, status=novo_status, ledger_entry=entrada, run=run_atualizado)


def _fechar_run_se_houver(
    run: AgentRun | None,
    lease_token: str,
    generation: int,
    novo_status: RequestStatus,
    resultado: Any,
    lease_ainda_valida: bool,
    agora: datetime | None,
) -> AgentRun | None:
    """Chamado só de dentro de `registrar_resultado_observado`, nos dois
    caminhos (nova conclusão e reentrega idempotente) -- ver sua docstring
    para a justificativa completa de `lease_ainda_valida` (SEMPRE calculada
    pelo chamador a partir da lease real, nunca assumida) e do mapeamento
    `_REQUEST_STATUS_PARA_AGENT_RUN_STATUS`. `run is None` (sem `AgentRun`
    associado, ver docstring de `PedidoDuravel`) devolve `None` sem erro."""
    if run is None:
        return None
    status_run = _REQUEST_STATUS_PARA_AGENT_RUN_STATUS.get(novo_status)
    if status_run is None:
        raise ValueError(
            f"'{novo_status.value}' não tem mapeamento para AgentRunStatus -- "
            "só CONCLUIDO/FALHA_FINAL/CANCELADO são esperados aqui (os únicos "
            "estados terminais alcançáveis por registrar_resultado_observado)."
        )
    return _run_concluir(
        run, lease_token, generation, status_run,
        lease_ainda_valida=lease_ainda_valida, resultado=resultado, agora=agora,
    )


def pedido_esta_ativo(pedido: PedidoDuravel) -> bool:
    """`True` quando `pedido.status` ainda pode produzir efeito ou avançar
    (não é terminal -- `autonomy.requests.ESTADOS_TERMINAIS`). Não confundir
    com "tem lease válida": um pedido `AGUARDANDO_EXTERNO` está ativo mas
    pode não ter reserva nenhuma no momento."""
    return pedido.status not in ESTADOS_TERMINAIS
