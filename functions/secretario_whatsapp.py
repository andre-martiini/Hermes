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
COLLECTION_PRIORITARIOS = "secretario_contatos_prioritarios"
PREFIXO_ASSINATURA = "**Hermes Bot:** "
DEFAULT_MAX_TROCAS = 2
DEFAULT_MAX_TROCAS_PRIORITARIO = 6
DEFAULT_JANELA_MIN = 10
TIPO_OUTBOX_SECRETARIO = "secretario_whatsapp"
ORIGEM_SECRETARIO = "secretario_whatsapp"

ESTADO_EM_ATENDIMENTO = "em_atendimento"
ESTADO_ESCALADO = "escalado"
ESTADO_ASSUMIDO_POR_ANDRE = "assumido_por_andre"
ESTADO_ENCERRADO = "encerrado"

STATUS_PRIORITARIO_ATIVO = "ativo"
STATUS_PRIORITARIO_CONCLUIDO = "concluido"
STATUS_PRIORITARIO_EXPIRADO = "expirado"
STATUS_PRIORITARIO_CANCELADO = "cancelado"

TIPO_ATENCAO_DECISAO_FORCADA = "secretario_decisao_forcada"
TIPO_ATENCAO_INSISTENCIA = "secretario_insistencia"
TIPO_ATENCAO_ASSUNTO_SENSIVEL = "secretario_assunto_sensivel"
TIPO_ATENCAO_INVESTIGACAO_CONCLUIDA = "secretario_investigacao_concluida"

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
            "max_trocas_prioritario": int(cfg.get("max_trocas_prioritario", DEFAULT_MAX_TROCAS_PRIORITARIO)),
            "janela_cancelamento_min": int(cfg.get("janela_cancelamento_min", DEFAULT_JANELA_MIN)),
        }
    except Exception as exc:
        print(f"[SecretarioWhatsApp] Erro ao ler system/settings: {exc}")
        return {
            "enabled": False,
            "chats_allowlist": [],
            "max_trocas": DEFAULT_MAX_TROCAS,
            "max_trocas_prioritario": DEFAULT_MAX_TROCAS_PRIORITARIO,
            "janela_cancelamento_min": DEFAULT_JANELA_MIN,
        }


# ---------------------------------------------------------------------------
# Gestão de Contatos Prioritários Pré-Avisados (Briefing e Investigação)
# ---------------------------------------------------------------------------

def _agora_sp() -> datetime.datetime:
    """Retorna datetime atual no fuso horário de Brasília (UTC-3)."""
    return datetime.datetime.now(timezone.utc).astimezone(
        datetime.timezone(datetime.timedelta(hours=-3))
    )


def _calcular_validade_iso(validade_horas: float | None = None, agora: datetime.datetime | None = None) -> str:
    """Calcula timestamp ISO da validade do briefing prioritário.
    
    Se validade_horas for omitido ou None, o padrão é o final do dia corrente em SP (23:59:59).
    """
    ref = agora or _agora_sp()
    if validade_horas is not None and float(validade_horas) > 0:
        valido_ate = ref + datetime.timedelta(hours=float(validade_horas))
    else:
        valido_ate = ref.replace(hour=23, minute=59, second=59, microsecond=999999)
    return valido_ate.isoformat()


def _esta_expirado(valido_ate_iso: str | None, agora: datetime.datetime | None = None) -> bool:
    """Verifica se o timestamp ISO informado já expirou em relação ao instante de referência."""
    if not valido_ate_iso:
        return False
    try:
        limite = datetime.datetime.fromisoformat(str(valido_ate_iso))
        ref = agora or _agora_sp()
        if limite.tzinfo is None:
            limite = limite.replace(tzinfo=datetime.timezone(datetime.timedelta(hours=-3)))
        return ref > limite
    except Exception as exc:
        print(f"[SecretarioWhatsApp] Erro ao parsear validade_iso '{valido_ate_iso}': {exc}")
        return False


def _garantir_chat_na_allowlist(db, chat_id: str) -> None:
    """Garante que o chat_id esteja presente em system/settings.whatsapp_secretario.chats_allowlist."""
    try:
        ref = db.collection("system").document("settings")
        snap = ref.get()
        data = (snap.to_dict() or {}) if snap.exists else {}
        sec_cfg = dict(data.get("whatsapp_secretario") or {})
        allowlist = list(sec_cfg.get("chats_allowlist") or [])
        if not chat_na_allowlist(chat_id, allowlist):
            allowlist.append(chat_id)
            sec_cfg["chats_allowlist"] = allowlist
            ref.set({"whatsapp_secretario": sec_cfg}, merge=True)
    except Exception as exc:
        print(f"[SecretarioWhatsApp] Erro ao adicionar chat_id '{chat_id}' na allowlist: {exc}")


def resolver_identificador_contato(db, identificador_contato: str, ctx=None) -> tuple[str, str]:
    """Resolve um nome, telefone ou JID para (chat_id, chat_name)."""
    identificador = str(identificador_contato or "").strip()
    if not identificador:
        raise ValueError("Identificador do contato não pode ser vazio.")

    # Rejeita grupos explicitamente
    if identificador.endswith("@g.us"):
        raise ValueError("O Modo Secretário com contato prioritário não oferece suporte a grupos de WhatsApp.")

    # Se já for um JID válido (@c.us ou @lid)
    if "@" in identificador and (identificador.endswith("@c.us") or identificador.endswith("@lid")):
        chat_name = identificador
        try:
            doc = db.collection("whatsapp_chats").document(identificador).get()
            if doc.exists:
                chat_name = str((doc.to_dict() or {}).get("chat_name") or identificador)
        except Exception:
            pass
        return identificador, chat_name

    # Tenta usar _destinatario_whatsapp_previa
    try:
        from tools import hermes_tools
        if ctx is None:
            class _SimpleCtx:
                def __init__(self, db_inst):
                    self.db = db_inst
                    self.user_uid = "system"
            ctx = _SimpleCtx(db)
        
        previa = hermes_tools._destinatario_whatsapp_previa(ctx, identificador)
        if previa.get("encontrado") and previa.get("chat_id"):
            if previa.get("tipo") == "grupo" or str(previa["chat_id"]).endswith("@g.us"):
                raise ValueError("O Modo Secretário com contato prioritário não oferece suporte a grupos de WhatsApp.")
            cid = str(previa["chat_id"]).strip()
            if "@" not in cid and cid.isdigit():
                cid = f"{cid}@c.us"
            return cid, str(previa.get("nome") or identificador).strip()
    except ValueError:
        raise
    except Exception as exc:
        print(f"[SecretarioWhatsApp] Aviso ao resolver via previa: {exc}")

    # Fallback 1: busca por nome ou telefone em perfil_pessoas (suporta telefone, telefones e whatsapp_chat_id)
    try:
        termo_lower = identificador.lower()
        digitos_busca = extrair_digitos(identificador)

        exatos = []
        parciais = []

        for doc in db.collection("perfil_pessoas").limit(200).stream():
            data = doc.to_dict() or {}
            nome = str(data.get("nome") or "").strip()
            chat_id = str(data.get("whatsapp_chat_id") or "").strip()
            telefone = str(data.get("telefone") or "").strip()
            telefones = data.get("telefones") or []
            if isinstance(telefones, str):
                telefones = [telefones]
            todos_telefones = [telefone] + list(telefones)
            telefones_limpos = [extrair_digitos(str(t)) for t in todos_telefones if str(t).strip()]

            dest_cid = chat_id or (f"{telefones_limpos[0]}@c.us" if telefones_limpos else None)
            if not dest_cid or dest_cid.endswith("@g.us"):
                continue

            bate_telefone_exato = bool(digitos_busca and any(digitos_busca == t for t in telefones_limpos))
            bate_telefone_parcial = bool(digitos_busca and any(len(digitos_busca) >= 8 and (digitos_busca in t or t in digitos_busca) for t in telefones_limpos))
            bate_nome_exato = bool(termo_lower and termo_lower == nome.lower())
            bate_nome_palavra = bool(termo_lower and termo_lower in [p.lower() for p in nome.split()])
            bate_nome_substring = bool(termo_lower and termo_lower in nome.lower())

            item = (dest_cid, nome or identificador)
            if bate_nome_exato or bate_telefone_exato:
                exatos.append(item)
            elif bate_nome_palavra or bate_nome_substring or bate_telefone_parcial:
                parciais.append(item)

        if exatos:
            unique_cids = {cid: n for cid, n in exatos}
            if len(unique_cids) == 1:
                return next(iter(unique_cids.items()))
            else:
                nomes_conflito = sorted(list(unique_cids.values()))
                raise ValueError(f"Múltiplos contatos encontrados para '{identificador}' ({', '.join(nomes_conflito)}). Especifique o número de telefone completo.")

        if parciais:
            unique_cids = {cid: n for cid, n in parciais}
            if len(unique_cids) == 1:
                return next(iter(unique_cids.items()))
            else:
                nomes_ambiguos = sorted(list(unique_cids.values()))
                raise ValueError(f"Ambiguidade: múltiplos contatos encontrados para '{identificador}' ({', '.join(nomes_ambiguos)}). Especifique o nome completo ou telefone.")
    except ValueError:
        raise
    except Exception as exc:
        print(f"[SecretarioWhatsApp] Aviso ao buscar em perfil_pessoas: {exc}")

    # Fallback 2: busca por chat_name em whatsapp_chats (ignora grupos e exige correspondência exata ou única)
    try:
        termo_lower = identificador.lower()
        exatos_chats = []
        parciais_chats = []

        for doc in db.collection("whatsapp_chats").limit(200).stream():
            data = doc.to_dict() or {}
            chat_id = str(data.get("chat_id") or doc.id).strip()
            if chat_id.endswith("@g.us") or data.get("is_group"):
                continue
            chat_name = str(data.get("chat_name") or "").strip()
            if not chat_name:
                continue

            item = (chat_id, chat_name)
            if termo_lower == chat_name.lower():
                exatos_chats.append(item)
            elif termo_lower in chat_name.lower():
                parciais_chats.append(item)

        if exatos_chats:
            unique_cids = {cid: name for cid, name in exatos_chats}
            if len(unique_cids) == 1:
                return next(iter(unique_cids.items()))
            else:
                nomes_conflito = sorted(list(unique_cids.values()))
                raise ValueError(f"Múltiplos chats encontrados para '{identificador}' ({', '.join(nomes_conflito)}). Especifique o número de telefone completo.")

        if parciais_chats:
            unique_cids = {cid: name for cid, name in parciais_chats}
            if len(unique_cids) == 1:
                return next(iter(unique_cids.items()))
            else:
                nomes_ambiguos = sorted(list(unique_cids.values()))
                raise ValueError(f"Ambiguidade: múltiplos chats encontrados para '{identificador}' ({', '.join(nomes_ambiguos)}). Especifique o nome completo ou telefone.")
    except ValueError:
        raise
    except Exception as exc:
        print(f"[SecretarioWhatsApp] Aviso ao buscar em whatsapp_chats: {exc}")

    # Fallback 3: se possui dígitos suficientes, monta chat_id puro @c.us
    digitos = extrair_digitos(identificador)
    if len(digitos) >= 8:
        return f"{digitos}@c.us", identificador

    raise ValueError(f"Não foi possível identificar um contato do WhatsApp correspondente a '{identificador}'.")


def preparar_contato_prioritario(
    db,
    identificador_contato: str,
    assunto: str,
    o_que_precisa_saber: str,
    validade_horas: float | None = None,
    ctx=None,
    agora_sp: datetime.datetime | None = None,
) -> dict:
    """Registra um briefing prioritário para o modo secretário conduzir investigação ativa."""
    try:
        chat_id, chat_name = resolver_identificador_contato(db, identificador_contato, ctx=ctx)
    except Exception as exc:
        return {"erro": str(exc)}

    assunto_limpo = str(assunto or "").strip()
    if not assunto_limpo:
        return {"erro": "O parâmetro 'assunto' é obrigatório."}

    saber_limpo = str(o_que_precisa_saber or "").strip()
    if not saber_limpo:
        return {"erro": "O parâmetro 'o_que_precisa_saber' é obrigatório."}

    valido_ate = _calcular_validade_iso(validade_horas, agora=agora_sp)

    # Garante inclusão na allowlist para atendimento sem descarte silencioso
    _garantir_chat_na_allowlist(db, chat_id)

    doc_ref = db.collection(COLLECTION_PRIORITARIOS).document(chat_id)
    doc_data = {
        "chat_id": chat_id,
        "chat_name": chat_name,
        "assunto": assunto_limpo,
        "o_que_precisa_saber": saber_limpo,
        "status": STATUS_PRIORITARIO_ATIVO,
        "valido_ate": valido_ate,
        "resumo_estruturado": None,
        "informacao_obtida": None,
        "criado_em": agora_sp or firestore.SERVER_TIMESTAMP,
        "atualizado_em": agora_sp or firestore.SERVER_TIMESTAMP,
    }
    doc_ref.set(doc_data, merge=True)

    # Reinicializa o contador de trocas da conversa para garantir ciclo limpo do novo briefing
    try:
        db.collection(COLLECTION_CONVERSAS).document(chat_id).set({
            "chat_id": chat_id,
            "chat_name": chat_name,
            "estado": ESTADO_EM_ATENDIMENTO,
            "trocas_count": 0,
            "briefing_id": chat_id,
            "historico_mensagens": [],
            "atualizado_em": agora_sp or firestore.SERVER_TIMESTAMP,
        }, merge=True)
    except Exception as exc:
        print(f"[SecretarioWhatsApp] Aviso ao resetar conversa em preparar_contato_prioritario: {exc}")

    return {
        "status": "ok",
        "mensagem": f"Briefing prioritário registrado com sucesso para {chat_name}.",
        "chat_id": chat_id,
        "chat_name": chat_name,
        "assunto": assunto_limpo,
        "o_que_precisa_saber": saber_limpo,
        "valido_ate": valido_ate,
    }


def consultar_contatos_prioritarios(
    db,
    apenas_ativos: bool = True,
    agora_sp: datetime.datetime | None = None,
) -> dict:
    """Consulta briefings prioritários cadastrados, atualizando automaticamente os expirados."""
    itens = []
    try:
        for doc in db.collection(COLLECTION_PRIORITARIOS).stream():
            dados = doc.to_dict() or {}
            dados["id"] = doc.id
            status = dados.get("status")
            valido_ate = dados.get("valido_ate")

            # Verifica se expirou
            if status == STATUS_PRIORITARIO_ATIVO and _esta_expirado(valido_ate, agora=agora_sp):
                doc.reference.update({
                    "status": STATUS_PRIORITARIO_EXPIRADO,
                    "atualizado_em": firestore.SERVER_TIMESTAMP,
                })
                dados["status"] = STATUS_PRIORITARIO_EXPIRADO

            if apenas_ativos:
                if dados.get("status") == STATUS_PRIORITARIO_ATIVO:
                    itens.append(dados)
            else:
                itens.append(dados)
    except Exception as exc:
        print(f"[SecretarioWhatsApp] Erro ao consultar contatos prioritários: {exc}")
        return {"erro": str(exc), "contatos_prioritarios": []}

    return {
        "total": len(itens),
        "apenas_ativos": apenas_ativos,
        "contatos_prioritarios": itens,
    }


def cancelar_contato_prioritario(
    db,
    identificador_contato: str,
    ctx=None,
) -> dict:
    """Cancela um briefing prioritário antes de sua expiração."""
    identificador = str(identificador_contato or "").strip()
    if not identificador:
        return {"erro": "Identificador do contato não informado."}

    chat_id = None
    chat_name = None
    try:
        chat_id, chat_name = resolver_identificador_contato(db, identificador, ctx=ctx)
    except Exception:
        pass

    doc_ref = None
    if chat_id:
        ref = db.collection(COLLECTION_PRIORITARIOS).document(chat_id)
        if ref.get().exists:
            doc_ref = ref

    if not doc_ref:
        termo_lower = identificador.lower()
        digitos = extrair_digitos(identificador)
        for doc in db.collection(COLLECTION_PRIORITARIOS).stream():
            d = doc.to_dict() or {}
            c_id = str(d.get("chat_id") or doc.id)
            c_name = str(d.get("chat_name") or "")
            if (c_id == identificador or
                (digitos and digitos == extrair_digitos(c_id)) or
                (termo_lower in c_name.lower()) or
                (termo_lower == c_name.lower())):
                doc_ref = doc.reference
                chat_id = c_id
                chat_name = c_name
                break

    if not doc_ref:
        return {"erro": f"Nenhum briefing prioritário encontrado para '{identificador}'."}

    doc_ref.update({
        "status": STATUS_PRIORITARIO_CANCELADO,
        "atualizado_em": firestore.SERVER_TIMESTAMP,
    })

    return {
        "status": "ok",
        "mensagem": f"Briefing prioritário para {chat_name or chat_id} foi cancelado com sucesso.",
        "chat_id": chat_id,
        "chat_name": chat_name,
    }


def obter_briefing_ativo(
    db,
    chat_id: str,
    agora_sp: datetime.datetime | None = None,
) -> dict | None:
    """Retorna o briefing prioritário ativo para o chat_id ou None se não houver ou expirou."""
    if not chat_id:
        return None

    c_id = str(chat_id).strip()
    doc_ref = db.collection(COLLECTION_PRIORITARIOS).document(c_id)
    snap = doc_ref.get()

    dados = None
    if snap.exists:
        dados = snap.to_dict() or {}
        dados["_doc_id"] = snap.id
    else:
        digitos = extrair_digitos(c_id)
        if digitos:
            for doc in db.collection(COLLECTION_PRIORITARIOS).stream():
                d = doc.to_dict() or {}
                if extrair_digitos(str(d.get("chat_id") or doc.id)) == digitos:
                    dados = d
                    dados["_doc_id"] = doc.id
                    doc_ref = doc.reference
                    break

    if not dados:
        return None

    if dados.get("status") != STATUS_PRIORITARIO_ATIVO:
        return None

    valido_ate = dados.get("valido_ate")
    if _esta_expirado(valido_ate, agora=agora_sp):
        try:
            doc_ref.update({
                "status": STATUS_PRIORITARIO_EXPIRADO,
                "atualizado_em": firestore.SERVER_TIMESTAMP,
            })
        except Exception:
            pass
        return None

    return dados


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


def _construir_tools_secretario(db, briefing: dict | None = None) -> tuple[list[dict], dict, dict]:
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
            "investigacao_concluida": False,
        })
        return {"status": "ok"}

    def _concluir_investigacao_prioritaria_fn(
        resposta_para_contato: str,
        resumo_estruturado: str,
        informacao_obtida: bool = True,
        forcou_decisao: bool = False,
        assunto_sensivel: bool = False,
    ) -> dict:
        resultado_final.update({
            "resposta_para_contato": prefixar_assinatura(resposta_para_contato),
            "resumo_estruturado": str(resumo_estruturado or "").strip(),
            "resumo_recado": str(resumo_estruturado or "").strip(),
            "informacao_obtida": bool(informacao_obtida),
            "investigacao_concluida": True,
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
            "description": "Emite a resposta intermediária ou geral formatada para envio ao WhatsApp e a avaliação de risco do contato.",
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

    if briefing:
        tools.append({
            "name": "concluir_investigacao_prioritaria",
            "description": "Conclui a investigação prioritária quando a informação requerida pelo André foi obtida com sucesso ou quando o contato confirmou que não pode fornecê-la.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "resposta_para_contato": {
                        "type": "string",
                        "description": "Mensagem exata a ser enviada no WhatsApp para o contato (começando com '**Hermes Bot:** ').",
                    },
                    "resumo_estruturado": {
                        "type": "string",
                        "description": "Resposta objetiva e estruturada ao que o André precisava saber.",
                    },
                    "informacao_obtida": {
                        "type": "boolean",
                        "description": "True se a informação que o André precisava saber foi obtida; False se não foi possível obter.",
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
                "required": ["resposta_para_contato", "resumo_estruturado", "informacao_obtida"],
            },
        })
        function_map["concluir_investigacao_prioritaria"] = _concluir_investigacao_prioritaria_fn

    return tools, function_map, resultado_final


def _executar_llm_secretario(
    db,
    chat_name: str,
    texto_mensagem: str,
    historico: list[dict],
    agora_sp: str,
    briefing: dict | None = None,
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
            "investigacao_concluida": False,
        }

    tools, function_map, resultado_coletado = _construir_tools_secretario(db, briefing=briefing)
    client = anthropic.Anthropic(api_key=claude_key)

    system_instruction = SECRETARIO_SYSTEM_PROMPT
    if briefing:
        assunto_br = briefing.get("assunto")
        o_que_saber = briefing.get("o_que_precisa_saber")
        system_instruction += f"""

BRIEFING PRIORITÁRIO ATIVO:
O André pré-avisou que está aguardando uma resposta específica deste contato.
- Assunto: {assunto_br}
- O que o André precisa saber: {o_que_saber}

DIRETRIZES DE INVESTIGAÇÃO ATIVA:
1. Conduza a conversa buscando ativamente entender e obter as informações necessárias sobre o assunto pré-avisado com cortesia.
2. Se faltarem detalhes importantes para responder ao que o André precisa saber, faça perguntas objetivas de esclarecimento e invoque `finalizar_atendimento`.
3. Assim que você tiver obtido a informação combinada (ou se o contato afirmar categoricamente que não tem a informação/não pode responder), invoque OBRIGATORIAMENTE a ferramenta `concluir_investigacao_prioritaria`.
4. MANTENHA TODOS OS GUARDRAILS INEGOCIÁVEIS:
   - Se o interlocutor perguntar sobre agenda e o André estiver livre, NUNCA confirme disponibilidade nem compromisso.
   - NUNCA revele dados de finanças ou de saúde do André; recuse polidamente e marque `assunto_sensivel=true`.
"""

    user_msg = (
        f"Data/hora atual: {agora_sp}\n"
        f"Interlocutor: {chat_name}\n"
        f"Nova mensagem recebida: \"{texto_mensagem}\"\n\n"
    )
    if briefing:
        user_msg += (
            "Analise a mensagem no contexto do briefing prioritário. Se a informação foi obtida ou não pode ser obtida, "
            "chame `concluir_investigacao_prioritaria`. Se precisar investigar mais, chame `finalizar_atendimento`."
        )
    else:
        user_msg += "Analise a mensagem, consulte a agenda se necessário e chame `finalizar_atendimento` com a resposta."

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
            system_instruction=system_instruction,
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
        "investigacao_concluida": False,
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


def registrar_investigacao_concluida_atencao(
    db,
    chat_id: str,
    chat_name: str,
    wa_message_id: str,
    assunto: str,
    o_que_precisa_saber: str,
    resumo_estruturado: str,
    informacao_obtida: bool,
    trocas_count: int,
) -> str:
    """Insere um item com prioridade MÉDIA na fila de atenção para entrega do resumo estruturado ao André."""
    chave_dedupe = f"secretario_investigacao:{chat_id}:{wa_message_id}"
    doc_ref = db.collection(atencao.COLLECTION).document(chave_dedupe)

    status_str = "Informação obtida com sucesso." if informacao_obtida else "Informação não obtida."
    titulo = f"WhatsApp ({chat_name}): Investigação concluída — {assunto}"[:120]
    resumo = (
        f"Contato prioritário: {chat_name}\n"
        f"Assunto: {assunto}\n"
        f"Objetivo do André: {o_que_precisa_saber}\n"
        f"Status: {status_str}\n"
        f"Resumo estruturado: {resumo_estruturado}"
    )[:500]

    item = {
        "origem": ORIGEM_SECRETARIO,
        "tipo": TIPO_ATENCAO_INVESTIGACAO_CONCLUIDA,
        "prioridade": atencao.PRIORIDADE_MEDIA,
        "titulo": titulo,
        "resumo": resumo,
        "sugestao": "Revisar as respostas coletadas pelo secretário.",
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
            "assunto": assunto,
            "o_que_precisa_saber": o_que_precisa_saber,
            "resumo_estruturado": resumo_estruturado,
            "informacao_obtida": informacao_obtida,
            "trocas_count": trocas_count,
        },
        "criado_em": firestore.SERVER_TIMESTAMP,
        "atualizado_em": firestore.SERVER_TIMESTAMP,
    }
    doc_ref.set(item, merge=True)
    return chave_dedupe


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

    # Fast path 4: Verifica briefing ativo ou allowlist
    briefing = obter_briefing_ativo(db, chat_id)
    if not briefing and not chat_na_allowlist(chat_id, cfg.get("chats_allowlist")):
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

    if briefing:
        max_trocas = int(cfg.get("max_trocas_prioritario", DEFAULT_MAX_TROCAS_PRIORITARIO))
    else:
        max_trocas = int(cfg.get("max_trocas", DEFAULT_MAX_TROCAS))

    # 1. Carrega ou inicializa o estado da conversa
    doc_conversa_ref = db.collection(COLLECTION_CONVERSAS).document(chat_id)
    snap_conversa = doc_conversa_ref.get()
    dados_conversa = snap_conversa.to_dict() if snap_conversa.exists else {}

    estado_atual = dados_conversa.get("estado")
    trocas_atuais = int(dados_conversa.get("trocas_count", 0))
    historico = list(dados_conversa.get("historico_mensagens") or [])

    briefing_doc_id = str(briefing.get("_doc_id") or briefing.get("chat_id") or chat_id) if briefing else None

    # Se a conversa anterior já foi assumida pelo André, encerrada ou escalada, inicia nova sessão com contador zerado
    if estado_atual in (ESTADO_ASSUMIDO_POR_ANDRE, ESTADO_ENCERRADO, ESTADO_ESCALADO):
        trocas_atuais = 0
        historico = []
        estado_atual = ESTADO_EM_ATENDIMENTO

    # 2. Verifica se atingiu o limite de trocas
    if trocas_atuais >= max_trocas:
        if briefing:
            resposta_fechamento = (
                f"{PREFIXO_ASSINATURA}Entendido. Já anotei todas as informações e vou repassar diretamente "
                "ao André assim que ele estiver disponível."
            )
            resumo_fechamento = f"Teto prioritário atingido ({max_trocas} trocas). Última mensagem: {texto_msg[:120]}"

            # Marca briefing como concluído usando o ID real do documento
            db.collection(COLLECTION_PRIORITARIOS).document(briefing_doc_id).update({
                "status": STATUS_PRIORITARIO_CONCLUIDO,
                "resumo_estruturado": resumo_fechamento,
                "informacao_obtida": False,
                "concluido_em": firestore.SERVER_TIMESTAMP,
                "atualizado_em": firestore.SERVER_TIMESTAMP,
            })

            # Registra item na fila atencao com prioridade média
            item_id = registrar_investigacao_concluida_atencao(
                db=db,
                chat_id=chat_id,
                chat_name=chat_name,
                wa_message_id=wa_message_id,
                assunto=str(briefing.get("assunto") or "Assunto prioritário"),
                o_que_precisa_saber=str(briefing.get("o_que_precisa_saber") or ""),
                resumo_estruturado=resumo_fechamento,
                informacao_obtida=False,
                trocas_count=trocas_atuais + 1,
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
                "estado": ESTADO_ENCERRADO,
                "trocas_count": trocas_atuais + 1,
                "briefing_id": briefing_doc_id,
                "ultimo_recado": resumo_fechamento,
                "escalado": True,
                "item_atencao_id": item_id,
                "atualizado_em": firestore.SERVER_TIMESTAMP,
            }, merge=True)

            return {
                "status": "concluido_limite_prioritario",
                "chat_id": chat_id,
                "trocas_count": trocas_atuais + 1,
            }
        else:
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
        import inspect
        sig = inspect.signature(llm_runner)
        accepts_kwargs = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
        if "briefing" in sig.parameters or accepts_kwargs:
            decisao = llm_runner(
                db=db,
                chat_name=chat_name,
                texto_mensagem=texto_msg,
                historico=historico,
                agora_sp=agora_sp,
                briefing=briefing,
            )
        else:
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
            briefing=briefing,
        )

    resposta_texto = prefixar_assinatura(decisao.get("resposta_para_contato") or "")
    resumo_recado = str(decisao.get("resumo_recado") or texto_msg[:120]).strip()
    forcou_decisao = bool(decisao.get("forcou_decisao"))
    assunto_sensivel = bool(decisao.get("assunto_sensivel"))
    investigacao_concluida = bool(decisao.get("investigacao_concluida"))
    resumo_estruturado = str(decisao.get("resumo_estruturado") or resumo_recado).strip()
    informacao_obtida = bool(decisao.get("informacao_obtida", True))

    # 4. Avaliação de risco e conclusão
    item_atencao_id = None
    if forcou_decisao or assunto_sensivel:
        # Guardrails prioritários têm precedência imediata com alta prioridade
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
    elif briefing and investigacao_concluida:
        # Conclusão bem-sucedida ou finalização da investigação com prioridade média
        db.collection(COLLECTION_PRIORITARIOS).document(briefing_doc_id).update({
            "status": STATUS_PRIORITARIO_CONCLUIDO,
            "resumo_estruturado": resumo_estruturado,
            "informacao_obtida": informacao_obtida,
            "concluido_em": firestore.SERVER_TIMESTAMP,
            "atualizado_em": firestore.SERVER_TIMESTAMP,
        })
        item_atencao_id = registrar_investigacao_concluida_atencao(
            db=db,
            chat_id=chat_id,
            chat_name=chat_name,
            wa_message_id=wa_message_id,
            assunto=str(briefing.get("assunto") or "Assunto prioritário"),
            o_que_precisa_saber=str(briefing.get("o_que_precisa_saber") or ""),
            resumo_estruturado=resumo_estruturado,
            informacao_obtida=informacao_obtida,
            trocas_count=trocas_atuais + 1,
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

    if forcou_decisao or assunto_sensivel:
        novo_estado = ESTADO_ESCALADO
    elif briefing and investigacao_concluida:
        novo_estado = ESTADO_ENCERRADO
    else:
        novo_estado = ESTADO_EM_ATENDIMENTO

    payload_conversa = {
        "chat_id": chat_id,
        "chat_name": chat_name,
        "estado": novo_estado,
        "trocas_count": trocas_atuais + 1,
        "historico_mensagens": novo_historico[-10:],  # mantém até os últimos 10 turnos
        "ultimo_recado": resumo_recado,
        "escalado": bool(forcou_decisao or assunto_sensivel or (briefing and investigacao_concluida)),
        "atualizado_em": firestore.SERVER_TIMESTAMP,
    }
    if briefing_doc_id:
        payload_conversa["briefing_id"] = briefing_doc_id
    if not snap_conversa.exists:
        payload_conversa["iniciado_em"] = firestore.SERVER_TIMESTAMP
    if item_atencao_id:
        payload_conversa["item_atencao_id"] = item_atencao_id

    doc_conversa_ref.set(payload_conversa, merge=True)

    status_retorno = "investigacao_concluida" if (briefing and investigacao_concluida) else "ok"

    return {
        "status": status_retorno,
        "chat_id": chat_id,
        "trocas_count": trocas_atuais + 1,
        "outbox_res": outbox_res,
        "escalado": bool(forcou_decisao or assunto_sensivel or (briefing and investigacao_concluida)),
        "investigacao_concluida": bool(briefing and investigacao_concluida),
    }
