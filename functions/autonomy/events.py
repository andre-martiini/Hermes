"""Envelope único de eventos (P05 do plano de autonomia,
docs/plano-hermes-autonomo-2026-09-06.md, seção "P05 — Normalizar eventos e
saúde das integrações", passos 1-2 do pacote:

1. "Definir envelope único para mensagens, agenda, tarefa, documento, SIPAC,
   transcrição, finanças e eventos de repositório já suportados."
2. "Manter fonte original e produzir evento com ID determinístico."

Lógica pura -- sem I/O, mesmo padrão incremental de `autonomy/requests.py`
(P04 sub-entrega 1/N) e `autonomy/ledger.py` (P04 sub-entrega 3/N): tipos e
regras primeiro (testável sem Firestore), wiring numa sub-entrega seguinte.
Nenhum trigger/worker existente (main.py, whatsapp_ingest.py,
email_action_linker.py) importa este módulo ainda -- eles continuam
escrevendo direto nas coleções de origem (tarefas, whatsapp_messages,
conhecimento, ...) exatamente como hoje. Este módulo não decide QUANDO um
evento é emitido nem onde é persistido (isso é o passo 3, outbox
transacional -- sub-entrega futura); só define a FORMA do envelope e como
calcular um event_id determinístico a partir de uma fonte já existente.

Passos 3-10 do pacote (outbox transacional, dedup por watermark/cursor,
supressão de alerta em replay antigo, heartbeat/cobertura por integração,
registrar_observacao_externa, reconciliação periódica) ficam para
sub-entregas seguintes -- ver `proximo_pacote` do bloco desta sub-entrega em
docs/autonomia/execucao.md.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from .ledger import hash_canonico
from .requests import _exigir_tz_aware


class CategoriaEvento(str, Enum):
    """As categorias de origem listadas no passo 1 do pacote, verbatim:
    "mensagens, agenda, tarefa, documento, SIPAC, transcrição, finanças e
    eventos de repositório já suportados"."""

    MENSAGEM = "mensagem"
    AGENDA = "agenda"
    TAREFA = "tarefa"
    DOCUMENTO = "documento"
    SIPAC = "sipac"
    TRANSCRICAO = "transcricao"
    FINANCAS = "financas"
    REPOSITORIO = "repositorio"


def calcular_event_id(
    categoria: CategoriaEvento,
    fonte_colecao: str,
    fonte_doc_id: str,
    payload_identificador: Mapping,
) -> str:
    """ID determinístico do evento -- passo 2 do pacote.

    Mesma (categoria, fonte_colecao, fonte_doc_id, conteúdo identificador)
    sempre produz o MESMO event_id, permitindo dedup por reentrega (passo 4,
    "validar origem, deduplicar...") sem exigir armazenamento externo do que
    já foi visto -- reprocessar a mesma ocorrência produz o mesmo ID, então
    um consumidor idempotente (outbox/dispatcher, sub-entrega futura) pode
    usar o próprio event_id como chave de dedup.

    `payload_identificador` é o SUBCONJUNTO dos campos da fonte que define
    "a mesma ocorrência" -- deliberadamente não o documento inteiro: campos
    que mudam sem representar uma ocorrência nova (ex.: contador de
    telemetria, timestamp de sync interno) não deveriam gerar um event_id
    novo a cada leitura -- ver passo 6 do pacote ("suprimir loops causados
    por atualização de resumo/telemetria pelo próprio agente"). Quem chama
    decide o que é identidade vs. ruído para sua fonte; este módulo não
    impõe uma regra única para todas as categorias (elas têm formas de
    payload muito diferentes -- uma mensagem de WhatsApp e uma linha de
    fatura não compartilham estrutura).

    Reusa `autonomy.ledger.hash_canonico` (mesmo hash SHA-256 de
    serialização canônica já usado para idempotência de operação em P04) em
    vez de reimplementar canonicalização -- mesma regra de "mesmo valor
    lógico produz o mesmo hash" nos dois módulos. `payload_identificador`
    precisa ser serializável em JSON (mesma exigência documentada em
    `hash_canonico`); um valor que não for levanta `TypeError` -- isso é
    responsabilidade de quem monta o payload, não deste módulo.
    """
    chave = (
        f"{categoria.value}:{fonte_colecao}:{fonte_doc_id}:"
        f"{hash_canonico(dict(payload_identificador))}"
    )
    return hashlib.sha256(chave.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class EventEnvelope:
    """Forma única de um evento normalizado -- passo 1 do pacote.

    Não substitui a fonte original: `fonte_colecao`/`fonte_doc_id` apontam de
    volta para o documento que continua sendo a fonte de verdade (passo 2,
    "manter fonte original") -- este envelope é uma PROJEÇÃO somada a ela,
    nunca uma cópia que passa a divergir do original.

    `occurred_at` (quando a ocorrência aconteceu no mundo real, segundo a
    fonte) e `ingested_at` (quando ESTE processo viu/normalizou o evento) são
    campos deliberadamente distintos (passo 5 do pacote) -- um
    replay/reprocessamento tem `ingested_at` novo mas `occurred_at`
    preservado, para que um consumidor futuro (outbox/dispatcher, sub-entrega
    seguinte) possa decidir não tratar evento antigo replayado como urgente.
    Este módulo só carrega os dois campos; a decisão de supressão por idade é
    do consumidor, ainda não implementada aqui.

    Não construa esta classe diretamente com um `event_id` calculado à mão
    -- use `montar_evento()`, que calcula o hash e monta o envelope numa
    única chamada consistente. `__post_init__` recalcula o hash esperado e
    falha fechado se `event_id` não bater, para que um bug de wiring futuro
    (sub-entrega que ligar isto a um trigger real) quebre alto e cedo, não
    silenciosamente com um event_id que não é realmente determinístico.
    """

    event_id: str
    categoria: CategoriaEvento
    fonte_colecao: str
    fonte_doc_id: str
    occurred_at: datetime
    ingested_at: datetime
    payload_identificador: Mapping = field(default_factory=dict)
    metadata: Mapping = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not str(self.fonte_colecao).strip():
            raise ValueError("fonte_colecao não pode ser vazio.")
        if not str(self.fonte_doc_id).strip():
            raise ValueError("fonte_doc_id não pode ser vazio.")
        _exigir_tz_aware(self.occurred_at, "occurred_at")
        _exigir_tz_aware(self.ingested_at, "ingested_at")
        event_id_esperado = calcular_event_id(
            self.categoria, self.fonte_colecao, self.fonte_doc_id, self.payload_identificador
        )
        if self.event_id != event_id_esperado:
            raise ValueError(
                "event_id não bate com o hash determinístico de "
                "(categoria, fonte_colecao, fonte_doc_id, payload_identificador) -- "
                "use montar_evento() para construir um EventEnvelope consistente "
                "em vez de calcular event_id manualmente."
            )


def montar_evento(
    categoria: CategoriaEvento,
    fonte_colecao: str,
    fonte_doc_id: str,
    payload_identificador: Mapping,
    occurred_at: datetime,
    ingested_at: datetime,
    metadata: Mapping | None = None,
) -> EventEnvelope:
    """Forma preferida de construir um `EventEnvelope`: calcula o event_id e
    monta o envelope numa única chamada, para que quem chama nunca precise
    (e nunca consiga, sem duplicar `calcular_event_id`) produzir um
    event_id inconsistente com seus próprios campos. `EventEnvelope.__post_init__`
    já falha fechado nesse caso; esta função evita o erro na origem."""
    event_id = calcular_event_id(categoria, fonte_colecao, fonte_doc_id, payload_identificador)
    return EventEnvelope(
        event_id=event_id,
        categoria=categoria,
        fonte_colecao=fonte_colecao,
        fonte_doc_id=fonte_doc_id,
        occurred_at=occurred_at,
        ingested_at=ingested_at,
        payload_identificador=dict(payload_identificador),
        metadata=dict(metadata or {}),
    )
