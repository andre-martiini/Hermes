"""
Triagem e indexação de conversas do WhatsApp capturadas por
services/whatsapp-capture/index.js (coleção `whatsapp_messages`).

Fluxo: agrupa mensagens novas por conversa em janelas, classifica cada
janela com uma única chamada de IA barata (relevante para uma ação? vale
lembrar depois? ruído?), propõe vínculo com uma ação via o motor
compartilhado de sugestões (email_action_linker.py) quando aplicável, e
grava um digest por janela em `whatsapp_digests` — vetorizado para busca
posterior pelo copiloto (`buscar_conversas_whatsapp`, ver main.py).

Mensagens cruas nunca são indexadas individualmente: são ruidosas demais
para RAG e caras demais para embeddar uma a uma — só o digest da janela é
vetorizado, no mesmo espírito de `knowledge_nodes`/`indice_artefatos`.
"""

import json
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from gemini_cost_controls import GEMINI_LIGHT_MODEL, generate_content_logged

FEATURE_TRIAGE = "whatsapp_ingest.triage"
FEATURE_DIGEST_EMBEDDING = "whatsapp_ingest.digest_embedding"

DEFAULT_MAX_WINDOWS_PER_PASS = 10
DEFAULT_MIN_CONFIDENCE = 0.6
DEFAULT_FIRST_RUN_LOOKBACK_HOURS = 24
MIN_WINDOW_TEXT_CHARS = 20

DIGEST_COLLECTION = "whatsapp_digests"
DIGEST_EMBEDDING_FIELD = "embedding"
DIGEST_EMBEDDING_DIM = 768

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _valid_date(value) -> str | None:
    s = str(value or "").strip()
    return s if _DATE_RE.match(s) else None


def _sanitize_itens_de_acao(raw) -> list[dict]:
    out = []
    for item in (raw or [])[:8]:
        if not isinstance(item, dict):
            continue
        descricao = str(item.get("descricao") or "").strip()
        if not descricao:
            continue
        out.append({
            "descricao": descricao[:300],
            "responsavel": str(item.get("responsavel") or "").strip()[:80],
            "prazo": _valid_date(item.get("prazo")),
        })
    return out


def _sanitize_decisoes(raw) -> list[str]:
    return [str(d).strip()[:300] for d in (raw or [])[:8] if str(d).strip()]


def _sanitize_datas_mencionadas(raw) -> list[dict]:
    out = []
    for item in (raw or [])[:8]:
        if not isinstance(item, dict):
            continue
        data = _valid_date(item.get("data"))
        if not data:
            continue
        out.append({"data": data, "contexto": str(item.get("contexto") or "").strip()[:200]})
    return out


def _sanitize_mutacoes_propostas(raw) -> dict | None:
    """
    Converte o `mutacoes_propostas` bruto do modelo (pode vir mal formado ou
    com placeholders) num dict pronto para virar `email_action_suggestions.mutacoes_propostas`
    — mesmo formato que `email_action_linker.py:apply_suggestion` sabe aplicar
    (novas etapas no `plano_acao`, ajuste de `data_limite`, lembrete). Retorna
    None quando não há nenhuma mutação de fato (evita oferecer um botão de
    "aplicar mudanças" vazio).
    """
    if not isinstance(raw, dict):
        return None
    novas_etapas = [str(e).strip()[:300] for e in (raw.get("novas_etapas") or [])[:6] if str(e).strip()]
    nova_data_limite = _valid_date(raw.get("nova_data_limite"))
    lembrete_raw = raw.get("lembrete_sugerido")
    lembrete_sugerido = None
    if isinstance(lembrete_raw, dict):
        data = _valid_date(lembrete_raw.get("data"))
        texto = str(lembrete_raw.get("texto") or "").strip()[:200]
        if data and texto:
            lembrete_sugerido = {"data": data, "texto": texto}
    if not novas_etapas and not nova_data_limite and not lembrete_sugerido:
        return None
    return {
        "novas_etapas": novas_etapas,
        "nova_data_limite": nova_data_limite,
        "lembrete_sugerido": lembrete_sugerido,
    }


def _ts_to_iso(ts) -> str:
    return ts.isoformat() if hasattr(ts, "isoformat") else str(ts or "")


def _load_settings(db) -> dict:
    from main import _cached_doc_get

    doc = _cached_doc_get(db, "system", "settings")
    cfg = ((doc.to_dict() or {}) if doc.exists else {}).get("whatsapp_ingest") or {}
    return {
        "enabled": bool(cfg.get("enabled", False)),
        "max_windows_per_pass": int(cfg.get("max_windows_per_pass", DEFAULT_MAX_WINDOWS_PER_PASS)),
        "min_confidence": float(cfg.get("min_confidence", DEFAULT_MIN_CONFIDENCE)),
    }


def _build_triage_prompt(chat_name: str, messages: list[dict], candidates_text: str) -> str:
    lines = []
    for m in messages[-40:]:
        quem = "Eu" if m.get("from_me") else (m.get("author_name") or "Contato")
        conteudo = str(m.get("content") or "").strip()
        if not conteudo:
            conteudo = f"[{m.get('message_type') or 'mídia'}]"
        lines.append(f"{quem}: {conteudo[:500]}")
    conversa = "\n".join(lines)
    hoje = datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%Y-%m-%d")

    return f"""Você é o Hermes, assistente pessoal, analisando uma janela de mensagens do WhatsApp
da conversa "{chat_name}". Hoje é {hoje}.

AÇÕES ATIVAS DO USUÁRIO:
{candidates_text or "(nenhuma ação ativa no momento)"}

CONVERSA:
{conversa}

Classifique esta janela de conversa e responda APENAS com um JSON no formato exato:
{{
  "relevancia": "acao" | "conhecimento" | "ruido",
  "resumo": "1 a 3 frases (português) do que esta janela trata",
  "topicos": ["até 4 palavras/expressões-chave"],
  "task_id": "id de uma das ações acima, ou null",
  "confidence": 0.0 a 1.0,
  "reativar_sugerido": true|false,
  "nota_sugerida": "nota curta e objetiva para o diário de bordo da ação (vazio se relevancia != acao)",
  "itens_de_acao": [
    {{"descricao": "o que precisa ser feito", "responsavel": "eu" | "contato" | "nome citado", "prazo": "YYYY-MM-DD ou null"}}
  ],
  "decisoes": ["pontos acordados/definidos na conversa — compromissos, valores, responsabilidades (ponto de auditoria)"],
  "datas_mencionadas": [
    {{"data": "YYYY-MM-DD", "contexto": "o que essa data significa"}}
  ],
  "mutacoes_propostas": {{
    "novas_etapas": ["etapas concretas a acrescentar ao plano de ação da ação vinculada, se houver"],
    "nova_data_limite": "YYYY-MM-DD ou null — só quando a conversa deixa claro um novo prazo para a ação inteira",
    "lembrete_sugerido": {{"data": "YYYY-MM-DD", "texto": "o que lembrar"}} ou null
  }}
}}

Regras:
- "acao": só quando houver vínculo claro e específico com uma das ações listadas.
- "ruido": conversa social, figurinhas, memes, sem conteúdo relevante para registrar.
- "conhecimento": relevante para lembrar depois, mas sem ação específica vinculada.
- "task_id" deve ser exatamente um dos IDs listados acima, ou null.
- "reativar_sugerido" só pode ser true se a ação correspondente estiver com status "stand-by".
- "itens_de_acao", "decisoes" e "datas_mencionadas" ficam vazios ([]) quando a conversa não traz nada desse tipo — não invente.
- "mutacoes_propostas" só é preenchido quando "task_id" não é null e a conversa realmente justifica a mudança; caso contrário use novas_etapas=[], nova_data_limite=null, lembrete_sugerido=null.
- Datas relativas ("amanhã", "sexta", "semana que vem") devem ser convertidas para YYYY-MM-DD com base em hoje ({hoje}).
"""


def _analyze_whatsapp_window(client, db, chat_name: str, messages: list[dict], candidates_text: str) -> dict:
    from google.genai import types

    prompt = _build_triage_prompt(chat_name, messages, candidates_text)
    response = generate_content_logged(
        client,
        model=GEMINI_LIGHT_MODEL,
        contents=prompt,
        feature=FEATURE_TRIAGE,
        db=db,
        config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.1),
    )
    raw = (response.text or "").strip()
    if "```json" in raw:
        raw = raw.split("```json")[-1].split("```")[0].strip()
    elif "```" in raw:
        raw = raw.split("```")[-1].split("```")[0].strip()
    return json.loads(raw)


def _window_digest_id(wa_chat_id: str, messages: list[dict]) -> str:
    last_ts = messages[-1].get("timestamp")
    key = last_ts.strftime("%Y%m%d%H%M%S") if hasattr(last_ts, "strftime") else str(len(messages))
    return f"{wa_chat_id}_{key}"


def _save_whatsapp_digest(db, digest_id: str, wa_chat_id: str, chat_name: str, messages: list[dict], analysis: dict, api_key: str) -> None:
    from google.cloud.firestore_v1.vector import Vector
    from main import get_embedding

    resumo = str(analysis.get("resumo") or "").strip()
    topicos = [str(t) for t in (analysis.get("topicos") or []) if str(t).strip()]
    itens_de_acao = _sanitize_itens_de_acao(analysis.get("itens_de_acao"))
    decisoes = _sanitize_decisoes(analysis.get("decisoes"))
    datas_mencionadas = _sanitize_datas_mencionadas(analysis.get("datas_mencionadas"))

    texto_fonte_parts = [chat_name, resumo, " ".join(topicos)]
    if itens_de_acao:
        texto_fonte_parts.append(" ".join(i["descricao"] for i in itens_de_acao))
    if decisoes:
        texto_fonte_parts.append(" ".join(decisoes))
    texto_fonte = "\n".join(p for p in texto_fonte_parts if p)

    doc = {
        "chat_id": wa_chat_id,
        "chat_name": chat_name,
        "resumo": resumo,
        "topicos": topicos,
        "relevancia": analysis.get("relevancia"),
        "n_mensagens": len(messages),
        "inicio": messages[0].get("timestamp"),
        "fim": messages[-1].get("timestamp"),
        "criado_em": datetime.now(timezone.utc).isoformat(),
        # Elementos executivos extraídos pela mesma chamada de triagem (ver
        # _build_triage_prompt) — o que transforma o digest de "resumo vago"
        # em algo com relevância funcional: itens de ação, pontos de decisão
        # (auditoria) e datas citadas na conversa.
        "itens_de_acao": itens_de_acao,
        "decisoes": decisoes,
        "datas_mencionadas": datas_mencionadas,
    }

    try:
        embedding = get_embedding(texto_fonte, api_key=api_key, task_type="RETRIEVAL_DOCUMENT")
        if len(embedding) == DIGEST_EMBEDDING_DIM:
            doc[DIGEST_EMBEDDING_FIELD] = Vector(embedding)
    except Exception as exc:
        print(f"[WA-INGEST] Falha ao gerar embedding do digest {digest_id}: {exc}")

    db.collection(DIGEST_COLLECTION).document(digest_id).set(doc, merge=True)


def triage_whatsapp_messages(db, sync_ref, logs) -> None:
    """
    Chamada no fim de `run_full_sync` (main.py). Consome mensagens novas de
    `whatsapp_messages` (cursor em `system/whatsapp_ingest.last_processed_at`),
    agrupa por conversa, classifica cada janela e roteia: `acao` propõe vínculo
    com uma tarefa via o motor compartilhado de sugestões; `acao`/`conhecimento`
    também viram um digest vetorizado; `ruido` é descartado sem gravar nada.
    """
    from main import (
        _cached_doc_get,
        get_genai_module,
        _resolve_default_telegram_chat_id,
        log_to_firestore,
    )
    from email_action_linker import _load_candidate_tasks, _format_candidates_for_prompt, queue_and_maybe_send_suggestion

    settings = _load_settings(db)
    if not settings["enabled"]:
        return

    cursor_ref = db.collection("system").document("whatsapp_ingest")
    cursor_doc = cursor_ref.get()
    since_ts = (cursor_doc.to_dict() or {}).get("last_processed_at") if cursor_doc.exists else None
    if since_ts is None:
        since_ts = datetime.now(timezone.utc) - timedelta(hours=DEFAULT_FIRST_RUN_LOOKBACK_HOURS)

    try:
        docs = list(
            db.collection("whatsapp_messages")
            .where("ingested_at", ">", since_ts)
            .order_by("ingested_at")
            .limit(1000)
            .stream()
        )
    except Exception as exc:
        log_to_firestore(sync_ref, logs, f"[WA-INGEST][ERRO] Falha ao consultar whatsapp_messages: {exc}", True)
        return

    if not docs:
        return

    groups: dict[str, list[dict]] = {}
    for doc in docs:
        data = doc.to_dict() or {}
        chat_id = data.get("chat_id")
        if not chat_id:
            continue
        groups.setdefault(chat_id, []).append(data)

    if not groups:
        # Nenhuma mensagem tinha chat_id (não deveria acontecer com o worker atualizado) —
        # seguro avançar o cursor, não há nada retido para reprocessar.
        latest_ingested_at = max((d.to_dict() or {}).get("ingested_at") for d in docs)
        cursor_ref.set({"last_processed_at": latest_ingested_at}, merge=True)
        return

    candidates = _load_candidate_tasks(db)
    candidates_text = _format_candidates_for_prompt(candidates)
    candidates_by_id = {c["id"]: c for c in candidates}

    keys_doc = _cached_doc_get(db, "system", "api_keys")
    api_key = keys_doc.to_dict().get("gemini_api_key") if keys_doc.exists else None
    if not api_key:
        log_to_firestore(sync_ref, logs, "[WA-INGEST][ERRO] Gemini API Key não configurada (system/api_keys).", True)
        return

    genai = get_genai_module()
    client = genai.Client(api_key=api_key)
    telegram_chat_id = _resolve_default_telegram_chat_id(db)

    # Processa as conversas mais antigas primeiro (por ingested_at mínimo do grupo) — dá
    # prioridade de progresso a quem está parado há mais tempo, em vez de ordem arbitrária.
    all_windows = sorted(groups.items(), key=lambda item: min(m.get("ingested_at") or since_ts for m in item[1]))
    windows = all_windows[: settings["max_windows_per_pass"]]
    skipped_windows = all_windows[settings["max_windows_per_pass"]:]
    skipped = len(skipped_windows)
    analyzed = 0

    for wa_chat_id, messages in windows:
        text_total = " ".join(str(m.get("content") or "") for m in messages).strip()
        if len(text_total) < MIN_WINDOW_TEXT_CHARS:
            continue  # janela pouco textual (figurinhas/mídia avulsa) — não vale a chamada de IA

        messages.sort(key=lambda m: m.get("timestamp") or 0)
        chat_name = messages[-1].get("chat_name") or wa_chat_id

        try:
            analysis = _analyze_whatsapp_window(client, db, chat_name, messages, candidates_text)
        except Exception as exc:
            log_to_firestore(sync_ref, logs, f"[WA-INGEST][!] Falha na análise da conversa '{chat_name}': {exc}", True)
            continue
        analyzed += 1

        relevancia = str(analysis.get("relevancia") or "ruido")
        if relevancia == "ruido":
            continue

        resumo = str(analysis.get("resumo") or "").strip()
        nota_sugerida = str(analysis.get("nota_sugerida") or "").strip() or resumo
        task_id = analysis.get("task_id")
        try:
            confidence = max(0.0, min(1.0, float(analysis.get("confidence") or 0.0)))
        except Exception:
            confidence = 0.0

        digest_id = _window_digest_id(wa_chat_id, messages)

        if relevancia == "acao" and task_id in candidates_by_id and confidence >= settings["min_confidence"] and resumo:
            task = candidates_by_id[task_id]
            itens_de_acao = _sanitize_itens_de_acao(analysis.get("itens_de_acao"))
            decisoes = _sanitize_decisoes(analysis.get("decisoes"))
            datas_mencionadas = _sanitize_datas_mencionadas(analysis.get("datas_mencionadas"))
            mutacoes_propostas = _sanitize_mutacoes_propostas(analysis.get("mutacoes_propostas"))

            # Elementos executivos extras (itens de ação, decisões, mutações propostas)
            # viajam via `extra` para o doc de sugestão — o motor compartilhado só
            # persiste e repassa, quem interpreta é o cartão do Telegram/fila web e
            # `apply_suggestion` (functions/email_action_linker.py).
            extra: dict = {
                "n_mensagens": len(messages),
                "periodo_inicio": _ts_to_iso(messages[0].get("timestamp")),
                "periodo_fim": _ts_to_iso(messages[-1].get("timestamp")),
            }
            if itens_de_acao:
                extra["itens_de_acao"] = itens_de_acao
            if decisoes:
                extra["decisoes"] = decisoes
            if datas_mencionadas:
                extra["datas_mencionadas"] = datas_mencionadas
            if mutacoes_propostas:
                extra["mutacoes_propostas"] = mutacoes_propostas

            queue_and_maybe_send_suggestion(
                db,
                f"whatsapp_{digest_id}",
                canal="whatsapp",
                task=task,
                titulo_sinal=chat_name,
                origem_sinal=f"{len(messages)} mensagem(ns)",
                resumo=resumo,
                nota_sugerida=nota_sugerida,
                reativar_sugerido=bool(analysis.get("reativar_sugerido")),
                confidence=confidence,
                chat_id=telegram_chat_id,
                extra=extra,
            )

        if resumo:
            _save_whatsapp_digest(db, digest_id, wa_chat_id, chat_name, messages, analysis, api_key)

    # Avança o cursor só até onde é seguro: se alguma janela ficou de fora por causa
    # do teto (`skipped_windows`), o cursor não pode passar da mensagem mais antiga
    # entre as adiadas — senão elas somem para sempre da próxima consulta por
    # `ingested_at > cursor`. Sem adiadas, é seguro avançar até a mensagem mais
    # recente deste lote inteiro.
    if skipped_windows:
        new_cursor = min(
            m.get("ingested_at") for _, msgs in skipped_windows for m in msgs if m.get("ingested_at")
        )
    else:
        new_cursor = max(
            m.get("ingested_at") for _, msgs in windows for m in msgs if m.get("ingested_at")
        )
    cursor_ref.set({"last_processed_at": new_cursor}, merge=True)

    if analyzed or skipped:
        extra = f" {skipped} conversa(s) adiada(s) para a próxima passada (teto)." if skipped else ""
        log_to_firestore(sync_ref, logs, f"[WA-INGEST] {analyzed} janela(s) de conversa de WhatsApp analisada(s).{extra}", True)


def buscar_conversas_whatsapp(db, query: str, limite: int = 5) -> dict:
    """
    Busca semântica nos digests de conversas de WhatsApp indexados
    (`whatsapp_digests`). Usada pela tool do copiloto `buscar_conversas_whatsapp`
    (main.py) — mesmo padrão de `tools/busca_acervo.py:buscar_acervo`.
    """
    from google.genai import types
    from google.cloud.firestore_v1.vector import Vector
    from google.cloud.firestore_v1.base_vector_query import DistanceMeasure
    from main import get_genai_module, _cached_doc_get
    from gemini_cost_controls import GEMINI_EMBEDDING_MODEL, embed_content_logged

    query = (query or "").strip()
    if not query:
        return {"resultados": [], "erro": "query vazia"}

    keys_doc = _cached_doc_get(db, "system", "api_keys")
    api_key = keys_doc.to_dict().get("gemini_api_key") if keys_doc.exists else None
    if not api_key:
        return {"resultados": [], "erro": "Gemini API Key não configurada."}

    try:
        genai = get_genai_module()
        client = genai.Client(api_key=api_key)
        response = embed_content_logged(
            client,
            model=GEMINI_EMBEDDING_MODEL,
            contents=query,
            feature="whatsapp_ingest.search_embedding",
            db=db,
            config=types.EmbedContentConfig(task_type="RETRIEVAL_QUERY", output_dimensionality=DIGEST_EMBEDDING_DIM),
        )
        query_vector = [float(v) for v in response.embeddings[0].values]

        docs = (
            db.collection(DIGEST_COLLECTION)
            .find_nearest(
                vector_field=DIGEST_EMBEDDING_FIELD,
                query_vector=Vector(query_vector),
                distance_measure=DistanceMeasure.COSINE,
                limit=limite,
            )
            .get()
        )

        resultados = []
        for doc in docs:
            data = doc.to_dict() or {}
            resultados.append({
                "chat_name": data.get("chat_name"),
                "resumo": data.get("resumo"),
                "topicos": data.get("topicos") or [],
                "itens_de_acao": data.get("itens_de_acao") or [],
                "decisoes": data.get("decisoes") or [],
                "inicio": str(data.get("inicio") or ""),
                "fim": str(data.get("fim") or ""),
            })
        return {"resultados": resultados, "erro": None}
    except Exception as e:
        return {"resultados": [], "erro": f"{type(e).__name__}: {str(e)}"}
