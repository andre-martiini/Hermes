"""
Diário pessoal: ajuste, a pedido do usuário, de um diário já gravado em
`diario_pessoal/{YYYY-MM-DD}` (callable `ajustarDiarioPessoal` e o fluxo
"✍️ Ajustar" do Telegram).

Os jobs agendados que geravam o diário (21h30) e consolidavam a personalidade
semanal (domingo 22h) foram removidos em 26/09/2026: a feature estava
desligada em `system/settings.personal_diary` e não será religada (ver
docs/okf/operacoes/custos.md). Os diários antigos continuam editáveis.

Ver docs/okf/propostas/automacoes-canais-e-diario-pessoal.md (eixo 3).
"""

from datetime import datetime, timezone

from firebase_functions import https_fn, options

from gemini_cost_controls import GEMINI_FRONTIER_MODEL, generate_content_logged

FEATURE_DIARY_EDIT = "personal_diary.edit"


def _load_settings(db) -> dict:
    from main import _cached_doc_get

    doc = _cached_doc_get(db, "system", "settings")
    cfg = ((doc.to_dict() or {}) if doc.exists else {}).get("personal_diary") or {}
    return {"enabled": bool(cfg.get("enabled", False))}


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


def _rewrite_diary_with_feedback(db, date_str: str, feedback_text: str) -> tuple[str | None, str]:
    """
    Núcleo do ajuste via IA: reescreve o diário de `date_str` incorporando o
    pedido do usuário e persiste o resultado. O diff é guardado em `ajustes[]`:
    é o sinal de calibração de personalidade mais direto que o usuário dá ao
    sistema (era insumo do antigo job `consolidar_personalidade`, removido).

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
