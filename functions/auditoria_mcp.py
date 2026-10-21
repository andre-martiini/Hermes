"""Registro das chamadas MCP no `mcp_audit_log`: a causa de cada erro e onde gravar.

A Retro Semanal de 04/10/2026 contou 421 erros em 3.059 chamadas; 398 eram de
testes locais que gravavam no Firestore de produção, e nenhum registro dizia a
causa. Aqui o registro passa a guardar o tipo e um resumo do erro, separa a
recusa esperada (id inexistente, argumento errado, política, conflito) da falha
real, e só grava no Firestore de verdade quando roda na nuvem.
"""

import json
import os
import re

COLECAO = "mcp_audit_log"
_RESUMO_MAX = 200

# Ferramentas que dependem de site ou serviço de terceiros: falha delas não é
# defeito do Gaspar, mas também não é engano de quem chamou.
_EXTERNAS = {"ler_pagina_web", "pesquisar_internet"}

_NAO_ENCONTRADO = re.compile(r"n[aã]o (?:foi )?encontrad|not[ _]found|inexistente|n[aã]o existe", re.I)
_NAO_MONITORADO = re.compile(r"n[aã]o (?:est[aá] )?monitorad|allowlist", re.I)
_CONFLITO = re.compile(r"modificad[oa] depois|conflito", re.I)
# Pedido sobre algo que já mudou de estado (rascunho já descartado, por exemplo):
# o Gaspar recusou certo; quem chamou é que estava com a informação velha.
_JA_RESOLVIDO = re.compile(r"\bj[aá] (?:decidid|descartad|aprovad|enviad|cancelad)", re.I)
_ARGUMENTOS = re.compile(
    r"obrigat[oó]ri|inv[aá]lid|invalid|informe |use um de|nenhum campo|nada para mudar|vazi[oa]|formato",
    re.I,
)
_POLITICA = re.compile(r"pol[ií]tica|bloquead", re.I)
_NUMERO_LONGO = re.compile(r"\d{8,}")

# erro_tipo -> é recusa esperada? (o resto é falha real)
RECUSAS = {"nao_encontrado", "nao_monitorado", "conflito", "ja_resolvido", "argumentos", "politica",
           "job_com_falha"}


def em_producao() -> bool:
    return bool(os.environ.get("K_SERVICE") or os.environ.get("FUNCTION_TARGET"))


def destino(db):
    """O banco onde gravar: o injetado (testes) ou, só na nuvem, o de produção.

    Fora da nuvem e sem banco injetado não grava nada: rodar um arquivo de teste
    sozinho pulava o bloqueio de credencial dos testes e sujava a produção.
    """
    if db is not None:
        return db
    if not em_producao():
        return None
    from firebase_admin import firestore

    return firestore.client()


def _mensagem(resultado) -> str:
    if isinstance(resultado, dict):
        msg = resultado.get("erro") or resultado.get("error")
        return str(msg) if msg else json.dumps(resultado, ensure_ascii=False, default=str)
    texto = str(resultado or "").strip()
    for prefixo in ("ERRO|", "⚠️"):
        if texto.startswith(prefixo):
            texto = texto[len(prefixo):].strip()
    if texto.startswith("{"):
        try:
            dados = json.loads(texto)
        except ValueError:
            return texto
        if isinstance(dados, dict) and (dados.get("erro") or dados.get("error")):
            return str(dados.get("erro") or dados.get("error"))
    return texto


def resumir(texto) -> str:
    texto = _NUMERO_LONGO.sub("<número>", " ".join(str(texto or "").split()))
    return texto[:_RESUMO_MAX]


def _tipo_pela_mensagem(tool: str, msg: str) -> str:
    if _NAO_ENCONTRADO.search(msg):
        return "nao_encontrado"
    if _NAO_MONITORADO.search(msg):
        return "nao_monitorado"
    if _CONFLITO.search(msg):
        return "conflito"
    if _JA_RESOLVIDO.search(msg):
        return "ja_resolvido"
    if _ARGUMENTOS.search(msg):
        return "argumentos"
    if _POLITICA.search(msg):
        return "politica"
    if tool in _EXTERNAS:
        return "externo"
    return "resultado_tool"


def classificar_erro(tool: str, resultado=None, excecao: BaseException | None = None) -> dict:
    """Tipo, resumo e se o erro é recusa esperada, para gravar junto da chamada."""
    if excecao is not None:
        tipo, msg = "excecao", str(excecao)
    else:
        msg = _mensagem(resultado)
        status = resultado.get("status") if isinstance(resultado, dict) else None
        if status == "not_found":
            tipo = "nao_encontrado"
        elif tool == "consultar_job" and status == "error":
            # A falha do job já é registrada uma vez, quando ele falha; cada
            # consulta seguinte só relata o mesmo fato.
            tipo = "job_com_falha"
        elif tool == "consultar_envio_whatsapp" and status == "failed":
            tipo = "envio_com_falha"
        elif isinstance(resultado, dict) and resultado.get("bloqueio_politica"):
            tipo = "politica"
        else:
            tipo = _tipo_pela_mensagem(tool, msg)
    return {"erro_tipo": tipo, "erro_resumo": resumir(msg), "recusa_esperada": tipo in RECUSAS}


def registrar_falha_job(db, *, uid, tool, job_id, erro, erro_tipo) -> None:
    """Uma entrada por job que falhou, no momento da falha, e não por consulta."""
    try:
        alvo = destino(db)
        if alvo is None:
            return
        from firebase_admin import firestore

        alvo.collection(COLECAO).add({
            "uid": uid,
            "tool": tool,
            "arguments": {"job_id": job_id},
            "latency_ms": 0.0,
            "is_error": True,
            "origem": "job",
            "erro_tipo": erro_tipo,
            "erro_resumo": resumir(erro),
            "recusa_esperada": erro_tipo == "politica",
            "timestamp": firestore.SERVER_TIMESTAMP,
        })
    except Exception as exc:  # noqa: BLE001 — auditoria nunca derruba o job
        print(f"[auditoria_mcp] Falha ao registrar falha do job {job_id}: {exc}")
