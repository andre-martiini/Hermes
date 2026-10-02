"""Wiring real (Firestore) do outbox de eventos puro em `autonomy/events.py` e
`autonomy/outbox.py` (P05 do plano de autonomia,
docs/plano-hermes-autonomo-2026-09-06.md, seção "P05 — Normalizar eventos e
saúde das integrações", passo 3 do pacote: "Quando escrita e evento forem
internos, persistir ambos na mesma transação ou usar outbox de eventos com
dispatcher reconciliável.").

`autonomy/outbox.py` (P05 sub-entrega 5/N) definiu a FORMA de uma entrada de
outbox e as transições puras de estado, mas nenhum escritor real ainda
persistia uma entrada, e nenhum dispatcher existia -- ver `proximo_pacote`
do bloco daquela sub-entrega em docs/autonomia/execucao.md. Este módulo é a
PONTE: converte `OutboxEntry`/`EventEnvelope` de/para o `dict` que o
Firestore lê e grava (mesmo papel que `agent_requests.py` cumpre para
`autonomy/requests.py` e `mcp_jobs.py` cumpre para `autonomy/mcp_jobs_adapter.py`),
e implementa o primeiro escritor ponta a ponta: `whatsapp_ingest.py::_save_whatsapp_digest`
-- ver `registrar_evento_outbox_transacional` e seu chamador. Um SEGUNDO
escritor foi ligado em P05 sub-entrega 14/N:
`email_action_linker.py::queue_and_maybe_send_suggestion` (ponto de entrada
compartilhado de todos os produtores de sinal -- SIPAC, Calendar, WhatsApp,
Monitor de Páginas), para os canais com categoria clara (SIPAC, AGENDA,
MENSAGEM; "pagina" fica de fora, sem categoria mapeada ainda -- ver
`email_action_linker._CANAL_PARA_CATEGORIA_EVENTO`). O produtor de e-mail
(`link_emails_to_actions`) NÃO passa por `queue_and_maybe_send_suggestion`
(grava `email_action_suggestions` diretamente) e por isso ainda não emite
evento -- fora do escopo desta sub-entrega.

Coleção nova: `outbox_eventos` -- deliberadamente NÃO `outbox` nem
`event_outbox` (colidiria em leitura apressada com a coleção pré-existente
e não relacionada `whatsapp_outbox`, a fila de ENVIO de mensagens do
worker WhatsApp, ver outbox_aprovacao.py -- um conceito de "outbox" bem
mais antigo e completamente diferente deste). ID do doc = `OutboxEntry.entry_id`
(== `EventEnvelope.event_id`, hash determinístico) -- dedupe estrutural,
mesmo padrão de `email_action_suggestions` (ID do doc = ID do sinal).

Escrita: `registrar_evento_outbox_transacional` grava o efeito principal
(fornecido pelo chamador via `escrever_efeito`) E a entrada de outbox NA
MESMA transação Firestore -- achado real de revisão automática do Codex
nesta sub-entrega (PR #382): uma versão anterior deste módulo tinha
`registrar_evento_outbox` como uma escrita separada, não-transacional, log
e siga-em-frente em caso de falha; se a escrita do efeito principal
sucedesse mas a escrita do outbox falhasse de forma transitória logo em
seguida, o evento era perdido para sempre -- nenhum consumidor futuro
jamais o veria, e nada reconstrói uma entrada de outbox a partir do efeito
já gravado (o outbox não é derivado do efeito, é uma segunda escrita
independente). `registrar_evento_outbox_transacional` fecha essa lacuna
lendo a existência da entrada e escrevendo os dois documentos dentro de
`@firestore.transactional`, mesmo padrão de `agent_requests.py::enfileirar_ou_atualizar`
(leitura + escrita atômica, sem fallback para escrita desprotegida se a
transação falhar -- ver a docstring de lá para o raciocínio: uma falha de
transação propaga para o chamador em vez de arriscar uma escrita parcial;
`whatsapp_ingest.py::_save_whatsapp_digest` já não protegia sua própria
escrita do digest com try/except antes desta sub-entrega, então deixar a
escrita conjunta propagar em caso de falha não é uma regressão de postura
-- é a MESMA postura que a escrita do digest sozinha já tinha).
`_entrada_ja_existe`/idempotência por `event_id` acontece DENTRO da
transação (a leitura do doc de outbox é o primeiro passo da função
transacional) -- reentrega do mesmo evento não reinicia o estado de
despacho de uma entrada já existente, e não há mais janela de corrida
check-then-act entre a leitura e a escrita (a versão anterior, não
transacional, tinha essa janela; benigna naquele desenho -- mesmo
`event_id` determinístico, sem duplicata -- mas a transação a fecha de
graça).

Despacho (`despachar_outbox_eventos_core`) segue o mesmo padrão de
`mcp_jobs.py::sweep_mcp_jobs_travados_core`: consulta paginada por
`order_by("__name__")` (mesmo motivo -- nenhuma entrada travada em
`PENDENTE` deve poder ocupar permanentemente a janela de uma página e
impedir entradas mais recentes de serem varridas), teto de segurança sobre
o volume de uma única execução, escrita de cada documento isolada em seu
próprio `try/except`. DELIBERADAMENTE AINDA NÃO REGISTRADA COMO SCHEDULED
FUNCTION em `main.py` -- segundo achado real do Codex nesta sub-entrega:
sem nenhum consumidor real de evento ainda (nenhum trigger/scheduler assina
`outbox_eventos` para agir sobre a categoria/payload), marcar uma entrada
como `ENVIADO` só porque foi logada não "envia" nada a ninguém -- só
fecha, de forma TERMINAL e irreversível, uma entrada que nenhum consumidor
futuro (P06/P07) jamais vai poder reprocessar/consumir num backfill, sem
nenhum ganho em troca (nada foi de fato entregue). Rodar este dispatcher a
cada 15 minutos hoje ativamente destruiria a garantia de reconciliação que
o outbox existe para dar, sem nenhum benefício. A função continua aqui,
testada e pronta (`despachar_outbox_eventos_core`/`_despachar_uma_entrada`)
para a sub-entrega que definir um consumidor real e decidir a forma dele --
essa sub-entrega troca o `print()` de `_despachar_uma_entrada` pela entrega
de verdade e só ENTÃO registra a scheduled function em `main.py` (mesmo
padrão de import de `sweep_mcp_jobs_travados`).
"""

from __future__ import annotations

from datetime import datetime
from types import MappingProxyType
from typing import Any, Callable

from firebase_admin import firestore

from autonomy.events import CategoriaEvento, EventEnvelope
from autonomy.outbox import (
    EstadoOutbox,
    OutboxEntry,
    criar_entrada,
    pronta_para_despachar,
    registrar_falha,
    registrar_sucesso,
)
from autonomy.requests import Lease

COLECAO = "outbox_eventos"

#: Mesmo tamanho de página/teto de segurança de `mcp_jobs.sweep_mcp_jobs_travados_core`
#: -- ver a docstring de lá para o raciocínio completo (paginação por
#: `__name__` evita que entradas nunca-elegíveis ocupem a janela de uma
#: página para sempre). Volume de produção hoje é uma fração do de
#: `mcp_jobs` (2 escritores -- `whatsapp_ingest.py` e, desde P05 sub-entrega
#: 14/N, `email_action_linker.py::queue_and_maybe_send_suggestion` -- emitem
#: eventos até agora), mas o mesmo teto genérico evita reintroduzir o mesmo bug de
#: escala se mais escritores forem ligados a este outbox no futuro.
_DESPACHO_TAMANHO_PAGINA = 500
_DESPACHO_MAX_DOCUMENTOS = 15 * _DESPACHO_TAMANHO_PAGINA


def _descongelar(valor: Any) -> Any:
    """Inverso de `autonomy.ledger._congelar_profundamente`: converte
    `MappingProxyType`/`tuple` (a forma congelada que `EventEnvelope`
    guarda em `payload_identificador`/`metadata`, ver seu `__post_init__`)
    de volta para `dict`/`list` -- o cliente do Firestore não aceita os
    tipos congelados diretamente num `.set()`/`.create()`."""
    if isinstance(valor, MappingProxyType):
        return {chave: _descongelar(item) for chave, item in valor.items()}
    if isinstance(valor, tuple):
        return [_descongelar(item) for item in valor]
    return valor


def _lease_para_doc(lease: Lease | None) -> dict | None:
    """`Lease` (P05 sub-entrega 17/N, `OutboxEntry.lease`) -> dict aninhado,
    ou `None` quando a entrada nunca passou por `iniciar_despacho()` --
    achado real de revisão automática do Codex (P2) na PR desta sub-entrega:
    antes desta função, `_entrada_para_doc` simplesmente omitia `lease`, o
    que perderia a lease de uma entrada `EM_PROCESSAMENTO` ao gravar (e
    `_entrada_de_doc` levantaria o erro de `OutboxEntry.__post_init__` ao
    reler, já que esse estado exige lease)."""
    if lease is None:
        return None
    return {
        "lease_token": lease.lease_token,
        "generation": lease.generation,
        "executor_id": lease.executor_id,
        "expires_at": lease.expires_at,
    }


def _lease_de_doc(dados: dict | None) -> Lease | None:
    """Inverso de `_lease_para_doc`."""
    if not dados:
        return None
    return Lease(
        lease_token=dados["lease_token"],
        generation=int(dados["generation"]),
        executor_id=dados["executor_id"],
        expires_at=dados["expires_at"],
    )


def _entrada_para_doc(entrada: OutboxEntry) -> dict:
    """`OutboxEntry` (mais o `EventEnvelope` embutido) -> dict pronto para
    `doc_ref.set()`. Datas ficam como `datetime` nativo (não `.isoformat()`)
    -- o cliente do Firestore grava isso como `Timestamp`, e lê de volta já
    como `datetime` tz-aware, sem exigir parsing na leitura (`_entrada_de_doc`
    conta com isso)."""
    evento = entrada.evento
    return {
        "categoria": evento.categoria.value,
        "fonte_colecao": evento.fonte_colecao,
        "fonte_doc_id": evento.fonte_doc_id,
        "occurred_at": evento.occurred_at,
        "ingested_at": evento.ingested_at,
        "payload_identificador": _descongelar(evento.payload_identificador),
        "metadata": _descongelar(evento.metadata),
        "estado": entrada.estado.value,
        "tentativas": entrada.tentativas,
        "criado_em": entrada.criado_em,
        "disponivel_em": entrada.disponivel_em,
        "ultima_tentativa_em": entrada.ultima_tentativa_em,
        "ultimo_erro": entrada.ultimo_erro,
        "lease": _lease_para_doc(entrada.lease),
    }


def _entrada_de_doc(entry_id: str, dados: dict) -> OutboxEntry:
    """Inverso de `_entrada_para_doc` -- reconstrói o `OutboxEntry`
    (`EventEnvelope` incluso) a partir do `dict` bruto de
    `snapshot.to_dict()`. `EventEnvelope.__post_init__`/`OutboxEntry.__post_init__`
    recalculam e conferem `event_id`/`entry_id` normalmente -- um documento
    corrompido (campo trocado por escrita manual, migração malfeita) falha
    fechado aqui, mesma garantia que já vale para quem constrói em memória.
    `dados.get("lease")` cobre documentos gravados ANTES da P05 sub-entrega
    17/N (sem o campo) -- lidos como `lease=None`, igual a uma entrada que
    nunca passou por `iniciar_despacho()`."""
    evento = EventEnvelope(
        event_id=entry_id,
        categoria=CategoriaEvento(dados["categoria"]),
        fonte_colecao=dados["fonte_colecao"],
        fonte_doc_id=dados["fonte_doc_id"],
        occurred_at=dados["occurred_at"],
        ingested_at=dados["ingested_at"],
        payload_identificador=dados.get("payload_identificador") or {},
        metadata=dados.get("metadata") or {},
    )
    return OutboxEntry(
        entry_id=entry_id,
        evento=evento,
        estado=EstadoOutbox(dados["estado"]),
        tentativas=int(dados.get("tentativas") or 0),
        criado_em=dados["criado_em"],
        disponivel_em=dados["disponivel_em"],
        ultima_tentativa_em=dados.get("ultima_tentativa_em"),
        ultimo_erro=dados.get("ultimo_erro"),
        lease=_lease_de_doc(dados.get("lease")),
    )


def registrar_evento_outbox_transacional(
    db,
    evento: EventEnvelope,
    *,
    agora: datetime,
    escrever_efeito: Callable[[Any], None],
) -> bool:
    """Grava o efeito principal (via `escrever_efeito`) e a entrada nova de
    outbox para `evento` NA MESMA transação Firestore -- ver docstring do
    módulo para o achado real do Codex que motivou substituir a versão
    anterior (não-transacional) por esta.

    `escrever_efeito(transaction)` é chamado DENTRO da transação e deve só
    enfileirar escrita(s) nela (`transaction.set(...)`/`transaction.update(...)`)
    -- nunca fazer I/O fora da transação nem qualquer efeito colateral
    não-idempotente, mesma exigência de qualquer função decorada com
    `@firestore.transactional` (a transação pode reexecutar em caso de
    conflito). Devolve `True` se uma entrada de outbox NOVA foi gravada
    (mesma semântica que a versão anterior tinha), `False` se já existia --
    idempotente por `evento.event_id`, mesmo padrão de
    `email_action_linker.queue_and_maybe_send_suggestion`, agora sem a
    janela de corrida check-then-act que uma leitura e escrita separadas
    teriam."""
    outbox_ref = db.collection(COLECAO).document(evento.event_id)

    @firestore.transactional
    def _executar(transaction):
        outbox_snap = outbox_ref.get(transaction=transaction)
        escrever_efeito(transaction)
        entrada_e_nova = not outbox_snap.exists
        if entrada_e_nova:
            entrada = criar_entrada(evento, agora)
            transaction.set(outbox_ref, _entrada_para_doc(entrada))
        return entrada_e_nova

    transaction = db.transaction()
    return _executar(transaction)


def _despachar_uma_entrada(doc_ref, entrada: OutboxEntry, *, agora: datetime) -> bool:
    """Tenta "despachar" uma única entrada pronta e grava o resultado.
    Devolve `True` se a entrada foi fechada como `ENVIADO` com sucesso.

    Sem consumidor real ainda (ver docstring do módulo) -- o corpo do
    `try` só loga a ocorrência; a exceção que ele pode pegar hoje é do
    próprio `print`/formatação, não de uma entrega de verdade. Mantido como
    `try/except` (em vez de chamar `registrar_sucesso` incondicionalmente)
    para que o caminho de `registrar_falha` já exista e seja exercido pelo
    dispatcher assim que um consumidor real substituir o `print` -- sem
    precisar mudar esta função de novo."""
    try:
        print(
            f"[outbox_eventos] despachando evento {entrada.evento.event_id} "
            f"(categoria={entrada.evento.categoria.value}, "
            f"fonte={entrada.evento.fonte_colecao}/{entrada.evento.fonte_doc_id}) "
            "-- sem consumidor real ainda, entrada fechada como enviada."
        )
    except Exception as exc:  # noqa: BLE001
        atualizada = registrar_falha(entrada, agora, str(exc))
    else:
        atualizada = registrar_sucesso(entrada, agora)

    campos = {
        "estado": atualizada.estado.value,
        "tentativas": atualizada.tentativas,
        "disponivel_em": atualizada.disponivel_em,
        "ultima_tentativa_em": atualizada.ultima_tentativa_em,
        "ultimo_erro": atualizada.ultimo_erro,
    }
    try:
        doc_ref.update(campos)
    except Exception as exc:  # noqa: BLE001
        print(f"[outbox_eventos] falha ao gravar despacho de {entrada.entry_id}: {exc}")
        return False
    return atualizada.estado == EstadoOutbox.ENVIADO


def despachar_outbox_eventos_core(db, *, agora: datetime) -> tuple[int, int]:
    """Núcleo do dispatcher, separado do decorator `on_schedule` para ser
    testável sem simular o `ScheduledEvent` real -- mesma separação de
    `mcp_jobs.sweep_mcp_jobs_travados_core`. Consulta `outbox_eventos` em
    `estado="pendente"`, pagina por `order_by("__name__")` (ver a docstring
    do módulo para o porquê) e despacha cada entrada elegível
    (`pronta_para_despachar`). Devolve `(varridas, despachadas)`."""
    consulta_base = (
        db.collection(COLECAO)
        .where(filter=firestore.FieldFilter("estado", "==", EstadoOutbox.PENDENTE.value))
        .order_by("__name__")
    )
    varridas = 0
    despachadas = 0
    cursor = None
    while varridas < _DESPACHO_MAX_DOCUMENTOS:
        pagina = consulta_base.limit(_DESPACHO_TAMANHO_PAGINA)
        if cursor is not None:
            pagina = pagina.start_after(cursor)
        docs_da_pagina = list(pagina.stream())
        if not docs_da_pagina:
            break
        for snap in docs_da_pagina:
            varridas += 1
            dados = snap.to_dict() or {}
            try:
                entrada = _entrada_de_doc(snap.id, dados)
            except Exception as exc:  # noqa: BLE001
                print(f"[outbox_eventos] entrada corrompida ignorada ({snap.id}): {exc}")
                continue
            if not pronta_para_despachar(entrada, agora):
                continue
            if _despachar_uma_entrada(snap.reference, entrada, agora=agora):
                despachadas += 1
        if len(docs_da_pagina) < _DESPACHO_TAMANHO_PAGINA:
            break
        cursor = docs_da_pagina[-1]
    return varridas, despachadas
