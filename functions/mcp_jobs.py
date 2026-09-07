"""Execucao assincrona das tools longas do canal MCP.

`mcp_server.py` cria um documento em `mcp_jobs/{jobId}` (status `processing`)
para tools em `_TOOLS_LONGAS` e devolve o `job_id` na hora; o cliente MCP
consulta o resultado depois via `ler_job`. O gatilho `on_mcp_job_created`
roda a tool de verdade em segundo plano e grava o resultado no mesmo
documento.

Achado do plano de autonomia (P01 passo 5-6, achado A10) — três problemas
no desenho original, todos corrigidos aqui (mais dois achados do Codex na
PR #189, pontos 4 e 5 abaixo):

1. Reentrega do evento do gatilho podia rodar a MESMA tool duas vezes,
   porque a checagem de status usava o snapshot do próprio evento
   (potencialmente desatualizado) em vez de uma leitura fresca. Corrigido
   com `_claim`: leitura+escrita transacional que só deixa UMA execução
   prosseguir por job, usando `status` como o próprio sentinela (mesma
   ideia de `core/idempotency.py`, adaptada — aqui é um claim de execução,
   não deduplicação por chave externa). Sobre "reentrega": este gatilho tem
   `retry` desligado (é o valor fixo usado por `FirestoreOptions._endpoint`
   na versão instalada de `firebase_functions` — não é configurável aqui,
   verificado lendo o código-fonte da lib), então uma invocação que FALHA
   não é redisparada automaticamente pelo Cloud Functions/Eventarc; a
   duplicidade de entrega que este módulo protege contra vem da semântica
   "at-least-once" do Pub/Sub por trás do Eventarc (que pode entregar o
   MESMO evento mais de uma vez mesmo quando a entrega anterior teve
   sucesso), não de uma política de retry em caso de erro.
2. O resultado da tool era gravado como `done` sem checar se o próprio
   resultado indicava erro (ex.: um dict com `erro` truthy, ou uma string
   `ERRO|...`/`⚠️...` — a mesma convenção já usada no caminho síncrono de
   `mcp_server.py`). Corrigido com `_resultado_indica_erro`, que classifica
   como `error` em vez de `done` nesse caso — sem isso o cliente MCP via
   `ler_job` recebia um "sucesso" que não era.
3. `expira_em` era gravado como inteiro Unix (`int(time.time()) + TTL`), que
   o TTL do Firestore não reconhece (precisa ser Timestamp/datetime) —
   corrigido para `datetime` timezone-aware nos dois pontos de escrita.
4. Achado do Codex na PR #189 (P1, "Avoid acknowledging retries for an
   orphaned fresh claim"): a primeira versão de `_claim` devolvia `None`
   (silenciosamente, sem lançar) quando encontrava um claim `em_execucao`
   ainda "jovem" (mais novo que `CLAIM_EXPIRA_APOS`) — e `on_mcp_job_created`
   então retornava normalmente, o que o Cloud Functions registra como
   invocação BEM-SUCEDIDA. Cenário do achado: a transação que grava o
   claim comita no servidor, mas a resposta se perde para o cliente
   (commit ambíguo — mesma classe de problema já corrigida em
   `core/idempotency.py` nas sub-entregas 3/N-3.1/N); a invocação que
   fazia essa gravação levanta uma exceção de rede e nunca chega a chamar
   `_executar_job`. Se uma entrega duplicada do MESMO evento (Pub/Sub
   at-least-once, não retry — ver ponto 1 acima) chegar enquanto o claim
   ainda está "jovem", ela encontra `em_execucao` recente, conclui
   "outra tentativa está com isto" e retorna sucesso — sem que a tool
   TENHA sido executada por ninguém, e sem nenhum sinal de erro em lugar
   nenhum. Essa é justamente a entrega mais provável de acontecer (Pub/Sub
   tende a duplicar entregas PRÓXIMAS no tempo, por corrida de ack, não
   depois de `CLAIM_EXPIRA_APOS`), então era exatamente a única
   oportunidade plausível de recuperação sendo transformada em um
   "sucesso" silencioso e falso. Corrigido: encontrar um claim jovem agora
   LEVANTA `ClaimAindaValidoError` em vez de devolver None — a invocação
   falha visivelmente (aparece como erro nos logs/métricas do Cloud
   Functions) em vez de mentir que processou algo que não processou. Isso
   NÃO causa nova tentativa automática (retry está desligado para este
   gatilho — ver ponto 1), então não é uma correção estrutural completa;
   ver a limitação aceita abaixo.

   Troca aceita deliberadamente (achado da revisão adversarial desta
   correção): o mesmo ramo também é onde uma entrega duplicada
   genuinamente benigna (tentativa irmã de fato ainda rodando a tool com
   sucesso) vai cair — levantar aqui faz essa invocação REDUNDANTE (mas
   inofensiva) também aparecer como falha nos logs/métricas, não só o caso
   realmente órfão. Considerado e não implementado: uma "janela de graça"
   separada (ex.: só levantar se o claim tiver mais que alguns segundos,
   silenciar se for recentíssimo) — rejeitado por exigir um segundo limiar
   arbitrário sem dado real sobre a distribuição de tempo das entregas
   duplicadas do Pub/Sub neste projeto (ao contrário de `CLAIM_EXPIRA_APOS`,
   que é derivado de `_TIMEOUT_SEC`, não inventado). Em vez disso, a
   mensagem da exceção inclui a idade real do claim encontrado (segundos
   desde `claimed_em`), para quem for investigar um erro nos logs
   distinguir na hora um claim de poucos segundos (provável duplicata
   benigna concorrente) de um claim de vários minutos (provável órfão) sem
   precisar adivinhar um limiar. O custo aceito é ruído ocasional nos logs
   para o caso benigno; o benefício é nunca mais perder silenciosamente o
   único sinal de um claim genuinamente órfão — dado que hoje esse sinal,
   quando existe, não tem nenhuma outra forma de aparecer (ver "Limitação
   aceita" abaixo).
5. Achado do Codex na PR #189 (segunda rodada, P1, "Add recovery instead of
   only raising for orphaned claims"): levantar `ClaimAindaValidoError`
   (ponto 4) torna a falha visível nos logs, mas sozinho não RECUPERA o
   job — sem uma entrega duplicada tardia e independente do mesmo evento
   (não garantida, ver ponto 1), o job continuava `em_execucao` para
   sempre do ponto de vista de quem consulta via `ler_job`. Corrigido com
   `_reaproveitar_claim_vencido_na_leitura`: a própria chamada a `ler_job`
   agora reexecuta a mesma checagem de claim vencido que `_claim` faz, e
   marca `error` se encontrar um claim `em_execucao` mais velho que
   `CLAIM_EXPIRA_APOS` — mesma transação, mesmo limiar, mesma garantia de
   segurança (ver `CLAIM_EXPIRA_APOS` abaixo). Isso funciona sem precisar
   de uma função agendada (reaper) nova porque o protocolo do canal MCP
   (ver `mcp_server.py`) já instrui o cliente a chamar `ler_job`
   repetidamente enquanto o job estiver `processing` — a consulta em loop
   que já acontece na prática É o mecanismo de recuperação, não uma peça
   nova de infraestrutura. Ver a limitação aceita (abaixo) para o que
   ainda não fecha: um job cujo cliente para de consultar antes de o claim
   vencer.

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

Limitação aceita (não corrigida aqui, fora do escopo do achado A10): depois
da correção do ponto 5, um claim genuinamente abandonado se recupera na
PRÓXIMA vez que alguém chamar `ler_job` para esse job (ou, como antes, se
uma entrega duplicada tardia do mesmo evento chegar por acaso) — não
depende mais só da sorte de uma reentrega tardia. O que ainda não fecha é o
caso em que NINGUÉM nunca mais consulta esse job_id de novo (cliente MCP
desistiu, caiu, ou nunca chegou a perguntar) — aí não há nem entrega
duplicada nem chamada a `ler_job` para acionar a recuperação, e o job fica
`em_execucao` indefinidamente no Firestore (`expira_em` só é gravado nos
caminhos terminais, então o TTL também não recupera esse caso; é um
documento órfão, não um job cujo estado alguém consulta errado). Esse
resíduo é inofensivo para quem usa o sistema (ninguém está esperando por
uma resposta que não vai checar) mas continua sem limpeza automática.
Resolver isso de verdade exigiria uma função agendada (reaper) varrendo
`em_execucao` vencidos independente de qualquer consulta, ou o protocolo
completo de lease/heartbeat da seção 4.5 do plano — fora do escopo deste
fix (que resolve o achado A10 tal como descrito no plano: dedupe de
reentrega e classificação de erro) e mais próximo do escopo de P04
(durabilidade de execução), mesmo precedente já usado para
`agent_requests.py` (achado A01, sub-entrega 3/N). Ainda assim, isso é
estritamente melhor que a correção do ponto 4 sozinha, que dependia
inteiramente de uma entrega duplicada tardia e não garantida.

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


class ClaimAindaValidoError(RuntimeError):
    """Levantada por `_claim` quando encontra um claim `em_execucao` mais
    novo que `CLAIM_EXPIRA_APOS` — ver ponto 4 da docstring do módulo
    (achado do Codex na PR #189).

    Existe para que essa situação ambígua (pode ser uma tentativa irmã
    genuinamente em andamento, ou pode ser um claim órfão de uma tentativa
    que já morreu sem nunca ter chegado a executar a tool) NUNCA vire uma
    invocação "bem-sucedida" do gatilho — antes desta correção, `_claim`
    devolvia None silenciosamente aqui, e `on_mcp_job_created` retornava
    normalmente, o que o Cloud Functions registra como sucesso mesmo que
    nenhuma execução real tenha acontecido para este job. Levantar aqui faz
    a invocação falhar de forma visível (nos logs/métricas do Cloud
    Functions) em vez de mentir.

    Isso NÃO desencadeia uma nova tentativa automática: o gatilho
    `on_mcp_job_created` tem `retry` desligado (valor fixo em
    `FirestoreOptions._endpoint`, não configurável nesta versão da lib —
    ver ponto 1 da docstring do módulo), então uma invocação que levanta
    esta exceção simplesmente falha e fica assim, sem redisparada
    automática do Cloud Functions. A recuperação deste job específico
    depende de outra coisa acontecer depois de `CLAIM_EXPIRA_APOS`: uma
    entrega duplicada independente do mesmo evento (via at-least-once do
    Pub/Sub, não retry), OU — desde o ponto 5 da docstring do módulo,
    achado da segunda rodada do Codex na PR #189 — a próxima chamada a
    `ler_job` para este job_id, que reexecuta a mesma checagem via
    `_reaproveitar_claim_vencido_na_leitura`. Ver a limitação aceita na
    docstring do módulo para o que ainda não fecha (nenhuma das duas coisas
    acontece). Levantar em vez de engolir não resolve essa limitação de
    fundo sozinho, só impede que ela seja mascarada como sucesso."""


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

    db = _db()
    ref = db.collection(COLECAO).document(str(job_id))
    snap = ref.get()
    if not snap.exists:
        return {"erro": f"Job '{job_id}' nao encontrado.", "status": "not_found"}
    job = snap.to_dict() or {}
    if job.get("uid") != uid:
        # Mesma resposta de inexistente: confirmar que o id existe ja
        # vazaria informacao para quem esta tentando adivinhar.
        return {"erro": f"Job '{job_id}' nao encontrado.", "status": "not_found"}

    if job.get("status") == STATUS_EM_EXECUCAO:
        # Achado do Codex na PR #189 (segunda rodada, P1: "Add recovery
        # instead of only raising for orphaned claims"): sem isto, um claim
        # vencido só se recupera se uma entrega duplicada tardia e
        # independente do MESMO evento chegar por acaso (não garantida, já
        # que retry está desligado — ver docstring do módulo). O protocolo
        # do canal MCP (mcp_server.py instrui o cliente a chamar esta
        # função de novo enquanto o job estiver "processing") já faz o
        # cliente consultar em loop — reaproveitado aqui como o mecanismo
        # de recuperação, sem precisar de uma função agendada (reaper) nova.
        job = _reaproveitar_claim_vencido_na_leitura(db, ref) or job

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


def _dados_claim_abandonado(agora: datetime) -> dict:
    """Campos gravados quando um claim `em_execucao` mais velho que
    `CLAIM_EXPIRA_APOS` é considerado abandonado (execução anterior morreu
    sem concluir — crash, timeout) e marcado `error` sem reprocessar
    automaticamente (P01 passo 6: efeito da tool pode não ser idempotente).
    Compartilhado entre `_claim` (uma nova entrega do evento do gatilho
    encontra o claim vencido) e `_reaproveitar_claim_vencido_na_leitura`
    (uma consulta de `ler_job` encontra o claim vencido) — mesma regra,
    uma única definição, para as duas nunca poderem divergir em silêncio."""
    return {
        "status": STATUS_ERROR,
        "erro": (
            "Execucao anterior nao concluiu dentro do prazo "
            f"({CLAIM_EXPIRA_APOS.total_seconds():.0f}s) e foi "
            "considerada abandonada; nao reprocessada automaticamente "
            "pois o efeito da tool pode nao ser idempotente."
        ),
        "concluido_em": int(time.time()),
        "expira_em": agora + timedelta(seconds=_TTL_SEC),
    }


def _reaproveitar_claim_vencido_na_leitura(db, ref) -> dict | None:
    """Reexecuta, a partir de uma leitura de `ler_job`, a mesma checagem e
    o mesmo abandono de claim vencido que `_claim` faz a partir de uma nova
    entrega do evento do gatilho — achado do Codex na PR #189 (segunda
    rodada, P1: 'Add recovery instead of only raising for orphaned
    claims'). Sem isto, um claim `em_execucao` vencido só se recupera se
    uma entrega duplicada tardia e independente do MESMO evento chegar por
    acaso (não garantida — retry está desligado para este gatilho, ver
    docstring do módulo); o job ficaria `processing` para sempre do ponto
    de vista de quem consulta. Com isto, a própria chamada a `ler_job` —
    que o protocolo do canal MCP já instrui o cliente a repetir enquanto o
    job estiver `processing` (ver mcp_server.py) — fecha essa lacuna sem
    precisar de uma função agendada (reaper) nova.

    Leitura+escrita dentro de uma transação, para não correr com uma
    conclusão genuína (`_executar_job` terminando bem no meio da consulta)
    nem com um novo claim legítimo. Devolve o dict do job já atualizado
    (com `status`/`erro`/etc. refletindo o abandono) se marcou como
    abandonado agora; devolve o dict do job tal como está (sem tocar nada)
    se o claim não está mais vencido ou já não é mais `em_execucao` — nesse
    caso outra coisa (uma execução legítima, um novo claim) já resolveu a
    situação entre a leitura inicial de `ler_job` e esta chamada. Devolve
    None se o documento sumiu (não deveria acontecer dentro do TTL de 3
    dias, mas `ler_job` já trata None como 'usar o dict antigo')."""
    agora = datetime.now(timezone.utc)

    @firestore.transactional
    def _txn(transaction, ref):
        snap = ref.get(transaction=transaction)
        if not snap.exists:
            return None
        job = snap.to_dict() or {}
        if job.get("status") != STATUS_EM_EXECUCAO:
            return job

        claimed_em = job.get("claimed_em")
        if isinstance(claimed_em, datetime) and (agora - claimed_em) < CLAIM_EXPIRA_APOS:
            return job

        campos = _dados_claim_abandonado(agora)
        transaction.update(ref, campos)
        return {**job, **campos}

    txn = db.transaction()
    return _txn(txn, ref)


def _claim(db, ref):
    """Tenta obter o claim de execução deste job, com leitura fresca dentro
    de uma transação (corrige o achado do Codex/plano: o snapshot do evento
    do gatilho pode estar desatualizado numa entrega duplicada do próprio
    evento).

    Devolve os dados do job (dict) se este invocação ganhou o claim — deve
    prosseguir para `_executar_job`. Devolve None (sem levantar) se não há
    nada de errado a sinalizar: o job já terminou (`done`/`error`), ou o
    claim encontrado estava abandonado e acabou de ser marcado `error`
    nesta chamada (P01 passo 6: não reprocessar automaticamente, porque a
    tool pode não ser idempotente) — nos dois casos algo definitivo já
    aconteceu, retornar sucesso normalmente é correto.

    Levanta `ClaimAindaValidoError` se encontrar um claim `em_execucao`
    ainda dentro de `CLAIM_EXPIRA_APOS` — achado do Codex na PR #189: essa
    situação é ambígua (pode ser uma tentativa irmã genuinamente em
    andamento, pode ser um claim órfão de uma tentativa que já morreu) e
    NÃO deve ser tratada como sucesso silencioso — ver a docstring da
    exceção e o ponto 4 da docstring do módulo."""
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
                # Achado do Codex na PR #189: NÃO devolver None em silêncio
                # aqui — isso faria on_mcp_job_created retornar normalmente,
                # e o Cloud Functions registraria esta invocação como
                # bem-sucedida mesmo que a tool nunca tenha rodado para este
                # job (ver docstring de ClaimAindaValidoError).
                idade_claim = (agora - claimed_em).total_seconds()
                raise ClaimAindaValidoError(
                    f"Claim de execucao para o job '{job.get('job_id')}' "
                    f"tem {idade_claim:.0f}s de idade, ainda dentro da janela "
                    f"de validade ({CLAIM_EXPIRA_APOS.total_seconds():.0f}s); "
                    "pode ser uma tentativa irma em andamento (provavel se a "
                    "idade for pequena) ou um claim orfao de uma tentativa "
                    "que ja morreu sem executar a tool (provavel se a idade "
                    "for grande). Nao tratado como sucesso silencioso."
                )
            # Claim abandonado (execução anterior morreu sem concluir e sem
            # erro registrado — crash, timeout). Não reprocessar
            # automaticamente: marcar como erro para decisão manual.
            transaction.update(ref, _dados_claim_abandonado(agora))
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
