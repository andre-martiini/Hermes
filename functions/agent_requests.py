"""Fila de trabalho autônomo do Hermes (agent_requests).

Enfileira tarefas autônomas (que não precisam de decisão prévia do dono)
para serem executadas pela próxima sessão agendada do Claude (ex.: consolidação de áudios).
Mantém estrita separação entre lógica pura e I/O com Firestore.

P04 sub-entrega 8/N (passo 5 do pacote, "Preservar consultar/concluir
legados. Pedidos schema_version novo exigem lease; executor legado não pode
concluir um pedido reservado por outro."): `concluir` importa
`autonomy.requests.SCHEMA_VERSION_ATUAL` para reconhecer um pedido já
migrado para o protocolo novo e recusar produzir efeito sobre ele enquanto
não for terminal -- ver a docstring de `concluir` para os detalhes. Nenhum
pedido em produção tem `schema_version` hoje (a migração é o passo 9 do
pacote, ainda não feita) -- esta sub-entrega é uma guarda preventiva para
quando pedidos novos (passo 6, unificação do ciclo de jobs MCP) começarem a
existir, não uma mudança de comportamento observável para os dados atuais.
"""

from __future__ import annotations

import datetime
from firebase_admin import firestore

from autonomy.requests import SCHEMA_VERSION_ATUAL

COLLECTION = "agent_requests"

TIPO_CONSOLIDAR_AUDIO = "consolidar_audio"

STATUS_PENDENTE = "pendente"
STATUS_EM_ANDAMENTO = "em_andamento"
STATUS_CONCLUIDO = "concluido"
STATUS_ERRO = "erro"

STATUS_TERMINAIS = {STATUS_CONCLUIDO, STATUS_ERRO}


# ---------------------------------------------------------------------------
# Lógica pura (testável sem Firestore / I/O)
# ---------------------------------------------------------------------------


def validar_transicao(status_atual: str | None) -> tuple[bool, str]:
    """Valida se o pedido pode transicionar para concluído ou erro.

    Só aceita concluir/errar a partir de 'pendente' ou 'em_andamento'.
    'concluido' e 'erro' são terminais (não regridem nem se sobrescrevem).
    """
    if status_atual in (STATUS_PENDENTE, STATUS_EM_ANDAMENTO):
        return True, ""
    if status_atual is None:
        return False, "Pedido não encontrado."
    if status_atual in STATUS_TERMINAIS:
        return False, f"já decidido (status atual: {status_atual})"
    return False, f"status inválido: {status_atual}"


def montar_payload_consolidar_audio(
    chat_id: str,
    chat_name: str,
    mensagem_ids: list[str],
    acao_id: str | None = None,
    item_atencao_id: str | None = None,
) -> dict:
    """Monta o payload padronizado para pedidos do tipo consolidar_audio."""
    return {
        "chat_id": str(chat_id or "").strip(),
        "chat_name": str(chat_name or "").strip(),
        "mensagem_ids": list(mensagem_ids or []),
        "acao_id": str(acao_id).strip() if acao_id else None,
        "item_atencao_id": str(item_atencao_id).strip() if item_atencao_id else None,
    }


def _to_iso(dt: object) -> str | None:
    if dt is None:
        return None
    if hasattr(dt, "isoformat"):
        return dt.isoformat()
    return str(dt)


def _protocolo_novo_ativo(data: dict) -> bool:
    """`True` quando `data` (documento cru do Firestore) já foi migrado para
    o protocolo novo do P04 (`schema_version` presente e >= `SCHEMA_VERSION_ATUAL`)
    -- ver a constante em `autonomy.requests` e a docstring de `concluir`.

    Ausência do campo (todo pedido legado hoje) devolve `False`. Um valor
    malformado (string não numérica, lista, etc. -- nunca deveria acontecer
    com escrita própria, mas este campo pode ter vindo de uma origem externa)
    também devolve `False` em vez de levantar: falha fechada NO SENTIDO de
    preservar o comportamento legado quando a evidência de protocolo novo é
    inconclusiva, não de bloquear por precaução -- o inverso do fencing de
    lease (`autonomy.requests.lease_pertence_ao_apresentante`), que falha
    fechado recusando quando a evidência de identidade é inconclusiva. Aqui
    quem decide "é protocolo novo" é sempre um campo gravado pelo próprio
    servidor (nunca apresentado por um consumidor não confiável), então um
    valor malformado é sinal de corrupção de dados, não de tentativa de
    burlar o fencing -- não há motivo para tratar isso como mais um caso de
    entrada hostil."""
    valor = data.get("schema_version")
    if valor is None:
        return False
    try:
        return int(valor) >= SCHEMA_VERSION_ATUAL
    except (TypeError, ValueError):
        return False


# ---------------------------------------------------------------------------
# Operações Firestore (I/O)
# ---------------------------------------------------------------------------


def enfileirar_ou_atualizar(
    db,
    doc_id: str,
    tipo: str,
    payload: dict,
    origem: str,
    acao_id: str | None = None,
    item_atencao_id: str | None = None,
) -> dict:
    """Cria um novo pedido ou atualiza um pedido existente se ainda estiver pendente.

    Se o pedido já existir e estiver em_andamento, concluido ou erro, NÃO mexe
    para evitar concorrência com o executor.

    Leitura (existe? qual status?) e escrita (criar, mesclar ou ignorar)
    acontecem dentro de uma única transação Firestore (mesmo padrão A04 de
    outbox_aprovacao.aprovar_rascunho/descartar_rascunho/aplicar_edicao_rascunho).
    Sem essa proteção, um enfileiramento tardio (retry, mensagem fora de
    ordem) que leu o documento como 'pendente' podia sobrescrever payload e
    campos derivados depois que o executor já tivesse avançado o status para
    em_andamento/concluido/erro entre a leitura e a escrita -- corrompendo
    silenciosamente um pedido que já estava sendo processado com dado novo.
    Sem suporte a transação real, recusa em vez de arriscar essa escrita
    desprotegida.
    """
    doc_id = str(doc_id or "").strip()
    if not doc_id:
        return {"erro": "doc_id é obrigatório."}

    doc_ref = db.collection(COLLECTION).document(doc_id)

    if not hasattr(db, "transaction"):
        return {
            "status": "erro_configuracao",
            "erro": "Backend Firestore sem suporte a transação; enfileiramento recusado para evitar condição de corrida.",
        }

    try:
        transaction = db.transaction()

        @firestore.transactional
        def _exec_enfileirar(tx):
            snap = doc_ref.get(transaction=tx)

            if not snap.exists:
                data = {
                    "tipo": tipo,
                    "status": STATUS_PENDENTE,
                    "payload": payload,
                    "origem": origem,
                    "item_atencao_id": item_atencao_id,
                    "acao_id": acao_id,
                    "criado_em": firestore.SERVER_TIMESTAMP,
                    "atualizado_em": firestore.SERVER_TIMESTAMP,
                    "processado_em": None,
                    "resultado": None,
                    "erro": None,
                }
                tx.set(doc_ref, data)
                return {"status": "enfileirado", "doc_id": doc_id}

            existente = snap.to_dict() or {}
            status = existente.get("status")

            if status == STATUS_PENDENTE:
                update_data = {
                    "payload": payload,
                    "atualizado_em": firestore.SERVER_TIMESTAMP,
                }
                if acao_id is not None:
                    update_data["acao_id"] = acao_id
                if item_atencao_id is not None:
                    update_data["item_atencao_id"] = item_atencao_id
                tx.update(doc_ref, update_data)
                return {"status": "atualizado", "doc_id": doc_id}

            return {
                "status": "ignorado",
                "motivo": f"status atual '{status}' nao permite atualizacao",
                "doc_id": doc_id,
            }

        return _exec_enfileirar(transaction)
    except Exception as tx_err:
        # Falha real de transação (ex.: Aborted após esgotar tentativas). Não há
        # fallback para escrita desprotegida -- retorna erro explícito em vez de
        # arriscar sobrescrever um pedido que o executor já esteja processando.
        print(f"[AgentRequests] Transação Firestore de enfileiramento falhou: {tx_err}")
        return {
            "status": "erro_transacao",
            "erro": f"Não foi possível enfileirar de forma atômica: {tx_err}",
        }


def listar_pendentes(db, tipo: str | None = None, limite: int = 20) -> dict:
    """Lista pedidos em status 'pendente', opcionalmente filtrando por tipo.

    Ordena por criado_em crescente (mais antigo primeiro).

    P04 sub-entrega 8/N (achado real do Codex na PR #359, revisão da própria
    sub-entrega -- passo 5 do pacote): pula pedidos do protocolo novo
    (`_protocolo_novo_ativo`), mesmo que estejam em status 'pendente' (mesma
    string usada pelos dois protocolos). Sem este filtro, `consultar_pedidos_agente`
    (MCP, backed por esta função) continuaria oferecendo um pedido já
    migrado para o executor legado do fluxo agendado -- que produziria todo
    o EFEITO de trabalho (consolidação, diário, resolução de atenção) antes
    de `concluir_pedido_agente` recusar no final (`_protocolo_novo_ativo` em
    `concluir`, ver acima), deixando o pedido `pendente` de novo para um
    segundo executor (agora sim pelo protocolo novo, com lease) repetir o
    mesmo trabalho -- exatamente a duplicação que o passo 5 existe para
    impedir, só que pelo caminho de leitura em vez do de escrita.
    """
    limite_ajustado = max(1, min(int(limite or 20), 50))
    query = db.collection(COLLECTION).where("status", "==", STATUS_PENDENTE)
    if tipo:
        query = query.where("tipo", "==", str(tipo).strip())

    docs = list(query.stream())
    pedidos: list[dict] = []

    for doc in docs:
        d = doc.to_dict() or {}
        if _protocolo_novo_ativo(d):
            continue
        pedidos.append({
            "id": doc.id,
            "tipo": d.get("tipo"),
            "status": d.get("status"),
            "payload": d.get("payload") or {},
            "origem": d.get("origem"),
            "item_atencao_id": d.get("item_atencao_id"),
            "acao_id": d.get("acao_id"),
            "criado_em": _to_iso(d.get("criado_em")),
            "atualizado_em": _to_iso(d.get("atualizado_em")),
        })

    def _sort_key(x: dict) -> str:
        return x.get("criado_em") or ""

    pedidos.sort(key=_sort_key)
    return {
        "total": len(pedidos),
        "pedidos": pedidos[:limite_ajustado],
    }


def contar_pendentes(db, tipo: str | None = None) -> int:
    """Contagem rápida de pedidos pendentes para o resumo de estado.

    Mesmo filtro de protocolo novo de `listar_pendentes` (ver sua docstring,
    achado do Codex na PR #359) -- um pedido já migrado não deve inflar a
    contagem que sinaliza "há trabalho legado esperando".
    """
    query = db.collection(COLLECTION).where("status", "==", STATUS_PENDENTE)
    if tipo:
        query = query.where("tipo", "==", str(tipo).strip())
    return sum(
        1 for doc in query.stream() if not _protocolo_novo_ativo(doc.to_dict() or {})
    )


def concluir(
    db,
    request_id: str,
    resultado: str | None = None,
    erro: str | None = None,
) -> dict:
    """Conclui ou registra erro em um pedido de trabalho autônomo.

    Exige exatamente um entre resultado e erro.
    É idempotente: se o pedido já estiver terminal, devolve status 'already_decided'
    sem sobrescrever o registro existente.

    Transição protegida por transação Firestore (mesmo padrão A04 de
    outbox_aprovacao.aprovar_rascunho/descartar_rascunho/aplicar_edicao_rascunho):
    a tool MCP concluir_pedido_agente é acionável por mais de uma sessão, e um
    get()+update() incondicional permite que duas conclusões concorrentes do
    mesmo pedido colidam -- a segunda, lendo o mesmo snapshot pendente antes da
    primeira escrever, sobrescreveria silenciosamente o resultado/erro já
    gravado. Sem suporte a transação real, recusa em vez de arriscar essa
    escrita desprotegida.

    P04 sub-entrega 8/N (passo 5 do pacote, seção 4 do plano de autonomia):
    um pedido já migrado para o protocolo novo (`_protocolo_novo_ativo`,
    `schema_version` >= `autonomy.requests.SCHEMA_VERSION_ATUAL`) que ainda
    não é terminal (`status_atual not in STATUS_TERMINAIS`, o conjunto
    LEGADO -- ver detalhe abaixo) recusa esta chamada com status
    `'protocolo_novo_exige_lease'`, sem escrever nada: este caminho legado
    não recebe (nem pode validar) lease_token/generation, então nunca pode
    provar que é o executor que detém a reserva atual -- use
    `autonomy.execution.registrar_resultado_observado` (com o lease/geração
    corretos) para concluir um pedido nesse protocolo. Isto cobre tanto "sem
    reserva nenhuma ainda" quanto "reservado por outro executor" com a MESMA
    recusa -- nenhum dos dois casos tem uma lease legítima para apresentar
    aqui, e o plano exige lease para qualquer efeito sobre estes pedidos,
    não só quando uma reserva concorrente está ativa no momento exato da
    chamada.

    Deliberadamente NÃO bloqueia quando `status_atual` já é um terminal
    LEGADO (`STATUS_TERMINAIS` = {concluido, erro} -- que inclui o valor
    "concluido" também usado pelo protocolo novo para o mesmo desfecho):
    nesse caso a chamada segue para `validar_transicao`, que já devolve
    'already_decided' sem tocar o documento, o mesmo no-op idempotente que
    já valia antes desta sub-entrega para qualquer pedido terminal -- não há
    risco de corromper uma reserva ativa (não há mais reserva ativa alguma
    num pedido terminal) nem de mascarar uma leitura inofensiva. Um pedido
    do protocolo novo em outro estado terminal (`falha_final`/`cancelado`,
    que este módulo legado não reconhece como terminal) continua caindo no
    bloqueio acima -- correto, e mais informativo que o 'status inválido'
    genérico que essa combinação produziria sem esta sub-entrega.
    """
    request_id = str(request_id or "").strip()
    if not request_id:
        return {"erro": "request_id é obrigatório."}

    tem_res = resultado is not None and str(resultado).strip() != ""
    tem_err = erro is not None and str(erro).strip() != ""

    if (tem_res and tem_err) or (not tem_res and not tem_err):
        return {"erro": "Informe exatamente um entre 'resultado' e 'erro'."}

    doc_ref = db.collection(COLLECTION).document(request_id)

    if not hasattr(db, "transaction"):
        return {
            "status": "erro_configuracao",
            "erro": "Backend Firestore sem suporte a transação; conclusão recusada para evitar condição de corrida.",
        }

    novo_status = STATUS_CONCLUIDO if tem_res else STATUS_ERRO

    try:
        transaction = db.transaction()

        @firestore.transactional
        def _exec_concluir(tx):
            snap = doc_ref.get(transaction=tx)
            if not snap.exists:
                return {"status": "not_found", "erro": f"Pedido '{request_id}' não encontrado."}

            data = snap.to_dict() or {}
            status_atual = data.get("status")

            if status_atual not in STATUS_TERMINAIS and _protocolo_novo_ativo(data):
                return {
                    "status": "protocolo_novo_exige_lease",
                    "estado_atual": status_atual,
                    "erro": (
                        f"Pedido '{request_id}' usa o protocolo novo "
                        f"(schema_version >= {SCHEMA_VERSION_ATUAL}) -- passo 5 do "
                        "pacote P04 exige lease/geração para produzir efeito "
                        "enquanto o pedido não é terminal. Use "
                        "autonomy.execution.registrar_resultado_observado em vez "
                        "de concluir_pedido_agente legado."
                    ),
                }

            valido, motivo = validar_transicao(status_atual)
            if not valido:
                return {
                    "status": "already_decided",
                    "estado_atual": status_atual,
                    "erro": f"Pedido {motivo}",
                    "dados": data,
                }

            tx.update(
                doc_ref,
                {
                    "status": novo_status,
                    "processado_em": firestore.SERVER_TIMESTAMP,
                    "atualizado_em": firestore.SERVER_TIMESTAMP,
                    "resultado": str(resultado).strip() if tem_res else None,
                    "erro": str(erro).strip() if tem_err else None,
                },
            )
            return {"status": "ok"}

        transaction_result = _exec_concluir(transaction)
    except Exception as tx_err:
        # Falha real de transação (ex.: Aborted após esgotar tentativas). Não há
        # fallback para escrita desprotegida -- retorna erro explícito em vez de
        # arriscar uma condição de corrida entre conclusões concorrentes.
        print(f"[AgentRequests] Transação Firestore de conclusão falhou: {tx_err}")
        return {
            "status": "erro_transacao",
            "erro": f"Não foi possível concluir de forma atômica: {tx_err}",
        }

    if transaction_result.get("status") != "ok":
        return transaction_result

    return {
        "status": "ok",
        "request_id": request_id,
        "novo_status": novo_status,
    }
