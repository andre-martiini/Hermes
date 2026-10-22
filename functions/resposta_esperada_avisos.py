"""Sinal de resposta esperada, nível 2: classifica a mensagem e avisa o André.

Medido em 15/10/2026 (ação "Sinal de Resposta Esperada"): numa amostra real de 91
casamentos de confiança média/alta, o nível 1 marcava tudo como resposta (46% de
precisão); o Gemini flash chegou a 84% sem deixar escapar nenhuma resposta de verdade
(Jev 75%, flash-lite 73%, regras 61%). Decisão do dono: Gemini flash, sem Jev.

Cada mensagem que casa com uma espera (confiança média ou alta) é classificada em
R (resolve ou entrega o que se esperava), P (do assunto, não resolve) ou N (ruído).
R e P viram aviso no Telegram, com botões para marcar a etapa como feita e para dizer
se o aviso estava certo — esse retorno mede o acerto em produção. No máximo um aviso
por espera a cada 4 h; um R depois de um P avisa de novo. Conversa com objetivo ativo
(Modo Objetivo) fica de fora. Atrás de system/settings.atencao.resposta_esperada.avisar.
"""

from __future__ import annotations

import html
from datetime import datetime, timedelta, timezone

from firebase_admin import firestore

COLECAO_ESTADO = "sinais_resposta_estado"
COLECAO_AVISOS = "sinais_resposta_avisos"
JANELA_AVISO = timedelta(hours=4)
# "Do assunto, sem resolver" no máximo uma vez por dia por etapa: na 1ª semana
# (16 a 22/10) uma conversa ativa gerou 4 avisos P em 3 dias para a mesma etapa,
# e os P repetidos foram a maior parte dos avisos ruins. R segue com 4 h.
JANELA_AVISO_P = timedelta(hours=24)
CONFIANCAS = ("alta", "media")
CLASSES = ("R", "P", "N")
CRITERIOS = {
    "R": "resolve ou entrega o que se esperava dessa pessoa (confirma, envia, conclui, dá a informação pedida)",
    "P": "é sobre o assunto que se esperava, mas não resolve: faz pergunta, pede algo, promete retorno ou dá andamento parcial",
    "N": "ruído: cumprimento, agradecimento, conversa social, mídia sem conteúdo ou outro assunto",
}
INSTRUCAO = ("Classifique a nova mensagem de WhatsApp em relação ao que o André aguarda dessa pessoa. "
             + " ".join(f"{k}: {v}." for k, v in CRITERIOS.items()) + " Responda só com R, P ou N.")


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def _como_data(valor) -> datetime | None:
    if isinstance(valor, datetime):
        return valor if valor.tzinfo else valor.replace(tzinfo=timezone.utc)
    if isinstance(valor, str) and valor:
        try:
            data = datetime.fromisoformat(valor)
        except ValueError:
            return None
        return data if data.tzinfo else data.replace(tzinfo=timezone.utc)
    return None


# ---------------------------------------------------------------------------
# Contexto e classificação
# ---------------------------------------------------------------------------

def texto_da_mensagem(db, mensagem: dict) -> str:
    texto = str(mensagem.get("content") or mensagem.get("text") or "").strip()
    tipo = str(mensagem.get("message_type") or "")
    extra = mensagem.get("transcription_text") or mensagem.get("image_description")
    if not extra and tipo in ("audio", "ptt"):
        from objetivos_whatsapp import transcrever_audio

        doc_id = str(mensagem.get("id") or mensagem.get("wa_message_id") or "")
        ref = db.collection("whatsapp_messages").document(doc_id) if doc_id else None
        extra = transcrever_audio(db, ref, mensagem) if ref is not None else None
    if extra:
        texto = f"{texto} [{tipo}: {extra}]".strip()
    return texto or (f"[{tipo} sem texto]" if tipo else "")


def _ultima_do_andre(db, chat_id: str, antes) -> str:
    quando = _como_data(antes)
    if not quando:
        return ""
    consulta = (db.collection("whatsapp_messages")
                .where(filter=firestore.FieldFilter("chat_id", "==", chat_id))
                .where(filter=firestore.FieldFilter("timestamp", "<", quando))
                .order_by("timestamp", direction=firestore.Query.DESCENDING)
                .limit(6))
    for snap in consulta.stream():
        dados = snap.to_dict() or {}
        if dados.get("from_me"):
            return str(dados.get("content") or "")[:400]
    return ""


def montar_contexto(entrada: dict, autor: str, texto: str, minha_ultima: str) -> str:
    etapa = entrada.get("etapa_texto")
    return (f"Ação do André: {entrada.get('acao_titulo') or ''}\n"
            + (f"Etapa: {etapa}\n" if etapa else "")
            + f"O André aguarda: {entrada.get('aguardando_de') or ''}\n"
            f"Última mensagem do André antes: {minha_ultima or '(nenhuma)'}\n"
            f"Nova mensagem de {autor}: {texto}")


def classificar_com_gemini(db, contexto: str) -> str | None:
    from google import genai
    from google.genai import types

    from gemini_cost_controls import GEMINI_AGENT_MODEL, generate_content_logged
    from main import _cached_doc_get

    keys = _cached_doc_get(db, "system", "api_keys")
    chave = (keys.to_dict() or {}).get("gemini_api_key") if keys.exists else None
    if not chave:
        return None
    resposta = generate_content_logged(
        genai.Client(api_key=chave),
        model=GEMINI_AGENT_MODEL,
        contents=contexto,
        feature="resposta_esperada_nivel2",
        db=db,
        config=types.GenerateContentConfig(
            system_instruction=INSTRUCAO, temperature=0,
            response_mime_type="text/x.enum",
            response_schema={"type": "STRING", "enum": list(CLASSES)},
        ),
    )
    classe = (resposta.text or "").strip()[:1]
    return classe if classe in CLASSES else None


# ---------------------------------------------------------------------------
# Decisão de avisar
# ---------------------------------------------------------------------------

def _id_estado(match: dict) -> str:
    return f"{match.get('acao_id')}__{match.get('etapa_id')}"


def _dentro_da_janela(estado: dict, agora: datetime) -> bool:
    ultimo = _como_data(estado.get("ultimo_aviso_em"))
    return bool(ultimo) and agora - ultimo < JANELA_AVISO


def _p_recente(estado: dict, agora: datetime) -> bool:
    ultimo_p = _como_data(estado.get("ultimo_p_em"))
    return bool(ultimo_p) and agora - ultimo_p < JANELA_AVISO_P


def avaliar(db, mensagem: dict, resultado: dict, entradas: list[dict], *,
            classificar=None, avisar=None, agora: datetime | None = None) -> dict | None:
    """Classifica a mensagem contra a espera mais provável e avisa se for R ou P."""
    agora = agora or _agora()
    match = next((m for m in resultado.get("matches") or [] if m.get("confianca") in CONFIANCAS), None)
    if not match:
        return None
    chat_id = str(resultado.get("chat_id") or mensagem.get("chat_id") or "")
    from objetivos_whatsapp import objetivo_ativo_do_chat

    if objetivo_ativo_do_chat(db, chat_id):
        return {"status": "objetivo_ativo"}

    estado_ref = db.collection(COLECAO_ESTADO).document(_id_estado(match))
    snap = estado_ref.get()
    estado = (snap.to_dict() or {}) if snap.exists else {}
    # Dentro da janela de um aviso, só um R depois de um P avisa de novo.
    na_janela = _dentro_da_janela(estado, agora)
    if na_janela and estado.get("ultima_classe") == "R":
        return {"status": "janela"}

    entrada = next((e for e in entradas if e.get("acao_id") == match["acao_id"]
                    and e.get("etapa_id") == match["etapa_id"]), {}) or {}
    autor = str((mensagem.get("author_name") if resultado.get("grupo") else
                 (mensagem.get("chat_name") or mensagem.get("contact_name"))) or "o contato")
    texto = texto_da_mensagem(db, mensagem)
    contexto = montar_contexto({**entrada, **match}, autor, texto,
                               _ultima_do_andre(db, chat_id, mensagem.get("timestamp")))
    classe = (classificar or classificar_com_gemini)(db, contexto)

    doc_id = str(mensagem.get("id") or mensagem.get("wa_message_id") or "")
    if doc_id:
        db.collection("sinais_resposta_sombra").document(doc_id).set(
            {"classificacao": {"classe": classe, "modelo": "gemini_flash", "em": agora.isoformat()}}, merge=True)
    if classe not in ("R", "P"):
        return {"status": "ruido" if classe == "N" else "sem_classificacao", "classe": classe}
    if classe == "P" and (na_janela or _p_recente(estado, agora)):
        return {"status": "janela", "classe": classe}

    aviso_ref = db.collection(COLECAO_AVISOS).document()
    aviso = {
        "acao_id": match["acao_id"], "etapa_id": match["etapa_id"], "acao_titulo": entrada.get("acao_titulo"),
        "aguardando_de": match.get("aguardando_de"), "classe": classe, "message_doc_id": doc_id,
        "chat_id": chat_id, "autor": autor, "criado_em": agora.isoformat(),
    }
    aviso_ref.set(aviso)
    novo_estado = {"ultimo_aviso_em": agora, "ultima_classe": classe, "ultimo_aviso_id": aviso_ref.id}
    ultimo_p = agora if classe == "P" else estado.get("ultimo_p_em")
    if ultimo_p:
        novo_estado["ultimo_p_em"] = ultimo_p
    estado_ref.set(novo_estado)
    (avisar or _avisar_no_telegram)(db, aviso_ref.id, aviso, texto)
    return {"status": "avisado", "classe": classe, "aviso_id": aviso_ref.id}


def _avisar_no_telegram(db, aviso_id: str, aviso: dict, texto: str) -> None:
    try:
        from main import _resolve_default_telegram_chat_id
        from telegram_utils import _get_telegram_token, _send_telegram_message_with_keyboard

        token = _get_telegram_token(db)
        chat = _resolve_default_telegram_chat_id(db)
        if not token or not chat:
            return
        resolveu = aviso["classe"] == "R"
        cabeca = "parece ter resolvido" if resolveu else "respondeu sobre o assunto, mas ainda falta algo"
        corpo = (f"💬 <b>{html.escape(aviso['autor'])}</b> {cabeca}\n"
                 f"Ação: <i>{html.escape(str(aviso.get('acao_titulo') or ''))}</i>\n"
                 f"Aguardando: {html.escape(str(aviso.get('aguardando_de') or ''))}\n\n"
                 f"“{html.escape(texto[:400])}”")
        botoes = [{"text": "✅ Etapa feita", "callback_data": f"respesp:{aviso_id}:feito"}] if resolveu else []
        botoes += [{"text": "👍 Aviso certo", "callback_data": f"respesp:{aviso_id}:ok"},
                   {"text": "👎 Não era", "callback_data": f"respesp:{aviso_id}:nao"}]
        _send_telegram_message_with_keyboard(token, chat, corpo, [botoes])
    except Exception as exc:  # noqa: BLE001
        print(f"[RespostaEsperada] Falha ao avisar no Telegram: {exc}")


# ---------------------------------------------------------------------------
# Botões
# ---------------------------------------------------------------------------

def tratar_botao(db, aviso_id: str, acao: str) -> str:
    ref = db.collection(COLECAO_AVISOS).document(aviso_id)
    snap = ref.get()
    if not snap.exists:
        return "Aviso não encontrado."
    aviso = snap.to_dict() or {}
    if acao == "feito":
        from tools.telegram_extended import editar_etapa_da_tarefa

        res = editar_etapa_da_tarefa(db, {
            "task_id": aviso["acao_id"], "etapa_id": aviso["etapa_id"], "estado": "feito",
            "justificativa_diario": f"Resposta de {aviso.get('autor')} pelo WhatsApp (sinal de resposta esperada).",
        }, origem="Sinal de resposta esperada")
        if not str(res).startswith("OK|"):
            return f"Não consegui marcar a etapa: {str(res)[:150]}"
        ref.update({"avaliacao_dono": "certo", "etapa_marcada_feita": True, "avaliado_em": _agora().isoformat()})
        return "Etapa marcada como feita."
    if acao in ("ok", "nao"):
        ref.update({"avaliacao_dono": "certo" if acao == "ok" else "errado", "avaliado_em": _agora().isoformat()})
        return "Anotado, obrigado." if acao == "ok" else "Anotado: esse não era. Uso isso para medir o acerto."
    return "Ação não reconhecida."
