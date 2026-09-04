"""Retrospectiva semanal de execuções do agente e auditoria de tools MCP.

Analisa agent_runs e mcp_audit_log dos últimos 7 dias corridos.
Executado aos domingos às 20h via Cloud Scheduler.
Propõe ajuste de POP via correcoes_pendentes se houver padrão concreto repetido.
Nunca aplica nada diretamente — a validação e consolidação ocorrem no Motor de Evolução.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from firebase_admin import firestore
from firebase_functions import options, scheduler_fn
from google import genai
from google.genai import types

from gemini_cost_controls import (
    GEMINI_STRUCTURED_MODEL,
    generate_content_logged,
)

_TZ_SP = ZoneInfo("America/Sao_Paulo")
COLLECTION_RETROS = "retros_agente"
COLLECTION_CORRECOES = "correcoes_pendentes"
COLLECTION_RUNS = "agent_runs"
COLLECTION_AUDIT = "mcp_audit_log"
FEATURE_RETRO_AGENTE = "retro_agente"


def _parse_dt(val: Any) -> datetime | None:
    """Converte valores variados de timestamp/datetime para datetime ciente de timezone (UTC)."""
    if val is None:
        return None
    if isinstance(val, datetime):
        if val.tzinfo is None:
            return val.replace(tzinfo=timezone.utc)
        return val.astimezone(timezone.utc)
    if isinstance(val, str):
        try:
            s = val.strip().replace("Z", "+00:00")
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            return None
    return None


def _extrair_json_obj(raw_text: str) -> dict | None:
    """Extrai objeto JSON de resposta textual defensivamente com regex."""
    if not raw_text:
        return None
    cleaned = raw_text.strip()
    if "```" in cleaned:
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE)
        cleaned = cleaned.strip()

    match = re.search(r"\{[\s\S]*\}", cleaned)
    if match:
        cleaned = match.group(0)

    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return None


def coletar_metricas_semana(db, now_utc: datetime) -> tuple[dict, dict]:
    """Coleta e agrega execuções de agent_runs e mcp_audit_log nos últimos 7 dias."""
    cutoff = now_utc - timedelta(days=7)

    # 1. Coleta e agregação de agent_runs
    runs_docs: list[Any] = []
    try:
        runs_docs = list(db.collection(COLLECTION_RUNS).where("criado_em", ">=", cutoff).stream())
    except Exception:
        try:
            runs_docs = list(db.collection(COLLECTION_RUNS).stream())
        except Exception as exc:
            print(f"[RetroAgente] Falha ao consultar agent_runs: {exc}")

    rotinas_map: dict[str, dict] = {}
    total_runs = 0
    total_erros_rotinas = 0

    for doc in runs_docs:
        d = doc.to_dict() if hasattr(doc, "to_dict") else doc
        if not isinstance(d, dict):
            continue

        ts = _parse_dt(d.get("criado_em") or d.get("finalizado_em") or d.get("iniciado_em"))
        if ts is not None and ts < cutoff:
            continue

        total_runs += 1
        rotina_nome = str(d.get("rotina") or "desconhecida").strip()
        status = str(d.get("status") or "sucesso").strip().lower()
        erro_msg = str(d.get("erro") or "").strip()

        eh_erro = (status == "erro") or bool(erro_msg)
        if eh_erro:
            total_erros_rotinas += 1

        if rotina_nome not in rotinas_map:
            rotinas_map[rotina_nome] = {
                "total": 0,
                "status": {},
                "erros": [],
            }

        rotinas_map[rotina_nome]["total"] += 1
        rotinas_map[rotina_nome]["status"][status] = rotinas_map[rotina_nome]["status"].get(status, 0) + 1

        if erro_msg:
            err_list = rotinas_map[rotina_nome]["erros"]
            if erro_msg not in err_list and len(err_list) < 3:
                err_list.append(erro_msg)

    metricas_rotinas = {
        "total_runs": total_runs,
        "total_erros": total_erros_rotinas,
        "rotinas": rotinas_map,
    }

    # 2. Coleta e agregação de mcp_audit_log
    audit_docs: list[Any] = []
    try:
        audit_docs = list(db.collection(COLLECTION_AUDIT).where("timestamp", ">=", cutoff).stream())
    except Exception:
        try:
            audit_docs = list(db.collection(COLLECTION_AUDIT).stream())
        except Exception as exc:
            print(f"[RetroAgente] Falha ao consultar mcp_audit_log: {exc}")

    tools_map: dict[str, dict] = {}
    total_calls = 0
    total_erros_tools = 0

    for doc in audit_docs:
        d = doc.to_dict() if hasattr(doc, "to_dict") else doc
        if not isinstance(d, dict):
            continue

        ts = _parse_dt(d.get("timestamp"))
        if ts is not None and ts < cutoff:
            continue

        total_calls += 1
        tool_nome = str(d.get("tool") or "desconhecida").strip()
        is_error = bool(d.get("is_error", False))
        latency = float(d.get("latency_ms") or 0.0)

        if is_error:
            total_erros_tools += 1

        if tool_nome not in tools_map:
            tools_map[tool_nome] = {
                "total": 0,
                "erros": 0,
                "latencias": [],
            }

        tools_map[tool_nome]["total"] += 1
        if is_error:
            tools_map[tool_nome]["erros"] += 1
        tools_map[tool_nome]["latencias"].append(latency)

    tools_agregadas: dict[str, dict] = {}
    for tool, dados in tools_map.items():
        tot = dados["total"]
        errs = dados["erros"]
        lats = dados["latencias"]
        lat_med = round(sum(lats) / len(lats), 1) if lats else 0.0
        lat_max = round(max(lats), 1) if lats else 0.0
        taxa = round(errs / tot, 3) if tot > 0 else 0.0

        tools_agregadas[tool] = {
            "total": tot,
            "erros": errs,
            "taxa_erro": taxa,
            "latencia_media_ms": lat_med,
            "latencia_max_ms": lat_max,
        }

    metricas_tools = {
        "total_calls": total_calls,
        "total_erros": total_erros_tools,
        "tools": tools_agregadas,
    }

    return metricas_rotinas, metricas_tools


def formatar_texto_agregado(
    inicio_iso: str,
    fim_iso: str,
    metricas_rotinas: dict,
    metricas_tools: dict,
) -> str:
    """Monta texto-fonte contendo exclusivamente dados agregados sem expor argumentos sensíveis."""
    linhas = [
        f"PERÍODO: {inicio_iso} até {fim_iso}",
        "",
        "ROTINAS AGENDADAS DO AGENTE (agent_runs):",
        f"- Total de execuções: {metricas_rotinas.get('total_runs', 0)}",
        f"- Total de falhas/erros: {metricas_rotinas.get('total_erros', 0)}",
    ]

    rotinas = metricas_rotinas.get("rotinas", {})
    if not rotinas:
        linhas.append("  (nenhuma rotina registrada)")
    else:
        for rotina, dados in rotinas.items():
            status_str = ", ".join(f"{k}: {v}" for k, v in dados.get("status", {}).items())
            errs = dados.get("erros", [])
            err_str = f" | Erros: {'; '.join(errs)}" if errs else ""
            linhas.append(f"  * {rotina}: {dados.get('total', 0)} execuções ({status_str}){err_str}")

    linhas.extend([
        "",
        "FERRAMENTAS MCP (mcp_audit_log):",
        f"- Total de chamadas: {metricas_tools.get('total_calls', 0)}",
        f"- Total com erro reportado: {metricas_tools.get('total_erros', 0)}",
    ])

    tools = metricas_tools.get("tools", {})
    if not tools:
        linhas.append("  (nenhuma chamada de ferramenta registrada)")
    else:
        for tool, dados in tools.items():
            taxa_pct = round(dados.get("taxa_erro", 0) * 100, 1)
            linhas.append(
                f"  * {tool}: {dados.get('total', 0)} chamadas, "
                f"latência média {dados.get('latencia_media_ms', 0)}ms (máx {dados.get('latencia_max_ms', 0)}ms), "
                f"{dados.get('erros', 0)} erros (taxa {taxa_pct}%)"
            )

    return "\n".join(linhas)


def construir_prompt_retro(texto_agregado: str) -> str:
    """Monta o prompt para o Gemini com a regra inegociável de proposta nula sem padrão repetido."""
    return f"""Você é o analista de retrospectiva semanal do sistema autônomo Hermes/Jarvis.
Sua missão é analisar o desempenho das rotinas agendadas do agente e o uso de ferramentas MCP na semana concluída.

DADOS AGREGADOS DA SEMANA:
{texto_agregado}

INSTRUÇÕES DE RESPOSTA:
Retorne estritamente um único objeto JSON com o formato:
{{
  "resumo": "2 a 3 frases objetivas sintetizando estabilidade, volume de execuções e principais gargalos ou sucessos da semana.",
  "proposta_pop": null OU {{
    "area_tematica": "Área correspondente (ex: 'rotinas_agente', 'mcp', 'integracoes')",
    "titulo_procedimento": "Título curto do procedimento a criar ou ajustar",
    "correcao_descrita": "Descrição clara do problema recorrente e o que deve ser corrigido",
    "novo_conteudo_proposto": "Texto ou diretriz concreta proposta para o procedimento",
    "justificativa": "Evidência concreta e quantificada das falhas (ex: 'Rotina X falhou 3 vezes pelo erro Y')"
  }}
}}

REGRA INEGOCIÁVEL PARA proposta_pop:
1. SÓ proponha ajuste se houver um padrão CONCRETO e REPETIDO (ex.: a mesma rotina falhando ≥3 vezes pelo mesmo motivo, ou uma ferramenta com taxa de falha sistemática anormal em múltiplas tentativas).
2. Se as execuções foram normais, ou se os erros foram isolados/esporádicos (<3 repetições), proposta_pop DEVE SER ESTRITAMENTE null.
3. NUNCA invente ou force uma sugestão genérica só para preencher o campo. Silêncio/null é o resultado padrão e esperado na maioria das semanas."""


def executar_retro_semanal(db, now: datetime | None = None, client: Any = None) -> dict:
    """Executa a retrospectiva semanal completa do agente."""
    if now is None:
        now_utc = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now_utc = now.replace(tzinfo=timezone.utc)
    else:
        now_utc = now.astimezone(timezone.utc)

    now_sp = now_utc.astimezone(_TZ_SP)
    cutoff = now_utc - timedelta(days=7)
    inicio_iso = cutoff.isoformat()
    fim_iso = now_utc.isoformat()

    # 1. Coleta métricas agregadas
    metricas_rotinas, metricas_tools = coletar_metricas_semana(db, now_utc)

    # 2. Silêncio por padrão se não houver execuções de agent_runs
    if metricas_rotinas.get("total_runs", 0) == 0:
        print("[RetroAgente] Nenhuma execução de agent_runs nos últimos 7 dias. Encerrando em silêncio.")
        return {
            "status": "silencio_sem_dados",
            "total_runs": 0,
            "mensagem": "Nenhuma execução de agent_runs no período.",
        }

    # 3. Monta texto-fonte com dados puramente agregados
    texto_agregado = formatar_texto_agregado(inicio_iso, fim_iso, metricas_rotinas, metricas_tools)
    prompt = construir_prompt_retro(texto_agregado)

    # 4. Resolve client Gemini
    if client is None:
        api_key = None
        try:
            from main import _cached_doc_get
            keys_doc = _cached_doc_get(db, "system", "api_keys")
            if keys_doc.exists:
                api_key = (keys_doc.to_dict() or {}).get("gemini_api_key")
        except Exception:
            pass
        if not api_key:
            api_key = os.environ.get("GEMINI_API_KEY")

        if api_key:
            try:
                client = genai.Client(api_key=api_key)
            except Exception as exc:
                print(f"[RetroAgente] Falha ao inicializar client genai: {exc}")

    # 5. Chama Gemini com controle de custo
    raw_response_text = ""
    if client is not None:
        try:
            response = generate_content_logged(
                client,
                model=GEMINI_STRUCTURED_MODEL,
                contents=prompt,
                feature=FEATURE_RETRO_AGENTE,
                db=db,
                config=types.GenerateContentConfig(
                    temperature=0.2,
                    max_output_tokens=1000,
                    response_mime_type="application/json",
                ),
            )
            raw_response_text = getattr(response, "text", "") or ""
        except Exception as exc:
            print(f"[RetroAgente] Exceção na chamada Gemini: {exc}")

    # 6. Parse defensivo
    parsed = _extrair_json_obj(raw_response_text) if raw_response_text else None
    if isinstance(parsed, dict) and parsed.get("resumo"):
        resumo = str(parsed.get("resumo")).strip()
        proposta_bruta = parsed.get("proposta_pop")
        if isinstance(proposta_bruta, dict):
            tit = str(proposta_bruta.get("titulo_procedimento") or "").strip()
            cont = str(proposta_bruta.get("novo_conteudo_proposto") or "").strip()
            if tit and cont:
                proposta_pop = {
                    "area_tematica": str(proposta_bruta.get("area_tematica") or "rotinas_agente").strip(),
                    "titulo_procedimento": tit,
                    "correcao_descrita": str(proposta_bruta.get("correcao_descrita") or "").strip(),
                    "novo_conteudo_proposto": cont,
                    "justificativa": str(proposta_bruta.get("justificativa") or "").strip(),
                }
            else:
                proposta_pop = None
        else:
            proposta_pop = None
    else:
        tot_r = metricas_rotinas.get("total_runs", 0)
        tot_err = metricas_rotinas.get("total_erros", 0)
        tot_c = metricas_tools.get("total_calls", 0)
        tot_tc_err = metricas_tools.get("total_erros", 0)
        resumo = (
            f"Na última semana foram registradas {tot_r} execuções de rotinas agendadas "
            f"({tot_err} com erro) e {tot_c} chamadas de ferramentas MCP ({tot_tc_err} com erro)."
        )
        proposta_pop = None

    # 7. Persiste em retros_agente/{id}
    retro_id = now_sp.strftime("retro_%Y_%m_%d")
    payload_retro = {
        "id": retro_id,
        "periodo_inicio": inicio_iso,
        "periodo_fim": fim_iso,
        "resumo": resumo,
        "metricas": {
            "total_runs": metricas_rotinas.get("total_runs", 0),
            "total_erros_rotinas": metricas_rotinas.get("total_erros", 0),
            "rotinas": metricas_rotinas.get("rotinas", {}),
            "total_mcp_calls": metricas_tools.get("total_calls", 0),
            "total_erros_tools": metricas_tools.get("total_erros", 0),
            "tools": metricas_tools.get("tools", {}),
        },
        "proposta_pop": proposta_pop,
        "criado_em": firestore.SERVER_TIMESTAMP,
    }

    try:
        db.collection(COLLECTION_RETROS).document(retro_id).set(payload_retro, merge=True)
    except Exception as exc:
        print(f"[RetroAgente] Falha ao persistir em {COLLECTION_RETROS}: {exc}")

    # 8. Se houver proposta concreta, grava em correcoes_pendentes
    corr_id = None
    if proposta_pop:
        try:
            corr_id = str(uuid.uuid4())[:12]
            corr_payload = {
                "id": corr_id,
                "area_tematica": proposta_pop.get("area_tematica"),
                "titulo_procedimento": proposta_pop.get("titulo_procedimento"),
                "correcao_descrita": proposta_pop.get("correcao_descrita"),
                "novo_conteudo_proposto": proposta_pop.get("novo_conteudo_proposto"),
                "justificativa_usuario": (
                    proposta_pop.get("justificativa")
                    or f"Proposta gerada automaticamente pelo retro semanal do agente ({retro_id})."
                ),
                "status": "pendente",
                "data_criacao": firestore.SERVER_TIMESTAMP,
                "session_id": "",
                "task_id": "",
                "origem": "retro_agente",
                "retro_id": retro_id,
            }
            db.collection(COLLECTION_CORRECOES).document(corr_id).set(corr_payload)
            print(f"[RetroAgente] Proposta de POP registrada em correcoes_pendentes/{corr_id}")
        except Exception as exc:
            print(f"[RetroAgente] Falha ao gravar proposta em correcoes_pendentes: {exc}")

    # 9. Envia UMA mensagem informativa no Telegram (sem botões)
    telegram_sent = False
    try:
        from main import _resolve_default_telegram_chat_id, _send_telegram_message_raw
        chat_id = _resolve_default_telegram_chat_id(db)
        if chat_id:
            tot_r = metricas_rotinas.get("total_runs", 0)
            tot_err = metricas_rotinas.get("total_erros", 0)
            tot_c = metricas_tools.get("total_calls", 0)
            tot_tc_err = metricas_tools.get("total_erros", 0)

            msg = (
                f"📊 <b>Retro Semanal do Agente</b>\n\n"
                f"{resumo}\n\n"
                f"• Execuções de rotinas: {tot_r} ({tot_err} com falha)\n"
                f"• Chamadas MCP: {tot_c} ({tot_tc_err} com erro)"
            )
            if proposta_pop:
                tit_pop = proposta_pop.get("titulo_procedimento")
                msg += f"\n\n⚙️ <i>Uma proposta de ajuste de POP para '<b>{tit_pop}</b>' foi registrada na fila de evolução autônoma para validação.</i>"

            _send_telegram_message_raw(db, chat_id, msg)
            telegram_sent = True
    except Exception as exc:
        print(f"[RetroAgente] Falha ao enviar mensagem no Telegram: {exc}")

    return {
        "status": "ok",
        "retro_id": retro_id,
        "proposta_pop": proposta_pop,
        "correcao_id": corr_id,
        "resumo": resumo,
        "telegram_sent": telegram_sent,
    }


@scheduler_fn.on_schedule(
    schedule="0 20 * * 0",
    timezone="America/Sao_Paulo",
    memory=options.MemoryOption.MB_512,
    timeout_sec=180,
)
def retro_semanal_agente(event: scheduler_fn.ScheduledEvent) -> None:
    """Retrospectiva semanal de execuções do agente e ferramentas MCP aos domingos às 20h."""
    db = firestore.client()
    executar_retro_semanal(db)
