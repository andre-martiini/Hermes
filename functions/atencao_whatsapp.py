"""Detectores reativos da fila de atencao baseados em WhatsApp.

Dois detectores, cada um atras da propria flag em `system/settings.atencao`,
disparados por trigger Firestore em `whatsapp_messages/{message_id}` (on-create) -
nao por cron, porque a latencia importa aqui: uma promessa precisa registrar a
hora exata em que foi feita, e um audio relevante deve virar item em segundos.

A unica excecao e o vencimento de promessas (`vencer_promessas`), que precisa de
um relogio e roda a cada 15 minutos.

Nenhum dos dois detectores transcreve audio ou usa LLM - a logica de deteccao e
toda determinística e pura, separada do Firestore, no mesmo espirito de
`atencao.py::avaliar_etapas` (ver testes em `test_atencao_whatsapp.py`).
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from firebase_admin import firestore
from firebase_functions import firestore_fn, scheduler_fn, options

import agent_requests
import atencao
from inbox_pendentes import _normalize_text

PROMESSAS_COLLECTION = "promessas_abertas"

TIPO_PROMESSA_SEM_RETORNO = "promessa_sem_retorno"
TIPO_AUDIO_RELEVANTE = "audio_relevante"

ESTADO_PROMESSA_ABERTA = "aberta"
ESTADO_PROMESSA_CUMPRIDA = "cumprida"
ESTADO_PROMESSA_VENCIDA = "vencida"

DEFAULT_HORAS_PROMESSA = 4
DEFAULT_SEGUNDOS_MIN_AUDIO = 20
JANELA_MERGE_AUDIO_MIN = 10
MIN_CHARS_CUMPRE_PROMESSA = 40

# Padroes de promessa/compromisso. O texto e normalizado (NFD, sem acento,
# minusculo - ver `_normalize_text` de inbox_pendentes.py) antes de comparar,
# entao os padroes abaixo ja sao escritos sem acento.
_PADROES_PROMESSA_RAW = [
    r"vou ver e te (retorno|falo|aviso)",
    r"ja estou vendo",
    r"te (retorno|aviso|falo) (ainda hoje|hoje|amanha|depois|mais tarde|em breve|assim que)",
    r"vou (verificar|checar|conferir|olhar) e (te )?(retorno|aviso|falo)",
    r"deixa comigo",
    r"pode deixar",
]
_PADROES_PROMESSA = [re.compile(p) for p in _PADROES_PROMESSA_RAW]

# Cache em memoria (mesmo padrao de `mcp_server.py::_ACCESS_CACHE_TTL_SEC`) do
# mapa chat_id -> acao ativa vinculada. Evita varrer `tarefas` a cada mensagem
# recebida - o detector de audio so precisa saber "existe uma acao ativa
# vinculada a este chat?", e uma folga de alguns minutos nessa resposta nao
# tem custo pratico (a fila de atencao ja e consumida em rotinas do Claude,
# nunca em tempo real).
_ACOES_POR_CHAT_CACHE: dict = {"expira_em": 0.0, "mapa": {}}
_ACOES_POR_CHAT_TTL_SEG = 300


def _acoes_ativas_por_chat_cached(db) -> dict[str, dict]:
    agora = datetime.now(timezone.utc).timestamp()
    if agora < _ACOES_POR_CHAT_CACHE["expira_em"]:
        return _ACOES_POR_CHAT_CACHE["mapa"]
    mapa = atencao.mapear_acoes_ativas_por_chat(db)
    _ACOES_POR_CHAT_CACHE["mapa"] = mapa
    _ACOES_POR_CHAT_CACHE["expira_em"] = agora + _ACOES_POR_CHAT_TTL_SEG
    return mapa


# ---------------------------------------------------------------------------
# Detector A - promessa_sem_retorno (logica pura)
# ---------------------------------------------------------------------------


def mensagem_e_promessa(texto: str) -> bool:
    """True se o texto (from_me, message_type == 'chat') casa com algum padrao
    de compromisso. Comparacao sempre normalizada (sem acento, minusculo)."""
    normalizado = _normalize_text(texto)
    if not normalizado:
        return False
    return any(p.search(normalizado) for p in _PADROES_PROMESSA)


def mensagem_cumpre_promessa(texto: str, tem_midia: bool) -> bool:
    """Fase 2 do detector: a mensagem seguinte (from_me) fecha a promessa aberta?

    Midia/documento sempre cumpre. Uma mensagem que e ela propria uma nova
    promessa nao cumpre a anterior (ela a substitui - ver `decidir_acao_mensagem_from_me`).
    Fora isso, so mensagens com mais de `MIN_CHARS_CUMPRE_PROMESSA` caracteres
    contam - "ok", "beleza" e as demais respostas curtas de encerramento
    (mesmo espirito de `inbox_pendentes._DEFAULT_ENDINGS`) nao cumprem.
    """
    if tem_midia:
        return True
    if mensagem_e_promessa(texto):
        return False
    return len(str(texto or "").strip()) > MIN_CHARS_CUMPRE_PROMESSA


def _promessa_doc_id(promessa: dict) -> str:
    return f"{promessa['chat_id']}_{promessa['mensagem_id']}"


def montar_promessa(mensagem: dict, horas: float) -> dict:
    """Monta o documento de `promessas_abertas` a partir da mensagem from_me que
    disparou a Fase 1 (ja confirmada como promessa pelo chamador)."""
    prometido_em = mensagem["timestamp"]
    return {
        "chat_id": mensagem["chat_id"],
        "chat_name": mensagem.get("chat_name") or mensagem["chat_id"],
        "mensagem_id": mensagem["wa_message_id"],
        "texto": mensagem.get("content") or "",
        "prometido_em": prometido_em,
        "vence_em": prometido_em + timedelta(hours=horas),
        "estado": ESTADO_PROMESSA_ABERTA,
        "acao_id": mensagem.get("acao_id"),
    }


def decidir_acao_mensagem_from_me(mensagem: dict, promessa_atual: dict | None, horas: float) -> dict:
    """Decisao pura para toda mensagem from_me == true em um chat individual.

    `promessa_atual` e a promessa em estado 'aberta' OU 'vencida' que o chat
    tiver no momento (ou None). Retorna um dict com `acao`:
      - "criar": uma nova promessa foi detectada (Fase 1) - substitui a atual,
        se houver (`substituiu`).
      - "cumprir": a mensagem fecha a promessa atual (Fase 2). Se a promessa
        estava 'vencida', o item correspondente na fila `atencao` deve ser
        resolvido automaticamente - `resolver_item_fila` traz o suficiente
        para isso (unico caso em que um detector fecha item sem o dono).
      - "nenhuma": nada a fazer.
    """
    texto = mensagem.get("content") or ""
    tem_midia = bool(mensagem.get("media"))

    # Fase 1: so mensagem de texto pode ser reconhecida como promessa nova.
    if mensagem.get("message_type") == "chat" and mensagem_e_promessa(texto):
        return {
            "acao": "criar",
            "promessa": montar_promessa(mensagem, horas),
            "substituiu": promessa_atual is not None,
        }

    # Fase 2: qualquer mensagem from_me pode cumprir uma promessa aberta/vencida.
    if promessa_atual is not None and mensagem_cumpre_promessa(texto, tem_midia):
        resultado = {"acao": "cumprir", "chave_doc": _promessa_doc_id(promessa_atual)}
        if promessa_atual.get("estado") == ESTADO_PROMESSA_VENCIDA:
            hora_str = mensagem["timestamp"].strftime("%H:%M")
            resultado["resolver_item_fila"] = {
                "chave_dedupe": f"{TIPO_PROMESSA_SEM_RETORNO}:{promessa_atual['chat_id']}:{promessa_atual['mensagem_id']}",
                "desfecho": f"respondeu em {hora_str}",
            }
        return resultado

    return {"acao": "nenhuma"}


def gerar_item_vencimento(promessa: dict, agora: datetime) -> dict:
    """A partir de uma promessa 'aberta' vencida, monta o item da fila `atencao`."""
    chat_id = promessa["chat_id"]
    mensagem_id = promessa["mensagem_id"]
    chat_name = promessa.get("chat_name") or chat_id
    texto = promessa.get("texto") or ""
    prometido_em = promessa["prometido_em"]
    horas = max(0, round((agora - prometido_em).total_seconds() / 3600))
    resumo = f"Promessa feita em {chat_name}: \"{texto}\" - ainda sem retorno."
    if len(resumo) > 400:
        resumo = resumo[:397] + "..."
    return {
        "origem": "whatsapp",
        "tipo": TIPO_PROMESSA_SEM_RETORNO,
        "prioridade": atencao.PRIORIDADE_ALTA,
        "titulo": f"Voce disse a {chat_name}: '{texto}' ha {horas}h e ainda nao respondeu",
        "resumo": resumo,
        "acao_id": promessa.get("acao_id"),
        "etapa_id": None,
        "pessoa": chat_name,
        "prazo": prometido_em,
        "evidencia": {"chat_id": chat_id, "mensagem_ids": [mensagem_id]},
        "sugestao": "Responder ou avisar que vai demorar",
        "chave_dedupe": f"{TIPO_PROMESSA_SEM_RETORNO}:{chat_id}:{mensagem_id}",
    }


def avaliar_promessas_vencidas(promessas: list[dict], agora: datetime) -> list[dict]:
    """Filtra promessas 'aberta' com `vence_em` <= agora e monta os itens da fila
    correspondentes. Funcao pura, sem Firestore - mesmo padrao de `avaliar_etapas`."""
    itens = []
    for p in promessas:
        if p.get("estado") != ESTADO_PROMESSA_ABERTA:
            continue
        vence_em = p.get("vence_em")
        if vence_em is None or vence_em > agora:
            continue
        itens.append(gerar_item_vencimento(p, agora))
    return itens


# ---------------------------------------------------------------------------
# Detector B - audio_relevante (logica pura)
# ---------------------------------------------------------------------------


def avaliar_audio(mensagem: dict, contexto: dict) -> dict | None:
    """Decisao pura: este audio (from_me == false, message_type ptt/audio) e
    relevante o bastante para virar item da fila?

    `contexto`:
      - `chat_vinculado` (bool): a condicao 1 OU 2 do detector ja resolvida
        pelo chamador (chat ligado a `tarefas.whatsapp_vinculos`, ou o contato
        do chat ligado a uma acao ativa via `perfil_pessoas`/`interacoes_pessoas`).
      - `acao` (dict | None): a acao ativa vinculada, se houver, com pelo menos
        `id`/`titulo` e os campos que `atencao._acao_e_critica` usa.
      - `segundos_min` (int, opcional): minimo de duracao para nao ser ruido
        (padrao `DEFAULT_SEGUNDOS_MIN_AUDIO`). Quando a duracao nao e conhecida
        (o worker ainda nao grava `media.duration_seconds` - ver nota no PR),
        o audio e tratado como relevante em vez de silenciado por falta de dado.
    """
    if mensagem.get("from_me"):
        return None
    if mensagem.get("message_type") not in ("ptt", "audio"):
        return None
    if not contexto.get("chat_vinculado"):
        return None

    media = mensagem.get("media") or {}
    duracao = media.get("duration_seconds")
    segundos_min = contexto.get("segundos_min", DEFAULT_SEGUNDOS_MIN_AUDIO)
    if duracao is not None and duracao < segundos_min:
        return None

    acao = contexto.get("acao") or {}
    hoje_str = mensagem["timestamp"].strftime("%Y-%m-%d")
    critica = bool(acao) and atencao._acao_e_critica(acao, hoje_str)
    prioridade = atencao.PRIORIDADE_ALTA if critica else atencao.PRIORIDADE_MEDIA

    autor = mensagem.get("author_name") or "Contato"
    chat_id = mensagem["chat_id"]
    duracao_str = f"{int(duracao)}s" if duracao is not None else "duracao desconhecida"
    titulo_acao = str(acao.get("titulo") or "").strip()
    sufixo = f" na conversa vinculada a '{titulo_acao}'" if titulo_acao else " em conversa vinculada a uma acao ativa"

    return {
        "origem": "whatsapp",
        "tipo": TIPO_AUDIO_RELEVANTE,
        "prioridade": prioridade,
        "titulo": f"Audio de {autor} ({duracao_str}){sufixo}",
        "resumo": f"Audio recebido de {autor} em {mensagem.get('chat_name') or chat_id}.",
        "acao_id": acao.get("id"),
        "etapa_id": None,
        "pessoa": autor,
        "prazo": None,
        "evidencia": {"chat_id": chat_id, "mensagem_ids": [mensagem["wa_message_id"]]},
        "sugestao": "Consolidar com consolidar_whatsapp e registrar no diario da acao",
        "chave_dedupe": f"{TIPO_AUDIO_RELEVANTE}:{chat_id}:{mensagem['wa_message_id']}",
        "_ultimo_audio_em": mensagem["timestamp"],
    }


def mesclar_ou_criar_item_audio(existing_item: dict | None, novo: dict, mensagem: dict,
                                  janela_min: int = JANELA_MERGE_AUDIO_MIN) -> dict:
    """Varios audios em sequencia no mesmo chat (< `janela_min` min entre eles)
    viram um item so, com todos os ids em `evidencia.mensagem_ids` - usa a
    `chave_dedupe` do primeiro audio da sequencia."""
    if existing_item is None:
        return novo

    ultimo_audio_em = existing_item.get("_ultimo_audio_em") or existing_item.get("atualizado_em")
    if ultimo_audio_em is not None and (mensagem["timestamp"] - ultimo_audio_em) <= timedelta(minutes=janela_min):
        merged = dict(existing_item)
        ids = list((merged.get("evidencia") or {}).get("mensagem_ids") or [])
        novo_id = mensagem["wa_message_id"]
        if novo_id not in ids:
            ids.append(novo_id)
        merged["evidencia"] = {**(merged.get("evidencia") or {}), "mensagem_ids": ids}
        merged["_ultimo_audio_em"] = mensagem["timestamp"]
        return merged

    return novo


# ---------------------------------------------------------------------------
# Resposta e aprovação de rascunhos do outbox pelo WhatsApp próprio
# ---------------------------------------------------------------------------

_COMANDOS_APROVAR = {
    "sim", "s", "ok", "pode", "manda", "mandar", "aprova", "aprovar",
    "envia", "enviar", "confirma", "confirmar", "pode enviar", "pode mandar",
    "sim pode mandar", "sim pode enviar", "sim manda", "sim envia",
    "ok pode mandar", "ok pode enviar", "ok manda", "ok envia",
    "pode sim", "manda sim", "positivo", "vai", "manda ver", "manda bala",
}

_COMANDOS_DESCARTAR = {
    "nao", "n", "descarta", "descartar", "cancela", "cancelar",
    "ignora", "ignorar", "lixo", "deleta", "deletar", "apaga", "apagar",
    "descarta isso", "cancela isso", "nao manda", "nao enviar", "nao mande",
}


def interpretar_resposta_aprovacao_whatsapp(
    mensagem: dict,
    rascunhos_pendentes: list[dict],
    owner_chat_id: str | None = None,
) -> dict | None:
    """Interpreta se uma mensagem enviada pelo dono no self-chat é uma aprovação,
    descarte ou edição de rascunho de WhatsApp aguardando aprovação no outbox.

    Regras puras (sem I/O):
    - Só considera mensagens `from_me == True` no chat do próprio dono (`owner_chat_id`).
    - Qualquer outro chat ou remetente retorna None (nunca interfere em terceiros).
    - Se não houver rascunhos pendentes: retorna None (mensagem pessoal comum do dono).
    - Se houver mais de um rascunho pendente: retorna `{"acao": "ambiguo", "quantidade": N}`.
    - Se houver exatamente um rascunho pendente:
      - Comando em `_COMANDOS_APROVAR` -> `{"outbox_id": ..., "acao": "aprovar"}`
      - Comando em `_COMANDOS_DESCARTAR` -> `{"outbox_id": ..., "acao": "descartar"}`
      - Qualquer outro texto não vazio -> `{"outbox_id": ..., "acao": "editar", "novo_texto": ...}`
    """
    if not owner_chat_id or not str(owner_chat_id).strip():
        return None

    if not mensagem.get("from_me"):
        return None

    chat_id = str(mensagem.get("chat_id") or "").strip()
    if chat_id != str(owner_chat_id).strip():
        return None

    if not rascunhos_pendentes:
        return None

    raw_texto = str(mensagem.get("content") or "").strip()
    if not raw_texto:
        return None

    if len(rascunhos_pendentes) > 1:
        return {
            "acao": "ambiguo",
            "quantidade": len(rascunhos_pendentes),
        }

    rascunho = rascunhos_pendentes[0]
    outbox_id = str(rascunho.get("id") or rascunho.get("outbox_id") or "").strip()
    if not outbox_id:
        return None

    norm = _normalize_text(raw_texto)
    clean_cmd = re.sub(r"[^\w\s]", "", norm).strip()

    if clean_cmd in _COMANDOS_APROVAR:
        return {"outbox_id": outbox_id, "acao": "aprovar"}

    if clean_cmd in _COMANDOS_DESCARTAR:
        return {"outbox_id": outbox_id, "acao": "descartar"}

    return {
        "outbox_id": outbox_id,
        "acao": "editar",
        "novo_texto": raw_texto,
    }


# ---------------------------------------------------------------------------
# Integracao com Firestore
# ---------------------------------------------------------------------------


def _flag_promessa(db) -> tuple[bool, float]:
    settings_doc = db.collection("system").document("settings").get()
    settings = settings_doc.to_dict() if settings_doc.exists else {}
    cfg = ((settings or {}).get("atencao") or {}).get("promessa_sem_retorno") or {}
    return bool(cfg.get("enabled", False)), float(cfg.get("horas", DEFAULT_HORAS_PROMESSA))


def _flag_audio(db) -> tuple[bool, int]:
    settings_doc = db.collection("system").document("settings").get()
    settings = settings_doc.to_dict() if settings_doc.exists else {}
    cfg = ((settings or {}).get("atencao") or {}).get("audio_relevante") or {}
    return bool(cfg.get("enabled", False)), int(cfg.get("segundos_min", DEFAULT_SEGUNDOS_MIN_AUDIO))


def _pessoa_vinculada_a_acao_ativa(db, chat_id: str) -> dict | None:
    """Condicao 2 do detector audio_relevante: o contato do chat individual
    (`perfil_pessoas.whatsapp_chat_id`, gravado por `linkWhatsappContacts`) tem
    mencao a alguma acao ativa via `interacoes_pessoas.tarefa_id` (extraida por
    `on_tarefa_written_extract_people`, knowledge_graph.py). So chamada quando a
    condicao 1 (whatsapp_vinculos direto na acao) ja falhou - mecanismo best
    effort, mais raro, nao vale cachear como a condicao 1."""
    pessoas = list(
        db.collection("perfil_pessoas").where("whatsapp_chat_id", "==", chat_id).limit(1).stream()
    )
    if not pessoas:
        return None
    pessoa_id = pessoas[0].id

    interacoes = list(
        db.collection("interacoes_pessoas").where("pessoa_id", "==", pessoa_id).limit(20).stream()
    )
    tarefa_ids = {str((i.to_dict() or {}).get("tarefa_id") or "") for i in interacoes}
    tarefa_ids.discard("")

    for tarefa_id in tarefa_ids:
        tdoc = db.collection("tarefas").document(tarefa_id).get()
        if not tdoc.exists:
            continue
        d = tdoc.to_dict() or {}
        status = str(d.get("status") or "").strip().lower()
        if status in atencao._ACTIVE_STATUS_ALIASES or status in atencao._STANDBY_STATUS_ALIASES:
            d["id"] = tdoc.id
            return d
    return None


def _processar_promessa(db, mensagem: dict) -> None:
    if not mensagem.get("from_me") or mensagem.get("is_group"):
        return
    enabled, horas = _flag_promessa(db)
    if not enabled:
        return
    chat_id = str(mensagem.get("chat_id") or "").strip()
    if not chat_id:
        return

    promessas_ref = db.collection(PROMESSAS_COLLECTION)
    ativos = list(
        promessas_ref.where("chat_id", "==", chat_id)
        .where("estado", "in", [ESTADO_PROMESSA_ABERTA, ESTADO_PROMESSA_VENCIDA])
        .stream()
    )
    promessa_atual = None
    if ativos:
        promessa_atual = ativos[0].to_dict() or {}
        promessa_atual["_doc_id"] = ativos[0].id

    decisao = decidir_acao_mensagem_from_me(mensagem, promessa_atual, horas)

    if decisao["acao"] == "criar":
        nova = decisao["promessa"]
        doc_id = _promessa_doc_id(nova)
        if promessa_atual is not None and promessa_atual["_doc_id"] != doc_id:
            promessas_ref.document(promessa_atual["_doc_id"]).delete()
        promessas_ref.document(doc_id).set(nova)
        return

    if decisao["acao"] == "cumprir" and promessa_atual is not None:
        promessas_ref.document(promessa_atual["_doc_id"]).update({
            "estado": ESTADO_PROMESSA_CUMPRIDA,
            "cumprida_em": firestore.SERVER_TIMESTAMP,
        })
        resolver = decisao.get("resolver_item_fila")
        if resolver:
            item_ref = db.collection(atencao.COLLECTION).document(resolver["chave_dedupe"])
            if item_ref.get().exists:
                item_ref.update({
                    "estado": atencao.ESTADO_RESOLVIDO,
                    "desfecho": resolver["desfecho"],
                    "resolvido_em": firestore.SERVER_TIMESTAMP,
                    "atualizado_em": firestore.SERVER_TIMESTAMP,
                })


def _processar_audio(db, mensagem: dict) -> None:
    if mensagem.get("from_me"):
        return
    if mensagem.get("message_type") not in ("ptt", "audio"):
        return
    enabled, segundos_min = _flag_audio(db)
    if not enabled:
        return

    chat_id = str(mensagem.get("chat_id") or "").strip()
    if not chat_id:
        return

    acao = _acoes_ativas_por_chat_cached(db).get(chat_id)
    if acao is None and not mensagem.get("is_group"):
        acao = _pessoa_vinculada_a_acao_ativa(db, chat_id)
    if acao is None:
        return

    contexto = {"chat_vinculado": True, "acao": acao, "segundos_min": segundos_min}
    novo_item = avaliar_audio(mensagem, contexto)
    if novo_item is None:
        return

    atencao_ref = db.collection(atencao.COLLECTION)
    abertos = list(
        atencao_ref.where("tipo", "==", TIPO_AUDIO_RELEVANTE)
        .where("estado", "==", atencao.ESTADO_ABERTO)
        .where("evidencia.chat_id", "==", chat_id)
        .stream()
    )
    existing_item = None
    existing_doc_id = None
    if abertos:
        existing_doc_id = abertos[0].id
        existing_item = abertos[0].to_dict() or {}

    item = mesclar_ou_criar_item_audio(existing_item, novo_item, mensagem)
    doc_id = existing_doc_id or item["chave_dedupe"]

    payload = dict(item)
    payload["atualizado_em"] = firestore.SERVER_TIMESTAMP
    if existing_doc_id is None:
        payload["estado"] = atencao.ESTADO_ABERTO
        payload["criado_em"] = firestore.SERVER_TIMESTAMP
    atencao_ref.document(doc_id).set(payload, merge=True)

    # Hook do PR 1 (Fase 1): enfileira ou atualiza pedido de consolidacao autonoma
    try:
        msg_ids = (item.get("evidencia") or {}).get("mensagem_ids") or [mensagem["wa_message_id"]]
        req_payload = agent_requests.montar_payload_consolidar_audio(
            chat_id=chat_id,
            chat_name=mensagem.get("chat_name") or chat_id,
            mensagem_ids=msg_ids,
            acao_id=item.get("acao_id"),
            item_atencao_id=doc_id,
        )
        agent_requests.enfileirar_ou_atualizar(
            db,
            doc_id=f"consolidar_audio:{doc_id}",
            tipo=agent_requests.TIPO_CONSOLIDAR_AUDIO,
            payload=req_payload,
            origem="atencao_whatsapp.audio_relevante",
            acao_id=item.get("acao_id"),
            item_atencao_id=doc_id,
        )
    except Exception as ar_exc:
        print(f"[AtencaoWhatsApp] Falha ao enfileirar agent_request para audio: {ar_exc}")


def _obter_whatsapp_owner_chat_id(db) -> str | None:
    settings_doc = db.collection("system").document("settings").get()
    settings = settings_doc.to_dict() if settings_doc.exists else {}
    owner_id = (settings or {}).get("whatsapp_owner_chat_id")
    if owner_id:
        return str(owner_id).strip()
    return None


def _processar_aprovacao_outbox(db, mensagem: dict) -> None:
    """Consome a mensagem no self-chat do dono para aprovar, descartar ou editar
    rascunhos de WhatsApp pendentes no outbox."""
    # Fast path: se a mensagem não é from_me, nunca pode ser aprovação do dono
    if not mensagem.get("from_me"):
        return

    owner_chat_id = _obter_whatsapp_owner_chat_id(db)
    if not owner_chat_id:
        return

    chat_id = str(mensagem.get("chat_id") or "").strip()
    if chat_id != owner_chat_id:
        return

    import outbox_aprovacao

    res_listar = outbox_aprovacao.listar_rascunhos(db, limite=50)
    pendentes = res_listar.get("rascunhos") or []

    decisao = interpretar_resposta_aprovacao_whatsapp(mensagem, pendentes, owner_chat_id)
    if not decisao:
        return

    acao = decisao.get("acao")
    outbox_id = decisao.get("outbox_id")

    if acao == "aprovar" and outbox_id:
        outbox_aprovacao.aprovar_rascunho(db, outbox_id=outbox_id, aprovado_via="whatsapp")
    elif acao == "descartar" and outbox_id:
        outbox_aprovacao.descartar_rascunho(db, outbox_id=outbox_id)
    elif acao == "editar" and outbox_id:
        novo_texto = decisao.get("novo_texto") or ""
        outbox_aprovacao.aplicar_edicao_rascunho(db, outbox_id=outbox_id, novo_texto=novo_texto)
    elif acao == "ambiguo":
        qtd = decisao.get("quantidade", 0)
        print(f"[AtencaoWhatsApp] Resposta no self-chat ambígua: {qtd} rascunhos pendentes no outbox.")


# ---------------------------------------------------------------------------
# Cloud Functions
# ---------------------------------------------------------------------------


@firestore_fn.on_document_created(
    document="whatsapp_messages/{message_id}",
    memory=options.MemoryOption.MB_256,
    timeout_sec=60,
)
def on_whatsapp_message_atencao(event: firestore_fn.Event[firestore_fn.DocumentSnapshot | None]) -> None:
    """Roda os detectores reativos a cada mensagem de WhatsApp capturada,
    cada um atras da propria flag e isolado em seu proprio try/except - uma
    falha em um detector nunca deve impedir o outro nem quebrar a captura."""
    snap = event.data
    if snap is None or not snap.exists:
        return

    mensagem = snap.to_dict() or {}
    mensagem.setdefault("wa_message_id", mensagem.get("wa_message_id") or snap.id)

    from main import get_db
    db = get_db()

    try:
        _processar_promessa(db, mensagem)
    except Exception as exc:
        print(f"[AtencaoWhatsApp] Falha no detector promessa_sem_retorno: {exc}")

    try:
        _processar_audio(db, mensagem)
    except Exception as exc:
        print(f"[AtencaoWhatsApp] Falha no detector audio_relevante: {exc}")

    try:
        _processar_aprovacao_outbox(db, mensagem)
    except Exception as exc:
        print(f"[AtencaoWhatsApp] Falha no detector aprovacao_outbox: {exc}")


@scheduler_fn.on_schedule(
    schedule="every 15 minutes",
    timezone="America/Sao_Paulo",
    memory=options.MemoryOption.MB_256,
    timeout_sec=120,
)
def vencer_promessas(event: scheduler_fn.ScheduledEvent = None) -> None:
    """Cloud Function agendada a cada 15 min: fecha o relogio das promessas
    'aberta' vencidas, gerando/atualizando o item correspondente na fila."""
    from main import get_db

    db = get_db()
    enabled, _horas = _flag_promessa(db)
    if not enabled:
        print("[AtencaoWhatsApp] Detector promessa_sem_retorno desligado; abortando vencer_promessas.")
        return

    agora = datetime.now(timezone.utc)
    promessas_ref = db.collection(PROMESSAS_COLLECTION)
    abertas_docs = list(promessas_ref.where("estado", "==", ESTADO_PROMESSA_ABERTA).stream())

    promessas = []
    for doc in abertas_docs:
        d = doc.to_dict() or {}
        d["_doc_id"] = doc.id
        promessas.append(d)

    itens = avaliar_promessas_vencidas(promessas, agora)
    chaves_vencidas = {item["chave_dedupe"] for item in itens}

    for item in itens:
        chave = item["chave_dedupe"]
        doc_ref = db.collection(atencao.COLLECTION).document(chave)
        existing = doc_ref.get()

        payload = dict(item)
        payload["atualizado_em"] = firestore.SERVER_TIMESTAMP

        if existing.exists:
            existing_estado = (existing.to_dict() or {}).get("estado")
            if existing_estado in atencao.ESTADOS_FECHADOS:
                continue  # o dono ja tratou; vencimento nao reabre
            doc_ref.set(payload, merge=True)
        else:
            payload["estado"] = atencao.ESTADO_ABERTO
            payload["criado_em"] = firestore.SERVER_TIMESTAMP
            doc_ref.set(payload)

    for p in promessas:
        chave = f"{TIPO_PROMESSA_SEM_RETORNO}:{p.get('chat_id')}:{p.get('mensagem_id')}"
        if chave in chaves_vencidas:
            promessas_ref.document(p["_doc_id"]).update({"estado": ESTADO_PROMESSA_VENCIDA})
