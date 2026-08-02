import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from database import get_db

LOCAL_TZ = ZoneInfo(os.getenv("HERMES_TIMEZONE", "America/Sao_Paulo"))

COPILOT_SOUL_DEFAULT = {
    "tone": "Consultivo, analitico e objetivo.",
    "detail_level": "Alto o suficiente para orientar execucao, sem prolixidade.",
    "interaction_style": "Clareza, transparencia sobre incertezas e foco em proximos passos concretos.",
}


def build_voice_context() -> str:
    db = get_db()
    sections = [
        _format_core_context(db),
        _format_user_profile(db),
        _format_recent_memories(db),
    ]
    return "\n\n".join(section for section in sections if section.strip())


def _format_core_context(db) -> str:
    core = _get_doc_dict(db, "system", "copilot_core")
    soul = _get_doc_dict(db, "system", "copilot_soul") or COPILOT_SOUL_DEFAULT

    lines = ["## CONTEXTO CENTRAL DO HERMES"]
    if core.get("content"):
        lines.append(f"- nucleo: {_clean(core.get('content'), 900)}")

    soul_content = soul.get("content")
    if soul_content:
        lines.append(f"- alma/persona: {_clean(soul_content, 700)}")
    else:
        for key in ("tone", "detail_level", "interaction_style"):
            if soul.get(key):
                lines.append(f"- {key}: {_clean(soul.get(key), 260)}")

    lines.append(
        "- modo_voz: responda como conversa falada, priorizando brevidade, clareza e continuidade."
    )
    lines.append(
        "- controle_de_interface_ui: Voce possui ferramentas de UI ativas para navegar e abrir/fechar telas no aplicativo do usuario em tempo real! "
        "1. Para ir a uma aba/modulo ou voltar para a pagina inicial ('dashboard', 'home', 'início', 'ações', 'financeiro', etc.), chame 'navegar_sistema(modulo=...)'. "
        "2. Para ABRIR o modal de uma acao, chame 'abrir_detalhe_acao(id_ou_termo=...)'. "
        "3. Para SAIR da acao, FECHAR o detalhamento ou VOLTAR da acao para a lista/tela principal, chame 'fechar_detalhe_acao()'."
    )
    lines.append(
        "- silencio_apos_comando_ui: REGRA CRITICA: Quando voce executar qualquer ferramenta de navegacao ou controle de interface ('navegar_sistema', 'abrir_detalhe_acao', 'fechar_detalhe_acao', 'abrir_ferramenta', 'filtrar_acoes'), VOCE NAO DEVE FALAR NADA! Nao diga 'aguarde um instante', nao diga 'navegando', nao fale nada. Apenas execute a ferramenta em silencio absoluto. O aplicativo exibira o indicador visual na tela do usuario automaticamente."
    )
    lines.append(
        "- leitura_google_drive: Voce possui a ferramenta 'ler_conteudo_link_drive(url_ou_id=...)' para extrair e ler o conteudo completo em texto de qualquer arquivo ou link do Google Drive (Google Docs, Planilhas, PDFs, Word, etc). "
        "Sempre que uma acao aberta possuir links do Google Drive ou quando o usuario pedir para ler, analisar ou resumir um documento do Drive, chame 'ler_conteudo_link_drive' informando a URL ou ID."
    )
    lines.append(
        "- personalidade_jarvis: Sua personalidade e inspirada no estilo Jarvis — hiper-competente, extremamente eficiente, polida e pontual, porem com um toque sutil de sarcasmo refinado e humor acido moderado. "
        "REGRAS DE PERSONALIDADE:\n"
        "1. EFICIENCIA EM PRIMEIRO LUGAR: Cumpras as tarefas com 100% de precisao e agilidade. Nunca sacrifique a utilidade pelo humor.\n"
        "2. NUNCA PROLIXO: Respostas obrigatoriamente curtas, diretas e concisas.\n"
        "3. HUMOR CONTEXTUAL E ESPORADICO: Comentarios ironicos devem ser esporadicos e SEMPRE contextualizados com a acao, prazo ou volume de trabalho atual. Nao faca piadas genericas.\n"
        "4. TOM REFINADO: Seja elegante e refinado, mantendo a postura de um copiloto de alto nivel."
    )
    return "\n".join(lines)


def _format_user_profile(db) -> str:
    uid = os.getenv("HERMES_DEFAULT_USER_ID", "").strip()
    user_doc = None

    if uid:
        snap = db.collection("usuarios").document(uid).get()
        if snap.exists:
            user_doc = {"id": snap.id, **(snap.to_dict() or {})}

    if not user_doc:
        for snap in db.collection("usuarios").limit(1).stream():
            user_doc = {"id": snap.id, **(snap.to_dict() or {})}
            break

    if not user_doc:
        return "## PERFIL DO USUARIO\n- perfil ainda nao encontrado em usuarios."

    ai_profile = user_doc.get("ai_profile") or {}
    lines = ["## PERFIL DO USUARIO"]
    for key in ("nome", "cargo", "setor", "email"):
        value = ai_profile.get(key) or user_doc.get(key)
        if value:
            lines.append(f"- {key}: {_clean(value, 220)}")

    preferences = ai_profile.get("preferences")
    if preferences:
        lines.append(f"- preferencias: {_clean(json.dumps(preferences, ensure_ascii=False), 420)}")

    history = ai_profile.get("historico_deduzido") or []
    if history:
        compact = [
            {
                "texto": item.get("texto"),
                "at": item.get("at"),
            }
            for item in history[-5:]
            if item.get("texto")
        ]
        if compact:
            lines.append(
                f"- historico_deduzido_recente: {_clean(json.dumps(compact, ensure_ascii=False), 700)}"
            )

    if len(lines) == 1:
        lines.append(f"- id: {user_doc['id']}")
    return "\n".join(lines)


def _format_recent_memories(db, limit: int = 8) -> str:
    memories = []
    try:
        docs = (
            db.collection("knowledge_nodes")
            .order_by("data_criacao", direction="DESCENDING")
            .limit(limit)
            .stream()
        )
    except Exception:
        docs = db.collection("knowledge_nodes").limit(limit).stream()

    for snap in docs:
        data = snap.to_dict() or {}
        content = (
            data.get("texto_memoria")
            or data.get("fato")
            or data.get("resumo")
            or data.get("titulo")
            or ""
        )
        if not content:
            continue
        memories.append(
            f"- [{data.get('tipo') or data.get('categoria') or 'memoria'}] {_clean(content, 280)}"
        )

    if not memories:
        return ""
    return "## MEMORIAS RECENTES DO HERMES\n" + "\n".join(memories)


def _get_doc_dict(db, collection: str, document: str) -> dict:
    try:
        snap = db.collection(collection).document(document).get()
        if snap.exists:
            return snap.to_dict() or {}
    except Exception:
        return {}
    return {}


def _clean(value, max_chars: int) -> str:
    text = str(value or "").replace("\n", " ").strip()
    text = " ".join(text.split())
    if len(text) <= max_chars:
        return text
    return f"{text[: max_chars - 3]}..."
