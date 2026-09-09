"""Execucao assincrona das tools longas do canal MCP.

Tres tools do catalogo fazem trabalho que passa de um minuto — gerar relatorio,
ler um documento inteiro e responder sobre ele, varrer e analisar e-mails. No
copiloto web elas ja rodavam fora do request, via Pub/Sub; pelo MCP passaram a
rodar sincronas, e isso funciona ate a hora em que nao funciona:

- pela URL direta da Cloud Function ha 300s de folga;
- pela URL do Hosting — que e a que Cowork, Desktop e celular usam — **o limite
  e 60s**, e o cliente recebe um erro de gateway sem explicacao.

Entao essas tools passam a devolver `{status: "processing", job_id}` na hora, e a
execucao de verdade acontece num trigger do Firestore com 540s. O cliente busca o
resultado com `consultar_job`. Um agente lida bem com esse ir e vir; era o
copiloto web que nao lidaria, e ele nem passa por aqui.

O contrato e o mesmo que a proposta original do servidor MCP ja previa para as
tools assincronas.

P01 passo 5 (achado A10 do plano): o trigger `on_mcp_job_created` corrigido
aqui nesta sub-entrega para quatro problemas concretos --

1. Reivindicacao sobre leitura atual: o gatilho nao decide mais com base no
   snapshot capturado no MOMENTO DO EVENTO (`event.data.to_dict()`), que pode
   estar desatualizado -- gatilhos do Firestore sao "ao menos uma vez", nao
   "exatamente uma vez", entao o mesmo evento de criacao pode invocar esta
   funcao mais de uma vez. Em vez disso, reivindica o job numa transacao que
   le o estado ATUAL antes de decidir executar, mesmo padrao A04 ja usado em
   core/idempotency.py e agent_requests.py.
2. Estado de erro normalizado: as tres tools deste trigger nao levantam
   excecao nem devolvem um dict com "erro" quando falham -- devolvem uma
   STRING de sucesso-na-forma que e, no conteudo, uma mensagem de erro
   (prefixo "⚠️", mesmo contrato de `mcp_server.py::_looks_like_error` para o
   caminho sincrono). Sem checar isso, o job virava "done" com uma mensagem
   de erro no lugar do resultado -- falso sucesso (risco citado no A10).
3. Resultado estruturado: quando o resultado da tool nao e string (hoje
   nenhuma das tres e, mas `execute()` e o mesmo dispatcher generico usado
   por qualquer tool), ele deixa de ser sempre serializado para uma string
   JSON antes de gravar -- fica no formato nativo (dict/lista) quando cabe no
   limite de tamanho, evitando dupla serializacao para quem consome
   `consultar_job` de forma programatica.
4. Timestamp de expiracao: `expira_em` passa de inteiro Unix para um
   `datetime` timezone-aware, que o cliente Firestore grava como Timestamp
   nativo -- o mesmo padrao ja usado em `core/idempotency.py::expires_at`.
   Um campo Unix-inteiro nao e elegivel para uma politica de TTL do
   Firestore (essas exigem campo Timestamp); o tipo agora permite configurar
   TTL nesta colecao -- configurar a politica em si continua sendo um passo
   de infraestrutura separado, fora do alcance de uma mudanca de codigo.
"""

from __future__ import annotations

import json
import secrets
import time
from datetime import datetime, timedelta, timezone

from firebase_functions import firestore_fn, options
from firebase_admin import firestore

COLECAO = "mcp_jobs"

# Retorno maior que isto e truncado: `Claude.ai`/Desktop cortam o resultado de
# tool em ~150 mil caracteres e o Claude Code em 25 mil tokens. Melhor truncar
# aqui, com aviso explicito, do que o cliente cortar no meio em silencio.
_MAX_RESULTADO_CHARS = 120_000

# Job concluido nao e apagado na hora: o cliente pode consultar de novo, e o
# historico serve para depurar. Some depois disto, pelo TTL do Firestore se
# configurado, ou por limpeza manual.
_TTL_SEC = 60 * 60 * 24 * 3

# Categorias normalizadas de `status: "error"` -- permitem a um consumidor
# programatico de `ler_job`/`consultar_job` distinguir a NATUREZA do erro sem
# casar texto livre em `erro`, mesmo padrao de proposito de
# `core/idempotency.py::RESULTADO_*`.
ERRO_TIPO_POLITICA = "politica"  # bloqueado pelo preflight de autonomia antes de executar
ERRO_TIPO_RESULTADO = "resultado_tool"  # a tool devolveu um resultado no formato de erro sem levantar excecao
ERRO_TIPO_EXCECAO = "excecao"  # excecao nao tratada durante a execucao da tool
ERRO_TIPO_CONFIGURACAO = "erro_configuracao"  # backend Firestore sem suporte a transacao real


def _db():
    return firestore.client()


def _expira_em() -> datetime:
    """`datetime` timezone-aware -- o cliente Firestore grava isto como
    Timestamp nativo, elegivel para uma politica de TTL (um inteiro Unix
    nao e). Mesmo padrao de `core/idempotency.py::expires_at`."""
    return datetime.now(timezone.utc) + timedelta(seconds=_TTL_SEC)


def _parece_mensagem_de_erro(texto: str) -> bool:
    """Mesmo contrato de `mcp_server.py::_looks_like_error`, duplicado aqui
    (nao importado) para nao criar acoplamento circular: `mcp_server.py` ja
    importa `mcp_jobs.criar_job`. As tres tools deste trigger vieram do canal
    Telegram e sinalizam falha no proprio texto, sem levantar excecao."""
    return texto.startswith("ERRO|") or texto.startswith("⚠️")


def _preparar_resultado(resultado):
    """Decide o valor final gravado em `resultado` e se foi truncado.

    String passa direto. Qualquer outro tipo (hoje teorico para as tres tools
    deste trigger, mas `execute()` e generico) fica na forma estruturada
    nativa quando cabe no limite de tamanho -- so vira string JSON truncada
    quando excede `_MAX_RESULTADO_CHARS`, caso em que preservar a estrutura
    deixaria de fazer sentido de qualquer forma.
    """
    if isinstance(resultado, str):
        texto = resultado
        estruturado = None
    else:
        texto = json.dumps(resultado, ensure_ascii=False, default=str)
        estruturado = resultado

    if len(texto) > _MAX_RESULTADO_CHARS:
        return texto[:_MAX_RESULTADO_CHARS] + "\n\n[...resultado truncado...]", True
    return (estruturado if estruturado is not None else texto), False


def criar_job(uid: str, tool: str, arguments: dict, *, session_id: str | None = None,
              task_id: str | None = None) -> str:
    """Enfileira a execucao e devolve o id. O trabalho acontece no trigger."""
    job_id = f"mcpjob-{secrets.token_urlsafe(12)}"
    _db().collection(COLECAO).document(job_id).set({
        "job_id": job_id,
        "uid": uid,
        "tool": tool,
        "arguments": json.loads(json.dumps(arguments or {}, ensure_ascii=False, default=str)),
        "session_id": session_id,
        "task_id": task_id,
        "status": "processing",
        "criado_em": int(time.time()),
        "criado_em_ts": firestore.SERVER_TIMESTAMP,
    })
    return job_id


def ler_job(uid: str, job_id: str) -> dict:
    """Estado do job. So o dono enxerga — o job_id sozinho nao da acesso."""
    if not job_id:
        return {"erro": "job_id obrigatorio."}

    snap = _db().collection(COLECAO).document(str(job_id)).get()
    if not snap.exists:
        return {"erro": f"Job '{job_id}' nao encontrado.", "status": "not_found"}

    dados = snap.to_dict() or {}
    if dados.get("uid") != uid:
        # Mesma resposta de inexistente: confirmar que o id existe ja vazaria
        # informacao para quem esta tentando adivinhar.
        return {"erro": f"Job '{job_id}' nao encontrado.", "status": "not_found"}

    saida = {
        "job_id": job_id,
        "tool": dados.get("tool"),
        "status": dados.get("status"),
    }
    if dados.get("status") == "done":
        saida["resultado"] = dados.get("resultado")
    elif dados.get("status") == "error":
        saida["erro"] = dados.get("erro")
        # Categoria normalizada (P01 sub-entrega 5/N) -- presente em toda
        # escrita de status "error" a partir desta sub-entrega; ausente so em
        # jobs gravados antes dela.
        if dados.get("erro_tipo") is not None:
            saida["erro_tipo"] = dados.get("erro_tipo")
        # Presente só quando o erro veio do preflight de política (P02
        # sub-entrega 9/N), nunca de uma falha de execução — permite ao
        # consumidor distinguir "bloqueado, não adianta repetir" de um bug.
        if dados.get("bloqueio_politica") is not None:
            saida["bloqueio_politica"] = dados.get("bloqueio_politica")
    else:
        saida["mensagem"] = (
            "Ainda processando. Consulte de novo em alguns segundos com o mesmo job_id."
        )
    return saida


def _reivindicar_job(db, ref):
    """Reivindica o job numa transacao que le o estado ATUAL do documento,
    nao o snapshot capturado no momento do evento (P01 passo 5 / achado A10).

    Devolve o dict do job se a reivindicacao teve sucesso (status ainda
    "processing" na leitura atual), ou `None` se nao havia nada a reivindicar
    -- job ja reivindicado por outra invocacao do mesmo evento, ja concluido,
    ou inexistente. `None` e o resultado correto e esperado diante de entrega
    duplicada do gatilho, nao um erro.

    Sem suporte a transacao real no backend, NAO ha fallback para leitura
    desprotegida (mesmo padrao de `core/idempotency.py`/`agent_requests.py`,
    achado A04): levanta `_SemSuporteTransacao` para o chamador decidir como
    sinalizar isso no job, em vez de arriscar executar a tool duas vezes.
    """
    if not hasattr(db, "transaction"):
        raise _SemSuporteTransacao()

    @firestore.transactional
    def _txn(transaction):
        snap_atual = ref.get(transaction=transaction)
        if not snap_atual.exists:
            return None
        dados_atuais = snap_atual.to_dict() or {}
        if dados_atuais.get("status") != "processing" or dados_atuais.get("reivindicado_em") is not None:
            return None
        transaction.update(ref, {"reivindicado_em": firestore.SERVER_TIMESTAMP})
        return dados_atuais

    return _txn(db.transaction())


class _SemSuporteTransacao(Exception):
    """Backend Firestore sem `.transaction()` -- ver `_reivindicar_job`."""


@firestore_fn.on_document_created(
    document=f"{COLECAO}/{{jobId}}",
    memory=options.MemoryOption.GB_1,
    timeout_sec=540,
)
def on_mcp_job_created(event: firestore_fn.Event[firestore_fn.DocumentSnapshot | None]):
    """Executa a tool longa fora do ciclo do request HTTP."""
    snap = event.data
    if snap is None or not snap.exists:
        return

    db = _db()
    # Deliberado: NAO usa `snap.reference` (o gatilho recebe esse snapshot de
    # um cliente Firestore proprio, interno ao SDK de functions -- ver
    # firebase_functions/firestore_fn.py -- separado do `db` obtido aqui).
    # Um documento e identificado pelo caminho, entao as duas referencias
    # apontam pro mesmo documento na pratica, mas reconstruir a partir de
    # `db` mantem uma unica origem para a leitura transacional, a escrita da
    # reivindicacao e todas as demais escritas desta funcao -- mesmo padrao
    # de `core/idempotency.py`/`agent_requests.py`, que sempre derivam a
    # referencia do `db` que tambem abre a transacao.
    ref = db.collection(COLECAO).document(snap.id)

    try:
        job = _reivindicar_job(db, ref)
    except _SemSuporteTransacao:
        print(f"[mcp_jobs] Backend Firestore sem suporte a transacao; job {ref.id} recusado (sem efeito).")
        ref.update({
            "status": "error",
            "erro": "Configuração do backend não permite reivindicar o job com segurança.",
            "erro_tipo": ERRO_TIPO_CONFIGURACAO,
            "concluido_em": int(time.time()),
            "expira_em": _expira_em(),
        })
        return
    except Exception as exc:  # noqa: BLE001
        # Falha real de transação (ex.: Aborted após esgotar tentativas). Sem
        # fallback para escrita desprotegida -- mesmo padrão A04 de
        # core/idempotency.py/agent_requests.py: melhor o job ficar visível
        # como "ainda processando" (o próximo poll de ler_job não mente) do
        # que arriscar reexecutar a tool ou sobrescrever uma reivindicação
        # concorrente que tenha tido sucesso.
        print(f"[mcp_jobs] Falha ao reivindicar job {ref.id}: {exc}")
        return

    if job is None:
        # Nada a reivindicar: evento duplicado chegando depois que outra
        # invocação já reivindicou/concluiu este job, ou o documento já não
        # existe mais. Sem efeito -- é o comportamento correto diante de
        # entrega "ao menos uma vez" do gatilho.
        print(f"[mcp_jobs] Job {ref.id} não reivindicado (já processado ou fora de 'processing').")
        return

    tool = job.get("tool")

    try:
        from autonomy.contracts import Decisao, TipoPrincipal
        from autonomy.policy import decisao_piso
        from tools.hermes_tools import execute
        from tools.tool_context import ToolContext, principal_de

        ctx = ToolContext(
            user_uid=job.get("uid"),
            session_id=job.get("session_id"),
            task_id=job.get("task_id"),
            canal="mcp",
        )
        argumentos = job.get("arguments") or {}

        # P02 sub-entrega 9/N (passo 1): este trigger retoma uma tool MCP
        # assincronamente, ja fora do ciclo do request HTTP original — sem
        # NENHUMA garantia de que o dono ainda esta acompanhando a sessao. E
        # exatamente o caso que a docstring de
        # `tools/tool_context.py::principal_de` (sub-entrega 5/N) cita como
        # motivo para o tipo do principal ser sempre explicito, nunca
        # inferido de `ctx.canal` (que aqui e "mcp", igual ao do cliente
        # interativo em `mcp_server.py`). Decisao de Andre: sempre
        # RUNNER_SERVICO, sempre `origem_humana=False` — nunca
        # DONO_INTERATIVO/CLIENTE_ASSISTIDO so porque o uid bate com o dono.
        principal = principal_de(ctx, TipoPrincipal.RUNNER_SERVICO, origem_humana=False)

        # Preflight do motor de politica (mesmo padrao de
        # `mcp_server.py::_decisao_piso_mcp`), passo 6 do P02: chamadas
        # internas tambem passam pela politica antes do efeito.
        # `decisao_piso` e fail-safe por dentro (nunca deixa excecao escapar)
        # e devolve `None` quando `tool` nao esta classificado em
        # `autonomy.policy.CLASSE_EFEITO_PISO` — hoje nenhuma das tres tools
        # que passam por este trigger (gerar_relatorio,
        # ler_documento_na_integra, buscar_e_analisar_email) esta
        # classificada, entao este bloco sempre recebe `None` e NAO muda
        # nenhum comportamento hoje; fica pronto para quando uma tool
        # assincrona for classificada no piso.
        #
        # IMPORTANTE (achado da revisão adversarial desta sub-entrega):
        # bloqueia em QUALQUER decisão diferente de ALLOW, não só
        # DENY/PREPARE_ONLY. `mcp_server.py::_handle_tools_call` deixa
        # REQUIRE_APPROVAL cair no fluxo abaixo porque esse fluxo cria uma
        # confirmação real e espera o "sim" do dono antes de executar — mas
        # este trigger não tem NENHUM mecanismo de confirmação: o fallthrough
        # aqui é execução direta. Copiar o mesmo "só bloqueia DENY/PREPARE_
        # ONLY" deste ponto executaria sem aprovação no dia em que uma tool
        # assíncrona for classificada no piso e a autonomia estiver ATIVA
        # (o caso mais comum, não o raro) — exatamente o cenário que este
        # preflight existe para impedir.
        decisao = decisao_piso(db, principal, tool, argumentos)
        if decisao is not None and decisao.decision != Decisao.ALLOW:
            mensagens = {
                Decisao.DENY: "Ação bloqueada pela política de autonomia vigente.",
                Decisao.PREPARE_ONLY: (
                    "Autonomia está em modo somente-preparação: esta ação não "
                    "pode ser executada automaticamente agora."
                ),
                Decisao.REQUIRE_APPROVAL: (
                    "Esta ação exige aprovação explícita do dono antes de "
                    "executar, mas este canal (job assíncrono de MCP) não tem "
                    "mecanismo de confirmação — só o canal síncrono original "
                    "(mcp_server.py) pode coletar essa aprovação."
                ),
                Decisao.DEFER: (
                    "Autonomia adiou esta ação (defer) — não pode ser "
                    "executada automaticamente agora."
                ),
            }
            base = mensagens.get(decisao.decision, "Ação não permitida pela política de autonomia vigente.")
            erro = (base + " " + (decisao.motivo_legivel or "")).strip()
            ref.update({
                "status": "error",
                "erro": erro,
                "erro_tipo": ERRO_TIPO_POLITICA,
                # Campo aditivo (não muda o contrato de `status`/`erro` que
                # `ler_job` já lê): permite a um consumidor programático
                # distinguir "bloqueado pela política, não adianta repetir"
                # de um erro/bug genuíno, sem precisar casar texto livre.
                "bloqueio_politica": {
                    "decision": decisao.decision.value,
                    "reason_code": decisao.reason_code,
                },
                "concluido_em": int(time.time()),
                "expira_em": _expira_em(),
            })
            print(
                f"[mcp_jobs] {tool} bloqueada pela politica "
                f"(job={job.get('job_id')}, decision={decisao.decision.value}, reason={decisao.reason_code})"
            )
            return

        resultado = execute(tool, argumentos, ctx)

        # P01 passo 5 / achado A10 ("falso sucesso"): as tres tools deste
        # trigger nao levantam excecao nem devolvem um dict com "erro"
        # quando falham -- devolvem uma string cujo CONTEUDO e uma mensagem
        # de erro (mesma convencao de `mcp_server.py::_looks_like_error`
        # para o caminho sincrono). Sem esta checagem, o job virava "done"
        # com a mensagem de erro no lugar do resultado.
        if isinstance(resultado, dict) and resultado.get("erro"):
            erro_detectado = str(resultado.get("erro"))
        elif isinstance(resultado, str) and _parece_mensagem_de_erro(resultado):
            erro_detectado = resultado
        else:
            erro_detectado = None

        if erro_detectado is not None:
            ref.update({
                "status": "error",
                "erro": erro_detectado,
                "erro_tipo": ERRO_TIPO_RESULTADO,
                "concluido_em": int(time.time()),
                "expira_em": _expira_em(),
            })
            print(
                f"[mcp_jobs] {tool} devolveu resultado no formato de erro, "
                f"sem levantar excecao (job={job.get('job_id')})"
            )
            return

        resultado_final, truncado = _preparar_resultado(resultado)

        ref.update({
            "status": "done",
            "resultado": resultado_final,
            "truncado": truncado,
            "concluido_em": int(time.time()),
            "expira_em": _expira_em(),
        })
        tamanho = len(resultado_final) if isinstance(resultado_final, str) else "estruturado"
        print(f"[mcp_jobs] {tool} concluida (job={job.get('job_id')}, {tamanho} chars)")
    except Exception as exc:  # noqa: BLE001
        print(f"[mcp_jobs] Falha em {tool} (job={job.get('job_id')}): {exc}")
        ref.update({
            "status": "error",
            "erro": str(exc),
            "erro_tipo": ERRO_TIPO_EXCECAO,
            "concluido_em": int(time.time()),
            "expira_em": _expira_em(),
        })
