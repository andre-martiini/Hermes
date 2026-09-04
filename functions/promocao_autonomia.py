"""Motor de promoção de autonomia por tipo de rascunho de WhatsApp (PR 2 da Fase 3).

Identifica quando um tipo de rascunho amadureceu o suficiente (volume >= 8, taxa sem edição >= 90%)
para ser promovido ao envio autônomo com janela de cancelamento (padrão 10 min), mantendo o
poder de veto do dono no Telegram.
"""

from __future__ import annotations

import datetime
from datetime import timezone

from firebase_admin import firestore

COL_PROMOCOES = "promocoes_autonomia_sugeridas"

STATUS_PENDENTE = "pendente"
STATUS_ACEITA = "aceita"
STATUS_ADIADA = "adiada"
STATUS_NUNCA = "nunca"


def _to_iso(val) -> str | None:
    if val is None:
        return None
    if isinstance(val, (datetime.datetime, datetime.date)):
        return val.isoformat()
    if hasattr(val, "isoformat"):
        return val.isoformat()
    if hasattr(val, "to_datetime"):
        return val.to_datetime().isoformat()
    return str(val)


def tipos_elegiveis_para_promocao(
    db,
    amostra_minima: int = 8,
    taxa_minima: float = 0.9,
    janela_recente: int = 200,
) -> list[dict]:
    """Descobre tipos de rascunho de WhatsApp elegíveis para promoção de autonomia.

    Varre os últimos `janela_recente` documentos de `whatsapp_outbox` com status
    em ('pending', 'sent'), agrupa por tipo em memória para identificar volume bruto,
    e para cada tipo com contagem >= `amostra_minima`:
    - Exclui tipos já em `system/mcp_access.tipos_promovidos`.
    - Exclui tipos com sugestão 'pendente' ou 'nunca' em `promocoes_autonomia_sugeridas`.
    - Consulta `metricas_por_tipo(db, tipo, limite=20)`.
    - Retorna aqueles com `taxa_sem_edicao >= taxa_minima`.
    """
    from outbox_aprovacao import metricas_por_tipo

    # 1. Busca documentos recentes com status pending ou sent
    docs = []
    try:
        query = db.collection("whatsapp_outbox").where("status", "in", ["pending", "sent"]).limit(janela_recente)
        docs = list(query.stream())
    except Exception:
        try:
            all_docs = list(db.collection("whatsapp_outbox").limit(janela_recente).stream())
            docs = [d for d in all_docs if (d.to_dict() or {}).get("status") in ("pending", "sent")]
        except Exception as exc:
            print(f"[PromocaoAutonomia] Falha ao consultar whatsapp_outbox: {exc}")
            return []

    if not docs:
        return []

    # 2. Agrupa volume bruto por tipo
    contagem_bruta: dict[str, int] = {}
    for doc in docs:
        d = doc.to_dict() or {}
        t = str(d.get("tipo") or "").strip().lower()
        if t:
            contagem_bruta[t] = contagem_bruta.get(t, 0) + 1

    # 3. Lê tipos já promovidos de system/mcp_access
    promovidos: set[str] = set()
    try:
        snap_mcp = db.collection("system").document("mcp_access").get()
        if snap_mcp.exists:
            lista = (snap_mcp.to_dict() or {}).get("tipos_promovidos") or []
            promovidos = {str(item).strip().lower() for item in lista if str(item).strip()}
    except Exception as exc:
        print(f"[PromocaoAutonomia] Falha ao ler system/mcp_access: {exc}")

    elegiveis: list[dict] = []

    # 4. Avalia cada tipo candidato
    for tipo_candidato, count in contagem_bruta.items():
        if count < amostra_minima:
            continue
        if tipo_candidato in promovidos:
            continue

        # Verifica se já existe sugestão pendente ou nunca
        try:
            snap_sug = db.collection(COL_PROMOCOES).document(tipo_candidato).get()
            if snap_sug.exists:
                st_sug = (snap_sug.to_dict() or {}).get("status")
                if st_sug in (STATUS_PENDENTE, STATUS_NUNCA):
                    continue
        except Exception as exc:
            print(f"[PromocaoAutonomia] Falha ao consultar sugestão para {tipo_candidato}: {exc}")

        # Avalia métricas reais dos últimos rascunhos decididos
        metricas = metricas_por_tipo(db, tipo=tipo_candidato, limite=20)
        amostra = metricas.get("amostra", 0)
        taxa = metricas.get("taxa_sem_edicao", 0.0)

        if amostra >= amostra_minima and taxa >= taxa_minima:
            elegiveis.append({
                "tipo": tipo_candidato,
                "metricas": metricas,
            })

    return elegiveis


def registrar_sugestao_promocao(db, tipo: str, metricas: dict) -> str:
    """Grava ou atualiza uma sugestão de promoção na coleção promocoes_autonomia_sugeridas."""
    tipo_limpo = str(tipo or "").strip().lower()
    if not tipo_limpo:
        raise ValueError("tipo é obrigatório para registrar sugestão.")

    doc_ref = db.collection(COL_PROMOCOES).document(tipo_limpo)
    agora_utc = datetime.datetime.now(timezone.utc)

    payload = {
        "tipo": tipo_limpo,
        "status": STATUS_PENDENTE,
        "amostra": metricas.get("amostra", 0),
        "aprovados_sem_edicao": metricas.get("aprovados_sem_edicao", 0),
        "taxa_sem_edicao": metricas.get("taxa_sem_edicao", 0.0),
        "sugerida_em": firestore.SERVER_TIMESTAMP if hasattr(firestore, "SERVER_TIMESTAMP") else agora_utc,
    }
    doc_ref.set(payload, merge=True)
    return tipo_limpo


def decidir_promocao_autonomia(db, tipo: str, decisao: str) -> dict:
    """Aplica a decisão do usuário (aceitar, adiar, nunca) sobre a promoção de um tipo.

    Transacional: ao aceitar, atualiza o status em promocoes_autonomia_sugeridas/{tipo}
    e adiciona o tipo a system/mcp_access.tipos_promovidos na mesma transação atômica.
    """
    tipo_limpo = str(tipo or "").strip().lower()
    decisao_limpa = str(decisao or "").strip().lower()

    if not tipo_limpo:
        return {"ok": False, "erro": "tipo é obrigatório."}

    mapa_decisoes = {
        "aceitar": STATUS_ACEITA,
        "adiar": STATUS_ADIADA,
        "nunca": STATUS_NUNCA,
    }
    if decisao_limpa not in mapa_decisoes:
        return {"ok": False, "erro": f"Decisão inválida '{decisao}'. Use: aceitar, adiar ou nunca."}

    novo_status = mapa_decisoes[decisao_limpa]
    sug_ref = db.collection(COL_PROMOCOES).document(tipo_limpo)
    mcp_ref = db.collection("system").document("mcp_access")
    agora_utc = datetime.datetime.now(timezone.utc)
    server_ts = firestore.SERVER_TIMESTAMP if hasattr(firestore, "SERVER_TIMESTAMP") else agora_utc

    # Execução transacional
    success = False
    transaction_result = {}

    if hasattr(db, "transaction"):
        try:
            tx = db.transaction()

            @firestore.transactional
            def _exec_decidir(transaction):
                sug_snap = sug_ref.get(transaction=transaction)
                if not sug_snap.exists:
                    return {"ok": False, "erro": f"Sugestão para o tipo '{tipo_limpo}' não encontrada."}

                sug_dados = sug_snap.to_dict() or {}
                if sug_dados.get("status") != STATUS_PENDENTE:
                    return {
                        "ok": False,
                        "erro": f"Sugestão já estava decidida com status '{sug_dados.get('status')}'.",
                    }

                if decisao_limpa == "aceitar":
                    mcp_snap = mcp_ref.get(transaction=transaction)
                    tipos_atuais = []
                    if mcp_snap.exists:
                        tipos_atuais = list((mcp_snap.to_dict() or {}).get("tipos_promovidos") or [])
                    tipos_set = {str(t).strip().lower() for t in tipos_atuais if str(t).strip()}
                    if tipo_limpo not in tipos_set:
                        tipos_atuais.append(tipo_limpo)

                    transaction.set(
                        mcp_ref,
                        {
                            "tipos_promovidos": tipos_atuais,
                            "atualizado_em": server_ts,
                        },
                        merge=True,
                    )

                transaction.update(
                    sug_ref,
                    {
                        "status": novo_status,
                        "decidida_em": server_ts,
                        "decisao": decisao_limpa,
                    },
                )
                return {"ok": True, "tipo": tipo_limpo, "decisao": decisao_limpa, "status": novo_status}

            transaction_result = _exec_decidir(tx)
            success = True
        except Exception as tx_err:
            print(f"[PromocaoAutonomia] Transação falhou ou mock sem suporte: {tx_err}")

    if not success:
        # Fallback defensivo para mock simples
        sug_snap = sug_ref.get()
        if not sug_snap.exists:
            return {"ok": False, "erro": f"Sugestão para o tipo '{tipo_limpo}' não encontrada."}

        sug_dados = sug_snap.to_dict() or {}
        if sug_dados.get("status") != STATUS_PENDENTE:
            return {
                "ok": False,
                "erro": f"Sugestão já estava decidida com status '{sug_dados.get('status')}'.",
            }

        if decisao_limpa == "aceitar":
            mcp_snap = mcp_ref.get()
            tipos_atuais = []
            if mcp_snap.exists:
                tipos_atuais = list((mcp_snap.to_dict() or {}).get("tipos_promovidos") or [])
            tipos_set = {str(t).strip().lower() for t in tipos_atuais if str(t).strip()}
            if tipo_limpo not in tipos_set:
                tipos_atuais.append(tipo_limpo)

            mcp_ref.set(
                {
                    "tipos_promovidos": tipos_atuais,
                    "atualizado_em": server_ts,
                },
                merge=True,
            )

        sug_ref.update({
            "status": novo_status,
            "decidida_em": server_ts,
            "decisao": decisao_limpa,
        })
        transaction_result = {"ok": True, "tipo": tipo_limpo, "decisao": decisao_limpa, "status": novo_status}

    if not transaction_result.get("ok"):
        return transaction_result

    detalhes = {
        "aceitar": f"Tipo '{tipo_limpo}' promovido com sucesso para envio com janela de cancelamento.",
        "adiar": f"Sugestão para o tipo '{tipo_limpo}' adiada. O tipo continuará exigindo aprovação no Telegram e poderá ser sugerido novamente em avaliações futuras.",
        "nunca": f"Promoção descartada para sempre para o tipo '{tipo_limpo}'. Não será mais sugerido.",
    }
    return {
        "ok": True,
        "tipo": tipo_limpo,
        "decisao": decisao_limpa,
        "status": novo_status,
        "detalhe": detalhes.get(decisao_limpa, ""),
    }


def listar_promocoes_pendentes(db, limite: int = 20) -> dict:
    """Lista as sugestões de promoção de autonomia aguardando decisão."""
    limite_ajustado = max(1, min(int(limite or 20), 50))
    try:
        query = db.collection(COL_PROMOCOES).where("status", "==", STATUS_PENDENTE)
        docs = list(query.stream())
    except Exception as exc:
        return {"total": 0, "promocoes": [], "erro": str(exc)}

    pendentes = []
    for doc in docs:
        d = doc.to_dict() or {}
        pendentes.append({
            "tipo": d.get("tipo") or doc.id,
            "status": d.get("status"),
            "amostra": d.get("amostra", 0),
            "aprovados_sem_edicao": d.get("aprovados_sem_edicao", 0),
            "taxa_sem_edicao": d.get("taxa_sem_edicao", 0.0),
            "sugerida_em": _to_iso(d.get("sugerida_em")),
        })

    pendentes.sort(key=lambda x: str(x.get("sugerida_em") or ""), reverse=True)
    return {
        "total": len(pendentes),
        "promocoes": pendentes[:limite_ajustado],
    }
