"""Projeto de vídeo: validação do roteiro, criação, máquina de estados e status.

Firestore:
    video_projetos/{id}              — projeto (status, formato, modo, bíblia, custos...)
    video_projetos/{id}/cenas/{NN}   — narração, descrição visual, duração do clipe
    video_projetos/{id}/keyframes/{k}, .../clipes/{NN_vV} — Fases 2 e 3

Toda mudança de estado é transacional: a transação relê o status ATUAL e só
escreve se a transição for válida, no mesmo padrão de `mcp_jobs._reivindicar_job`.
Sem suporte a transação no backend não há fallback para escrita desprotegida.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from firebase_admin import firestore

from video import estimativa

COLECAO = "video_projetos"

ROTEIRO = "roteiro"
PREVIA_GERANDO = "previa_gerando"
AGUARDANDO_STORYBOARD = "aguardando_storyboard"
RENDERIZANDO = "renderizando"
MONTANDO = "montando"
CONCLUIDO = "concluido"
ERRO = "erro"
CANCELADO = "cancelado"

# Transições de avanço. Além delas, qualquer estado não final pode ir para
# `erro` ou `cancelado` (ver `transicao_valida`).
TRANSICOES: dict[str, set[str]] = {
    ROTEIRO: {PREVIA_GERANDO},
    PREVIA_GERANDO: {AGUARDANDO_STORYBOARD},
    # Ajuste no storyboard volta a gerar só o que mudou.
    AGUARDANDO_STORYBOARD: {PREVIA_GERANDO, RENDERIZANDO},
    RENDERIZANDO: {MONTANDO},
    MONTANDO: {CONCLUIDO},
    # `video_refazer_cena` reabre um vídeo pronto.
    CONCLUIDO: {RENDERIZANDO},
    # Retomar depois de uma falha: o worker pula o que já está `done`.
    ERRO: {PREVIA_GERANDO, RENDERIZANDO, MONTANDO},
    CANCELADO: set(),
}
FINAIS = {CONCLUIDO, CANCELADO}

FORMATOS = {"16:9", "9:16"}
MODOS = {"padrao", "final"}
DURACAO_MIN_S = 15
DURACAO_MAX_S = 120
MAX_CENAS = 30
LEASE_EXECUCAO = timedelta(minutes=15)


class ErroVideo(Exception):
    """Base das falhas do Hermes Vídeo. Não herda de ValueError de propósito: o
    Firestore levanta ValueError quando as retentativas de uma transação se
    esgotam, e um `except ValueError` confundiria disputa com transição inválida."""


class TransicaoInvalida(ErroVideo):
    pass


class ProjetoNaoEncontrado(ErroVideo):
    pass


class SemSuporteTransacao(ErroVideo):
    pass


def transicao_valida(de: str, para: str) -> bool:
    if para in (ERRO, CANCELADO):
        return de not in FINAIS and de != para
    return para in TRANSICOES.get(de, set())


# --- roteiro --------------------------------------------------------------------------

def _texto(valor) -> str:
    return str(valor or "").strip()


def _booleano(valor) -> bool:
    """`bool("false")` é True; aceita só o que claramente significa sim."""
    if isinstance(valor, bool):
        return valor
    return str(valor or "").strip().lower() in {"true", "1", "sim", "yes"}


def id_projeto_valido(projeto_id: str) -> bool:
    # Barra no id faz o Firestore descer para uma subcoleção:
    # document("OUTRO/cenas/01") vira video_projetos/OUTRO/cenas/01.
    return bool(projeto_id) and "/" not in projeto_id


def validar_roteiro(dados: dict, precos: dict | None = None) -> tuple[dict | None, list[str], list[str]]:
    """Normaliza o roteiro vindo do Claude. Devolve (roteiro, erros, avisos).

    Com erro, `roteiro` é `None` e nada deve ser gravado. A duração de cada clipe
    aqui é PROVISÓRIA (ritmo de ~2,0 palavras/s); a prévia (Fase 2) mede o áudio
    real e recalcula.
    """
    precos = precos or estimativa.PRECOS_PADRAO
    erros: list[str] = []
    avisos: list[str] = []
    dados = dados if isinstance(dados, dict) else {}

    titulo = _texto(dados.get("titulo"))
    if not titulo:
        erros.append("titulo é obrigatório.")
    formato = _texto(dados.get("formato")) or "16:9"
    if formato not in FORMATOS:
        erros.append(f"formato deve ser 16:9 ou 9:16 (veio {formato!r}).")
    modo = _texto(dados.get("modo")) or "padrao"
    if modo not in MODOS:
        erros.append(f"modo deve ser 'padrao' ou 'final' (veio {modo!r}).")

    biblia_in = dados.get("biblia") if isinstance(dados.get("biblia"), dict) else {}
    # O MCP só valida o tipo dos campos de primeiro nível: `personagens` pode chegar
    # como texto solto, e iterar uma string viraria uma lista de letras.
    personagens_in = biblia_in.get("personagens") or []
    if isinstance(personagens_in, str):
        personagens_in = [personagens_in]
    biblia = {
        "estilo": _texto(biblia_in.get("estilo")),
        "paleta": _texto(biblia_in.get("paleta")),
        "personagens": [_texto(p) for p in personagens_in if _texto(p)] if isinstance(personagens_in, list) else [],
        "evitar": _texto(biblia_in.get("evitar")),
    }
    if not biblia["estilo"]:
        erros.append("biblia.estilo é obrigatório: é o que mantém as cenas com a mesma cara.")

    voz_in = dados.get("voz") if isinstance(dados.get("voz"), dict) else {}
    voz = {"nome": _texto(voz_in.get("nome")) or "Kore", "estilo": _texto(voz_in.get("estilo")) or "neutro e claro"}
    musica = _texto(dados.get("musica")) or "nenhuma"
    legenda = _booleano(dados.get("legenda"))

    cenas_in = dados.get("cenas") if isinstance(dados.get("cenas"), list) else []
    if not cenas_in:
        erros.append("cenas é obrigatório (lista com ao menos uma cena).")
    if len(cenas_in) > MAX_CENAS:
        erros.append(f"No máximo {MAX_CENAS} cenas (vieram {len(cenas_in)}).")

    cenas = []
    for i, c in enumerate(cenas_in[:MAX_CENAS], start=1):
        c = c if isinstance(c, dict) else {}
        narracao = _texto(c.get("narracao"))
        visual = _texto(c.get("descricao_visual"))
        if not visual:
            erros.append(f"Cena {i}: descricao_visual é obrigatória.")
        fala_s = estimativa.duracao_fala_estimada(narracao)
        duracao = estimativa.duracao_clipe(fala_s)
        if duracao is None:
            erros.append(
                f"Cena {i}: narração de {estimativa.contar_palavras(narracao)} palavras (~{fala_s:.1f} s) "
                "não cabe num clipe de 8 s — divida em duas cenas."
            )
            duracao = 8
        cenas.append({
            "ordem": i,
            "narracao": narracao,
            "descricao_visual": visual,
            "prompt_video": _texto(c.get("prompt_video")),
            "duracao_s": duracao,
            "fala_estimada_s": round(fala_s, 1),
            "audio_gcs": None,
            "audio_duracao_s": None,
            "versao": 1,
        })

    total = sum(c["duracao_s"] for c in cenas)
    if cenas and total > DURACAO_MAX_S:
        erros.append(f"Duração total prevista de {total} s passa do limite da v1 ({DURACAO_MAX_S} s).")
    if cenas and total < DURACAO_MIN_S:
        avisos.append(f"Duração total prevista de {total} s é menor que o mínimo sugerido ({DURACAO_MIN_S} s).")
    if not narracao_em_alguma(cenas):
        avisos.append("Nenhuma cena tem narração: o vídeo sai sem voz.")

    if erros:
        return None, erros, avisos
    roteiro = {
        "titulo": titulo,
        "formato": formato,
        "resolucao": "720p",
        "modo": modo,
        "modelo_video": estimativa.modelo_do_modo(modo, precos),
        "biblia": biblia,
        "voz": voz,
        "musica": musica,
        "legenda": legenda,
        "acao_id": _texto(dados.get("acao_id")) or None,
        "cenas": cenas,
    }
    return roteiro, erros, avisos


def narracao_em_alguma(cenas: list[dict]) -> bool:
    return any(c["narracao"] for c in cenas)


def id_cena(ordem: int) -> str:
    return f"{int(ordem):02d}"


# --- criação --------------------------------------------------------------------------

def criar_projeto(db, uid: str | None, dados: dict, precos: dict | None = None) -> dict:
    """Valida e grava projeto + cenas num único batch. Custo zero (nenhuma chamada paga)."""
    if not _texto(uid):
        # Projeto sem dono seria legível por qualquer um em `obter_status`.
        return {"status": "erro", "erro": "Usuário não identificado; projeto não criado."}
    precos = precos or estimativa.carregar_precos(db)
    roteiro, erros, avisos = validar_roteiro(dados, precos)
    if erros:
        return {"status": "invalido", "erros": erros, "avisos": avisos}

    est = estimativa.estimar([c["duracao_s"] for c in roteiro["cenas"]], modo=roteiro["modo"],
                             resolucao=roteiro["resolucao"], precos=precos)
    # Com a estimativa acima do teto, o worker pararia no meio de uma renderização
    # que o usuário aprovou pelo valor maior.
    if est["custo_estimado_usd"] > float(precos["teto_projeto_usd"]):
        erros.append(
            f"Estimativa de US$ {est['custo_estimado_usd']:.2f} passa do teto por projeto "
            f"(US$ {float(precos['teto_projeto_usd']):.2f}). Encurte o vídeo"
            + (" ou use o modo padrão." if roteiro["modo"] == "final" else ".")
        )
    if est["custo_previa_usd"] > float(precos["teto_previa_usd"]):
        erros.append(
            f"A prévia custaria US$ {est['custo_previa_usd']:.2f}, acima do teto por prévia "
            f"(US$ {float(precos['teto_previa_usd']):.2f}). Use menos cenas."
        )
    if erros:
        return {"status": "invalido", "erros": erros, "avisos": avisos, "estimativa": est}
    if est["folga_teto_reduzida"]:
        avisos.append(
            f"O teto do projeto (US$ {est['teto_projeto_usd']:.2f}) deixa menos que a folga usual de "
            f"{float(precos['fator_teto_projeto']):.1f}× para refazer cenas."
        )
    ref = db.collection(COLECAO).document()
    projeto = {k: v for k, v in roteiro.items() if k != "cenas"}
    projeto.update({
        "uid": uid,
        "status": ROTEIRO,
        "estimativa": est,
        "custo_estimado_usd": est["custo_estimado_usd"],
        "orcamento_usd": est["teto_projeto_usd"],
        "custo_real_usd": 0.0,
        "folha_contato_drive_id": None,
        "video_drive_id": None,
        "video_link": None,
        "worker_execucao": None,
        "criado_em": firestore.SERVER_TIMESTAMP,
        "atualizado_em": firestore.SERVER_TIMESTAMP,
    })
    batch = db.batch()
    batch.set(ref, projeto)
    for cena in roteiro["cenas"]:
        batch.set(ref.collection("cenas").document(id_cena(cena["ordem"])), cena)
    batch.commit()
    return {
        "status": "ok",
        "projeto_id": ref.id,
        "estado": ROTEIRO,
        "titulo": roteiro["titulo"],
        "cenas": [{"ordem": c["ordem"], "duracao_s": c["duracao_s"], "fala_estimada_s": c["fala_estimada_s"]}
                  for c in roteiro["cenas"]],
        "estimativa": est,
        "avisos": avisos,
    }


# --- estado ---------------------------------------------------------------------------

def _transacional(db):
    if not hasattr(db, "transaction"):
        raise SemSuporteTransacao("Backend Firestore sem transação; mudança de estado recusada.")
    return db.transaction()


def transicionar(db, projeto_id: str, para: str, *, de: set[str] | None = None,
                 campos: dict | None = None) -> dict:
    """Muda o status numa transação que relê o estado atual.

    `de`, quando informado, restringe ainda mais os estados de origem aceitos
    (ex.: o worker só avança de `renderizando`). Devolve o projeto como estava
    ANTES da transição; levanta `TransicaoInvalida`/`ProjetoNaoEncontrado`.
    """
    ref = db.collection(COLECAO).document(projeto_id)
    transaction = _transacional(db)

    @firestore.transactional
    def _txn(tx):
        snap = ref.get(transaction=tx)
        if not snap.exists:
            raise ProjetoNaoEncontrado(projeto_id)
        atual = snap.to_dict() or {}
        estado = atual.get("status")
        if (de is not None and estado not in de) or not transicao_valida(estado, para):
            raise TransicaoInvalida(f"Projeto {projeto_id}: {estado!r} → {para!r} não é permitido.")
        tx.update(ref, {**(campos or {}), "status": para, "atualizado_em": firestore.SERVER_TIMESTAMP})
        return atual

    return _txn(transaction)


def reivindicar_execucao(db, projeto_id: str, execucao_id: str, *, agora: datetime | None = None) -> bool:
    """Garante uma única execução do worker por projeto.

    Reivindica se não há execução registrada, se ela é a mesma (retomada da
    própria execução) ou se o lease expirou (worker derrubado no meio).

    O lease (15 min) é menor que uma renderização longa (30 cenas × ~55 s): o
    worker precisa chamar `renovar_execucao` a cada clipe. Sem isso, outra
    execução assume o projeto e paga de novo pelos clipes em andamento.
    """
    agora = agora or datetime.now(timezone.utc)
    ref = db.collection(COLECAO).document(projeto_id)
    transaction = _transacional(db)

    @firestore.transactional
    def _txn(tx):
        snap = ref.get(transaction=tx)
        if not snap.exists:
            raise ProjetoNaoEncontrado(projeto_id)
        atual = (snap.to_dict() or {}).get("worker_execucao") or {}
        expira = atual.get("expira_em")
        if atual.get("id") and atual.get("id") != execucao_id and isinstance(expira, datetime) and expira > agora:
            return False
        tx.update(ref, {"worker_execucao": {"id": execucao_id, "desde": agora, "expira_em": agora + LEASE_EXECUCAO}})
        return True

    return _txn(transaction)


def renovar_execucao(db, projeto_id: str, execucao_id: str, *, agora: datetime | None = None) -> bool:
    """Estende o lease da execução que já é dona do projeto. `False` = perdeu o
    projeto para outra execução (o lease tinha vencido): o worker deve parar
    antes de enviar o próximo clipe."""
    agora = agora or datetime.now(timezone.utc)
    ref = db.collection(COLECAO).document(projeto_id)
    transaction = _transacional(db)

    @firestore.transactional
    def _txn(tx):
        snap = ref.get(transaction=tx)
        atual = ((snap.to_dict() or {}).get("worker_execucao") or {}) if snap.exists else {}
        if atual.get("id") != execucao_id:
            return False
        tx.update(ref, {"worker_execucao": {**atual, "expira_em": agora + LEASE_EXECUCAO}})
        return True

    return _txn(transaction)


def liberar_execucao(db, projeto_id: str, execucao_id: str) -> bool:
    ref = db.collection(COLECAO).document(projeto_id)
    transaction = _transacional(db)

    @firestore.transactional
    def _txn(tx):
        snap = ref.get(transaction=tx)
        atual = ((snap.to_dict() or {}).get("worker_execucao") or {}) if snap.exists else {}
        if atual.get("id") != execucao_id:
            return False
        tx.update(ref, {"worker_execucao": None})
        return True

    return _txn(transaction)


# --- status ---------------------------------------------------------------------------

def _iso(valor):
    return valor.isoformat() if isinstance(valor, datetime) else valor


def obter_status(db, projeto_id: str, uid: str | None) -> dict:
    """Resumo do projeto para o Claude: estado, cenas, progresso dos clipes, custos e links."""
    projeto_id = _texto(projeto_id)
    if not projeto_id:
        return {"status": "erro", "erro": "projeto_id é obrigatório."}
    nao_encontrado = {"status": "nao_encontrado", "erro": f"Projeto {projeto_id!r} não encontrado."}
    if not id_projeto_valido(projeto_id) or not _texto(uid):
        return nao_encontrado
    ref = db.collection(COLECAO).document(projeto_id)
    snap = ref.get()
    dados = (snap.to_dict() or {}) if snap.exists else {}
    # Falha fechada: projeto de outro usuário (ou sem dono) responde igual a
    # inexistente, sem confirmar que o id existe.
    if not snap.exists or dados.get("uid") != uid:
        return nao_encontrado

    cenas = sorted((c.to_dict() or {} for c in ref.collection("cenas").stream()), key=lambda c: c.get("ordem", 0))
    clipes = [c.to_dict() or {} for c in ref.collection("clipes").stream()]
    por_status: dict[str, int] = {}
    for c in clipes:
        por_status[c.get("status") or "pendente"] = por_status.get(c.get("status") or "pendente", 0) + 1

    return {
        "status": "ok",
        "projeto_id": projeto_id,
        "estado": dados.get("status"),
        "titulo": dados.get("titulo"),
        "formato": dados.get("formato"),
        "modo": dados.get("modo"),
        "modelo_video": dados.get("modelo_video"),
        "acao_id": dados.get("acao_id"),
        "cenas": [{"ordem": c.get("ordem"), "duracao_s": c.get("duracao_s"), "versao": c.get("versao"),
                   "narracao": c.get("narracao")} for c in cenas],
        "clipes": {"total": len(clipes), "por_status": por_status},
        "custo_estimado_usd": dados.get("custo_estimado_usd"),
        "custo_real_usd": dados.get("custo_real_usd"),
        "orcamento_usd": dados.get("orcamento_usd"),
        "tempo_renderizacao_min": (dados.get("estimativa") or {}).get("tempo_renderizacao_min"),
        "video_link": dados.get("video_link"),
        # Não se chama `erro`: numa resposta de sucesso, o canal MCP leria a chave como falha.
        "falha": dados.get("erro"),
        "atualizado_em": _iso(dados.get("atualizado_em")),
    }
