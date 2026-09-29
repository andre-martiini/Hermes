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

Passos 4-10 do pacote (dedup por watermark/cursor de webhook, distinguir
occurred_at de ingested_at para suprimir alerta em replay antigo -- já
coberto por `autonomy.events` --, supressão de loop por atualização do
próprio agente, heartbeat/cobertura por integração -- já coberto por
`autonomy.integrations`/`integrations_sync` --, `registrar_observacao_externa`,
reconciliação periódica) ficam fora deste módulo. Em particular, a
RECONCILIAÇÃO (passo 10 -- encontrar entradas presas porque um dispatcher
caiu no meio de uma tentativa, sem nunca chamar `registrar_sucesso` nem
`registrar_falha`) não é modelada aqui: este módulo só tem os estados
"pendente" e terminal, sem um estado intermediário "em processamento" com
lease própria -- adicionar isso é decisão de uma sub-entrega futura dedicada
à wiring real (que também decide se reusa `autonomy.requests.Lease` para o
dispatcher tomar posse de um lote de entradas, ou modela um mecanismo
próprio mais simples para o outbox).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from enum import Enum

from .events import EventEnvelope
from .requests import DEFAULT_MAX_TENTATIVAS, _exigir_tz_aware, calcular_backoff_segundos


class EstadoOutbox(str, Enum):
    """Estados de uma entrada de outbox. Só dois são terminais
    (`ENVIADO`/`FALHA_FINAL`) -- ver `_ESTADOS_TERMINAIS`."""

    PENDENTE = "pendente"
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
    junto do estado."""

    entry_id: str
    evento: EventEnvelope
    estado: EstadoOutbox
    tentativas: int
    criado_em: datetime
    disponivel_em: datetime
    ultima_tentativa_em: datetime | None = None
    ultimo_erro: str | None = None

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
    tentativa a agendar)."""
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
    alcançar `max_tentativas`, transiciona para `FALHA_FINAL` (terminal --
    esgotou as retentativas automáticas, precisa de intervenção/reconciliação
    futura). Caso contrário permanece `PENDENTE` com `disponivel_em`
    avançado pelo backoff de `autonomy.requests.calcular_backoff_segundos`
    para a nova contagem de tentativas.

    `max_tentativas` e `rng` existem para o mesmo motivo de
    `calcular_backoff_segundos`: permitir teste determinístico (RNG com seed
    fixa) e um limite configurável sem editar este módulo -- o padrão reusa
    `DEFAULT_MAX_TENTATIVAS` de `autonomy.requests` (seção 4.5) para não
    introduzir uma segunda política de "quantas tentativas automáticas" só
    para o outbox."""
    if entrada.estado in _ESTADOS_TERMINAIS:
        raise EstadoOutboxTerminal(entrada.entry_id, entrada.estado)
    _exigir_tz_aware(agora, "agora")
    if max_tentativas < 1:
        raise ValueError("max_tentativas deve ser >= 1.")

    novas_tentativas = entrada.tentativas + 1
    if novas_tentativas >= max_tentativas:
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

