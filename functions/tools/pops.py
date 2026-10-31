"""POPs pelo MCP: criar, editar, listar e desativar (sem nunca apagar).

Os POPs vivem em `pops_diretrizes`, a mesma coleção que a tela de POPs
(`PopManagerTool.tsx`) grava e que alimenta `pops_ativos` em
`obter_estado_atual` (`main._pops_sempre_ativos`, os com `sempre_ativo: true`).

Desativar MOVE o documento, com o mesmo id, para `pops_diretrizes_inativos`:
todo leitor de `pops_diretrizes` (estado, matcher, prompts do MCP, mapa de POPs,
telas) deixa de vê-lo sem precisar conhecer um campo novo. Reativar traz de volta.

Cada escrita deixa uma linha em `pops_historico` com o antes e o depois: é dali
que se recupera a versão anterior de uma edição (`listar_pops` com `id`).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

ATIVOS = "pops_diretrizes"
INATIVOS = "pops_diretrizes_inativos"
HISTORICO = "pops_historico"
ORIGENS = ("sempre_ativo", "gatilhos")
AUTOR = "agente"


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat()


def _texto(args: dict, campo: str) -> str:
    return str(args.get(campo) or "").strip()


def _limpar_cache() -> None:
    # `main._pops_sempre_ativos` guarda a coleção por 60 s; sem isto o POP novo
    # só apareceria em `pops_ativos` depois do TTL nesta instância.
    try:
        import main
        main._POPS_DATA_CACHE = None
    except Exception:  # noqa: BLE001 — sem main (testes), não há cache
        pass


def _historico(db, pop_id: str, versao: int, operacao: str, antes, depois) -> str:
    # `versao` ordena o histórico: duas escritas no mesmo instante empatam no `em`.
    hid = uuid.uuid4().hex[:20]
    db.collection(HISTORICO).document(hid).set({
        "pop_id": pop_id, "versao": versao, "operacao": operacao, "antes": antes, "depois": depois,
        "autor": AUTOR, "em": _agora(),
    })
    return hid


def _achar(db, pop_id: str):
    """(ref, dados, ativo) do POP nas duas coleções, ou (None, None, None)."""
    for colecao, ativo in ((ATIVOS, True), (INATIVOS, False)):
        snap = db.collection(colecao).document(pop_id).get()
        if snap.exists:
            return snap.reference, snap.to_dict() or {}, ativo
    return None, None, None


def criar(db, args: dict) -> dict:
    titulo, instrucao = _texto(args, "titulo"), _texto(args, "instrucao_sistema")
    faltam = [c for c, v in (("titulo", titulo), ("instrucao_sistema", instrucao)) if not v]
    if faltam:
        return {"erro": f"Campo obrigatório ausente: {', '.join(faltam)}."}
    origem = _texto(args, "origem") or "sempre_ativo"
    if origem not in ORIGENS:
        return {"erro": f"origem deve ser 'sempre_ativo' ou 'gatilhos', não {origem!r}."}
    gatilhos = [g for g in (str(x or "").strip().lower() for x in args.get("gatilhos") or []) if g]
    if origem == "gatilhos" and not gatilhos:
        return {"erro": "Com origem 'gatilhos', informe ao menos um gatilho em `gatilhos`."}

    pop_id = uuid.uuid4().hex[:20]
    dados = {
        "titulo": titulo, "instrucao_sistema": instrucao,
        # A tela faz `pop.gatilhos.join`: o campo precisa existir, mesmo vazio.
        "gatilhos": gatilhos, "sempre_ativo": origem == "sempre_ativo",
        "autor": AUTOR, "origem": AUTOR, "criado_em": _agora(), "versao": 1,
        # `obter_estado_atual` mostra só os 5 sempre ativos mais recentes por
        # `atualizado_em`/`updated_at`: sem o campo, o POP novo ficaria de fora.
        "atualizado_em": _agora(),
    }
    db.collection(ATIVOS).document(pop_id).set(dados)
    _historico(db, pop_id, 1, "criar", None, dados)
    _limpar_cache()
    return {"status": "criado", "id": pop_id, "titulo": titulo, "origem": origem}


def editar(db, args: dict) -> dict:
    pop_id = _texto(args, "id")
    if not pop_id:
        return {"erro": "Campo obrigatório ausente: id."}
    mudancas = {c: _texto(args, c) for c in ("titulo", "instrucao_sistema") if _texto(args, c)}
    if not mudancas:
        return {"erro": "Informe titulo e/ou instrucao_sistema para editar."}
    ref, dados, ativo = _achar(db, pop_id)
    if ref is None:
        return {"erro": f"POP '{pop_id}' não encontrado."}

    antes = {c: dados.get(c) for c in mudancas}
    versao = int(dados.get("versao") or 1) + 1
    ref.update({**mudancas, "versao": versao, "editado_em": _agora(), "atualizado_em": _agora(),
                "editado_por": AUTOR})
    hid = _historico(db, pop_id, versao, "editar", antes, mudancas)
    _limpar_cache()
    return {"status": "editado", "id": pop_id, "ativo": ativo, "anterior": antes, "historico_id": hid,
            "como_desfazer": "editar_pop com os valores de `anterior`"}


def desativar(db, args: dict) -> dict:
    pop_id = _texto(args, "id")
    if not pop_id:
        return {"erro": "Campo obrigatório ausente: id."}
    reativar = args.get("reativar") is True
    origem, destino = (INATIVOS, ATIVOS) if reativar else (ATIVOS, INATIVOS)
    snap = db.collection(origem).document(pop_id).get()
    if not snap.exists:
        _, _, ativo = _achar(db, pop_id)
        if ativo is None:
            return {"erro": f"POP '{pop_id}' não encontrado."}
        return {"status": "sem_mudanca", "id": pop_id, "ativo": ativo}

    dados = snap.to_dict() or {}
    dados["reativado_em" if reativar else "desativado_em"] = dados["atualizado_em"] = _agora()
    dados["versao"] = int(dados.get("versao") or 1) + 1
    # Grava o destino antes de tirar da origem: uma falha no meio deixa o POP
    # nas duas coleções (repetir resolve), nunca em nenhuma.
    db.collection(destino).document(pop_id).set(dados)
    snap.reference.delete()
    _historico(db, pop_id, dados["versao"], "reativar" if reativar else "desativar", None, None)
    _limpar_cache()
    return {"status": "reativado" if reativar else "desativado", "id": pop_id,
            "titulo": dados.get("titulo"), "ativo": reativar}


def listar(db, args: dict) -> dict:
    filtro = _texto(args, "filtro") or "todos"
    if filtro not in ("ativos", "inativos", "todos"):
        return {"erro": "filtro deve ser 'ativos', 'inativos' ou 'todos'."}
    pop_id = _texto(args, "id")
    if pop_id:
        ref, dados, ativo = _achar(db, pop_id)
        if ref is None:
            return {"erro": f"POP '{pop_id}' não encontrado."}
        historico = sorted(
            (s.to_dict() for s in db.collection(HISTORICO).where("pop_id", "==", pop_id).stream()),
            key=lambda h: h.get("versao") or 0)
        return {"pop": {"id": pop_id, "ativo": ativo, **dados}, "historico": historico}

    pops = []
    for colecao, ativo in ((ATIVOS, True), (INATIVOS, False)):
        if filtro != "todos" and ativo != (filtro == "ativos"):
            continue
        for s in db.collection(colecao).stream():
            d = s.to_dict() or {}
            pops.append({"id": s.id, "titulo": d.get("titulo"), "instrucao_sistema": d.get("instrucao_sistema"),
                         "sempre_ativo": d.get("sempre_ativo") is True, "gatilhos": d.get("gatilhos") or [],
                         "ativo": ativo, "autor": d.get("autor") or d.get("origem")})
    return {"filtro": filtro, "total": len(pops), "pops": pops}
