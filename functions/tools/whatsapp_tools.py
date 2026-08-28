"""Leitura e consolidacao de conversas do WhatsApp pelo canal MCP.

A maquinaria de consolidacao ja existia e e boa: `whatsapp_consolidation.py`
carrega as mensagens selecionadas, transcreve audio e video, monta o transcript
literal e sintetiza resumo, itens de acao e decisoes. So que era acionavel
apenas pela Caixa de Entrada na web — pelo MCP dava para buscar o resumo de uma
consolidacao ja feita, e nada mais.

Faltava a porta: enxergar as conversas, ler as mensagens para escolher o
recorte, disparar a consolidacao e ler o resultado inteiro.

## A allowlist manda

Toda leitura de conteudo aqui exige que o chat esteja em
`system/settings.whatsapp_ingest.chats_allowlist`.

A decisao e do dono do sistema (2026-08-26) e o motivo importa: conversa de
WhatsApp e o dado mais sensivel do Hermes, e envolve terceiros que nao sabem que
ha um agente lendo.

## Capturar e ler sao decisoes separadas (27/08/2026)

Ate 27/08 a allowlist fazia as duas coisas: dizia o que o worker guardava e o
que o agente podia ler. Quando o dono pediu captura ativa em todos os contatos,
isso apareceu — ligar a captura geral daria ao agente, de uma vez, leitura das
450 conversas individuais. Nao era o pedido.

Agora sao dois campos:

    whatsapp_ingest.capturar_todos     o worker guarda TODA conversa
    whatsapp_ingest.chats_allowlist    o que o agente pode ler

Guardar e um risco (armazenamento); deixar um agente ler e outro (uso). Manter
os dois no mesmo interruptor obrigava a aceitar os dois juntos.

`listar_conversas` e a unica que enxerga alem da allowlist, e de proposito:
listar nome de conversa nao e ler conteudo, e sem isso nao da para descobrir o
que existe para liberar.
"""

from __future__ import annotations

from datetime import datetime, timezone

COL_CHATS = "whatsapp_chats"
COL_MENSAGENS = "whatsapp_messages"
COL_CONSOLIDACOES = "whatsapp_consolidacoes"
COL_OUTBOX = "whatsapp_outbox"

# Mesmo teto de `whatsapp_consolidation.MAX_MESSAGES_PER_JOB`. Replicado aqui
# para a recusa sair antes de criar o job, com mensagem util, em vez de o
# trigger falhar depois.
MAX_MENSAGENS_POR_JOB = 200

# O transcript literal e a conversa inteira, palavra por palavra. Fica fora da
# resposta por padrao: e o campo mais sensivel e o maior, e quase sempre o
# resumo com itens de acao ja responde.
LIMITE_TRANSCRIPT_CHARS = 20_000


class WhatsAppNaoMonitorado(Exception):
    """Chat fora da allowlist. Nao e erro de uso: e o limite funcionando."""


def _config_ingest(db) -> dict:
    snap = db.collection("system").document("settings").get()
    dados = (snap.to_dict() or {}) if snap.exists else {}
    return dados.get("whatsapp_ingest") or {}


def _allowlist(db) -> set[str]:
    """Conversas que o agente pode ler. Nao e a lista do que se captura."""
    bruto = _config_ingest(db).get("chats_allowlist") or []
    return {str(x).strip() for x in bruto if str(x).strip()}


def _captura_total(db) -> bool:
    """Se o worker esta guardando toda conversa, e nao so as da allowlist."""
    return bool(_config_ingest(db).get("capturar_todos"))


def _leitura_total(db) -> bool:
    """Se o agente pode abrir qualquer conversa, sem consultar a allowlist.

    Ligado pelo dono em 27/08/2026, depois de a ressalva ter sido colocada: a
    leitura e uma ferramenta que ELE aciona, quando pergunta alguma coisa — nao
    uma varredura de fundo. A exposicao acontece no momento do pedido.

    Continua sendo um interruptor, e nao a remocao do mecanismo: desligar
    devolve o comportamento restrito sem precisar de deploy, e a allowlist
    permanece intacta enquanto isso.
    """
    return bool(_config_ingest(db).get("leitura_total"))


def _exigir_monitorado(db, chat_id: str) -> None:
    chat_id = (chat_id or "").strip()
    if not chat_id:
        raise WhatsAppNaoMonitorado("Informe o chat_id.")
    if _leitura_total(db):
        return
    if chat_id not in _allowlist(db):
        raise WhatsAppNaoMonitorado(
            f"A conversa '{chat_id}' nao esta monitorada. O Hermes so le conteudo "
            "de conversas na allowlist — habilite na Caixa de Entrada do WhatsApp "
            "se quiser que ela seja acompanhada. Use listar_conversas_whatsapp "
            "para ver quais estao monitoradas."
        )


def _iso(valor) -> str | None:
    if valor is None:
        return None
    return valor.isoformat() if hasattr(valor, "isoformat") else str(valor)


# --------------------------------------------------------------------------
# Leitura
# --------------------------------------------------------------------------

def listar_conversas(ctx, args: dict) -> dict:
    """Conversas conhecidas, marcando quais estao monitoradas.

    Enxerga alem da allowlist de proposito — nome de conversa nao e conteudo, e
    sem isso nao ha como descobrir o que poderia ser monitorado.
    """
    monitoradas = _allowlist(ctx.db)
    captura_total = _captura_total(ctx.db)
    leitura_total = _leitura_total(ctx.db)
    apenas_monitoradas = args.get("apenas_monitoradas")
    apenas_monitoradas = True if apenas_monitoradas is None else bool(apenas_monitoradas)
    limite = max(1, min(int(args.get("limite") or 60), 200))

    conversas = []
    for snap in ctx.db.collection(COL_CHATS).limit(500).stream():
        dados = snap.to_dict() or {}
        chat_id = str(dados.get("chat_id") or snap.id)
        monitorada = leitura_total or chat_id in monitoradas
        if apenas_monitoradas and not monitorada:
            continue
        conversas.append({
            "chat_id": chat_id,
            "chat_name": dados.get("chat_name") or chat_id,
            "grupo": bool(dados.get("is_group")),
            # `monitorada` = o agente pode ler. `capturada` = o Hermes esta
            # guardando. Sao coisas distintas desde 27/08/2026, e confundi-las
            # faria o agente achar que tem acesso ao que so esta armazenado.
            "monitorada": monitorada,
            "capturada": captura_total or monitorada,
            "ultima_atividade": _iso(dados.get("last_activity_ts")),
        })

    # Sem atividade conhecida vai para o fim, em vez de encabecar a lista.
    conversas.sort(key=lambda c: (c["ultima_atividade"] or ""), reverse=True)
    return {
        "total": len(conversas),
        "monitoradas": sum(1 for c in conversas if c["monitorada"]),
        "conversas": conversas[:limite],
        "observacao": (
            "Leitura liberada em todas as conversas por decisão do dono. Use com "
            "critério: há terceiros nessas conversas que não sabem que um agente lê."
            if leitura_total else
            ("Só conversas monitoradas permitem ler mensagens ou consolidar."
             + (" O Hermes está capturando todas as conversas, mas capturada≠legível: "
                "peça ao dono para habilitar a leitura na Caixa de Entrada."
                if captura_total else "")
             if apenas_monitoradas else
             "monitorada=false: aparece na lista, mas o conteúdo não é acessível.")),
    }


def ler_mensagens(ctx, args: dict) -> dict:
    """Mensagens de uma conversa monitorada, para escolher o recorte a consolidar."""
    from google.cloud import firestore as gcf

    chat_id = str(args.get("chat_id") or "").strip()
    _exigir_monitorado(ctx.db, chat_id)

    limite = max(1, min(int(args.get("limite") or 80), 400))
    desde = str(args.get("desde") or "").strip()
    ate = str(args.get("ate") or "").strip()

    consulta = ctx.db.collection(COL_MENSAGENS).where("chat_id", "==", chat_id)
    if desde:
        consulta = consulta.where("timestamp", ">=", _para_datahora(desde))
    if ate:
        consulta = consulta.where("timestamp", "<=", _para_datahora(ate, fim_do_dia=True))
    consulta = consulta.order_by("timestamp", direction=gcf.Query.DESCENDING).limit(limite)

    mensagens = []
    for snap in consulta.stream():
        d = snap.to_dict() or {}
        mensagens.append({
            # Este `id` e o que `consolidar_whatsapp` espera em message_ids.
            "id": d.get("id") or snap.id,
            "quando": _iso(d.get("timestamp")),
            "autor": "eu" if d.get("from_me") else (d.get("author_name") or "?"),
            "tipo": d.get("message_type"),
            "texto": d.get("content") or "",
            # Audio e video so tem transcricao depois de consolidados; antes
            # disso o texto vem vazio e o tipo e a unica pista do que ha ali.
            "transcricao": d.get("transcription_text"),
            "links": d.get("links") or [],
        })

    mensagens.reverse()   # cronologico, que e como se le conversa
    pendentes = [m for m in mensagens if m["tipo"] in ("ptt", "audio", "video")
                 and not m["transcricao"]]
    return {
        "chat_id": chat_id,
        "total": len(mensagens),
        "mensagens": mensagens,
        "midia_sem_transcricao": len(pendentes),
        "observacao": (f"{len(pendentes)} mensagem(ns) de áudio/vídeo ainda sem transcrição — "
                       "consolidar_whatsapp transcreve como parte do processamento."
                       if pendentes else None),
    }


def _para_datahora(valor: str, fim_do_dia: bool = False) -> datetime:
    texto = valor.strip()
    if len(texto) == 10:   # YYYY-MM-DD
        texto += "T23:59:59" if fim_do_dia else "T00:00:00"
    dt = datetime.fromisoformat(texto)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# --------------------------------------------------------------------------
# Consolidacao
# --------------------------------------------------------------------------

def consolidar(ctx, args: dict) -> dict:
    """Enfileira a consolidacao de um recorte de mensagens.

    Cria o doc que `on_whatsapp_consolidacao_created` consome — o mesmo contrato
    que a Caixa de Entrada usa. E assincrono porque o trabalho real (transcrever
    audio e video, sintetizar) leva minutos e tem 540s de orcamento no trigger.
    """
    from google.cloud import firestore as gcf

    chat_id = str(args.get("chat_id") or "").strip()
    _exigir_monitorado(ctx.db, chat_id)

    ids = [str(m).strip() for m in (args.get("message_ids") or []) if str(m).strip()]
    if not ids:
        # Sem selecao explicita, o periodo define o recorte — evita obrigar o
        # cliente a listar as mensagens so para repetir os ids de volta.
        janela = ler_mensagens(ctx, {"chat_id": chat_id, "desde": args.get("desde"),
                                     "ate": args.get("ate"),
                                     "limite": MAX_MENSAGENS_POR_JOB})
        ids = [m["id"] for m in janela["mensagens"]]
    if not ids:
        return {"erro": "Nenhuma mensagem no recorte informado."}
    if len(ids) > MAX_MENSAGENS_POR_JOB:
        return {"erro": f"Seleção de {len(ids)} mensagens excede o máximo de "
                        f"{MAX_MENSAGENS_POR_JOB}. Reduza o período ou selecione message_ids."}

    chat = ctx.db.collection(COL_CHATS).document(chat_id).get()
    dados_chat = (chat.to_dict() or {}) if chat.exists else {}

    ref = ctx.db.collection(COL_CONSOLIDACOES).document()
    ref.set({
        "chat_id": chat_id,
        "chat_name": dados_chat.get("chat_name") or chat_id,
        "is_group": bool(dados_chat.get("is_group")),
        "message_ids": ids,
        "status": "queued",
        "origem": "mcp",
        "requested_at": gcf.SERVER_TIMESTAMP,
        "updated_at": gcf.SERVER_TIMESTAMP,
    })

    return {
        "status": "queued",
        "job_id": ref.id,
        "chat_id": chat_id,
        "n_mensagens": len(ids),
        "message": ("Consolidação enfileirada. Transcrever áudio e vídeo leva alguns "
                    "minutos; busque o resultado com ler_consolidacao_whatsapp "
                    f"usando job_id='{ref.id}'."),
    }


def ler_consolidacao(ctx, args: dict) -> dict:
    """Uma consolidacao inteira, ou as mais recentes de uma conversa."""
    from google.cloud import firestore as gcf

    job_id = str(args.get("job_id") or "").strip()
    incluir_transcript = bool(args.get("incluir_transcript"))

    if job_id:
        snap = ctx.db.collection(COL_CONSOLIDACOES).document(job_id).get()
        if not snap.exists:
            return {"erro": f"Consolidação '{job_id}' não encontrada.", "status": "not_found"}
        return _formatar_consolidacao(ctx, snap, incluir_transcript)

    chat_id = str(args.get("chat_id") or "").strip()
    if not chat_id:
        return {"erro": "Informe job_id ou chat_id."}
    _exigir_monitorado(ctx.db, chat_id)

    consulta = (ctx.db.collection(COL_CONSOLIDACOES)
                .where("chat_id", "==", chat_id)
                .order_by("requested_at", direction=gcf.Query.DESCENDING)
                .limit(max(1, min(int(args.get("limite") or 5), 20))))
    return {"chat_id": chat_id,
            "consolidacoes": [_formatar_consolidacao(ctx, s, incluir_transcript)
                              for s in consulta.stream()]}


def _formatar_consolidacao(ctx, snap, incluir_transcript: bool) -> dict:
    d = snap.to_dict() or {}
    chat_id = str(d.get("chat_id") or "")

    saida = {
        "job_id": snap.id,
        "status": d.get("status"),
        "chat_id": chat_id,
        "chat_name": d.get("chat_name"),
        "n_mensagens": d.get("n_mensagens"),
        "periodo": {"inicio": d.get("periodo_inicio"), "fim": d.get("periodo_fim")},
        "resumo": d.get("resumo"),
        "itens_de_acao": d.get("itens_de_acao") or [],
        "decisoes": d.get("decisoes") or [],
        "midia": {
            "audios_transcritos": d.get("n_audios_transcritos"),
            "audios_ignorados": d.get("n_audios_ignorados"),
            "videos_transcritos": d.get("n_videos_transcritos"),
            "videos_ignorados": d.get("n_videos_ignorados"),
        },
    }
    if d.get("status") == "queued" or d.get("status") == "processing":
        saida["message"] = (d.get("progress")
                            or "Ainda processando. Consulte de novo em alguns segundos.")
    if d.get("error"):
        saida["erro"] = d["error"]

    if incluir_transcript:
        # Reconfere a allowlist aqui tambem: uma consolidacao antiga pode ser de
        # conversa que saiu do monitoramento desde entao, e o transcript e a
        # conversa literal.
        _exigir_monitorado(ctx.db, chat_id)
        transcript = d.get("transcript_literal") or ""
        saida["transcript_literal"] = transcript[:LIMITE_TRANSCRIPT_CHARS]
        saida["transcript_truncado"] = len(transcript) > LIMITE_TRANSCRIPT_CHARS
    return saida

def consultar_envio(ctx, args: dict) -> dict:
    """Estado real de uma mensagem enfileirada por `schedule_whatsapp_message`.

    Existe porque enfileirar nao e enviar. Em 28/08/2026 dois envios foram
    aceitos, falharam no worker por destino invalido, e o agente afirmou ao dono
    que tinha mandado — nao havia como saber. Sem esta consulta, todo envio e
    uma afirmacao sem prova.

    Sem `job_id`, devolve os envios mais recentes: serve para descobrir se algo
    esta encalhado sem precisar guardar o id de cada um.
    """
    from google.cloud import firestore as gcf

    def formatar(snap):
        d = snap.to_dict() or {}
        saida = {
            "job_id": snap.id,
            "status": d.get("status"),
            "destino_pedido": d.get("to_number"),
            "agendado_para": _iso(d.get("scheduled_for")),
            "tentativas": int(d.get("attempts") or 0),
            "trecho": str(d.get("content") or "")[:80],
        }
        if d.get("status") == "sent":
            saida["enviado_em"] = _iso(d.get("sent_at"))
            # Para onde foi de fato: o worker resolve o numero e pode acabar num
            # JID diferente do que se pediu.
            saida["destino_real"] = d.get("sent_to")
            saida["wa_message_id"] = d.get("wa_message_id")
        if d.get("status") == "failed":
            saida["falhou_em"] = _iso(d.get("failed_at"))
            saida["erro"] = d.get("error_message")
            saida["erro_origem"] = d.get("error_origem")
        if d.get("status") == "pending":
            saida["message"] = ("Ainda na fila — NAO diga ao usuario que a mensagem "
                                "foi enviada. Consulte de novo depois do horario agendado.")
        return saida

    job_id = str(args.get("job_id") or "").strip()
    if job_id:
        snap = ctx.db.collection(COL_OUTBOX).document(job_id).get()
        if not snap.exists:
            return {"erro": f"Envio '{job_id}' nao encontrado.", "status": "not_found"}
        return formatar(snap)

    limite = max(1, min(int(args.get("limite") or 5), 20))
    consulta = (ctx.db.collection(COL_OUTBOX)
                .order_by("created_at", direction=gcf.Query.DESCENDING)
                .limit(limite))
    return {"envios": [formatar(s) for s in consulta.stream()]}
