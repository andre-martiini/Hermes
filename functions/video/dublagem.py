"""Dublagem no servidor (tool video_dublar): ElevenLabs Dubbing com a voz do próprio André (clonagem automática do
falante, autorizada por ele em 01/11/2026), sem lip-sync — o vídeo original volta com o áudio no outro idioma.

O agente da nuvem não alcança api.elevenlabs.io: o vídeo chega por `upload_token` (preparar_upload) ou
`drive_file_id`, o Hermes envia, espera e devolve uma URL assinada de 2 h do MP4 dublado (para guardar na ação:
anexar_arquivo com essa url). Custo: US$ 0,50 por minuto de origem por idioma (API sem marca d'água, preço de
01/11/2026; o plano Starter cobre ~10 min/mês em créditos). Acima de US$ 5 pede confirmação, como o fal.
O lip-sync (caro) continua só local, no gaspar-v2v (`efeitos.py dublar --lipsync`).
"""
from __future__ import annotations

import time
from types import SimpleNamespace

URL = "https://api.elevenlabs.io/v1/dubbing"
USD_POR_MINUTO = 0.50
TETO_CONFIRMACAO_USD = 5.0
ESPERA_MAXIMA_S = 8 * 60
COLECAO_JOBS = "videoJobs"


def _chave(db) -> str:
    d = db.collection("system").document("api_keys").get().to_dict() or {}
    if not d.get("elevenlabs_api_key"):
        raise ValueError("Sem elevenlabs_api_key em system/api_keys.")
    return d["elevenlabs_api_key"]


def _requests():
    import requests

    return requests


def executar_tool(db, uid: str, args: dict, *, http=None, dormir=None, relogio=None) -> dict:
    http = http or _requests()
    if args.get("dubbing_id"):
        return _acompanhar(db, uid, str(args["dubbing_id"]), str(args.get("idioma") or ""), http=http, dormir=dormir,
                           relogio=relogio)
    idioma = str(args.get("idioma") or "").strip().lower()
    fontes = [k for k in ("upload_token", "drive_file_id") if args.get(k)]
    if not idioma or len(fontes) != 1:
        return {"erro": "Informe `idioma` (ex.: en, es) e exatamente um de upload_token ou drive_file_id."}
    try:
        segundos = float(args.get("segundos") or 0)
    except (TypeError, ValueError):
        segundos = 0
    if segundos <= 0:
        return {"erro": "Informe `segundos` (duração do vídeo) para o custo ser mostrado antes de gastar."}
    custo = round(USD_POR_MINUTO * segundos / 60, 2)
    aprovado = float(args.get("aprovado_ate_usd") or 0)
    if custo > TETO_CONFIRMACAO_USD and aprovado < custo:
        return {"status": "confirmation_required", "custo_estimado_usd": custo,
                "mensagem": f"Dublagem estimada em US$ {custo:.2f} (passa de US$ {TETO_CONFIRMACAO_USD:.2f}). "
                            f"Mostre ao André e, se ele aprovar, chame de novo com aprovado_ate_usd={custo}."}
    from tools import anexar_arquivo

    ctx = SimpleNamespace(db=db, user_uid=uid)
    try:
        dados, nome = anexar_arquivo._resolver_conteudo(ctx, {fontes[0]: args[fontes[0]]})
        r = http.post(URL, headers={"xi-api-key": _chave(db)}, files={"file": (nome, dados, "video/mp4")},
                      data={"source_lang": str(args.get("idioma_origem") or "pt"), "target_lang": idioma,
                            "num_speakers": "1", "watermark": "false", "name": f"gaspar-{nome}-{idioma}"}, timeout=300)
    except ValueError as e:
        return {"erro": str(e)}
    if not r.ok:
        return {"erro": f"ElevenLabs recusou a dublagem ({r.status_code}): {r.text[:300]}"}
    dub_id = r.json()["dubbing_id"]
    if fontes[0] == "upload_token":
        anexar_arquivo.consumir_upload_token(ctx, args["upload_token"])
    from google.cloud import firestore as gcf

    db.collection(COLECAO_JOBS).document(f"eleven-{dub_id}").set({
        "uid": uid, "modelo": "elevenlabs/dubbing", "nome_modelo": f"ElevenLabs Dubbing → {idioma} (sem lip-sync)",
        "entrada": {"arquivo": nome, "idioma": idioma, "segundos": segundos}, "custo_estimado_usd": custo,
        "status": "IN_PROGRESS", "task_id": args.get("task_id"), "dubbing_id": dub_id, "criado_em": gcf.SERVER_TIMESTAMP})
    return _acompanhar(db, uid, dub_id, idioma, http=http, dormir=dormir, relogio=relogio)


def _acompanhar(db, uid: str, dub_id: str, idioma: str, *, http, dormir=None, relogio=None) -> dict:
    dormir, relogio = dormir or time.sleep, relogio or time.monotonic
    ref = db.collection(COLECAO_JOBS).document(f"eleven-{dub_id}")
    job = ref.get().to_dict() or {}
    if job.get("uid") not in (None, uid):
        return {"erro": "dubbing_id desconhecido."}
    idioma = idioma or (job.get("entrada") or {}).get("idioma", "")
    cab = {"xi-api-key": _chave(db)}
    inicio, st = relogio(), {}
    while relogio() - inicio < ESPERA_MAXIMA_S:
        st = http.get(f"{URL}/{dub_id}", headers=cab, timeout=60).json()
        if st.get("status") in ("dubbed", "failed"):
            break
        dormir(10)
    saida = {"dubbing_id": dub_id, "idioma": idioma, "status": st.get("status"),
             "custo_estimado_usd": job.get("custo_estimado_usd")}
    if st.get("status") == "failed":
        ref.update({"status": "FAILED", "erro": st.get("error")})
        return {"erro": f"ElevenLabs falhou: {st.get('error')}", **saida}
    if st.get("status") != "dubbed":
        return {**saida, "mensagem": f"Ainda dublando. Chame de novo com dubbing_id={dub_id} (não cobra de novo)."}
    mp4 = http.get(f"{URL}/{dub_id}/audio/{idioma}", headers=cab, timeout=600).content
    from google.cloud import storage

    from tools.anexar_arquivo import assinar
    from video.midia import BUCKET

    blob = storage.Client().bucket(BUCKET).blob(f"tmp/dublagem/{uid}/{dub_id}-{idioma}.mp4")
    blob.upload_from_string(mp4, content_type="video/mp4")
    url = assinar(blob, minutos=120)
    ref.update({"status": "COMPLETED", "urls": [url], "custo_real_usd": job.get("custo_estimado_usd")})
    return {**saida, "status": "COMPLETED", "custo_real_usd": job.get("custo_estimado_usd"), "urls": [url],
            "proximo_passo": "anexar_arquivo com esta url (e o task_id) para guardar o vídeo dublado na ação."}
