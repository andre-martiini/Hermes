"""Modo Secretário no WhatsApp — atendimento autônomo seguro quando o André estiver indisponível.

Permite ao Hermes conversar com contatos autorizados no WhatsApp em nome do André:
- Entende o assunto e anota recados.
- Consulta a agenda real do André (multi-calendário).
- Assimetria de agenda:
    * Se ocupado: pode informar o compromisso diretamente de forma factual.
    * Se livre: NUNCA confirma disponibilidade nem fecha compromisso — apenas informa
      que anotou e vai repassar ao André para confirmação pessoal.
- Limite de trocas e insistência:
    * Após até max_trocas (padrão 2), encerra a investigação, informa que repassará
      ao André e escala para a fila de atenção (alta prioridade) para notificação via Telegram.
- Proteção de dados sensíveis:
    * NUNCA responde com ou discute dados financeiros ou de saúde do André com terceiros;
      qualquer solicitação é recusada com polidez e escalada imediatamente ao André.
- Veto humano garantido:
    * Toda resposta enviada passa pela janela de cancelamento existente do outbox
      (tipo 'secretario_whatsapp' promovido, status 'aguardando_janela'), com card no Telegram
      e botão de cancelamento imediato. Se o card Telegram falhar, degrada para aprovação manual.
- Identidade explícita obrigatória:
    * Toda mensagem enviada pelo bot começa rigorosamente com '**Hermes Bot:** '.
"""

from __future__ import annotations

import datetime
from datetime import timezone
import os
import re
from typing import Callable

from firebase_admin import firestore

import atencao
import outbox_aprovacao

COLLECTION_CONVERSAS = "whatsapp_secretario_conversas"
PREFIXO_ASSINATURA = "**Hermes Bot:** "
DEFAULT_MAX_TROCAS = 2
DEFAULT_JANELA_MIN = 10
TIPO_OUTBOX_SECRETARIO = "secretario_whatsapp"
ORIGEM_SECRETARIO = "secretario_whatsapp"

ESTADO_EM_ATENDIMENTO = "em_atendimento"
ESTADO_ESCALADO = "escalado"
ESTADO_ASSUMIDO_POR_ANDRE = "assumido_por_andre"
ESTADO_ENCERRADO = "encerrado"

TIPO_ATENCAO_DECISAO_FORCADA = "secretario_decisao_forcada"
TIPO_ATENCAO_INSISTENCIA = "secretario_insistencia"
TIPO_ATENCAO_ASSUNTO_SENSIVEL = "secretario_assunto_sensivel"

_MODELO_CLAUDE = os.environ.get("SECRETARIO_MODEL", "claude-fable-5")
_MODELO_FALLBACK = os.environ.get("SECRETARIO_FALLBACK_MODEL", "claude-opus-4-8")
_MAX_TOKENS = int(os.environ.get("SECRETARIO_MAX_TOKENS", "1024"))


# ---------------------------------------------------------------------------
# Lógica pura e formatação
# ---------------------------------------------------------------------------

def prefixar_assinatura(texto: str) -> str:
    """Garante que toda mensagem do secretário comece rigorosamente com '**Hermes Bot:** '."""
    limpo = str(texto or "").strip()
    if not limpo:
        return PREFIXO_ASSINATURA.strip()
    if limpo.startswith(PREFIXO_ASSINATURA):
        return limpo
    # Se tiver variações como "**Hermes Bot:**" sem espaço ou sem negrito
    sem_tag = re.sub(r"^\*{0,2}Hermes Bot:?\*{0,2}\s*", "", limpo, flags=re.IGNORECASE).strip()
    return f"{PREFIXO_ASSINATURA}{sem_tag}"


def extrair_digitos(texto: str) -> str:
    """Extrai apenas os dígitos de um chat_id ou telefone."""
    return re.sub(r"\D", "", str(texto or ""))


def chat_na_allowlist(chat_id: str, allowlist: set[str] | list[str] | None) -> bool:
    """Valida se o chat_id (ex: '5511999999999@c.us') está na allowlist configurada.
    
    Aceita correspondência exata de string ou comparação por dígitos (para suportar
    tanto o formato com '@c.us' quanto apenas o número puro na allowlist).
    """
    if not allowlist:
        return False
    chat_limpo = str(chat_id or "").strip()
    if not chat_limpo:
        return False

    allowlist_limpa = {str(x).strip() for x in allowlist if str(x).strip()}
    if chat_limpo in allowlist_limpa:
        return True

    chat_digitos = extrair_digitos(chat_limpo)
    if chat_digitos:
        for item in allowlist_limpa:
            item_digitos = extrair_digitos(item)
            if item_digitos and (item_digitos == chat_digitos or chat_digitos.endswith(item_digitos)):
                return True

    return False


def validar_regra_agenda(eventos_conflito: list[dict] | None) -> dict:
    """Aplica a regra pura de assimetria de agenda:
    - Ocupado: factual, pode informar.
    - Livre: NUNCA confirma disponibilidade nem fecha compromisso; só anota recado.
    """
    conflitos = eventos_conflito or []
    if conflitos:
        titulos = [ev.get("titulo") or "Compromisso" for ev in conflitos]
        return {
            "ocupado": True,
            "motivo": f"Ocupado no horário com: {', '.join(titulos)}",
            "pode_informar_conflito": True,
        }
    return {
        "ocupado": False,
        "motivo": "Sem compromissos no horário, mas NUNCA confirmar disponibilidade nem fechar agenda.",
        "pode_informar_conflito": False,
    }


def obter_config_secretario(db) -> dict:
    """Lê as configurações de whatsapp_secretario em system/settings."""
    try:
        snap = db.collection("system").document("settings").get()
        data = (snap.to_dict() or {}) if snap.exists else {}
        cfg = data.get("whatsapp_secretario") or {}
        return {
            "enabled": bool(cfg.get("enabled", False)),
            "chats_allowlist": [str(x).strip() for x in (cfg.get("chats_allowlist") or []) if str(x).strip()],
            "max_trocas": int(cfg.get("max_trocas", DEFAULT_MAX_TROCAS)),
            "janela_cancelamento_min": int(cfg.get("janela_cancelamento_min", DEFAULT_JANELA_MIN)),
        }
    except Exception as exc:
        print(f"[SecretarioWhatsApp] Erro ao ler system/settings: {exc}")
        return {
            "enabled": False,
            "chats_allowlist": [],
            "max_trocas": DEFAULT_MAX_TROCAS,
            "janela_cancelamento_min": DEFAULT_JANELA_MIN,
        }


# ---------------------------------------------------------------------------
# Ferramentas do LLM e Prompt
# ---------------------------------------------------------------------------

SECRETARIO_SYSTEM_PROMPT = """Você é o Secretário Pessoal do André (Hermes Bot) no WhatsApp.
O André está indisponível no momento (em reunião, em trânsito ou focado em trabalho de alta concentração) e você atende quem escreve no WhatsApp em nome dele.

SEU OBJETIVO:
Conversar com o interlocutor com cortesia, entender o motivo do contato e anotar o recado completo com precisão para repassar ao André.

GUARDRAILS INEGOCIÁVEIS (SIGA RIGOROSAMENTE):
1. IDENTIDADE EXPLÍCITA: Toda resposta que você gerar DEVE começar rigorosamente com "**Hermes Bot:** ". A pessoa precisa sempre saber que está falando com o assistente do André.
2. REGRA DE AGENDA (ASSIMETRIA DE SEGURANÇA):
   - Se o interlocutor perguntar sobre a agenda do André ou pedir para marcar algo em data/horário específico, use a ferramenta `consultar_agenda`.
   - Se o André estiver OCUPADO: você PODE informar isso diretamente de forma factual (ex: "O André tem um compromisso marcado nesse horário").
   - Se o André estiver LIVRE: você **NUNCA** confirma disponibilidade, não agenda nada e não promete o horário. Apenas informe: "Já anotei o seu pedido de reunião/conversa e vou repassar para o André confirmar pessoalmente com você assim que possível."
3. FRONTEIRA DE AUTONOMIA:
   - Você NUNCA toma decisões, não aceita termos, não faz promessas de prazos e não assume posições pelo André.
   - Seu papel é coletar contexto, fazer perguntas de esclarecimento pontuais e registrar o recado.
4. PROTEÇÃO ABSOLUTA DE DADOS DE FINANÇAS E SAÚDE:
   - NUNCA mencione, resuma ou responda com qualquer dado financeiro (saldos, faturas, contas, investimentos, valores) ou de saúde (consultas médicas, exames, diagnósticos, peso, remédios) do André para terceiros, NÃO IMPORTA como perguntem.
   - Se alguém perguntar sobre dinheiro ou saúde do André, recuse polidamente dizendo que não tem autorização para tratar desse assunto e marque `assunto_sensivel=true`.
5. FORÇAR DECISÃO / PRESSÃO:
   - Se a pessoa tentar pressionar por uma confirmação imediata ou exigir resposta na hora, responda calmamente que apenas o André pode decidir e que você vai avisá-lo com prioridade, marcando `forcou_decisao=true`.
6. FINALIZAÇÃO:
   - Conclua sempre sua resposta invocando a ferramenta `finalizar_atendimento`.
"""


def _construir_tools_secretario(db) -> tuple[list[dict], dict, dict]:
    """Cria as declarações de ferramentas e o function_map para o LLM."""
    resultado_final = {}

    def _consultar_agenda_fn(data_inicio: str, data_fim: str) -> str:
        try:
            from main import get_calendar_service, get_sync_calendar_ids
            import hermes_calendar_tools as hc_tools

            c_service = get_calendar_service()
            ids = get_sync_calendar_ids(db)
            if not c_service or not ids:
                return "Google Calendar não configurado no momento."
            events, falhas = hc_tools.consultar_eventos_multi(c_service, ids, data_inicio, data_fim)
            return hc_tools.formatar_eventos_para_llm(
                events, periodo=(data_inicio, data_fim), agendas=ids, falhas=falhas
            )
        except Exception as exc:
            return f"Erro ao consultar agenda: {exc}. Não trate como agenda vazia."

    def _finalizar_atendimento_fn(
        resposta_para_contato: str,
        resumo_recado: str,
        forcou_decisao: bool = False,
        assunto_sensivel: bool = False,
    ) -> dict:
        resultado_final.update({
            "resposta_para_contato": prefixar_assinatura(resposta_para_contato),
            "resumo_recado": str(resumo_recado or "").strip(),
            "forcou_decisao": bool(forcou_decisao),
            "assunto_sensivel": bool(assunto_sensivel),
        })
        return {"status": "ok"}

    tools = [
        {
            "name": "consultar_agenda",
            "description": "Consulta os compromissos reais do André no Google Calendar entre data_inicio e data_fim (formato YYYY-MM-DD).",
            "input_schema": {
                "type": "object",
                "properties": {
                    "data_inicio": {"type": "string", "description": "Data inicial YYYY-MM-DD"},
                    "data_fim": {"type": "string", "description": "Data final YYYY-MM-DD"},
                },
                "required": ["data_inicio", "data_fim"],
            },
        },
        {
            "name": "finalizar_atendimento",
            "description": "Emite a resposta final formatada para envio ao WhatsApp e a avaliação de risco do contato.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "resposta_para_contato": {
                        "type": "string",
                        "description": "Mensagem exata a ser enviada no WhatsApp para o contato (começando com '**Hermes Bot:** ').",
                    },
                    "resumo_recado": {
                        "type": "string",
                        "description": "Resumo curto e objetivo do assunto trazido pelo contato para ciência do André.",
                    },
                    "forcou_decisao": {
                        "type": "boolean",
                        "description": "True se a mensagem tentou forçar uma confirmação de compromisso ou decisão imediata.",
                    },
                    "assunto_sensivel": {
                        "type": "boolean",
                        "description": "True se o contato perguntou ou mencionou assuntos financeiros ou de saúde do André.",
                    },
                },
                "required": ["resposta_para_contato", "resumo_recado"],
            },
        },
    ]

    function_map = {
        "consultar_agenda": _consultar_agenda_fn,
        "finalizar_atendimento": _finalizar_atendimento_fn,
    }

    return tools, function_map, resultado_final


def _executar_llm_secretario(
    db,
    chat_name: str,
    texto_mensagem: str,
    historico: list[dict],
    agora_sp: str,
) -> dict:
    """Executa o loop de decisões com a Claude Messages API."""
    import anthropic
    from llm_providers import claude_provider
    from main import _cached_doc_get

    keys_doc = _cached_doc_get(db, "system", "api_keys")
    claude_key = (keys_doc.to_dict() or {}).get("claude_api_key") if keys_doc.exists else None
    if not claude_key:
        print("[SecretarioWhatsApp] claude_api_key não configurada; usando resposta de contingência.")
        return {
            "resposta_para_contato": prefixar_assinatura(
                "Olá! O André está indisponível no momento. Anotei sua mensagem e vou repassar a ele assim que possível."
            ),
            "resumo_recado": texto_mensagem[:150],
            "forcou_decisao": False,
            "assunto_sensivel": False,
        }

    tools, function_map, resultado_coletado = _construir_tools_secretario(db)
    client = anthropic.Anthropic(api_key=claude_key)

    user_msg = (
        f"Data/hora atual: {agora_sp}\n"
        f"Interlocutor: {chat_name}\n"
        f"Nova mensagem recebida: \"{texto_mensagem}\"\n\n"
        "Analise a mensagem, consulte a agenda se necessário e chame `finalizar_atendimento` com a resposta."
    )

    formatted_history = []
    for h in (historico or []):
        role = h.get("role")
        content = h.get("content")
        if role in ("user", "assistant") and content:
            formatted_history.append({"role": role, "content": str(content)})

    try:
        claude_provider.run_tool_loop(
            client=client,
            model=_MODELO_CLAUDE,
            system_instruction=SECRETARIO_SYSTEM_PROMPT,
            tools=tools,
            function_map=function_map,
            history=formatted_history,
            user_message=user_msg,
            max_tokens=_MAX_TOKENS,
            fallback_model=_MODELO_FALLBACK,
        )
    except Exception as exc:
        print(f"[SecretarioWhatsApp] Falha no loop LLM da Claude: {exc}")

    if resultado_coletado.get("resposta_para_contato"):
        return resultado_coletado

    # Fallback caso a tool finalizar_atendimento não tenha sido acionada
    return {
        "resposta_para_contato": prefixar_assinatura(
            "Olá! O André está indisponível no momento. Já recebi seu recado e vou repassar para ele assim que estiver livre."
        ),
        "resumo_recado": texto_mensagem[:150],
        "forcou_decisao": False,
        "assunto_sensivel": False,
    }


# ---------------------------------------------------------------------------
# Operações de Banco de Dados e Fila
# ---------------------------------------------------------------------------

def processar_mensagem_from_me(db, mensagem: dict) -> None:
    """Quando o próprio André envia mensagem para um chat, marca o estado da conversa
    como 'assumido_por_andre' para que o bot não interfira."""
    chat_id = str(mensagem.get("chat_id") or "").strip()
    if not chat_id:
        return

    doc_ref = db.collection(COLLECTION_CONVERSAS).document(chat_id)
    snap = doc_ref.get()
    if not snap.exists:
        return

    dados = snap.to_dict() or {}
    if dados.get("estado") == ESTADO_EM_ATENDIMENTO:
        doc_ref.update({
            "estado": ESTADO_ASSUMIDO_POR_ANDRE,
            "atualizado_em": firestore.SERVER_TIMESTAMP,
        })


def escalar_para_atencao(
    db,
    chat_id: str,
    chat_name: str,
    wa_message_id: str,
    motivo: str,
    tipo_atencao: str,
    resumo_recado: str,
    texto_mensagem: str,
    trocas_count: int,
    forcou_decisao: bool = False,
) -> str:
    """Insere um item com alta prioridade na fila de atenção (atencao).
    
    Será processado pelo avaliar_interrupcao_atencao e notificado no Telegram.
    """
    chave_dedupe = f"secretario:{chat_id}:{wa_message_id}"
    doc_ref = db.collection(atencao.COLLECTION).document(chave_dedupe)

    item = {
        "origem": ORIGEM_SECRETARIO,
        "tipo": tipo_atencao,
        "prioridade": atencao.PRIORIDADE_ALTA,
        "titulo": f"WhatsApp ({chat_name}): {motivo}"[:120],
        "resumo": f"{chat_name} enviou: \"{texto_mensagem[:180]}\". Recado: {resumo_recado}"[:300],
        "sugestao": "Avaliar o recado e responder diretamente no WhatsApp.",
        "estado": atencao.ESTADO_ABERTO,
        "chave_dedupe": chave_dedupe,
        "acao_id": None,
        "etapa_id": None,
        "pessoa": chat_name,
        "prazo": None,
        "evidencia": {
            "chat_id": chat_id,
            "chat_name": chat_name,
            "wa_message_id": wa_message_id,
            "trocas_count": trocas_count,
            "forcou_decisao": forcou_decisao,
        },
        "criado_em": firestore.SERVER_TIMESTAMP,
        "atualizado_em": firestore.SERVER_TIMESTAMP,
    }
    doc_ref.set(item, merge=True)
    return chave_dedupe


def enviar_resposta_via_outbox(
    db,
    chat_id: str,
    chat_name: str,
    texto_resposta: str,
    resumo_recado: str,
) -> dict:
    """Envia a resposta do secretário pelo outbox com janela de cancelamento."""
    texto_final = prefixar_assinatura(texto_resposta)
    motivo = f"Resposta do Secretário para {chat_name}: {resumo_recado}"[:150]

    return outbox_aprovacao.criar_rascunho(
        db=db,
        contact_number=chat_id,
        message=texto_final,
        motivo=motivo,
        tipo=TIPO_OUTBOX_SECRETARIO,
        origem=ORIGEM_SECRETARIO,
    )


# ---------------------------------------------------------------------------
# Fluxo Principal (Orquestrador do Modo Secretário)
# ---------------------------------------------------------------------------

def processar_mensagem_secretario(
    db,
    mensagem: dict,
    llm_runner: Callable[..., dict] | None = None,
) -> dict | None:
    """Ponto de entrada reativo para cada mensagem recebida em whatsapp_messages."""
    # Fast path 1: Mensagens from_me (enviadas pelo André/Hermes)
    if mensagem.get("from_me"):
        processar_mensagem_from_me(db, mensagem)
        return None

    # Fast path 2: Ignora mensagens de grupos
    if mensagem.get("is_group"):
        return None

    chat_id = str(mensagem.get("chat_id") or "").strip()
    if not chat_id:
        return None

    # Fast path 3: Configuração em system/settings
    cfg = obter_config_secretario(db)
    if not cfg.get("enabled"):
        return None

    # Fast path 4: Allowlist restrita
    if not chat_na_allowlist(chat_id, cfg.get("chats_allowlist")):
        return None

    texto_msg = str(
        mensagem.get("content")
        or mensagem.get("text")
        or mensagem.get("transcription_text")
        or ""
    ).strip()
    if not texto_msg:
        return None

    chat_name = str(mensagem.get("chat_name") or chat_id).strip()
    wa_message_id = str(mensagem.get("wa_message_id") or mensagem.get("id") or "msg").strip()

    max_trocas = cfg.get("max_trocas", DEFAULT_MAX_TROCAS)

    # 1. Carrega ou inicializa o estado da conversa
    doc_conversa_ref = db.collection(COLLECTION_CONVERSAS).document(chat_id)
    snap_conversa = doc_conversa_ref.get()
    dados_conversa = snap_conversa.to_dict() if snap_conversa.exists else {}

    estado_atual = dados_conversa.get("estado")
    trocas_atuais = int(dados_conversa.get("trocas_count", 0))
    historico = list(dados_conversa.get("historico_mensagens") or [])

    # Se a conversa anterior já foi assumida pelo André ou encerrada, inicia nova sessão
    if estado_atual in (ESTADO_ASSUMIDO_POR_ANDRE, ESTADO_ENCERRADO):
        trocas_atuais = 0
        historico = []
        estado_atual = ESTADO_EM_ATENDIMENTO

    # 2. Verifica se atingiu o limite de trocas (Regra 4: ~2 trocas)
    if trocas_atuais >= max_trocas:
        resposta_fechamento = (
            f"{PREFIXO_ASSINATURA}Entendido. Já anotei todos os detalhes e vou repassar diretamente "
            "ao André assim que ele estiver disponível."
        )
        resumo_fechamento = f"Interlocutor continuou conversa após {trocas_atuais} trocas: {texto_msg[:100]}"

        # Escala pro André via avaliar_interrupcao_atencao (prioridade alta)
        item_id = escalar_para_atencao(
            db=db,
            chat_id=chat_id,
            chat_name=chat_name,
            wa_message_id=wa_message_id,
            motivo="Limite de trocas atingido — aguardando retorno do André",
            tipo_atencao=TIPO_ATENCAO_INSISTENCIA,
            resumo_recado=resumo_fechamento,
            texto_mensagem=texto_msg,
            trocas_count=trocas_atuais,
            forcou_decisao=True,
        )

        # Envia mensagem de encerramento via outbox
        enviar_resposta_via_outbox(
            db=db,
            chat_id=chat_id,
            chat_name=chat_name,
            texto_resposta=resposta_fechamento,
            resumo_recado=resumo_fechamento,
        )

        doc_conversa_ref.set({
            "chat_id": chat_id,
            "chat_name": chat_name,
            "estado": ESTADO_ESCALADO,
            "trocas_count": trocas_atuais + 1,
            "ultimo_recado": resumo_fechamento,
            "escalado": True,
            "item_atencao_id": item_id,
            "atualizado_em": firestore.SERVER_TIMESTAMP,
        }, merge=True)

        return {
            "status": "escalado_insistencia",
            "chat_id": chat_id,
            "trocas_count": trocas_atuais + 1,
        }

    # 3. Execução da decisão via LLM (Claude)
    agora_sp = datetime.datetime.now(timezone.utc).astimezone(
        datetime.timezone(datetime.timedelta(hours=-3))
    ).strftime("%Y-%m-%d %H:%M:%S BRT")

    if llm_runner is not None:
        decisao = llm_runner(
            db=db,
            chat_name=chat_name,
            texto_mensagem=texto_msg,
            historico=historico,
            agora_sp=agora_sp,
        )
    else:
        decisao = _executar_llm_secretario(
            db=db,
            chat_name=chat_name,
            texto_mensagem=texto_msg,
            historico=historico,
            agora_sp=agora_sp,
        )

    resposta_texto = prefixar_assinatura(decisao.get("resposta_para_contato") or "")
    resumo_recado = str(decisao.get("resumo_recado") or texto_msg[:120]).strip()
    forcou_decisao = bool(decisao.get("forcou_decisao"))
    assunto_sensivel = bool(decisao.get("assunto_sensivel"))

    # 4. Se forçou decisão ou assunto sensível, escala para a fila de atenção (alta prioridade)
    item_atencao_id = None
    if forcou_decisao or assunto_sensivel:
        tipo_at = TIPO_ATENCAO_ASSUNTO_SENSIVEL if assunto_sensivel else TIPO_ATENCAO_DECISAO_FORCADA
        motivo_at = "Tentativa de forçar decisão/compromisso" if forcou_decisao else "Menção a finanças/saúde"
        item_atencao_id = escalar_para_atencao(
            db=db,
            chat_id=chat_id,
            chat_name=chat_name,
            wa_message_id=wa_message_id,
            motivo=motivo_at,
            tipo_atencao=tipo_at,
            resumo_recado=resumo_recado,
            texto_mensagem=texto_msg,
            trocas_count=trocas_atuais + 1,
            forcou_decisao=forcou_decisao,
        )

    # 5. Envia a resposta gerada via outbox com janela de cancelamento
    outbox_res = enviar_resposta_via_outbox(
        db=db,
        chat_id=chat_id,
        chat_name=chat_name,
        texto_resposta=resposta_texto,
        resumo_recado=resumo_recado,
    )

    # 6. Atualiza o estado da conversa
    novo_historico = list(historico)
    novo_historico.append({
        "role": "user",
        "content": texto_msg,
        "wa_message_id": wa_message_id,
        "timestamp": datetime.datetime.now(timezone.utc).isoformat(),
    })
    novo_historico.append({
        "role": "assistant",
        "content": resposta_texto,
        "timestamp": datetime.datetime.now(timezone.utc).isoformat(),
    })

    novo_estado = ESTADO_ESCALADO if (forcou_decisao or assunto_sensivel) else ESTADO_EM_ATENDIMENTO

    payload_conversa = {
        "chat_id": chat_id,
        "chat_name": chat_name,
        "estado": novo_estado,
        "trocas_count": trocas_atuais + 1,
        "historico_mensagens": novo_historico[-10:],  # mantém até os últimos 10 turnos
        "ultimo_recado": resumo_recado,
        "escalado": bool(forcou_decisao or assunto_sensivel),
        "atualizado_em": firestore.SERVER_TIMESTAMP,
    }
    if not snap_conversa.exists:
        payload_conversa["iniciado_em"] = firestore.SERVER_TIMESTAMP
    if item_atencao_id:
        payload_conversa["item_atencao_id"] = item_atencao_id

    doc_conversa_ref.set(payload_conversa, merge=True)

    return {
        "status": "ok",
        "chat_id": chat_id,
        "trocas_count": trocas_atuais + 1,
        "outbox_res": outbox_res,
        "escalado": bool(forcou_decisao or assunto_sensivel),
    }
