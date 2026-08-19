"""
CRUD de objetivos estratégicos pessoais (`estrategia_pessoal`), compartilhado
entre o Copiloto padrão (main.py, ferramentas do `copilot_mode == 'estrategia'`)
e o Godmode (godmode.py) — mesmo padrão de extração já usado para finanças
(`tools/telegram_extended.py`).

Todas as funções operam sobre `db` e exigem `user_uid` (fail-closed: só
enxergam/alteram objetivos cujo `userId` bate exatamente com o chamador).
"""
import time
import uuid
from datetime import datetime, timezone

from firebase_admin import firestore

PILARES = {'carreira', 'financas', 'saude', 'intelectual', 'estilo_vida'}
STATUS_VALUES = {'ativo', 'concluido', 'revisar'}
TIPOS = {'absoluta', 'relativa_qualitativa'}


def novo_id_estrategia(prefixo: str) -> str:
    return f"{prefixo}-{int(time.time() * 1000)}-{str(uuid.uuid4())[:6]}"


def carregar_objetivo_estrategico(db, user_uid: str | None, objetivo_id: str):
    """Carrega um objetivo garantindo posse pelo usuário atual. Retorna (ref, data) ou (None, None).
    Fail-closed: exige usuário autenticado e que o userId do documento bata exatamente."""
    if not user_uid or not objetivo_id:
        return None, None
    ref = db.collection('estrategia_pessoal').document(str(objetivo_id))
    snap = ref.get()
    if not snap.exists:
        return None, None
    data = snap.to_dict() or {}
    if data.get('userId') != user_uid:
        return None, None
    return ref, data


def criar_objetivo_estrategico(
    db,
    user_uid: str | None,
    objetivoMacro: str,
    pilar: str = "carreira",
    tipoMeta: str = "relativa_qualitativa",
    status: str = "ativo",
    diretrizes: list[str] | None = None,
    indicadores: list[str] | None = None,
    marcos: list[str] | None = None,
    metrica_valor_inicial: float | None = None,
    metrica_valor_atual: float | None = None,
    metrica_valor_objetivo: float | None = None,
    metrica_unidade: str = "",
) -> dict:
    if not user_uid:
        return {"status": "error", "reason": "auth_required"}
    titulo = (objetivoMacro or "").strip()
    if not titulo:
        return {"status": "error", "reason": "objetivoMacro_obrigatorio"}
    pilar_norm = (pilar or "carreira").strip().lower()
    if pilar_norm not in PILARES:
        pilar_norm = "carreira"
    tipo_norm = (tipoMeta or "relativa_qualitativa").strip().lower()
    if tipo_norm not in TIPOS:
        tipo_norm = "relativa_qualitativa"
    status_norm = (status or "ativo").strip().lower()
    if status_norm not in STATUS_VALUES:
        status_norm = "ativo"

    diretrizes_clean = [str(d).strip() for d in (diretrizes or []) if str(d).strip()]
    if not diretrizes_clean:
        return {"status": "error", "reason": "diretrizes_obrigatorias"}

    indicadores_obj = [
        {"id": novo_id_estrategia("indicador"), "descricao": str(d).strip(), "concluido": False, "registros": []}
        for d in (indicadores or []) if str(d).strip()
    ]
    marcos_obj = [
        {"id": novo_id_estrategia("marco"), "descricao": str(d).strip(), "concluido": False, "registros": []}
        for d in (marcos or []) if str(d).strip()
    ]

    payload = {
        "userId": user_uid,
        "pilar": pilar_norm,
        "objetivoMacro": titulo,
        "tipoMeta": tipo_norm,
        "indicadoresSucesso": indicadores_obj,
        "marcos": marcos_obj,
        "diretrizesDerivadas": diretrizes_clean,
        "status": status_norm,
        "timestamp": firestore.SERVER_TIMESTAMP,
    }

    if tipo_norm == "absoluta":
        val_obj = float(metrica_valor_objetivo or 0)
        val_atual = float(metrica_valor_atual or 0)
        val_ini = float(metrica_valor_inicial) if metrica_valor_inicial is not None else (val_atual if val_obj < val_atual else 0)
        payload["metricaAlvo"] = {
            "valorInicial": val_ini,
            "valorAtual": val_atual,
            "valorObjetivo": val_obj,
            "unidade": str(metrica_unidade or "").strip(),
        }

    ref = db.collection('estrategia_pessoal').document()
    ref.set(payload)
    return {"status": "created", "objetivo_id": ref.id, "objetivoMacro": titulo, "pilar": pilar_norm}


def editar_objetivo_estrategico(
    db,
    user_uid: str | None,
    objetivo_id: str,
    objetivoMacro: str | None = None,
    pilar: str | None = None,
    tipoMeta: str | None = None,
    status: str | None = None,
    diretrizes: list[str] | None = None,
    metrica_valor_inicial: float | None = None,
    metrica_valor_atual: float | None = None,
    metrica_valor_objetivo: float | None = None,
    metrica_unidade: str | None = None,
) -> dict:
    ref, data = carregar_objetivo_estrategico(db, user_uid, objetivo_id)
    if not ref:
        return {"status": "error", "reason": "objetivo_nao_encontrado"}

    updates = {}
    if objetivoMacro is not None and str(objetivoMacro).strip():
        updates["objetivoMacro"] = str(objetivoMacro).strip()
    if pilar is not None:
        p = str(pilar).strip().lower()
        if p in PILARES:
            updates["pilar"] = p
    if status is not None:
        s = str(status).strip().lower()
        if s in STATUS_VALUES:
            updates["status"] = s
    if tipoMeta is not None:
        tm = str(tipoMeta).strip().lower()
        if tm in TIPOS:
            updates["tipoMeta"] = tm
    if diretrizes is not None:
        dz = [str(d).strip() for d in (diretrizes or []) if str(d).strip()]
        if not dz:
            return {"status": "error", "reason": "diretrizes_nao_podem_ficar_vazias"}
        updates["diretrizesDerivadas"] = dz

    # Métrica: só aplica se o objetivo é/torna-se absoluto
    tipo_final = updates.get("tipoMeta", data.get("tipoMeta"))
    if tipo_final == "absoluta" and any(v is not None for v in [metrica_valor_inicial, metrica_valor_atual, metrica_valor_objetivo, metrica_unidade]):
        metrica = dict(data.get("metricaAlvo") or {})
        if metrica_valor_inicial is not None:
            metrica["valorInicial"] = float(metrica_valor_inicial)
        if metrica_valor_atual is not None:
            metrica["valorAtual"] = float(metrica_valor_atual)
        if metrica_valor_objetivo is not None:
            metrica["valorObjetivo"] = float(metrica_valor_objetivo)
        if metrica_unidade is not None:
            metrica["unidade"] = str(metrica_unidade).strip()
        metrica.setdefault("valorInicial", 0)
        metrica.setdefault("valorAtual", 0)
        metrica.setdefault("valorObjetivo", 0)
        metrica.setdefault("unidade", "")
        updates["metricaAlvo"] = metrica

    if not updates:
        return {"status": "noop", "reason": "nenhum_campo_alterado"}

    updates["timestamp"] = firestore.SERVER_TIMESTAMP
    ref.update(updates)
    return {
        "status": "updated",
        "objetivo_id": ref.id,
        "campos_alterados": [k for k in updates.keys() if k != "timestamp"],
    }


def gerenciar_item_estrategico(
    db,
    user_uid: str | None,
    objetivo_id: str,
    tipo: str,
    acao: str,
    descricao: str | None = None,
    item_id: str | None = None,
) -> dict:
    if not user_uid or not objetivo_id:
        return {"status": "error", "reason": "objetivo_nao_encontrado"}
    tipo_norm = (tipo or "").strip().lower()
    if tipo_norm not in {"indicador", "marco"}:
        return {"status": "error", "reason": "tipo_invalido"}
    acao_norm = (acao or "").strip().lower()
    if acao_norm not in {"adicionar", "editar", "remover", "concluir"}:
        return {"status": "error", "reason": "acao_invalida"}
    campo = "indicadoresSucesso" if tipo_norm == "indicador" else "marcos"
    ref = db.collection('estrategia_pessoal').document(str(objetivo_id))

    # Transação: indispensável porque o loop de tool-calling pode disparar
    # várias chamadas gerenciar_item_estrategico em paralelo sobre o mesmo
    # objetivo. Ler/recompor/gravar o array inteiro fora de transação faria
    # o último writer sobrescrever silenciosamente os demais. A transação
    # relê dentro do escopo e o Firestore reexecuta sob contenção.
    @firestore.transactional
    def _aplicar(transaction):
        snap = ref.get(transaction=transaction)
        if not snap.exists:
            return {"status": "error", "reason": "objetivo_nao_encontrado"}
        data = snap.to_dict() or {}
        if data.get('userId') != user_uid:
            return {"status": "error", "reason": "objetivo_nao_encontrado"}

        lista = []
        for item in (data.get(campo) or []):
            if isinstance(item, str):
                lista.append({"id": novo_id_estrategia(tipo_norm), "descricao": item, "concluido": False, "registros": []})
            else:
                lista.append({
                    "id": item.get("id") or novo_id_estrategia(tipo_norm),
                    "descricao": item.get("descricao", ""),
                    "concluido": bool(item.get("concluido")),
                    "registros": item.get("registros", []),
                    **({"dataConclusao": item["dataConclusao"]} if item.get("dataConclusao") else {}),
                    **({"evidencia": item["evidencia"]} if item.get("evidencia") else {}),
                })

        if acao_norm == "adicionar":
            if not (descricao or "").strip():
                return {"status": "error", "reason": "descricao_obrigatoria"}
            novo = {"id": novo_id_estrategia(tipo_norm), "descricao": descricao.strip(), "concluido": False, "registros": []}
            lista.append(novo)
            resultado_id = novo["id"]
        else:  # editar | remover | concluir
            if not item_id:
                return {"status": "error", "reason": "item_id_obrigatorio"}
            alvo = next((it for it in lista if it["id"] == item_id), None)
            if not alvo:
                return {"status": "error", "reason": "item_nao_encontrado"}
            if acao_norm == "editar":
                if not (descricao or "").strip():
                    return {"status": "error", "reason": "descricao_obrigatoria"}
                alvo["descricao"] = descricao.strip()
            elif acao_norm == "remover":
                lista = [it for it in lista if it["id"] != item_id]
            elif acao_norm == "concluir":
                alvo["concluido"] = True
                alvo["dataConclusao"] = datetime.now(timezone.utc).isoformat()
            resultado_id = item_id

        transaction.update(ref, {campo: lista, "timestamp": firestore.SERVER_TIMESTAMP})
        return {
            "status": "ok",
            "objetivo_id": ref.id,
            "tipo": tipo_norm,
            "acao": acao_norm,
            "item_id": resultado_id,
        }

    return _aplicar(db.transaction())


def excluir_objetivo_estrategico(db, user_uid: str | None, objetivo_id: str) -> dict:
    ref, data = carregar_objetivo_estrategico(db, user_uid, objetivo_id)
    if not ref:
        return {"status": "error", "reason": "objetivo_nao_encontrado"}
    titulo = data.get("objetivoMacro", "")
    ref.delete()
    return {"status": "deleted", "objetivo_id": objetivo_id, "objetivoMacro": titulo}
