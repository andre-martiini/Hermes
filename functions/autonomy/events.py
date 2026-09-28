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

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from .ledger import _snapshot_json, hash_canonico
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
    payload_identificador: Mapping[str, Any],
    occurred_at: datetime,
) -> str:
    """ID determinístico do evento -- passo 2 do pacote.

    Mesma (categoria, fonte_colecao, fonte_doc_id, conteúdo identificador,
    occurred_at) sempre produz o MESMO event_id, permitindo dedup por
    reentrega (passo 4, "validar origem, deduplicar...") sem exigir
    armazenamento externo do que já foi visto -- reprocessar a mesma
    ocorrência produz o mesmo ID, então um consumidor idempotente
    (outbox/dispatcher, sub-entrega futura) pode usar o próprio event_id
    como chave de dedup.

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

    `occurred_at` PARTICIPA do hash -- achado REAL de revisão automática do
    Codex (P2) na PR #373: uma fonte MUTÁVEL que volta a um valor já visto
    antes (ex.: uma tarefa que retorna a um status anterior) produz o MESMO
    `payload_identificador` das duas vezes; sem `occurred_at` no hash, as
    duas ocorrências -- genuinamente distintas no mundo real -- colidiriam
    no mesmo event_id, e um consumidor futuro de dedup por event_id (passo
    4, ainda não implementado) descartaria silenciosamente a ocorrência mais
    recente como se fosse reentrega da mais antiga. Incluir `occurred_at`
    resolve isso SEM enfraquecer a garantia de dedup por reentrega: uma
    reentrega de verdade (mesmo webhook reentregue, mesmo trigger reexecutado
    sobre o mesmo evento de origem) preserva o mesmo `occurred_at` -- é
    "quando a ocorrência aconteceu no mundo real, segundo a fonte"
    (`EventEnvelope.occurred_at`), não quando ESTE processo a viu, então não
    varia entre reentregas do MESMO evento, só entre ocorrências
    genuinamente diferentes. Isto não elimina por completo o caso
    degenerado de duas ocorrências coincidindo em categoria+fonte+payload+
    occurred_at (ex.: fonte com granularidade de timestamp grosseira demais
    para distinguir duas mudanças reais no mesmo instante) -- mas isso é
    responsabilidade de qualidade de dado de quem chama (mesma classe de
    responsabilidade já documentada para `payload_identificador`), não algo
    que este módulo possa resolver sem um token de versão/sequência que a
    fonte não necessariamente fornece.

    Reusa `autonomy.ledger.hash_canonico` (mesmo hash SHA-256 de
    serialização canônica já usado para idempotência de operação em P04) em
    vez de reimplementar canonicalização -- mesma regra de "mesmo valor
    lógico produz o mesmo hash" nos dois módulos. Os cinco componentes
    (categoria, fonte_colecao, fonte_doc_id, payload_identificador,
    occurred_at) são passados como campos NOMEADOS de um único dict a
    `hash_canonico`, nunca concatenados como string com separador --
    achado real de revisão adversarial independente (1a rodada, P05
    sub-entrega 1/N): concatenar com ":" (`f"{fonte_colecao}:{fonte_doc_id}"`)
    faz `fonte_colecao` conter um ":" colidir com `fonte_doc_id` vizinho
    (ex.: `("whatsapp", "messages:msg-1")` e `("whatsapp:messages", "msg-1")`
    produziam o MESMO event_id) -- plausível na prática, já que várias das
    categorias do passo 1 usam identificadores com ":" (JID do WhatsApp,
    referência de processo SIPAC, `owner/repo:branch`). Delegar a
    serialização inteira (incluindo o aninhamento de cada campo em sua
    própria chave JSON) a `hash_canonico` evita esse tipo de colisão de
    delimitador -- é a mesma razão pela qual `hash_canonico` já serializa
    para JSON em vez de concatenar valores. `occurred_at` entra como
    `.astimezone(timezone.utc).isoformat()` (string, sempre normalizado
    para UTC antes de serializar) -- achado real de uma rodada de revisão
    adversarial sobre a correção do achado do Codex (P05 sub-entrega 1/N):
    `datetime.isoformat()` cru preserva o OFFSET original (`+02:00`,
    `+00:00`, etc.), então dois instantes IGUAIS no mundo real
    (`datetime(...,tzinfo=timezone(timedelta(hours=2))) ==
    datetime(...,tzinfo=timezone.utc)` quando representam o mesmo instante
    -- `==` em `datetime` compara o instante absoluto, não o offset)
    produziam strings DIFERENTES (`"...+02:00"` vs `"...+00:00"`) e,
    portanto, hashes diferentes -- uma fonte que às vezes serializa
    `occurred_at` num offset e às vezes noutro (ex.: horário local vs. UTC)
    quebraria silenciosamente a garantia de dedup por reentrega descrita
    acima, mesmo sendo a MESMA ocorrência. Normalizar para UTC antes de
    serializar fecha essa brecha: mesmo instante, qualquer offset de
    entrada, sempre a mesma string.

    `payload_identificador` precisa ser serializável em JSON (mesma
    exigência documentada em `hash_canonico`); um valor que não for levanta
    `TypeError` -- isso é responsabilidade de quem monta o payload, não
    deste módulo. `occurred_at` precisa ser timezone-aware (mesma exigência
    de `EventEnvelope`, aqui verificada via `_exigir_tz_aware` antes do
    hash, já que esta função pode ser chamada isoladamente sem nunca passar
    por `EventEnvelope.__post_init__`).
    """
    _exigir_tz_aware(occurred_at, "occurred_at")
    return hash_canonico(
        {
            "categoria": categoria.value,
            "fonte_colecao": fonte_colecao,
            "fonte_doc_id": fonte_doc_id,
            "payload_identificador": dict(payload_identificador),
            "occurred_at": occurred_at.astimezone(timezone.utc).isoformat(),
        }
    )


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
    Além disso `occurred_at` (não `ingested_at`) participa do cálculo de
    `event_id` -- ver `calcular_event_id` para o porquê (achado real de
    revisão automática do Codex, P2, PR #373: sem isso, uma fonte mutável
    que revisita um valor já visto -- ex.: tarefa que volta a um status
    anterior -- colidiria com a ocorrência antiga no mesmo event_id).

    Não construa esta classe diretamente com um `event_id` calculado à mão
    -- use `montar_evento()`, que calcula o hash e monta o envelope numa
    única chamada consistente. `__post_init__` recalcula o hash esperado e
    falha fechado se `event_id` não bater, para que um bug de wiring futuro
    (sub-entrega que ligar isto a um trigger real) quebre alto e cedo, não
    silenciosamente com um event_id que não é realmente determinístico.

    `payload_identificador`/`metadata` são congelados RECURSIVAMENTE em
    `__post_init__` (via `autonomy.ledger._snapshot_json`, mesmo mecanismo
    de `Checkpoint.dados`/`LedgerEntry.resultado` em `ledger.py`) -- achado
    real de revisão adversarial independente (1a rodada, P05 sub-entrega
    1/N): `frozen=True` só impede reatribuir o ATRIBUTO
    (`evento.payload_identificador = outra_coisa` levanta
    `FrozenInstanceError`), nunca protegeu o CONTEÚDO de um `dict` mutável
    apontado por ele -- sem o congelamento, `evento.payload_identificador["x"]
    = 999` funcionava silenciosamente e invalidava a garantia de consistência
    com `event_id` que este `__post_init__` afirma proteger; o mesmo valia
    para o `dict` do CHAMADOR ser guardado por referência (mutá-lo depois de
    construir o envelope também mudava o envelope). Depois do congelamento,
    ambos os campos passam a ser `MappingProxyType`/`tuple` recursivos (não
    hasheáveis por si só -- não coloque um `EventEnvelope` num `set`/chave de
    `dict`; dedup é por `event_id`, uma `str`).

    O hash de `event_id` é calculado sobre o `payload_identificador` já
    congelado (não sobre o valor cru recebido do chamador), para que o que é
    verificado seja exatamente o que fica armazenado no envelope.
    """

    event_id: str
    categoria: CategoriaEvento
    fonte_colecao: str
    fonte_doc_id: str
    occurred_at: datetime
    ingested_at: datetime
    payload_identificador: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not str(self.fonte_colecao).strip():
            raise ValueError("fonte_colecao não pode ser vazio.")
        if not str(self.fonte_doc_id).strip():
            raise ValueError("fonte_doc_id não pode ser vazio.")
        _exigir_tz_aware(self.occurred_at, "occurred_at")
        _exigir_tz_aware(self.ingested_at, "ingested_at")
        object.__setattr__(
            self, "payload_identificador", _snapshot_json(dict(self.payload_identificador))
        )
        object.__setattr__(self, "metadata", _snapshot_json(dict(self.metadata)))
        event_id_esperado = calcular_event_id(
            self.categoria,
            self.fonte_colecao,
            self.fonte_doc_id,
            self.payload_identificador,
            self.occurred_at,
        )
        if self.event_id != event_id_esperado:
            raise ValueError(
                "event_id não bate com o hash determinístico de "
                "(categoria, fonte_colecao, fonte_doc_id, payload_identificador, "
                "occurred_at) -- use montar_evento() para construir um EventEnvelope "
                "consistente em vez de calcular event_id manualmente."
            )


def montar_evento(
    categoria: CategoriaEvento,
    fonte_colecao: str,
    fonte_doc_id: str,
    payload_identificador: Mapping[str, Any],
    occurred_at: datetime,
    ingested_at: datetime,
    metadata: Mapping[str, Any] | None = None,
) -> EventEnvelope:
    """Forma preferida de construir um `EventEnvelope`: calcula o event_id e
    monta o envelope numa única chamada, para que quem chama nunca precise
    (e nunca consiga, sem duplicar `calcular_event_id`) produzir um
    event_id inconsistente com seus próprios campos. `EventEnvelope.__post_init__`
    já falha fechado nesse caso; esta função evita o erro na origem."""
    event_id = calcular_event_id(
        categoria, fonte_colecao, fonte_doc_id, payload_identificador, occurred_at
    )
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
