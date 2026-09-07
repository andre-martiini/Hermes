"""Execucao assincrona das tools longas do canal MCP.

`mcp_server.py` cria um documento em `mcp_jobs/{jobId}` (status `processing`)
para tools em `_TOOLS_LONGAS` e devolve o `job_id` na hora; o cliente MCP
consulta o resultado depois via `ler_job`. O gatilho `on_mcp_job_created`
roda a tool de verdade em segundo plano e grava o resultado no mesmo
documento.

Achado do plano de autonomia (P01 passo 5-6, achado A10) — três problemas
no desenho original, todos corrigidos aqui:

1. Reentrega do evento do gatilho (Cloud Functions garante "at-least-once")
   podia rodar a MESMA tool duas vezes, porque a checagem de status usava o
   snapshot do próprio evento (potencialmente desatualizado) em vez de uma
   leitura fresca. Corrigido com `_claim`: leitura+escrita transacional que
   só deixa UMA execução prosseguir por job, usando `status` como o próprio
   sentinela (mesma ideia de `core/idempotency.py`, adaptada — aqui é um
   claim de execução, não deduplicação por chave externa).
2. O resultado da tool era gravado como `done` sem checar se o próprio
   resultado indicava erro (ex.: um dict com `erro` truthy, ou uma string
   `ERRO|...`/`⚠️...` — a mesma convenção já usada no caminho síncrono de
   `mcp_server.py`). Corrigido com `_resultado_indica_erro`, que classifica
   como `error` em vez de `done` nesse caso — sem isso o cliente MCP via
   `ler_job` recebia um "sucesso" que não era.
3. `expira_em` era gravado como inteiro Unix (`int(time.time()) + TTL`), que
   o TTL do Firestore não reconhece (precisa ser Timestamp/datetime) —
   corrigido para `datetime` timezone-aware nos dois pontos de escrita.

Reserva de execução (claim) tem sua própria expiração — `CLAIM_EXPIRA_APOS`
— separada da reserva de idempotência: se uma execução for interrompida sem
concluir (crash, timeout da função) e o claim expirar, uma nova tentativa
NÃO reprocessa automaticamente (a tool pode não ser idempotente) — marca o
job como `error` com uma mensagem explicando a situação, para o chamador
decidir se tenta de novo manualmente. Isso implementa a instrução explícita
do plano (P01 passo 6): não retry automático de handler cujo efeito pode
não ser idempotente.

`CLAIM_EXPIRA_APOS` (600s) é deliberadamente maior que `_TIMEOUT_SEC` (540s,
o `timeout_sec` do gatilho): o Cloud Functions mata a execução com
segurança nessa marca, então qualquer execução que ainda estivesse "em
andamento" aos 600s já foi encerrada à força pela plataforma — não é uma
margem arbitrária, é uma garantia. Os dois valores são derivados da mesma
constante (`_TIMEOUT_SEC`) com uma asserção no import garantindo a relação,
para que uma mudança futura em um não quebre a garantia do outro em
silêncio.

Limitação aceita (não corrigida aqui, fora do escopo do achado A10): a
recuperação de um claim abandonado só roda quando uma NOVA entrega do
evento do gatilho chega para o mesmo documento — se a instância que
detinha o claim morrer sem que o Cloud Functions redisparar o evento (o
"at-least-once" não garante uma redisparada por crash, só que pelo menos
uma entrega bem-sucedida aconteça), o job fica `em_execucao` indefinidamente
e `ler_job` reporta "processing" para sempre. `expira_em` só é gravado nos
caminhos terminais (done/error), então o TTL do Firestore também não
recupera esse caso. Resolver isso de verdade exigiria uma função agendada
(reaper) varrendo `em_execucao` vencidos — fora do escopo deste fix, que
resolve o achado A10 tal como descrito no plano (dedupe de reentrega e
classificação de erro), não introduz um mecanismo de reaper novo. Ainda
assim, isso é estritamente melhor que o código anterior, que não tinha
proteção nenhuma contra reexecução por reentrega.

`ler_job` preserva o contrato público original: `not_found` (job
inexistente ou de outro uid — mesma resposta para os dois casos, para não
vazar se um job_id existe mas pertence a outro usuário) e os três valores
de status (`processing` / `done` / `error`). Os dois estados internos
`processing` (job criado, aguardando claim) e `em_execucao` (claim obtido,
tool rodando) aparecem como `processing` para quem consulta — o estado
intermediário é um detalhe de implementação interno, não um novo valor
público. O campo `erro` no status `error` é sempre uma string (nunca o
dict completo que a tool devolveu) — isso já era o contrato antes deste
fix (o caminho de exceção sempre gravou `str(exc)`); a versão nova apenas
estende a mesma forma para o caso de a tool devolver um resultado que
indica erro sem lançar exceção.
"""
from __future__ import annotations

import json
import secrets
import time
from datetime import datetime, timedelta, timezone

from firebase_functions import firestore_fn, options
from firebase_admin import firestore

COLECAO = "mcp_jobs"
_MAX_RESULTADO_CHARS = 120_000
_TTL_SEC = 60 * 60 * 24 * 3

STATUS_PROCESSING = "processing"
STATUS_EM_EXECUCAO = "em_execucao"
STATUS_DONE = "done"
STATUS_ERROR = "error"

# timeout_sec do gatilho (usado também na decoração abaixo) — único lugar
# onde este número é escrito, para CLAIM_EXPIRA_APOS nunca poder divergir
# dele em silêncio (ver asserção logo abaixo e docstring do módulo).
_TIMEOUT_SEC = 540

# 60s de folga além de _TIMEOUT_SEC para o kill da plataforma se propagar
# antes de qualquer outra tentativa considerar o claim abandonado.
CLAIM_EXPIRA_APOS = timedelta(seconds=_TIMEOUT_SEC + 60)

assert CLAIM_EXPIRA_APOS > timedelta(seconds=_TIMEOUT_SEC), (
    "CLAIM_EXPIRA_APOS precisa exceder _TIMEOUT_SEC — ver docstring do módulo"
)

# Mesma convenção de mcp_server.py (_looks_like_error / checagem de "erro"
# em dict), reaproveitada aqui para classificar o resultado de uma tool
# longa como erro em vez de sucesso.
_PREFIXOS_ERRO = ("ERRO|", "⚠️")


def _db():
    return firestore.client()


def _resultado_indica_erro(resultado) -> str | None:
    """Se `resultado` indica erro (mesma convenção usada no caminho síncrono
    de mcp_server.py), devolve a mensagem de erro extraída. Devolve None se
    o resultado não indica erro."""
    if isinstance(resultado, dict):
        erro = resultado.get("erro")
        if erro:
            return str(erro)
        return None
    if isinstance(resultado, str) and resultado.startswith(_PREFIXOS_ERRO):
        return resultado
    return None


def criar_job(uid, tool, arguments, *, session_id=None, task_id=None) -> str:
    job_id = f"mcpjob-{secrets.token_urlsafe(12)}"
    _db().collection(COLECAO).document(job_id).set({
        "job_id": job_id,
        "uid": uid,
        "tool": tool,
        "arguments": json.loads(json.dumps(arguments or {}, ensure_ascii=False, default=str)),
        "session_id": session_id,
        "task_id": task_id,
        "status": STATUS_PROCESSING,
        "criado_em": int(time.time()),
        "criado_em_ts": firestore.SERVER_TIMESTAMP,
    })
    return job_id


def ler_job(uid, job_id) -> dict:
    """Estado do job. So o dono enxerga — o job_id sozinho nao da acesso."""
    if not job_id:
        return {"erro": "job_id obrigatorio.", "status": "not_found"}

    ref = _db().collection(COLECAO).document(str(job_id))
    snap = ref.get()
    if not snap.exists:
        return {"erro": f"Job '{job_id}' nao encontrado.", "status": "not_found"}
    job = snap.to_dict() or {}
    if job.get("uid") != uid:
        # Mesma resposta de inexistente: confirmar que o id existe ja
        # vazaria informacao para quem esta tentando adivinhar.
        return {"erro": f"Job '{job_id}' nao encontrado.", "status": "not_found"}

    status = job.get("status")
    resposta = {"job_id": job_id, "tool": job.get("tool"), "status": status}

    if status == STATUS_DONE:
        resposta["resultado"] = job.get("resultado")
        if job.get("truncado"):
            resposta["truncado"] = True
    elif status == STATUS_ERROR:
        resposta["erro"] = job.get("erro")
    elif status in (STATUS_PROCESSING, STATUS_EM_EXECUCAO):
        # Contrato público preservado: ambos os estados internos aparecem
        # como "processing" para quem consulta de fora (ver docstring do
        # módulo) — em_execucao é um detalhe interno de implementação.
        resposta["status"] = STATUS_PROCESSING
        resposta["mensagem"] = "ainda processando"
    else:
        resposta["status"] = STATUS_PROCESSING
        resposta["mensagem"] = "ainda processando"

    return resposta


def _claim(db, ref):
    """Tenta obter o claim de execução deste job, com leitura fresca dentro
    de uma transação (corrige o achado do Codex/plano: o snapshot do evento
    do gatilho pode estar desatualizado numa reentrega do próprio evento).

    Devolve os dados do job (dict) se este invocação ganhou o claim — deve
    prosseguir para `_executar_job`. Devolve None se não deve prosseguir:
    já existe um claim válido de outra tentativa (`em_execucao` recente),
    o job já terminou (`done`/`error`), ou o claim encontrado estava
    abandonado (expirado) — nesse último caso, marca o job como `error`
    em vez de reprocessar automaticamente, porque a tool pode não ser
    idempotente (P01 passo 6)."""
    agora = datetime.now(timezone.utc)

    @firestore.transactional
    def _txn(transaction, ref):
        snap = ref.get(transaction=transaction)
        if not snap.exists:
            return None
        job = snap.to_dict() or {}
        status = job.get("status")

        if status in (STATUS_DONE, STATUS_ERROR):
            return None

        if status == STATUS_EM_EXECUCAO:
            claimed_em = job.get("claimed_em")
            if isinstance(claimed_em, datetime) and (agora - claimed_em) < CLAIM_EXPIRA_APOS:
                # Outra tentativa detém um claim ainda válido.
                return None
            # Claim abandonado (execução anterior morreu sem concluir e sem
            # erro registrado — crash, timeout). Não reprocessar
            # automaticamente: marcar como erro para decisão manual.
            transaction.update(ref, {
                "status": STATUS_ERROR,
                "erro": (
                    "Execucao anterior nao concluiu dentro do prazo "
                    f"({CLAIM_EXPIRA_APOS.total_seconds():.0f}s) e foi "
                    "considerada abandonada; nao reprocessada automaticamente "
                    "pois o efeito da tool pode nao ser idempotente."
                ),
                "concluido_em": int(time.time()),
                "expira_em": agora + timedelta(seconds=_TTL_SEC),
            })
            return None

        # status == STATUS_PROCESSING (ou legado sem status reconhecido):
        # ganha o claim agora.
        transaction.update(ref, {
            "status": STATUS_EM_EXECUCAO,
            "claimed_em": agora,
        })
        return job

    txn = db.transaction()
    return _txn(txn, ref)


def _executar_job(db, ref, dados: dict) -> None:
    """Roda a tool de verdade e grava o resultado. Separado de `_claim` (e
    do gatilho) para ser testável sem precisar simular o wrapper de evento
    do Firestore."""
    tool = dados.get("tool")
    agora = datetime.now(timezone.utc)
    expira_em = agora + timedelta(seconds=_TTL_SEC)
    try:
        from tools.hermes_tools import execute
        from tools.tool_context import ToolContext

        ctx = ToolContext(
            user_uid=dados.get("uid"),
            session_id=dados.get("session_id"),
            task_id=dados.get("task_id"),
            canal="mcp",
        )
        resultado = execute(tool, dados.get("arguments") or {}, ctx)

        erro = _resultado_indica_erro(resultado)
        if erro is not None:
            ref.update({
                "status": STATUS_ERROR,
                "erro": erro,
                "concluido_em": int(time.time()),
                "expira_em": expira_em,
            })
            return

        texto = resultado if isinstance(resultado, str) else json.dumps(resultado, ensure_ascii=False, default=str)
        truncado = len(texto) > _MAX_RESULTADO_CHARS
        if truncado:
            texto = texto[:_MAX_RESULTADO_CHARS] + "\n\n[...resultado truncado...]"
        ref.update({
            "status": STATUS_DONE,
            "resultado": texto,
            "truncado": truncado,
            "concluido_em": int(time.time()),
            "expira_em": expira_em,
        })
    except Exception as exc:
        ref.update({
            "status": STATUS_ERROR,
            "erro": str(exc),
            "concluido_em": int(time.time()),
            "expira_em": expira_em,
        })


@firestore_fn.on_document_created(
    document=f"{COLECAO}/{{jobId}}",
    memory=options.MemoryOption.GB_1,
    timeout_sec=_TIMEOUT_SEC,
)
def on_mcp_job_created(event):
    snap = event.data
    if snap is None or not snap.exists:
        return
    ref = snap.reference

    db = _db()
    dados = _claim(db, ref)
    if dados is None:
        return

    _executar_job(db, ref, dados)
