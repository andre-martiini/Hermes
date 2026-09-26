"""Comandos pagos e de controle do Hermes Vídeo (Fase 4): renderizar, refazer cena, cancelar.

`video_renderizar` e `video_refazer_cena` estão no piso de confirmação obrigatória
(autonomy/policy.py): a prévia (`avaliar_*`) calcula o custo e confere tudo SEM
gastar nada; o "sim" executa (`renderizar`/`refazer_cena`), que confere tudo de
novo e só segue se o projeto ainda é o que o usuário aprovou (`impressao`).

Travas conferidas antes de gastar (revisão adversária da Fase 4, 26/09/2026):
- projeto do usuário, no estado certo, com a prévia publicada e aprovável
  (`renderizavel` só é True depois de a folha de contato e o MP3 saírem);
- o "sim" corresponde à prévia mostrada: storyboard, durações, refações e custo
  iguais — mudou nos minutos entre a prévia e o sim, pede nova confirmação;
- custo dos clipes QUE FALTAM (pela assinatura) dentro do orçamento do projeto;
- teto mensal: gasto do mês + custo máximo das renderizações em andamento +
  custo máximo desta não passa de `teto_mensal_usd`.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from firebase_admin import firestore

from video import estimativa
from video import projeto as vp

TZ = ZoneInfo("America/Sao_Paulo")
ESTADOS_PARA_RENDERIZAR = {vp.AGUARDANDO_STORYBOARD, vp.ERRO}
ESTADOS_EM_ANDAMENTO = {vp.RENDERIZANDO, vp.MONTANDO}
# Pedido de renderização sem worker ativo há mais que isto = worker morreu (OOM,
# recusa, disparo perdido): `video_renderizar` pode disparar de novo sem transição.
WORKER_PARADO_APOS = timedelta(minutes=15)


class Recusado(vp.ErroVideo):
    pass


def _agora(agora):
    return agora or datetime.now(timezone.utc)


def _impressao(valores) -> str:
    return hashlib.sha1(json.dumps(valores, ensure_ascii=False, default=str).encode()).hexdigest()[:12]


def gasto_do_mes(db, agora: datetime | None = None) -> float:
    """Soma do uso diário de vídeo (`system_usage/video/daily`) do mês corrente, no fuso de Brasília."""
    hoje = _agora(agora).astimezone(TZ).date()
    total = 0.0
    for dia in range(1, hoje.day + 1):
        snap = (db.collection("system_usage").document("video").collection("daily")
                .document(hoje.replace(day=dia).isoformat()).get())
        if snap.exists:
            total += float((snap.to_dict() or {}).get("estimated_usd") or 0)
    return round(total, 4)


def reservado_em_andamento(db, uid: str, exceto: str | None = None) -> float:
    """Quanto as renderizações ainda rodando podem gastar (o uso só é gravado ao fim de cada clipe)."""
    total = 0.0
    for snap in db.collection(vp.COLECAO).where("uid", "==", uid).stream():
        p = snap.to_dict() or {}
        if snap.id != exceto and p.get("status") in ESTADOS_EM_ANDAMENTO:
            total += max(float(p.get("orcamento_usd") or 0) - float(p.get("custo_real_usd") or 0), 0.0)
    return round(total, 4)


def _carregar(db, uid: str | None, projeto_id: str):
    projeto_id = (projeto_id or "").strip()
    if not vp.id_projeto_valido(projeto_id) or not (uid or "").strip():
        raise Recusado(f"Projeto {projeto_id!r} não encontrado.")
    ref = db.collection(vp.COLECAO).document(projeto_id)
    snap = ref.get()
    if not snap.exists or (snap.to_dict() or {}).get("uid") != uid:
        raise Recusado(f"Projeto {projeto_id!r} não encontrado.")
    cenas = sorted((c.to_dict() or {} for c in ref.collection("cenas").stream()), key=lambda c: c["ordem"])
    quadros = {int(q.get("indice")): q for q in (s.to_dict() or {} for s in ref.collection("keyframes").stream())}
    return ref, snap.to_dict() or {}, cenas, quadros


def _teto_mensal(db, uid, projeto_id, precos, custo_max: float, agora) -> dict:
    gasto = gasto_do_mes(db, agora)
    reservado = reservado_em_andamento(db, uid, exceto=projeto_id)
    teto = float(precos["teto_mensal_usd"])
    if gasto + reservado + custo_max > teto + 1e-9:
        raise Recusado(f"Teto mensal de vídeo: o mês já gastou US$ {gasto:.2f}, renderizações em andamento podem "
                       f"gastar mais US$ {reservado:.2f}, e esta pode custar até US$ {custo_max:.2f} — passaria "
                       f"de US$ {teto:.2f}.")
    return {"gasto_do_mes_usd": round(gasto, 2), "reservado_em_andamento_usd": round(reservado, 2),
            "teto_mensal_usd": teto}


def _preco_segundo(projeto, precos) -> float:
    modelo = projeto.get("modelo_video") or estimativa.modelo_do_modo(projeto.get("modo") or "padrao", precos)
    return estimativa.preco_segundo(modelo, projeto.get("resolucao") or "720p", precos)


def _worker_parado(projeto, agora) -> bool:
    lease = (projeto.get("worker_execucao") or {}).get("expira_em")
    ativo = isinstance(lease, datetime) and lease > agora
    pedido = projeto.get("render_pedido_em")
    antigo = not isinstance(pedido, datetime) or agora - pedido > WORKER_PARADO_APOS
    return not ativo and antigo


# --- renderizar -----------------------------------------------------------------------

def avaliar_renderizacao(db, uid, projeto_id, *, precos=None, agora=None) -> dict:
    """Prévia da confirmação: tudo conferido, nada gasto. Levanta `Recusado` com o motivo."""
    from video.renderizacao import clipes_pendentes, pendencias

    agora = _agora(agora)
    ref, projeto, cenas, quadros = _carregar(db, uid, projeto_id)
    precos = precos or estimativa.carregar_precos(db)
    estado = projeto.get("status")
    retomada = estado in ESTADOS_EM_ANDAMENTO
    if retomada and not _worker_parado(projeto, agora):
        raise Recusado(f"O vídeo já está sendo renderizado ({estado}); acompanhe com video_status.")
    if not retomada and estado not in ESTADOS_PARA_RENDERIZAR:
        raise Recusado(f"Renderizar só a partir do storyboard aprovado (estado atual: {estado}).")
    if projeto.get("renderizavel") is not True or not projeto.get("folha_contato_link"):
        raise Recusado("Não há storyboard aprovável: a última prévia não terminou (ou marcou pendências). "
                       "Gere a prévia de novo e mostre a folha de contato antes de renderizar.")
    faltas = pendencias(cenas, quadros)
    if faltas:
        raise Recusado("A prévia não está pronta: " + "; ".join(faltas) + ". Ajuste ou gere a prévia de novo.")
    preco_s = _preco_segundo(projeto, precos)
    segundos = sum(int(c["duracao_s"]) for c in cenas)
    if segundos * preco_s * float(precos["margem_retrabalho"]) > float(precos["teto_projeto_usd"]):
        raise Recusado(f"Os clipes (~US$ {segundos * preco_s:.2f} + margem) passam do teto por projeto "
                       f"(US$ {float(precos['teto_projeto_usd']):.2f}). Encurte o vídeo.")
    orcamento = float(projeto.get("orcamento_usd") or 0)
    gasto = float(projeto.get("custo_real_usd") or 0)
    custo_max = max(orcamento - gasto, 0.0)
    faltam = clipes_pendentes(ref, projeto, cenas, quadros)
    restante = sum(int(c["duracao_s"]) for c in faltam) * preco_s
    if restante > custo_max + 1e-9:
        raise Recusado(f"O orçamento que sobra (US$ {custo_max:.2f} de US$ {orcamento:.2f}) não cobre os clipes "
                       f"que faltam (US$ {restante:.2f}): o worker pararia no meio.")
    mes = _teto_mensal(db, uid, projeto_id, precos, custo_max, agora)
    return {
        "status": "confirmation_required",
        "projeto_id": projeto_id,
        "titulo": projeto.get("titulo"),
        "retomada": retomada,
        "modelo_video": projeto.get("modelo_video"),
        "cenas": len(cenas),
        "segundos_video": segundos,
        "clipes_a_gerar": [c["ordem"] for c in faltam],
        "custo_clipes_a_gerar_usd": round(restante, 2),
        "custo_ja_gasto_usd": round(gasto, 2),
        "orcamento_usd": round(orcamento, 2),
        "custo_maximo_desta_renderizacao_usd": round(custo_max, 2),
        "tempo_estimado_min": max(len(faltam), 1),
        "impressao": _impressao([projeto_id, estado, projeto.get("previa_versao"), projeto.get("modelo_video"),
                                 [(c["ordem"], c.get("duracao_s"), c.get("versao"), c.get("refacao")) for c in cenas],
                                 round(custo_max, 2)]),
        **mes,
    }


def _conferir_aprovado(previa: dict, aprovado: dict | None):
    if aprovado and aprovado.get("impressao") and aprovado["impressao"] != previa["impressao"]:
        raise Recusado("O projeto mudou desde a prévia que o usuário aprovou (storyboard, durações ou custo). "
                       "Peça uma nova confirmação com a prévia atual.")


def renderizar(db, uid, projeto_id, disparar, *, aprovado: dict | None = None, precos=None, agora=None) -> dict:
    """Executa o "sim": confere de novo, leva a `renderizando` (ou retoma um worker parado) e dispara."""
    from video.renderizacao import VERSAO_WORKER

    try:
        previa = avaliar_renderizacao(db, uid, projeto_id, precos=precos, agora=agora)
        _conferir_aprovado(previa, aprovado)
    except Recusado as exc:
        return {"status": "recusado", "erro": str(exc)}
    campos = {"erro": None, "render_pedido_em": _agora(agora), "worker_min_versao": VERSAO_WORKER}
    try:
        if previa["retomada"]:
            db.collection(vp.COLECAO).document(projeto_id).update(campos)
        else:
            vp.transicionar(db, projeto_id, vp.RENDERIZANDO, de=ESTADOS_PARA_RENDERIZAR, campos={
                **campos, "video_drive_id": None, "video_link": None, "video_gcs": None, "video_anexado": False})
    except vp.ErroVideo as exc:
        return {"status": "recusado", "erro": str(exc)}
    return _disparar(db, projeto_id, disparar, previa["tempo_estimado_min"],
                     "Retomando a renderização" if previa["retomada"] else "Renderização iniciada",
                     previa["custo_maximo_desta_renderizacao_usd"])


def _disparar(db, projeto_id, disparar, minutos, titulo, custo_max) -> dict:
    try:
        execucao = disparar(projeto_id)
    except Exception as exc:  # noqa: BLE001
        if "timeout" in type(exc).__name__.lower() or "timed out" in str(exc).lower():
            # O Cloud Run pode ter aceitado: não afirmar que não começou.
            return {"status": "incerto", "projeto_id": projeto_id, "estado": vp.RENDERIZANDO,
                    "erro": f"Sem resposta do Cloud Run ({exc}): o worker pode ter iniciado. Confira com "
                            "video_status em alguns minutos; se continuar parado, video_renderizar retoma."}
        try:
            vp.transicionar(db, projeto_id, vp.ERRO, de=ESTADOS_EM_ANDAMENTO,
                            campos={"erro": f"worker não disparou: {exc}"[:500]})
        except vp.ErroVideo:
            pass
        return {"status": "erro", "erro": f"Não consegui iniciar o worker: {exc}"}
    db.collection(vp.COLECAO).document(projeto_id).update({"worker_disparo": execucao})
    return {"status": "ok", "projeto_id": projeto_id, "estado": vp.RENDERIZANDO, "execucao": execucao,
            "mensagem": f"{titulo}: o worker gera os clipes em sequência (~{minutos} min) e avisa no Telegram "
                        "quando o vídeo estiver no Drive. Acompanhe com video_status.",
            "custo_maximo_usd": custo_max}


# --- refazer cena ---------------------------------------------------------------------

def _ordem_valida(ordem):
    if isinstance(ordem, bool):
        return None
    try:
        return int(ordem)
    except (TypeError, ValueError):
        return None


def avaliar_refacao(db, uid, projeto_id, ordem, *, refazer_seguintes=False, instrucao=None, precos=None,
                    agora=None) -> dict:
    ref, projeto, cenas, quadros = _carregar(db, uid, projeto_id)
    precos = precos or estimativa.carregar_precos(db)
    if projeto.get("status") != vp.CONCLUIDO:
        raise Recusado(f"Refazer cena só com o vídeo concluído (estado atual: {projeto.get('status')}); para "
                       "retomar uma renderização que parou, use video_renderizar.")
    n = _ordem_valida(ordem)
    if n is None or not any(c["ordem"] == n for c in cenas):
        raise Recusado(f"Cena {ordem!r} não existe (o projeto tem {len(cenas)}).")
    alvo = [c for c in cenas if c["ordem"] == n or (refazer_seguintes and c["ordem"] > n)]
    custo = round(sum(int(c["duracao_s"]) for c in alvo) * _preco_segundo(projeto, precos), 2)
    gasto, orcamento = float(projeto.get("custo_real_usd") or 0), float(projeto.get("orcamento_usd") or 0)
    if gasto + custo > orcamento + 1e-9:
        raise Recusado(f"Orçamento do projeto: já gastou US$ {gasto:.2f} de US$ {orcamento:.2f}; refazer custaria "
                       f"US$ {custo:.2f}.")
    mes = _teto_mensal(db, uid, projeto_id, precos, custo, agora)
    instrucao = (instrucao or "").strip() or None
    cenas_refeitas = [c["ordem"] for c in alvo]
    return {
        "status": "confirmation_required",
        "projeto_id": projeto_id,
        "titulo": projeto.get("titulo"),
        "cenas_refeitas": cenas_refeitas,
        "instrucao": instrucao,
        "custo_usd": custo,
        "custo_ja_gasto_usd": round(gasto, 2),
        "orcamento_usd": round(orcamento, 2),
        "aviso": None if refazer_seguintes or n == len(cenas) else
        "Só esta cena é refeita: a seguinte continua começando onde a versão antiga terminava, e pode sobrar "
        "um salto pequeno nessa emenda. Com refazer_seguintes=true a emenda fica perfeita (custa as seguintes também).",
        "impressao": _impressao([projeto_id, projeto.get("video_link"), cenas_refeitas, instrucao, custo,
                                 [(c["ordem"], c.get("refacao")) for c in alvo]]),
        **mes,
    }


def refazer_cena(db, uid, projeto_id, ordem, disparar, *, refazer_seguintes=False, instrucao=None,
                 aprovado: dict | None = None, precos=None, agora=None) -> dict:
    from video.renderizacao import VERSAO_WORKER

    try:
        previa = avaliar_refacao(db, uid, projeto_id, ordem, refazer_seguintes=refazer_seguintes,
                                 instrucao=instrucao, precos=precos, agora=agora)
        _conferir_aprovado(previa, aprovado)
    except Recusado as exc:
        return {"status": "recusado", "erro": str(exc)}
    ref = db.collection(vp.COLECAO).document(projeto_id)
    n = _ordem_valida(ordem)
    transaction = vp._transacional(db)

    @firestore.transactional
    def _txn(tx):
        # Estado, refações e link anterior juntos: um "sim" repetido não passa da checagem
        # de estado, e nunca sobra projeto em `renderizando` sem as cenas marcadas.
        atual = ref.get(transaction=tx).to_dict() or {}
        if atual.get("status") != vp.CONCLUIDO:
            raise Recusado(f"O vídeo não está mais concluído ({atual.get('status')}).")
        for m in previa["cenas_refeitas"]:
            campos = {"refacao": firestore.Increment(1)}
            if m == n:
                campos["instrucao_video"] = previa["instrucao"]
            tx.update(ref.collection("cenas").document(vp.id_cena(m)), campos)
        tx.update(ref, {"status": vp.RENDERIZANDO, "erro": None, "video_link_anterior": atual.get("video_link"),
                        "video_drive_id": None, "video_link": None, "video_gcs": None, "video_anexado": False,
                        "render_pedido_em": _agora(agora), "worker_min_versao": VERSAO_WORKER,
                        "atualizado_em": firestore.SERVER_TIMESTAMP})

    try:
        _txn(transaction)
    except vp.ErroVideo as exc:
        return {"status": "recusado", "erro": str(exc)}
    return _disparar(db, projeto_id, disparar, len(previa["cenas_refeitas"]) + 1,
                     f"Refazendo a(s) cena(s) {previa['cenas_refeitas']}", previa["custo_usd"])


# --- cancelar -------------------------------------------------------------------------

def cancelar(db, uid, projeto_id, *, motivo: str | None = None) -> dict:
    try:
        ref, projeto, _, _ = _carregar(db, uid, projeto_id)
    except Recusado as exc:
        return {"status": "nao_encontrado", "erro": str(exc)}
    if projeto.get("status") == vp.CANCELADO:
        return {"status": "ok", "projeto_id": projeto_id, "estado": vp.CANCELADO,
                "mensagem": "Já estava cancelado."}
    try:
        vp.transicionar(db, projeto_id, vp.CANCELADO, campos={"cancelado_motivo": (motivo or "").strip() or None})
    except vp.ErroVideo as exc:
        return {"status": "recusado", "erro": str(exc), "estado": projeto.get("status")}
    rodando = projeto.get("status") in ESTADOS_EM_ANDAMENTO
    return {"status": "ok", "projeto_id": projeto_id, "estado": vp.CANCELADO,
            "custo_real_usd": round(float(projeto.get("custo_real_usd") or 0), 2),
            "mensagem": ("Cancelado. O worker para antes do próximo clipe; o clipe que já estiver no Veo ainda "
                         "pode ser cobrado." if rodando else "Cancelado.")}
