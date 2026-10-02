"""Outbox de eventos (P05 do plano de autonomia,
docs/plano-hermes-autonomo-2026-09-06.md, seção "P05 — Normalizar eventos e
saúde das integrações", passo 3 do pacote: "Quando escrita e evento forem
internos, persistir ambos na mesma transação ou usar outbox de eventos com
dispatcher reconciliável.").

Lógica pura -- sem I/O, mesmo padrão incremental de `autonomy/requests.py`
(P04 sub-entrega 1/N), `autonomy/ledger.py` (P04 sub-entrega 3/N) e
`autonomy/events.py` (P05 sub-entrega 1/N): tipos e regras primeiro
(testável sem Firestore), wiring numa sub-entrega seguinte. Nenhum
trigger/worker existente importa este módulo ainda -- nada aqui decide QUE
evento é emitido (isso é `autonomy.events`) nem QUANDO/ONDE a linha do
outbox é persistida (transação Firestore vs. dispatcher assíncrono -- isso é
a wiring futura). Este módulo só define a FORMA de uma entrada de outbox e
as transições de estado puras entre "pendente de envio" e "terminal", dado
um relógio (`agora`) e um resultado de tentativa (sucesso/falha) que o
dispatcher real vai produzir.

`OutboxEntry.entry_id` reusa `EventEnvelope.event_id` (mesmo hash
determinístico de `autonomy.events.calcular_event_id`) como chave -- uma
linha de outbox representa exatamente UM evento já normalizado, então a
mesma garantia de dedup por reentrega do evento (ver `autonomy.events`) se
propaga para o outbox sem precisar de um segundo esquema de ID: escrever a
mesma ocorrência duas vezes produz o mesmo `entry_id`, e cabe à wiring
futura (Firestore `create` que falha se o doc já existir, ou `set` com
merge condicional) decidir como tratar a colisão -- este módulo não impõe
isso porque não tem transação para proteger.

O backoff entre tentativas reusa `autonomy.requests.calcular_backoff_segundos`
(mesmos patamares de 1/5/20 minutos com jitter e o mesmo
`DEFAULT_MAX_TENTATIVAS`, seção 4.5) em vez de reimplementar uma política de
retentativa própria para o outbox -- o plano não pede uma política
diferente para eventos, e duas políticas de backoff divergentes no mesmo
código seriam uma inconsistência sem motivo.

Passos 4, 6 e 9 do pacote (dedup por watermark/cursor de webhook, supressão
de loop por atualização do próprio agente, `registrar_observacao_externa`)
ficam fora deste módulo -- o passo 9 já foi implementado em módulo próprio
(`tools/registrar_observacao_externa.py`, P05 sub-entrega 16/N), sem relação
com o outbox. Passos 1-2 (envelope) e 5/7/8 (occurred_at vs ingested_at,
heartbeat/cobertura) também são de `autonomy.events`/`autonomy.integrations`,
não deste módulo.

A RECONCILIAÇÃO (passo 10 -- encontrar entradas presas porque um dispatcher
caiu no meio de uma tentativa, sem nunca chamar `registrar_sucesso` nem
`registrar_falha`) É modelada aqui desde a P05 sub-entrega 17/N: um terceiro
estado não-terminal, `EM_PROCESSAMENTO`, junto de uma `autonomy.requests.Lease`
própria da entrada (`OutboxEntry.lease`) -- mesma reutilização de `Lease`
que `autonomy.execution.PedidoDuravel` já faz para pedidos duráveis (P04),
em vez de inventar um segundo mecanismo de posse só para o outbox. Um
dispatcher que queira proteção contra crash no meio de uma tentativa chama
`iniciar_despacho()` antes de agir (em vez de ir direto para
`registrar_sucesso`/`registrar_falha`, que continuam aceitando uma entrada
ainda `PENDENTE` diretamente -- ver suas docstrings) e, se cair sem concluir,
uma varredura periódica futura (wiring real, fora deste módulo -- mesmo
padrão de `autonomy.sweep.varrer_lease_vencida` para pedidos) chama
`varrer_lease_vencida_outbox()` sobre as entradas `EM_PROCESSAMENTO` com
lease vencida para devolvê-las a `PENDENTE` (com backoff) ou desistir em
`FALHA_FINAL` com uma `DiagnosticoOutbox`, reaproveitando os mesmos
`DEFAULT_MAX_TENTATIVAS`/`calcular_backoff_segundos` de `registrar_falha`
para não ter dois limites de tentativas divergentes para a mesma entrada.
A função que varre o armazenamento de verdade em busca de entradas
`EM_PROCESSAMENTO` com lease vencida (consulta Firestore por
`estado`+`lease.expires_at`, mesmo padrão de `autonomy.sweep`) fica para a
sub-entrega de wiring real -- este módulo só decide o desfecho de UMA
entrada já identificada como presa, dado um relógio.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import Enum

from .events import EventEnvelope
from .requests import (
    DEFAULT_LEASE_SEGUNDOS,
    DEFAULT_MAX_TENTATIVAS,
    Lease,
    _exigir_tz_aware,
    calcular_backoff_segundos,
    lease_expirada,
    nova_lease,
)


class EstadoOutbox(str, Enum):
    """Estados de uma entrada de outbox. Só dois são terminais
    (`ENVIADO`/`FALHA_FINAL`) -- ver `_ESTADOS_TERMINAIS`. `EM_PROCESSAMENTO`
    é opcional e intermediário (P05 sub-entrega 17/N, passo 10 do pacote):
    um dispatcher que queira proteção contra crash no meio de uma tentativa
    passa por ele via `iniciar_despacho()`; um dispatcher simples pode
    continuar indo direto de `PENDENTE` para `registrar_sucesso`/
    `registrar_falha`, sem usar este estado -- ambos os caminhos continuam
    válidos."""

    PENDENTE = "pendente"
    EM_PROCESSAMENTO = "em_processamento"
    ENVIADO = "enviado"
    FALHA_FINAL = "falha_final"


#: Nenhuma transição parte de um estado terminal -- `registrar_sucesso` e
#: `registrar_falha` recusam operar sobre uma entrada já terminal (ver
#: `EstadoOutboxTerminal`), mesmo padrão de "estado terminal não regride nem
#: se sobrescreve" já usado em `autonomy.requests` (`RequestStatus`) e
#: implícito no `ConflitoIdempotencia` de `autonomy.ledger`.
_ESTADOS_TERMINAIS = frozenset({EstadoOutbox.ENVIADO, EstadoOutbox.FALHA_FINAL})


class EstadoOutboxTerminal(Exception):
    """Tentativa de transicionar uma entrada que já está num estado
    terminal (`ENVIADO`/`FALHA_FINAL`). Quem pega esta exceção tem um bug de
    wiring (dispatcher processando a mesma entrada duas vezes depois dela já
    ter concluído) -- a entrada existente não é alterada."""

    def __init__(self, entry_id: str, estado_atual: EstadoOutbox) -> None:
        self.entry_id = entry_id
        self.estado_atual = estado_atual
        super().__init__(
            f"entrada de outbox '{entry_id}' já está em estado terminal "
            f"'{estado_atual.value}' -- não pode transicionar de novo."
        )


@dataclass(frozen=True)
class OutboxEntry:
    """Uma linha de outbox: um `EventEnvelope` mais o estado de despacho.

    Não construa diretamente com um `entry_id` diferente de
    `evento.event_id` -- use `criar_entrada()`. `__post_init__` falha
    fechado se os dois não baterem, mesmo padrão de `EventEnvelope`
    (`autonomy.events`) para `event_id`: um bug de wiring futuro que tentar
    associar uma entrada de outbox ao evento errado quebra alto e cedo.
    Pela mesma razão, `__post_init__` também recusa um `estado` que não seja
    um membro de `EstadoOutbox` e um `disponivel_em` anterior a `criado_em`
    -- achados reais de revisão adversarial independente (P05 sub-entrega
    5/N): um `estado` fora do enum nunca aparece em `_ESTADOS_TERMINAIS`,
    então uma entrada corrompida (ex.: por uma futura desserialização do
    Firestore com um valor com erro de digitação) seria tratada como
    não-terminal para sempre, contornando silenciosamente o travamento que
    `EstadoOutboxTerminal` existe para garantir.

    `disponivel_em` é "não tentar despachar antes deste instante" -- para
    uma entrada nova (`criar_entrada`) é igual a `criado_em` (elegível
    imediatamente); depois de uma falha (`registrar_falha`), avança pelo
    backoff calculado. `pronta_para_despachar` é quem interpreta este campo
    junto do estado.

    `lease` (P05 sub-entrega 17/N, passo 10 do pacote) só é preenchida por
    `iniciar_despacho()`, ao transicionar para `EM_PROCESSAMENTO`. Não é
    limpa ao sair desse estado (nem por `registrar_sucesso`/
    `registrar_falha`, nem por `varrer_lease_vencida_outbox` ao devolver a
    entrada para `PENDENTE`) -- mesmo padrão de
    `autonomy.execution.PedidoDuravel.lease`, que também retém a última
    lease emitida depois que ela expira ou a entrada volta a um estado
    reivindicável, para que a PRÓXIMA chamada a `iniciar_despacho()` leia
    `lease.generation` e emita a geração seguinte (fencing contra um
    dispatcher antigo que ainda tente concluir com a geração anterior)."""

    entry_id: str
    evento: EventEnvelope
    estado: EstadoOutbox
    tentativas: int
    criado_em: datetime
    disponivel_em: datetime
    ultima_tentativa_em: datetime | None = None
    ultimo_erro: str | None = None
    lease: Lease | None = None

    def __post_init__(self) -> None:
        if self.entry_id != self.evento.event_id:
            raise ValueError(
                f"entry_id ({self.entry_id!r}) não bate com evento.event_id "
                f"({self.evento.event_id!r}) -- use criar_entrada() em vez de "
                "construir OutboxEntry diretamente."
            )
        if not isinstance(self.estado, EstadoOutbox):
            raise ValueError(
                f"estado deve ser um EstadoOutbox; recebido: {self.estado!r} -- achado "
                "real de revisão adversarial independente (P05 sub-entrega 5/N): sem "
                "esta checagem, um `estado` construído à mão fora do enum (ex.: uma "
                "string com erro de digitação vinda de uma futura desserialização do "
                "Firestore) nunca aparece em `_ESTADOS_TERMINAIS`, então "
                "`registrar_sucesso`/`registrar_falha` tratam a entrada como não-terminal "
                "e continuam avançando uma entrada que já deveria estar travada -- "
                "exatamente o cenário que `EstadoOutboxTerminal` existe para impedir."
            )
        if self.tentativas < 0:
            raise ValueError("tentativas não pode ser negativo.")
        _exigir_tz_aware(self.criado_em, "criado_em")
        _exigir_tz_aware(self.disponivel_em, "disponivel_em")
        if self.disponivel_em < self.criado_em:
            raise ValueError(
                f"disponivel_em ({self.disponivel_em!r}) não pode ser anterior a "
                f"criado_em ({self.criado_em!r}) -- achado real de revisão adversarial "
                "independente (P05 sub-entrega 5/N): sem esta checagem, uma entrada "
                "construída à mão (fora de criar_entrada()/registrar_falha()) podia "
                "afirmar que estava disponível para despacho ANTES de ter sido criada."
            )
        if self.ultima_tentativa_em is not None:
            _exigir_tz_aware(self.ultima_tentativa_em, "ultima_tentativa_em")
        if self.estado == EstadoOutbox.EM_PROCESSAMENTO and self.lease is None:
            raise ValueError(
                "estado 'em_processamento' exige lease -- use iniciar_despacho() em vez "
                "de construir OutboxEntry diretamente."
            )


def criar_entrada(evento: EventEnvelope, agora: datetime) -> OutboxEntry:
    """Cria uma entrada nova em `PENDENTE`, elegível para despacho
    imediato (`disponivel_em == agora`), zero tentativas."""
    _exigir_tz_aware(agora, "agora")
    return OutboxEntry(
        entry_id=evento.event_id,
        evento=evento,
        estado=EstadoOutbox.PENDENTE,
        tentativas=0,
        criado_em=agora,
        disponivel_em=agora,
    )


def pronta_para_despachar(entrada: OutboxEntry, agora: datetime) -> bool:
    """Uma entrada é elegível para a próxima tentativa de despacho quando
    está `PENDENTE` e `agora` já alcançou `disponivel_em` -- não quando é
    igual, mas também não quando já passou; qualquer um dos dois serve
    ("já é hora ou passou da hora"), então a comparação é `>=`, não `==`.
    Uma entrada terminal nunca é elegível, mesmo que `disponivel_em` já
    tenha passado."""
    _exigir_tz_aware(agora, "agora")
    return entrada.estado == EstadoOutbox.PENDENTE and agora >= entrada.disponivel_em


def registrar_sucesso(entrada: OutboxEntry, agora: datetime) -> OutboxEntry:
    """Despacho confirmado -- transiciona para `ENVIADO` (terminal).
    `disponivel_em` congela no valor anterior (não há mais próxima
    tentativa a agendar). Aceita a entrada tanto em `PENDENTE` quanto em
    `EM_PROCESSAMENTO` -- um dispatcher que não usa `iniciar_despacho()`
    continua podendo chamar esta função direto a partir de `PENDENTE`, sem
    nenhuma lease envolvida (ver docstring de `EstadoOutbox.EM_PROCESSAMENTO`).
    `entrada.lease`, se presente, é preservada sem alteração (ver docstring
    de `OutboxEntry.lease` -- não há mais próxima reivindicação a fencing
    depois de um estado terminal)."""
    if entrada.estado in _ESTADOS_TERMINAIS:
        raise EstadoOutboxTerminal(entrada.entry_id, entrada.estado)
    _exigir_tz_aware(agora, "agora")
    return replace(
        entrada,
        estado=EstadoOutbox.ENVIADO,
        ultima_tentativa_em=agora,
    )


def registrar_falha(
    entrada: OutboxEntry,
    agora: datetime,
    erro: str,
    max_tentativas: int = DEFAULT_MAX_TENTATIVAS,
    rng: object | None = None,
) -> OutboxEntry:
    """Tentativa de despacho falhou. Incrementa `tentativas`; se o total
    ULTRAPASSAR `max_tentativas`, transiciona para `FALHA_FINAL` (terminal --
    esgotou as retentativas automáticas, precisa de intervenção/reconciliação
    futura). Caso contrário permanece `PENDENTE` com `disponivel_em`
    avançado pelo backoff de `autonomy.requests.calcular_backoff_segundos`
    para a nova contagem de tentativas.

    O corte é `novas_tentativas > max_tentativas` (estritamente maior), NÃO
    `>=` -- achado real de revisão automática do Codex (P2) na PR desta
    sub-entrega: com `max_tentativas` padrão de 3 (seção 4.5, mesmo
    `DEFAULT_MAX_TENTATIVAS` de `autonomy.requests`), `>=` desistia na 3a
    falha sem nunca conceder o patamar de 20 minutos de
    `calcular_backoff_segundos` -- usando só 2 dos 3 patamares documentados
    (1/5/20 min). Mesmo achado, mesma correção e mesmo raciocínio já
    aplicados a `autonomy.sweep` (achado do Codex na PR #344) para o mesmo
    tipo de corte -- ver a docstring de `autonomy.sweep.tratar_lease_vencida`
    para a explicação completa. Com `>`, as `max_tentativas` retentativas
    automáticas são todas concedidas antes de desistir na falha seguinte (a
    `max_tentativas + 1`-ésima) -- então `max_tentativas=1` NÃO significa
    "falha imediatamente na 1a tentativa": significa "conceda 1 retentativa
    (com backoff), desista na 2a falha".

    `max_tentativas` e `rng` existem para o mesmo motivo de
    `calcular_backoff_segundos`: permitir teste determinístico (RNG com seed
    fixa) e um limite configurável sem editar este módulo -- o padrão reusa
    `DEFAULT_MAX_TENTATIVAS` de `autonomy.requests` (seção 4.5) para não
    introduzir uma segunda política de "quantas tentativas automáticas" só
    para o outbox.

    Aceita a entrada tanto em `PENDENTE` quanto em `EM_PROCESSAMENTO` --
    mesmo motivo de `registrar_sucesso` (ver sua docstring). `entrada.lease`,
    se presente, é preservada sem alteração mesmo que o resultado seja
    `PENDENTE` de novo (ver docstring de `OutboxEntry.lease`): a próxima
    chamada a `iniciar_despacho()` lê `lease.generation` dali para emitir a
    geração seguinte."""
    if entrada.estado in _ESTADOS_TERMINAIS:
        raise EstadoOutboxTerminal(entrada.entry_id, entrada.estado)
    _exigir_tz_aware(agora, "agora")
    if max_tentativas < 1:
        raise ValueError("max_tentativas deve ser >= 1.")

    novas_tentativas = entrada.tentativas + 1
    if novas_tentativas > max_tentativas:
        return replace(
            entrada,
            estado=EstadoOutbox.FALHA_FINAL,
            tentativas=novas_tentativas,
            ultima_tentativa_em=agora,
            ultimo_erro=erro,
        )

    backoff_segundos = calcular_backoff_segundos(novas_tentativas, rng=rng)
    return replace(
        entrada,
        estado=EstadoOutbox.PENDENTE,
        tentativas=novas_tentativas,
        disponivel_em=agora + timedelta(seconds=backoff_segundos),
        ultima_tentativa_em=agora,
        ultimo_erro=erro,
    )


# ---------------------------------------------------------------------------
# Reconciliação (passo 10 do pacote) -- P05 sub-entrega 17/N
# ---------------------------------------------------------------------------


def iniciar_despacho(
    entrada: OutboxEntry,
    executor_id: str,
    agora: datetime,
    duracao_segundos: float = DEFAULT_LEASE_SEGUNDOS,
) -> OutboxEntry:
    """Um dispatcher que quer proteção contra crash no meio de uma tentativa
    chama isto ANTES de agir, em vez de ir direto para
    `registrar_sucesso`/`registrar_falha` -- transiciona `PENDENTE ->
    EM_PROCESSAMENTO` e emite uma `Lease` nova (`autonomy.requests.nova_lease`,
    mesma reutilização que `autonomy.execution.assumir_pedido` já faz para
    pedidos duráveis, em vez de um segundo mecanismo de posse só para o
    outbox). Se o dispatcher cair sem chamar `registrar_sucesso`/
    `registrar_falha`, a entrada fica presa em `EM_PROCESSAMENTO` até uma
    varredura futura (`varrer_lease_vencida_outbox`) encontrar a lease
    vencida.

    Exige `pronta_para_despachar(entrada, agora)` -- mesma checagem de
    "está `PENDENTE` e já chegou a hora" que qualquer dispatcher precisa
    fazer antes de tentar despachar, só que aqui é reforçada em vez de
    deixada implícita. Levanta `ValueError` (não `EstadoOutboxTerminal`) se
    a entrada não estiver pronta -- `EstadoOutboxTerminal` é especificamente
    para "já terminal", e aqui o motivo de recusa também inclui "ainda não
    chegou a hora" ou "já está em processamento por outro dispatcher", que
    não são a mesma coisa.

    Defesa extra, mesmo padrão de `autonomy.execution.assumir_pedido`: se
    `entrada.lease` já existir (reassumindo depois de uma geração anterior)
    e ainda não tiver expirado, recusa -- um dispatcher não deveria estar
    livre para despachar uma entrada cuja lease anterior pode ainda estar
    sendo honrada por outro executor (isso só pode acontecer se o estado
    foi manipulado fora de `iniciar_despacho`/`varrer_lease_vencida_outbox`,
    já que estas duas funções são as únicas que escrevem `lease`, mas a
    checagem fica aqui por segurança em profundidade, mesmo raciocínio de
    `assumir_pedido`)."""
    if not pronta_para_despachar(entrada, agora):
        raise ValueError(
            f"entrada de outbox '{entrada.entry_id}' não está pronta para despacho "
            f"(estado atual: '{entrada.estado.value}', disponível em "
            f"{entrada.disponivel_em.isoformat()}) -- iniciar_despacho() exige "
            "pronta_para_despachar(entrada, agora) == True."
        )
    if entrada.lease is not None and not lease_expirada(entrada.lease, agora=agora):
        raise ValueError(
            f"entrada de outbox '{entrada.entry_id}' já tem lease de "
            f"'{entrada.lease.executor_id}' ainda válida (expira em "
            f"{entrada.lease.expires_at.isoformat()}) -- não é possível iniciar um "
            "despacho novo."
        )
    generation_anterior = entrada.lease.generation if entrada.lease is not None else 0
    lease_nova = nova_lease(
        executor_id, generation_anterior, agora=agora, duracao_segundos=duracao_segundos
    )
    return replace(entrada, estado=EstadoOutbox.EM_PROCESSAMENTO, lease=lease_nova)


@dataclass(frozen=True)
class DiagnosticoOutbox:
    """Uma entrada da "fila de diagnóstico" do outbox -- entrada que esgotou
    tentativas automáticas (lease vencida repetidamente em
    `EM_PROCESSAMENTO`) e precisa de atenção não-automática. Lógica pura:
    só o registro; persistência/alerta reais ficam para o wiring. Mesmo
    papel de `autonomy.sweep.DiagnosticoPedido`, mas para entradas de
    outbox em vez de pedidos duráveis -- os dois tipos não são unificados
    porque representam entidades de domínio diferentes (evento despachado
    vs. pedido executado), sem campo em comum além do padrão de forma."""

    entry_id: str
    motivo: str
    estado_anterior: EstadoOutbox
    tentativas: int
    registrado_em: datetime

    def __post_init__(self) -> None:
        _exigir_tz_aware(self.registrado_em, "registrado_em")
        if self.tentativas < 0:
            raise ValueError("tentativas não pode ser negativa.")


@dataclass(frozen=True)
class ResultadoSweepOutbox:
    """Devolvido por `varrer_lease_vencida_outbox`: a `OutboxEntry`
    atualizada e, quando a entrada esgotou as tentativas automáticas, o
    `DiagnosticoOutbox` correspondente (`None` quando uma nova tentativa foi
    agendada em vez de desistir) -- mesma forma de
    `autonomy.sweep.ResultadoSweepLeaseVencida`."""

    entrada: OutboxEntry
    diagnostico: DiagnosticoOutbox | None


def varrer_lease_vencida_outbox(
    entrada: OutboxEntry,
    agora: datetime,
    max_tentativas: int = DEFAULT_MAX_TENTATIVAS,
    rng: object | None = None,
) -> ResultadoSweepOutbox:
    """Decide o desfecho de UMA entrada de outbox cuja lease já venceu sem
    o dispatcher ter chamado `registrar_sucesso`/`registrar_falha` --
    "dispatcher morto" (mesmo cenário de `autonomy.sweep.varrer_lease_vencida`
    para pedidos duráveis, passo 10 do pacote P05 em vez do passo 7 do
    pacote P04).

    Só aceita `entrada.estado == EM_PROCESSAMENTO` e exige `entrada.lease`
    presente e de fato vencida (`autonomy.requests.lease_expirada`) --
    levanta `ValueError` fora disso, mesmo estilo defensivo do resto do
    módulo (nunca assume, sempre confere antes de agir). A função que
    encontra entradas assim no armazenamento de verdade (consulta Firestore
    por `estado`+`lease.expires_at`) fica para o wiring real -- esta função
    só decide UMA entrada já identificada.

    `tentativas_novas = entrada.tentativas + 1` (reusa o mesmo contador de
    `registrar_falha` -- "lease venceu em processamento" conta como uma
    tentativa falha, mesmo raciocínio de `autonomy.sweep.varrer_lease_vencida`
    contar uma lease vencida de pedido como tentativa). Se
    `tentativas_novas > max_tentativas` (estritamente maior, NÃO `>=` --
    mesma correção de off-by-one de `registrar_falha`/`autonomy.sweep`,
    para conceder todos os `max_tentativas` patamares de backoff antes de
    desistir): transiciona para `FALHA_FINAL` e devolve um
    `DiagnosticoOutbox`. Caso contrário: volta para `PENDENTE` com
    `disponivel_em` avançado pelo mesmo
    `autonomy.requests.calcular_backoff_segundos` de `registrar_falha` (não
    duas políticas de backoff divergentes para a mesma entrada, dependendo
    de ter sido uma falha reportada ou uma lease vencida).

    `entrada.lease` É PRESERVADA sem alteração em ambos os desfechos (ver
    docstring de `OutboxEntry.lease`) -- mesmo quando o resultado é
    `PENDENTE`, para que a geração monotônica continue protegendo contra um
    dispatcher antigo que ainda tente concluir com a lease vencida (fencing
    -- `iniciar_despacho()` da próxima vez lê `lease.generation` dali)."""
    if entrada.estado != EstadoOutbox.EM_PROCESSAMENTO:
        raise ValueError(
            f"entrada de outbox '{entrada.entry_id}' está em '{entrada.estado.value}', "
            "não 'em_processamento' -- nada para varrer."
        )
    if entrada.lease is None:
        raise ValueError(f"entrada de outbox '{entrada.entry_id}' não tem lease -- nada para varrer.")
    _exigir_tz_aware(agora, "agora")
    if not lease_expirada(entrada.lease, agora=agora):
        raise ValueError(
            f"entrada de outbox '{entrada.entry_id}' tem lease ainda válida (expira em "
            f"{entrada.lease.expires_at.isoformat()}) -- não é um caso de sweep."
        )
    if max_tentativas < 1:
        raise ValueError("max_tentativas deve ser >= 1.")

    tentativas_novas = entrada.tentativas + 1
    if tentativas_novas > max_tentativas:
        entrada_nova = replace(
            entrada,
            estado=EstadoOutbox.FALHA_FINAL,
            tentativas=tentativas_novas,
            ultima_tentativa_em=agora,
            ultimo_erro=(
                f"lease vencida em 'em_processamento' após {tentativas_novas} "
                f"tentativa(s) (limite {max_tentativas}) -- sem nova retentativa, "
                "requer atenção manual."
            ),
        )
        diagnostico = DiagnosticoOutbox(
            entry_id=entrada.entry_id,
            motivo=(
                f"lease vencida em 'em_processamento' por {tentativas_novas} vez(es) "
                f"(limite {max_tentativas}) -- possível dispatcher que trava/cai no "
                "meio da tentativa; entrada marcada falha_final, requer atenção manual."
            ),
            estado_anterior=entrada.estado,
            tentativas=tentativas_novas,
            registrado_em=agora,
        )
        return ResultadoSweepOutbox(entrada=entrada_nova, diagnostico=diagnostico)

    backoff_segundos = calcular_backoff_segundos(tentativas_novas, rng=rng)
    entrada_nova = replace(
        entrada,
        estado=EstadoOutbox.PENDENTE,
        tentativas=tentativas_novas,
        disponivel_em=agora + timedelta(seconds=backoff_segundos),
        ultima_tentativa_em=agora,
        ultimo_erro=(
            f"lease vencida em 'em_processamento' ({tentativas_novas}a tentativa) -- "
            "devolvida para nova tentativa."
        ),
    )
    return ResultadoSweepOutbox(entrada=entrada_nova, diagnostico=None)

