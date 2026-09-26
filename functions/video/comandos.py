"""Comandos pagos e de controle do Hermes Vídeo (Fase 4): renderizar, refazer cena, cancelar.

`video_renderizar` e `video_refazer_cena` estão no piso de confirmação obrigatória
(autonomy/policy.py): a prévia (`avaliar_*`) calcula o custo e confere tudo SEM
gastar nada; o "sim" do usuário executa (`renderizar`/`refazer_cena`), que
confere tudo de novo — o estado pode ter mudado nos minutos entre a prévia e o
sim — antes de disparar o worker.

Travas conferidas antes de gastar:
- projeto do usuário, no estado certo e pronto (prévia completa, nada a dividir);
- estimativa dentro do teto por projeto; custo máximo restante dentro do orçamento;
- gasto de vídeo do mês + custo máximo desta renderização dentro do teto mensal.
"""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from firebase_admin import firestore

from video import estimativa
from video import projeto as vp

TZ = ZoneInfo("America/Sao_Paulo")
ESTADOS_PARA_RENDERIZAR = {vp.AGUARDANDO_STORYBOARD, vp.ERRO}


class Recusado(vp.ErroVideo):
    pass


def _agora(agora):
    return agora or datetime.now(timezone.utc)


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


def _teto_mensal(db, precos, custo_max: float, agora) -> dict:
    gasto = gasto_do_mes(db, agora)
    teto = float(precos["teto_mensal_usd"])
    if gasto + custo_max > teto + 1e-9:
        raise Recusado(f"Teto mensal de vídeo: o mês já gastou US$ {gasto:.2f}; esta renderização pode custar até "
                       f"US$ {custo_max:.2f} e passaria de US$ {teto:.2f}.")
    return {"gasto_do_mes_usd": round(gasto, 2), "teto_mensal_usd": teto}


# --- renderizar -----------------------------------------------------------------------

def avaliar_renderizacao(db, uid, projeto_id, *, precos=None, agora=None) -> dict:
    """Prévia da confirmação: tudo conferido, nada gasto. Levanta `Recusado` com o motivo."""
    from video.renderizacao import pendencias

    ref, projeto, cenas, quadros = _carregar(db, uid, projeto_id)
    precos = precos or estimativa.carregar_precos(db)
    if projeto.get("status") not in ESTADOS_PARA_RENDERIZAR:
        raise Recusado(f"Renderizar só a partir do storyboard aprovado (estado atual: {projeto.get('status')}).")
    faltas = pendencias(cenas, quadros)
    if faltas or projeto.get("renderizavel") is False:
        raise Recusado("A prévia não está pronta: " + ("; ".join(faltas) or "renderizavel=false")
                       + ". Ajuste ou gere a prévia de novo.")
    est = estimativa.estimar([int(c["duracao_s"]) for c in cenas], modo=projeto.get("modo") or "padrao",
                             resolucao=projeto.get("resolucao") or "720p", precos=precos)
    if est["custo_estimado_usd"] > float(precos["teto_projeto_usd"]):
        raise Recusado(f"Estimativa de US$ {est['custo_estimado_usd']:.2f} acima do teto por projeto "
                       f"(US$ {float(precos['teto_projeto_usd']):.2f}). Encurte o vídeo.")
    orcamento = float(projeto.get("orcamento_usd") or 0)
    gasto = float(projeto.get("custo_real_usd") or 0)
    custo_max = max(orcamento - gasto, 0.0)
    # Clipes que faltam (numa retomada, os já renderizados não se pagam de novo).
    restante = max(est["custo_video_usd"] - float(projeto.get("custo_render_usd") or 0), 0.0)
    if restante > custo_max + 1e-9:
        raise Recusado(f"O orçamento que sobra (US$ {custo_max:.2f} de US$ {orcamento:.2f}) não cobre os clipes "
                       f"que faltam (~US$ {restante:.2f}): o worker pararia no meio. Encurte o vídeo ou gere a "
                       "prévia de novo para recalcular o orçamento.")
    mes = _teto_mensal(db, precos, custo_max, agora)
    return {
        "status": "confirmation_required",
        "projeto_id": projeto_id,
        "titulo": projeto.get("titulo"),
        "modelo_video": projeto.get("modelo_video"),
        "cenas": len(cenas),
        "segundos_video": est["segundos_video"],
        "custo_clipes_usd": est["custo_video_usd"],
        "custo_ja_gasto_usd": round(gasto, 2),
        "orcamento_usd": round(orcamento, 2),
        "custo_maximo_desta_renderizacao_usd": round(custo_max, 2),
        "tempo_estimado_min": est["tempo_renderizacao_min"],
        **mes,
    }


def renderizar(db, uid, projeto_id, disparar, *, precos=None, agora=None) -> dict:
    """Executa o "sim": confere de novo, leva a `renderizando` e dispara o worker."""
    try:
        previa = avaliar_renderizacao(db, uid, projeto_id, precos=precos, agora=agora)
    except Recusado as exc:
        return {"status": "recusado", "erro": str(exc)}
    try:
        vp.transicionar(db, projeto_id, vp.RENDERIZANDO, de=ESTADOS_PARA_RENDERIZAR, campos={
            "erro": None, "video_drive_id": None, "video_link": None, "video_gcs": None, "video_anexado": False,
            "render_pedido_em": _agora(agora)})
    except vp.ErroVideo as exc:
        return {"status": "recusado", "erro": str(exc)}
    return _disparar(db, projeto_id, disparar, previa, "Renderização iniciada")


def _disparar(db, projeto_id, disparar, previa, titulo) -> dict:
    try:
        execucao = disparar(projeto_id)
    except Exception as exc:  # noqa: BLE001 - sem worker não há gasto: devolve o projeto a `erro`
        try:
            vp.transicionar(db, projeto_id, vp.ERRO, de={vp.RENDERIZANDO},
                            campos={"erro": f"worker não disparou: {exc}"[:500]})
        except vp.ErroVideo:
            pass
        return {"status": "erro", "erro": f"Não consegui iniciar o worker: {exc}"}
    db.collection(vp.COLECAO).document(projeto_id).update({"worker_disparo": execucao})
    return {"status": "ok", "projeto_id": projeto_id, "estado": vp.RENDERIZANDO, "execucao": execucao,
            "mensagem": f"{titulo}: o worker gera os clipes em sequência (~{previa.get('tempo_estimado_min')} min) "
                        "e avisa no Telegram quando o vídeo estiver no Drive. Acompanhe com video_status.",
            "custo_maximo_usd": previa.get("custo_maximo_desta_renderizacao_usd")}


# --- refazer cena ---------------------------------------------------------------------

def _cenas_a_refazer(cenas, ordem, refazer_seguintes):
    return [c for c in cenas if c["ordem"] == ordem or (refazer_seguintes and c["ordem"] > ordem)]


def avaliar_refacao(db, uid, projeto_id, ordem, *, refazer_seguintes=False, instrucao=None, precos=None,
                    agora=None) -> dict:
    ref, projeto, cenas, quadros = _carregar(db, uid, projeto_id)
    precos = precos or estimativa.carregar_precos(db)
    if projeto.get("status") != vp.CONCLUIDO:
        raise Recusado(f"Refazer cena só com o vídeo concluído (estado atual: {projeto.get('status')}); para "
                       "retomar uma renderização que parou, use video_renderizar.")
    try:
        ordem = int(ordem)
    except (TypeError, ValueError):
        raise Recusado("Informe 'ordem' (número da cena).") from None
    if isinstance(ordem, bool) or not any(c["ordem"] == ordem for c in cenas):
        raise Recusado(f"Cena {ordem} não existe (o projeto tem {len(cenas)}).")
    alvo = _cenas_a_refazer(cenas, ordem, refazer_seguintes)
    preco_s = estimativa.preco_segundo(projeto.get("modelo_video"), projeto.get("resolucao") or "720p", precos)
    custo = round(sum(int(c["duracao_s"]) for c in alvo) * preco_s, 2)
    gasto, orcamento = float(projeto.get("custo_real_usd") or 0), float(projeto.get("orcamento_usd") or 0)
    if gasto + custo > orcamento + 1e-9:
        raise Recusado(f"Orçamento do projeto: já gastou US$ {gasto:.2f} de US$ {orcamento:.2f}; refazer custaria "
                       f"US$ {custo:.2f}.")
    mes = _teto_mensal(db, precos, custo, agora)
    return {
        "status": "confirmation_required",
        "projeto_id": projeto_id,
        "titulo": projeto.get("titulo"),
        "cenas_refeitas": [c["ordem"] for c in alvo],
        "instrucao": (instrucao or "").strip() or None,
        "custo_usd": custo,
        "custo_ja_gasto_usd": round(gasto, 2),
        "orcamento_usd": round(orcamento, 2),
        "aviso": None if refazer_seguintes or ordem == len(cenas) else
        "Só esta cena é refeita: a seguinte continua começando onde a versão antiga terminava, e pode sobrar "
        "um salto pequeno nessa emenda. Com refazer_seguintes=true a emenda fica perfeita (custa as seguintes também).",
        **mes,
    }


def refazer_cena(db, uid, projeto_id, ordem, disparar, *, refazer_seguintes=False, instrucao=None, precos=None,
                 agora=None) -> dict:
    try:
        previa = avaliar_refacao(db, uid, projeto_id, ordem, refazer_seguintes=refazer_seguintes,
                                 instrucao=instrucao, precos=precos, agora=agora)
    except Recusado as exc:
        return {"status": "recusado", "erro": str(exc)}
    ref = db.collection(vp.COLECAO).document(projeto_id)
    instrucao = (instrucao or "").strip()
    try:
        # Primeiro o estado (transação): um "sim" repetido não passa daqui e não marca a cena duas vezes.
        anterior = vp.transicionar(db, projeto_id, vp.RENDERIZANDO, de={vp.CONCLUIDO}, campos={
            "erro": None, "video_drive_id": None, "video_link": None, "video_gcs": None, "video_anexado": False,
            "render_pedido_em": _agora(agora)})
    except vp.ErroVideo as exc:
        return {"status": "recusado", "erro": str(exc)}
    batch = db.batch()
    for n in previa["cenas_refeitas"]:
        campos = {"refacao": firestore.Increment(1)}
        if n == int(ordem):
            campos["instrucao_video"] = instrucao or None
        batch.update(ref.collection("cenas").document(vp.id_cena(n)), campos)
    batch.update(ref, {"video_link_anterior": anterior.get("video_link")})
    batch.commit()
    return _disparar(db, projeto_id, disparar, {"tempo_estimado_min": len(previa["cenas_refeitas"]) + 1},
                     f"Refazendo a(s) cena(s) {previa['cenas_refeitas']}")


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
    rodando = projeto.get("status") in (vp.RENDERIZANDO, vp.MONTANDO)
    return {"status": "ok", "projeto_id": projeto_id, "estado": vp.CANCELADO,
            "custo_real_usd": round(float(projeto.get("custo_real_usd") or 0), 2),
            "mensagem": ("Cancelado. O worker para antes do próximo clipe; o clipe que já estiver no Veo ainda "
                         "pode ser cobrado." if rodando else "Cancelado.")}
