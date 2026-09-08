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
"""

from __future__ import annotations

import json
import secrets
import time

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


def _db():
    return firestore.client()


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

    job = snap.to_dict() or {}
    if job.get("status") != "processing":
        return

    ref = snap.reference
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
        decisao = decisao_piso(_db(), principal, tool, argumentos)
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
                # Campo aditivo (não muda o contrato de `status`/`erro` que
                # `ler_job` já lê): permite a um consumidor programático
                # distinguir "bloqueado pela política, não adianta repetir"
                # de um erro/bug genuíno, sem precisar casar texto livre.
                "bloqueio_politica": {
                    "decision": decisao.decision.value,
                    "reason_code": decisao.reason_code,
                },
                "concluido_em": int(time.time()),
                "expira_em": int(time.time()) + _TTL_SEC,
            })
            print(
                f"[mcp_jobs] {tool} bloqueada pela politica "
                f"(job={job.get('job_id')}, decision={decisao.decision.value}, reason={decisao.reason_code})"
            )
            return

        resultado = execute(tool, argumentos, ctx)
        texto = resultado if isinstance(resultado, str) else json.dumps(
            resultado, ensure_ascii=False, default=str
        )
        truncado = len(texto) > _MAX_RESULTADO_CHARS
        if truncado:
            texto = texto[:_MAX_RESULTADO_CHARS] + "\n\n[...resultado truncado...]"

        ref.update({
            "status": "done",
            "resultado": texto,
            "truncado": truncado,
            "concluido_em": int(time.time()),
            "expira_em": int(time.time()) + _TTL_SEC,
        })
        print(f"[mcp_jobs] {tool} concluida (job={job.get('job_id')}, {len(texto)} chars)")
    except Exception as exc:  # noqa: BLE001
        print(f"[mcp_jobs] Falha em {tool} (job={job.get('job_id')}): {exc}")
        ref.update({
            "status": "error",
            "erro": str(exc),
            "concluido_em": int(time.time()),
            "expira_em": int(time.time()) + _TTL_SEC,
        })
