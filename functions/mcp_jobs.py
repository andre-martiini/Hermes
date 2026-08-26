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
        from tools.hermes_tools import execute
        from tools.tool_context import ToolContext

        ctx = ToolContext(
            user_uid=job.get("uid"),
            session_id=job.get("session_id"),
            task_id=job.get("task_id"),
            canal="mcp",
        )
        resultado = execute(tool, job.get("arguments") or {}, ctx)
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
