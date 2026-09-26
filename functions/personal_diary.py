"""
Diário pessoal: agrega as interações do dia em todas as superfícies do
Hermes (ações, saúde, finanças, agenda, conversas com o copiloto, pessoas)
e usa um modelo de linguagem para redigir um registro em primeira pessoa,
na voz do usuário — não um relatório frio de métricas.

Um consolidador semanal destila os diários acumulados (e os ajustes que o
próprio usuário pediu neles) num perfil de personalidade gravado em
`usuarios/{uid}.ai_profile.personalidade` — como esse campo já é lido pelo
copiloto web e pela ponte de voz, o perfil se propaga para
todas as superfícies sem nenhuma mudança adicional nelas.

Logo depois de gravar um perfil novo, o consolidador manda no Telegram o
"espelho semanal" (resumo + o que mudou desde a versão anterior) com os botões
"✏️ Corrigir" e "👍 Está certo". A correção em texto livre fica em
`ai_profile.personalidade_ajustes` e entra no prompt da consolidação seguinte
como o sinal de calibração mais forte (ver `registrar_ajuste_personalidade` e
telegram_callbacks_perfil.py).

Os dois jobs agendados foram removidos em 26/09/2026 (PR #356) e restaurados
no mesmo dia, a pedido do André; continuam atrás de
`system/settings.personal_diary.enabled` (padrão desligado).

Ver docs/okf/propostas/automacoes-canais-e-diario-pessoal.md (eixo 3).
"""

import html
import json
from datetime import datetime, timedelta, timezone

from firebase_functions import https_fn, scheduler_fn, options

from gemini_cost_controls import GEMINI_FRONTIER_MODEL, generate_content_logged

FEATURE_DIARY = "personal_diary.generate"
FEATURE_DIARY_EDIT = "personal_diary.edit"
FEATURE_PERSONALITY = "personal_diary.consolidate_personality"

MIN_DIARIES_FOR_PERSONALITY = 3
PREVIOUS_DIARIES_FOR_CONTEXT = 3

# Espelho semanal (Telegram) e correções diretas do perfil.
PERFIL_CALLBACK_CORRIGIR = "perfil:fix"
PERFIL_CALLBACK_OK = "perfil:ok"
MAX_AJUSTES_PERSONALIDADE = 20       # guardados em ai_profile.personalidade_ajustes
MAX_AJUSTES_NO_PROMPT = 10           # os mais recentes vão para a consolidação
IDADE_MAX_AJUSTE_NO_PROMPT = timedelta(weeks=8)  # correção mais velha deixa de pesar
MAX_CHARS_AJUSTE = 1000
MAX_ITENS_POR_LINHA_ESPELHO = 3
AJUSTE_CONFIRMACAO = "Anotado — entra na próxima leitura de domingo."


def _load_settings(db) -> dict:
    from main import _cached_doc_get

    doc = _cached_doc_get(db, "system", "settings")
    cfg = ((doc.to_dict() or {}) if doc.exists else {}).get("personal_diary") or {}
    return {"enabled": bool(cfg.get("enabled", False))}


def _day_bounds(date_str: str) -> tuple[datetime, datetime]:
    """Converte 'YYYY-MM-DD' (dia local America/Sao_Paulo) em (início, fim) UTC."""
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("America/Sao_Paulo")
    start_local = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def _next_day_str(date_str: str) -> str:
    return (datetime.strptime(date_str, "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")


def _query_by_date_range(db, collection: str, field: str, date_str: str) -> list:
    """
    Consulta por prefixo de data num campo string ISO 8601 — funciona tanto para
    datas puras ("2026-08-08") quanto datetimes completos ("2026-08-08T14:30:00Z"),
    já que a comparação lexicográfica de strings ISO preserva a ordem cronológica.
    """
    try:
        return list(
            db.collection(collection)
            .where(field, ">=", date_str)
            .where(field, "<", _next_day_str(date_str))
            .stream()
        )
    except Exception as exc:
        print(f"[Diario] Falha ao consultar {collection}.{field} em {date_str}: {exc}")
        return []


def _diary_note_to_plain_text(nota: str) -> str:
    """
    Converte uma nota de diário de bordo para texto legível, incluindo o
    envelope rico `TIPO::JSON::{...}` usado por LINK/CONTACT/FILE/EMAIL
    (ver src/utils/diaryEntries.ts) — o LLM não precisa ver JSON cru.
    """
    nota = str(nota or "")
    for tipo in ("EMAIL", "LINK", "CONTACT", "FILE"):
        prefix = f"{tipo}::JSON::"
        if not nota.startswith(prefix):
            continue
        try:
            payload = json.loads(nota[len(prefix):])
        except Exception:
            return nota
        nome = str(payload.get("n") or "")
        valor = str(payload.get("v") or "")
        if tipo == "EMAIL":
            resumo = str(payload.get("r") or "")
            sender = str(payload.get("s") or "")
            texto = f"E-mail de {sender}: {nome}" if sender else f"E-mail: {nome}"
            return f"{texto} — {resumo}" if resumo else texto
        if tipo == "LINK":
            return f"Link: {nome or valor}"
        if tipo == "CONTACT":
            return f"Contato: {nome or valor}"
        if tipo == "FILE":
            return f"Arquivo: {nome or 'anexo'}"
    return nota


def _collect_diary_material(db, date_str: str) -> dict:
    """Coletor determinístico (sem IA) do material bruto do dia, varrendo as
    coleções onde a atividade do usuário já fica registrada hoje."""
    material = {
        "notas_manuais": [],
        "acoes": [],
        "concluidas": [],
        "criadas": [],
        "saude": None,
        "peso": None,
        "financeiro": [],
        "agenda": [],
        "conversas": [],
        "pessoas": [],
        "feedback_ia": [],
    }

    # Anotações que o usuário deixou ao longo do dia direto no doc do diário
    # (via UI web — PersonalDiaryView.tsx) para entrarem na consolidação da noite.
    diary_doc = db.collection("diario_pessoal").document(date_str).get()
    if diary_doc.exists:
        for nota in (diary_doc.to_dict() or {}).get("notas_manuais") or []:
            texto_nota = str((nota or {}).get("texto") or "").strip() if isinstance(nota, dict) else str(nota or "").strip()
            if texto_nota:
                material["notas_manuais"].append(texto_nota)

    for doc in db.collection("tarefas").stream():
        data = doc.to_dict() or {}
        acompanhamento = data.get("acompanhamento") or []
        notas_do_dia = [
            _diary_note_to_plain_text(entry.get("nota") or "")
            for entry in acompanhamento
            if isinstance(entry, dict) and str(entry.get("data") or "")[:10] == date_str
        ]
        if notas_do_dia:
            material["acoes"].append({"titulo": data.get("titulo") or "(sem título)", "notas": notas_do_dia})
        if str(data.get("data_conclusao") or "")[:10] == date_str:
            material["concluidas"].append(data.get("titulo") or "(sem título)")
        if str(data.get("data_criacao") or "")[:10] == date_str:
            material["criadas"].append(data.get("titulo") or "(sem título)")

    health_doc = db.collection("health_exercise_logs").document(date_str).get()
    if health_doc.exists:
        material["saude"] = health_doc.to_dict()

    for w in _query_by_date_range(db, "health_weights", "date", date_str):
        material["peso"] = w.to_dict()
        break

    for tx in _query_by_date_range(db, "finance_transactions", "date", date_str):
        d = tx.to_dict() or {}
        material["financeiro"].append({
            "descricao": d.get("description"),
            "valor": d.get("amount"),
            "categoria": d.get("category"),
        })

    for ev in _query_by_date_range(db, "google_calendar_events", "data_inicio", date_str):
        d = ev.to_dict() or {}
        material["agenda"].append({"titulo": d.get("titulo"), "inicio": d.get("data_inicio"), "fim": d.get("data_fim")})

    for p in _query_by_date_range(db, "interacoes_pessoas", "data", date_str):
        d = p.to_dict() or {}
        material["pessoas"].append({"tipo": d.get("tipo"), "descricao": d.get("descricao")})

    for n in _query_by_date_range(db, "scheduled_notifications", "feedback_at", date_str):
        d = n.to_dict() or {}
        if d.get("feedback"):
            material["feedback_ia"].append({"title": d.get("title"), "feedback": d.get("feedback")})

    # Conversas com o copiloto: sessões tocadas no dia, em qualquer superfície
    # (web global/drawer/task view, voz, Telegram) — lastMessageAt é
    # Timestamp nativo em ambas as coleções de sessão.
    start_utc, end_utc = _day_bounds(date_str)

    def _collect_sessions(collection_name: str, canal_padrao: str) -> None:
        try:
            sessions = list(
                db.collection(collection_name)
                .where("lastMessageAt", ">=", start_utc)
                .where("lastMessageAt", "<", end_utc)
                .limit(30)
                .stream()
            )
        except Exception as exc:
            print(f"[Diario] Falha ao consultar {collection_name} em {date_str}: {exc}")
            return

        for sess_doc in sessions:
            sess_data = sess_doc.to_dict() or {}
            # source por mensagem só é gravado hoje em web/drawer/voz/telegram; sessões antigas ou
            # turnos do backend (askCopilotoHermes) caem para o canal padrão.
            canal = sess_data.get("channel") or sess_data.get("copilotScope") or canal_padrao
            try:
                msgs = list(
                    sess_doc.reference.collection("mensagens")
                    .where("timestamp", ">=", start_utc)
                    .where("timestamp", "<", end_utc)
                    .order_by("timestamp")
                    .limit(40)
                    .stream()
                )
            except Exception as exc:
                print(f"[Diario] Falha ao ler mensagens da sessão {sess_doc.id}: {exc}")
                continue

            trechos = []
            for m in msgs:
                m_data = m.to_dict() or {}
                if m_data.get("subtype") == "proactive_insight":
                    continue
                content = str(m_data.get("content") or "").strip()
                if not content:
                    continue
                trechos.append(f"{m_data.get('role') or '?'}: {content[:280]}")
            if trechos:
                material["conversas"].append({"canal": m_data.get("source") or canal, "trechos": trechos[:20]})

    _collect_sessions("sessoes_copiloto", "web")

    return material


def _material_is_empty(material: dict) -> bool:
    return not any([
        material["notas_manuais"],
        material["acoes"], material["concluidas"], material["criadas"],
        material["saude"], material["peso"], material["financeiro"],
        material["agenda"], material["conversas"], material["pessoas"],
        material["feedback_ia"],
    ])


def _resolve_default_uid(db) -> str | None:
    """Mesma resolução usada pela ponte de voz (context.py:_format_user_profile) —
    sistema pessoal de um único usuário, sem seleção multiusuário."""
    import os

    uid = os.environ.get("HERMES_DEFAULT_USER_ID", "").strip()
    if uid:
        return uid
    for snap in db.collection("usuarios").limit(1).stream():
        return snap.id
    return None


def _build_diary_prompt(date_str: str, material: dict, persona_text: str, profile_text: str, previous_diaries_text: str) -> str:
    material_json = json.dumps(material, ensure_ascii=False, indent=2)
    return f"""Você vai escrever, em primeira pessoa, o diário pessoal do usuário do dia {date_str}.

PERSONA DO GASPAR (contexto de quem observa, não é quem escreve o diário):
{persona_text or "(sem persona configurada)"}

PERFIL CONHECIDO DO USUÁRIO:
{profile_text or "(perfil ainda não bootstrapado)"}

DIÁRIOS ANTERIORES (para manter continuidade e a mesma voz):
{previous_diaries_text or "(nenhum diário anterior — este é o primeiro)"}

MATERIAL BRUTO DO DIA (dados de sistema — ações, saúde, finanças, agenda, conversas, pessoas — não é prosa):
{material_json}

INSTRUÇÕES:
- O campo `notas_manuais` do material são anotações que o PRÓPRIO USUÁRIO escreveu ao longo do dia para entrarem no diário — são a entrada mais importante: incorpore todas, com prioridade sobre os dados de sistema, e trate-as como fato relatado (não como impressão sua).
- Escreva EM PRIMEIRA PESSOA, como se fosse o próprio usuário escrevendo seu diário à noite — não um relatório sobre ele.
- Tom pessoal e humano, natural, como alguém realmente escreveria — nada de bullet points de métricas nem linguagem corporativa.
- Baseie-se estritamente no material fornecido. Não invente eventos, conversas ou fatos que não estejam nele.
- Você PODE inferir estado de ânimo/disposição a partir dos dados (ex.: muitas reuniões + dor lombar alta = dia cansativo), mas deixe claro que é uma impressão sua, não um fato relatado.
- Não seja prescritivo nem dê conselhos — registrar o dia, não orientar o próximo.
- 2 a 5 parágrafos curtos, português do Brasil.
- Responda APENAS com o texto do diário — sem título, sem aspas, sem comentários extras.
"""


@scheduler_fn.on_schedule(
    schedule="30 21 * * *",
    timezone="America/Sao_Paulo",
    memory=options.MemoryOption.MB_512,
    timeout_sec=180,
)
def gerar_diario_pessoal(event: scheduler_fn.ScheduledEvent = None) -> None:
    """Agendada 21:30 BRT — gera o diário pessoal do dia corrente."""
    from main import (
        get_db,
        _cached_doc_get,
        get_genai_module,
        _resolve_default_telegram_chat_id,
        _send_telegram_message_raw_with_keyboard,
        _format_ai_profile_for_prompt,
    )
    from zoneinfo import ZoneInfo

    db = get_db()
    settings = _load_settings(db)
    if not settings["enabled"]:
        return

    today_str = datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%Y-%m-%d")
    diary_ref = db.collection("diario_pessoal").document(today_str)
    existing = diary_ref.get()
    existing_data = (existing.to_dict() or {}) if existing.exists else {}
    # O doc pode já existir só com `notas_manuais` (anotações feitas na UI ao longo
    # do dia) ou com `sem_material` de uma rodada anterior — só `texto` conta como
    # diário gerado.
    if existing_data.get("texto"):
        print(f"[Diario] Diário de {today_str} já existe; nada a fazer.")
        return

    material = _collect_diary_material(db, today_str)
    if _material_is_empty(material):
        diary_ref.set({"data": today_str, "sem_material": True, "gerado_em": datetime.now(timezone.utc).isoformat()}, merge=True)
        print(f"[Diario] Sem material para {today_str}.")
        return

    uid = _resolve_default_uid(db)
    ai_profile = {}
    if uid:
        user_doc = db.collection("usuarios").document(uid).get()
        if user_doc.exists:
            ai_profile = (user_doc.to_dict() or {}).get("ai_profile") or {}
    profile_text = _format_ai_profile_for_prompt(ai_profile)

    soul_doc = _cached_doc_get(db, "system", "copilot_soul")
    persona_text = ""
    if soul_doc.exists:
        soul_data = soul_doc.to_dict() or {}
        persona_text = str(soul_data.get("texto") or soul_data.get("content") or "").strip()[:1500]

    previous = []
    for i in range(1, PREVIOUS_DIARIES_FOR_CONTEXT + 1):
        d = (datetime.strptime(today_str, "%Y-%m-%d") - timedelta(days=i)).strftime("%Y-%m-%d")
        doc = db.collection("diario_pessoal").document(d).get()
        if doc.exists:
            data = doc.to_dict() or {}
            if data.get("texto"):
                previous.append(f"[{d}]\n{data['texto']}")
    previous_diaries_text = "\n\n---\n\n".join(reversed(previous))

    keys_doc = _cached_doc_get(db, "system", "api_keys")
    api_key = keys_doc.to_dict().get("gemini_api_key") if keys_doc.exists else None
    if not api_key:
        print("[Diario] Gemini API Key não configurada (system/api_keys).")
        return

    genai = get_genai_module()
    client = genai.Client(api_key=api_key)
    prompt = _build_diary_prompt(today_str, material, persona_text, profile_text, previous_diaries_text)

    try:
        response = generate_content_logged(client, model=GEMINI_FRONTIER_MODEL, contents=prompt, feature=FEATURE_DIARY, db=db)
        texto = (response.text or "").strip()
    except Exception as exc:
        print(f"[Diario] Falha ao gerar diário de {today_str}: {exc}")
        return

    if not texto:
        print(f"[Diario] Resposta vazia do modelo para {today_str}.")
        return

    fontes = {
        "notas_manuais": len(material["notas_manuais"]),
        "acoes": len(material["acoes"]),
        "concluidas": len(material["concluidas"]),
        "saude": bool(material["saude"] or material["peso"]),
        "financeiro": len(material["financeiro"]),
        "agenda": len(material["agenda"]),
        "conversas": sum(len(c["trechos"]) for c in material["conversas"]),
        "pessoas": len(material["pessoas"]),
    }

    # merge=True preserva `notas_manuais` gravadas pela UI antes da consolidação.
    diary_ref.set({
        "data": today_str,
        "texto": texto,
        "fontes": fontes,
        "gerado_em": datetime.now(timezone.utc).isoformat(),
        "modelo": GEMINI_FRONTIER_MODEL,
        "editado": False,
        "confirmado": False,
    }, merge=True)

    chat_id = _resolve_default_telegram_chat_id(db)
    if chat_id:
        preview = texto if len(texto) <= 3500 else texto[:3500] + "…"
        keyboard = [[
            {"text": "✍️ Ajustar", "callback_data": f"diary_edit:{today_str}"},
            {"text": "👍 Ok", "callback_data": f"diary_ok:{today_str}"},
        ]]
        _send_telegram_message_raw_with_keyboard(db, chat_id, f"📔 Diário de {today_str}\n\n{preview}", keyboard)

    print(f"[Diario] Diário de {today_str} gerado ({len(texto)} chars).")


def _rewrite_diary_with_feedback(db, date_str: str, feedback_text: str) -> tuple[str | None, str]:
    """
    Núcleo do ajuste via IA: reescreve o diário de `date_str` incorporando o
    pedido do usuário e persiste o resultado. O diff é guardado em `ajustes[]`:
    é o sinal de calibração de personalidade mais direto que o usuário dá ao
    sistema (insumo de `consolidar_personalidade`).

    Retorna `(novo_texto, erro)` — `novo_texto` é None quando falhou, com
    `erro` legível para o usuário.
    """
    from main import _cached_doc_get, get_genai_module
    from firebase_admin import firestore

    diary_ref = db.collection("diario_pessoal").document(date_str)
    diary_doc = diary_ref.get()
    if not diary_doc.exists:
        return None, f"Não encontrei o diário de {date_str} para ajustar."

    settings = _load_settings(db)
    if not settings["enabled"]:
        return None, "O diário pessoal está desativado."

    diary_data = diary_doc.to_dict() or {}
    texto_atual = diary_data.get("texto") or ""
    if not texto_atual:
        return None, f"O diário de {date_str} ainda não foi gerado."
    texto_original = diary_data.get("texto_original") or texto_atual

    keys_doc = _cached_doc_get(db, "system", "api_keys")
    api_key = keys_doc.to_dict().get("gemini_api_key") if keys_doc.exists else None
    if not api_key:
        return None, "⚠️ Gemini não configurado."

    genai = get_genai_module()
    client = genai.Client(api_key=api_key)
    prompt = f"""Você é o Gaspar reescrevendo, a pedido do próprio usuário, o diário pessoal dele do dia {date_str}.

TEXTO ATUAL DO DIÁRIO:
{texto_atual}

AJUSTE PEDIDO PELO USUÁRIO:
{feedback_text}

Reescreva o diário incorporando o ajuste, mantendo o tom em primeira pessoa e preservando o que não foi contestado. Responda APENAS com o texto revisado, sem comentários extras."""

    try:
        response = generate_content_logged(client, model=GEMINI_FRONTIER_MODEL, contents=prompt, feature=FEATURE_DIARY_EDIT, db=db)
        novo_texto = (response.text or "").strip()
    except Exception as exc:
        print(f"[Diario] Falha ao aplicar ajuste de {date_str}: {exc}")
        return None, "⚠️ Não consegui gerar o ajuste agora."

    if not novo_texto:
        return None, "⚠️ Não consegui gerar o ajuste."

    now_iso = datetime.now(timezone.utc).isoformat()
    diary_ref.update({
        "texto": novo_texto,
        "texto_original": texto_original,
        "editado": True,
        "ajustes": firestore.ArrayUnion([{"pedido": feedback_text, "em": now_iso}]),
        "atualizado_em": now_iso,
    })
    return novo_texto, ""


def apply_diary_feedback(db, date_str: str, feedback_text: str) -> str:
    """
    Wrapper do fluxo Telegram (botão "✍️ Ajustar" trava a sessão, a próxima
    mensagem livre vira o pedido — ver hermes_core_logic.py, session
    `pending_diary_edit`): devolve a resposta pronta para enviar no chat.
    """
    novo_texto, erro = _rewrite_diary_with_feedback(db, date_str, feedback_text)
    if novo_texto is None:
        return erro
    preview = novo_texto if len(novo_texto) <= 3500 else novo_texto[:3500] + "…"
    return f"✍️ Diário de {date_str} ajustado:\n\n{preview}"


@https_fn.on_call(memory=options.MemoryOption.MB_512, timeout_sec=120)
def ajustarDiarioPessoal(req: https_fn.CallableRequest):
    """
    Ajuste via IA a partir da UI web (PersonalDiaryView.tsx): recebe a data e o
    pedido de ajuste, reescreve o diário com o mesmo fluxo do Telegram e
    retorna o texto revisado.
    """
    from main import get_db

    if not (req.auth and req.auth.uid):
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.UNAUTHENTICATED,
            message="Usuário não autenticado.",
        )

    data = req.data or {}
    date_str = str(data.get("date") or "").strip()
    feedback = str(data.get("feedback") or "").strip()
    if not date_str or not feedback:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.INVALID_ARGUMENT,
            message="Campos 'date' e 'feedback' são obrigatórios.",
        )

    db = get_db()
    novo_texto, erro = _rewrite_diary_with_feedback(db, date_str, feedback)
    if novo_texto is None:
        raise https_fn.HttpsError(
            code=https_fn.FunctionsErrorCode.FAILED_PRECONDITION,
            message=erro.replace("⚠️ ", ""),
        )
    return {"texto": novo_texto}


def _format_ajustes_personalidade(ajustes, agora: datetime | None = None) -> str:
    """Correções diretas do perfil (botão "✏️ Corrigir" do espelho semanal),
    mais recentes por último, no formato que vai para o prompt. Só entram as
    das últimas IDADE_MAX_AJUSTE_NO_PROMPT (sem data legível, não entra), no
    máximo MAX_AJUSTES_NO_PROMPT."""
    if not isinstance(ajustes, list):
        return ""
    agora = agora or datetime.now(timezone.utc)
    limite = agora - IDADE_MAX_AJUSTE_NO_PROMPT
    recentes = []
    for ajuste in ajustes:
        if not isinstance(ajuste, dict):
            continue
        texto = str(ajuste.get("texto") or "").strip()
        if not texto:
            continue
        try:
            em = datetime.fromisoformat(str(ajuste.get("em") or ""))
        except ValueError:
            continue
        if em.tzinfo is None:
            em = em.replace(tzinfo=timezone.utc)
        if em < limite:
            continue
        recentes.append(f"- [{em.date().isoformat()}] {texto}")
    return "\n".join(recentes[-MAX_AJUSTES_NO_PROMPT:])


def _build_personality_prompt(perfil_atual, ajustes_text: str, diaries_text: str, correcoes_text: str = "") -> str:
    """Prompt da consolidação semanal. `correcoes_text` são as correções
    diretas do espelho semanal; `ajustes_text`, os pedidos feitos nos diários."""
    return f"""Analise os diários pessoais da última semana de um usuário e destile um perfil de personalidade.
Este perfil vira contexto para um assistente de IA entender melhor quem é o usuário — não é um
diagnóstico nem uma avaliação, são impressões úteis para personalizar a interação.

PERFIL DE PERSONALIDADE ATUAL (evolua-o, não o substitua do zero — mantenha o que ainda é válido):
{json.dumps(perfil_atual, ensure_ascii=False) if perfil_atual else "(nenhum perfil anterior)"}

CORREÇÕES DIRETAS DO USUÁRIO SOBRE O PERFIL (o sinal de calibração MAIS FORTE — ele leu o espelho semanal e disse o que não bate; prevalecem sobre qualquer impressão tirada dos diários, e o perfil novo não pode contradizê-las):
{correcoes_text or "(nenhuma correção direta)"}

AJUSTES QUE O PRÓPRIO USUÁRIO PEDIU NOS DIÁRIOS DA SEMANA (sinal forte de calibração — o que ele corrigiu sobre como o Gaspar o descreveu):
{ajustes_text or "(nenhum ajuste pedido)"}

DIÁRIOS DA SEMANA:
{diaries_text}

Responda APENAS com um JSON no formato:
{{
  "tracos": ["até 6 traços de personalidade, curtos"],
  "estilo_comunicacao": "como o usuário se comunica",
  "valores_recorrentes": ["o que parece importar para ele"],
  "rotinas": ["padrões de rotina observados"],
  "gatilhos_de_estresse": ["o que parece gerar tensão/cansaço, se houver sinal claro"],
  "fontes_de_energia": ["o que parece animar/energizar, se houver sinal claro"],
  "resumo_narrativo": "2-3 frases resumindo quem é essa pessoa, em tom respeitoso e humano"
}}
Se não houver sinal suficiente para um campo, retorne lista vazia ou string vazia — não invente."""


@scheduler_fn.on_schedule(
    schedule="0 22 * * 0",
    timezone="America/Sao_Paulo",
    memory=options.MemoryOption.MB_512,
    timeout_sec=180,
)
def consolidar_personalidade(event: scheduler_fn.ScheduledEvent = None) -> None:
    """
    Agendada semanalmente (domingo 22h BRT) — destila os diários da semana
    (e os ajustes que o usuário pediu neles) num perfil de personalidade
    gravado em usuarios/{uid}.ai_profile.personalidade. Evolui o perfil
    anterior em vez de substituí-lo do zero, e guarda um histórico curto
    de versões para o perfil poder mudar sem perder o rastro.
    """
    from main import get_db, _cached_doc_get, get_genai_module
    from google.genai import types
    from zoneinfo import ZoneInfo

    db = get_db()
    settings = _load_settings(db)
    if not settings["enabled"]:
        return

    today = datetime.now(ZoneInfo("America/Sao_Paulo")).date()

    diaries = []
    ajustes_totais = []
    for i in range(1, 8):
        d = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        doc = db.collection("diario_pessoal").document(d).get()
        if not doc.exists:
            continue
        data = doc.to_dict() or {}
        if data.get("sem_material") or not data.get("texto"):
            continue
        diaries.append(data)
        ajustes_totais.extend(data.get("ajustes") or [])

    if len(diaries) < MIN_DIARIES_FOR_PERSONALITY:
        print(f"[Personalidade] Só {len(diaries)} diário(s) na semana; pulando (mínimo {MIN_DIARIES_FOR_PERSONALITY}).")
        return

    diaries.sort(key=lambda d: d.get("data") or "")
    diaries_text = "\n\n---\n\n".join(f"[{d.get('data')}]\n{d.get('texto', '')}" for d in diaries)
    ajustes_text = "\n".join(f"- {a.get('pedido')}" for a in ajustes_totais if a.get("pedido"))

    uid = _resolve_default_uid(db)
    if not uid:
        print("[Personalidade] Nenhum usuário encontrado em 'usuarios'.")
        return

    user_ref = db.collection("usuarios").document(uid)
    user_doc = user_ref.get()
    ai_profile = ((user_doc.to_dict() or {}) if user_doc.exists else {}).get("ai_profile") or {}
    perfil_atual = ai_profile.get("personalidade")

    keys_doc = _cached_doc_get(db, "system", "api_keys")
    api_key = keys_doc.to_dict().get("gemini_api_key") if keys_doc.exists else None
    if not api_key:
        print("[Personalidade] Gemini API Key não configurada.")
        return

    genai = get_genai_module()
    client = genai.Client(api_key=api_key)
    correcoes_text = _format_ajustes_personalidade(ai_profile.get("personalidade_ajustes"))
    prompt = _build_personality_prompt(perfil_atual, ajustes_text, diaries_text, correcoes_text)

    try:
        response = generate_content_logged(
            client,
            model=GEMINI_FRONTIER_MODEL,
            contents=prompt,
            feature=FEATURE_PERSONALITY,
            db=db,
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        perfil_novo = json.loads(response.text or "{}")
    except Exception as exc:
        print(f"[Personalidade] Falha ao consolidar: {exc}")
        return

    if not isinstance(perfil_novo, dict) or not perfil_novo:
        print("[Personalidade] Resposta vazia/inválida do modelo.")
        return

    historico = ai_profile.get("personalidade_historico") or []
    if perfil_atual:
        historico = (historico + [{"versao": perfil_atual, "vigente_ate": datetime.now(timezone.utc).isoformat()}])[-6:]

    user_ref.set({
        "ai_profile": {
            "personalidade": perfil_novo,
            "personalidade_atualizada_em": datetime.now(timezone.utc).isoformat(),
            "personalidade_historico": historico,
        }
    }, merge=True)
    print(f"[Personalidade] Perfil atualizado a partir de {len(diaries)} diário(s).")

    # Espelho semanal: falha no envio só vai para o log — o perfil já está gravado.
    try:
        _enviar_espelho_semanal(db, perfil_novo, perfil_atual)
    except Exception as exc:
        print(f"[Personalidade] Falha ao enviar espelho semanal: {exc}")


# --------------------------------------------------------------------------- #
# Espelho semanal no Telegram + correções diretas do perfil                    #
# --------------------------------------------------------------------------- #

def _itens(valor) -> list[str]:
    if not isinstance(valor, list):
        return []
    return [str(v).strip() for v in valor if str(v or "").strip()]


def _diff_itens(antigos, novos) -> tuple[list[str], list[str]]:
    """(entraram, saíram) entre duas listas do perfil, sem diferenciar
    maiúsculas/espaços — o modelo reescreve a mesma ideia com caixa diferente."""
    antigos_l, novos_l = _itens(antigos), _itens(novos)
    chave_antigos = {a.casefold() for a in antigos_l}
    chave_novos = {n.casefold() for n in novos_l}
    entraram = [n for n in novos_l if n.casefold() not in chave_antigos]
    sairam = [a for a in antigos_l if a.casefold() not in chave_novos]
    return entraram, sairam


def _juntar_itens(itens: list[str]) -> str:
    mostrados = [
        html.escape(i if len(i) <= 80 else i[:80].rstrip() + "…")
        for i in itens[:MAX_ITENS_POR_LINHA_ESPELHO]
    ]
    extra = len(itens) - len(mostrados)
    texto = "; ".join(mostrados)
    return f"{texto} (+{extra})" if extra > 0 else texto


def build_mirror_message(perfil_novo: dict, perfil_anterior: dict | None) -> str:
    """Texto HTML (4–5 linhas) do espelho semanal: resumo do perfil novo e o
    que entrou/saiu em gatilhos de estresse e fontes de energia desde a
    versão anterior."""
    perfil_novo = perfil_novo if isinstance(perfil_novo, dict) else {}
    linhas = ["🪞 <b>O que percebi em você esta semana</b>"]

    resumo = str(perfil_novo.get("resumo_narrativo") or "").strip()
    if len(resumo) > 400:
        resumo = resumo[:400].rstrip() + "…"
    linhas.append(html.escape(resumo) if resumo else "<i>(sem resumo desta vez)</i>")

    if not isinstance(perfil_anterior, dict) or not perfil_anterior:
        linhas.append("Primeira leitura — ainda não há versão anterior para comparar.")
    else:
        entraram, sairam = [], []
        for campo, rotulo in (("gatilhos_de_estresse", "tensão"), ("fontes_de_energia", "energia")):
            novos, antigos = _diff_itens(perfil_anterior.get(campo), perfil_novo.get(campo))
            if novos:
                entraram.append(f"{rotulo}: {_juntar_itens(novos)}")
            if antigos:
                sairam.append(f"{rotulo}: {_juntar_itens(antigos)}")
        if entraram:
            linhas.append("➕ " + " | ".join(entraram))
        if sairam:
            linhas.append("➖ " + " | ".join(sairam))
        if not entraram and not sairam:
            linhas.append("Sem mudança em gatilhos de tensão nem em fontes de energia desde a última leitura.")

    linhas.append("<i>São impressões, não fatos. Se algo não bate, toque em ✏️ Corrigir.</i>")
    return "\n".join(linhas)


def mirror_keyboard() -> list[list[dict]]:
    return [[
        {"text": "✏️ Corrigir", "callback_data": PERFIL_CALLBACK_CORRIGIR},
        {"text": "👍 Está certo", "callback_data": PERFIL_CALLBACK_OK},
    ]]


def _enviar_espelho_semanal(db, perfil_novo: dict, perfil_anterior: dict | None) -> bool:
    from main import _resolve_default_telegram_chat_id
    from telegram_utils import _get_telegram_token, _send_telegram_message_with_keyboard

    chat_id = _resolve_default_telegram_chat_id(db)
    if not chat_id:
        print("[Personalidade] Sem chat_id do Telegram; espelho semanal não enviado.")
        return False
    token = _get_telegram_token(db)
    texto = build_mirror_message(perfil_novo, perfil_anterior)
    _send_telegram_message_with_keyboard(token, chat_id, texto, mirror_keyboard())
    return True


def registrar_ajuste_personalidade(db, texto: str) -> str:
    """
    Grava a correção em texto livre que o usuário mandou depois de tocar em
    "✏️ Corrigir" no espelho semanal (sessão `pending_perfil_ajuste`, ver
    telegram_message_deterministic.py). Fica em
    `usuarios/{uid}.ai_profile.personalidade_ajustes` (lista com teto) e entra
    na próxima `consolidar_personalidade`. Devolve a resposta para o chat.
    """
    texto = str(texto or "").strip()
    if not texto:
        return "⚠️ Não recebi nenhum texto para a correção."
    if len(texto) > MAX_CHARS_AJUSTE:
        texto = texto[:MAX_CHARS_AJUSTE].rstrip() + "…"

    uid = _resolve_default_uid(db)
    if not uid:
        return "⚠️ Não encontrei o seu perfil para anotar a correção."

    user_ref = db.collection("usuarios").document(uid)
    snap = user_ref.get()
    ai_profile = ((snap.to_dict() or {}) if snap.exists else {}).get("ai_profile") or {}
    ajustes = ai_profile.get("personalidade_ajustes")
    ajustes = list(ajustes) if isinstance(ajustes, list) else []
    ajustes.append({
        "texto": texto,
        "em": datetime.now(timezone.utc).isoformat(),
        "versao_perfil": ai_profile.get("personalidade_atualizada_em"),
    })
    user_ref.set(
        {"ai_profile": {"personalidade_ajustes": ajustes[-MAX_AJUSTES_PERSONALIDADE:]}},
        merge=True,
    )
    return AJUSTE_CONFIRMACAO
