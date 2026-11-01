"""Dublagem no servidor (tool video_dublar): ElevenLabs Dubbing com a voz do próprio André (clonagem automática do
falante, autorizada por ele em 01/11/2026), sem lip-sync — o vídeo original volta com o áudio no outro idioma.

O agente da nuvem não alcança api.elevenlabs.io: o vídeo chega por `upload_token` (preparar_upload) ou
`drive_file_id`, o Hermes envia, espera e devolve uma URL assinada de 2 h do MP4 dublado (para guardar na ação:
anexar_arquivo com essa url). Custo: US$ 0,50 por minuto de origem por idioma (API sem marca d'água, preço de
01/11/2026; o plano Starter cobre ~10 min/mês em créditos). Acima de US$ 5 pede confirmação, como o fal; a duração
vale a do arquivo (lida no MP4), não só a declarada. O lip-sync (caro) continua só local, no gaspar-v2v.

A tradução é automática e pode traduzir nomes próprios ("Reditec" → "Tech Network" em 01/11/2026); corrigir o
texto pela API é só do plano Enterprise. Confira a transcrição do dublado antes de entregar.
"""
from __future__ import annotations

import re
import struct
import time
from types import SimpleNamespace

URL = "https://api.elevenlabs.io/v1/dubbing"
USD_POR_MINUTO = 0.50
TETO_CONFIRMACAO_USD = 5.0
# O job MCP morre aos 540 s: envio + espera + download cabem em ~450 s; passou, devolve o dubbing_id para retomar.
ORCAMENTO_S = 450
ERROS_SEGUIDOS_MAX = 3
COLECAO_JOBS = "videoJobs"
ID_OK = re.compile(r"^[A-Za-z0-9_-]{4,64}$")
IDIOMA_OK = re.compile(r"^[a-z]{2,3}(-[A-Za-z]{2,4})?$")


def _chave(db) -> str:
    d = db.collection("system").document("api_keys").get().to_dict() or {}
    if not d.get("elevenlabs_api_key"):
        raise ValueError("Sem elevenlabs_api_key em system/api_keys.")
    return d["elevenlabs_api_key"]


def _requests():
    import requests

    return requests


def duracao_mp4(dados: bytes) -> float | None:
    """Duração (s) pelo átomo mvhd do MP4/MOV; None se não achar."""
    i = dados.find(b"mvhd")
    if i < 0 or len(dados) < i + 24:
        return None
    versao = dados[i + 4]
    if versao == 1:
        if len(dados) < i + 36:
            return None
        escala, dur = struct.unpack(">IQ", dados[i + 24:i + 36])
    else:
        escala, dur = struct.unpack(">II", dados[i + 16:i + 24])
    return dur / escala if escala else None


def _nome_seguro(nome: str) -> str:
    return re.sub(r"[^\w.-]", "_", str(nome).replace("\\", "/").rsplit("/", 1)[-1])[:80] or "video.mp4"


def executar_tool(db, uid: str, args: dict, *, http=None, dormir=None, relogio=None) -> dict:
    http, relogio = http or _requests(), relogio or time.monotonic
    inicio = relogio()
    if args.get("dubbing_id"):
        return _acompanhar(db, uid, str(args["dubbing_id"]), http=http, dormir=dormir, relogio=relogio, inicio=inicio)
    idioma = str(args.get("idioma") or "").strip().lower()
    fontes = [k for k in ("upload_token", "drive_file_id") if args.get(k)]
    if not IDIOMA_OK.match(idioma) or len(fontes) != 1:
        return {"erro": "Informe `idioma` (ex.: en, es) e exatamente um de upload_token ou drive_file_id."}
    try:
        declarados = float(args.get("segundos") or 0)
    except (TypeError, ValueError):
        declarados = 0
    if declarados <= 0:
        return {"erro": "Informe `segundos` (duração do vídeo) para o custo ser mostrado antes de gastar."}
    aprovado = float(args.get("aprovado_ate_usd") or 0)

    def teto(seg):
        custo = round(USD_POR_MINUTO * seg / 60, 2)
        if custo > TETO_CONFIRMACAO_USD and aprovado < custo:
            return custo, {"status": "confirmation_required", "custo_estimado_usd": custo,
                           "mensagem": f"Dublagem estimada em US$ {custo:.2f} (passa de US$ {TETO_CONFIRMACAO_USD:.2f}). "
                                       f"Mostre ao André e, se ele aprovar, chame de novo com aprovado_ate_usd={custo}."}
        return custo, None

    custo, parar = teto(declarados)
    if parar:
        return parar
    from tools import anexar_arquivo

    ctx = SimpleNamespace(db=db, user_uid=uid)
    try:
        dados, nome = anexar_arquivo._resolver_conteudo(ctx, {fontes[0]: args[fontes[0]]})
    except ValueError as e:
        return {"erro": str(e)}
    real = duracao_mp4(dados)
    if real and real > declarados + 1:  # vale a duração do arquivo: o teto não depende do que o agente declarou
        custo, parar = teto(real)
        if parar:
            return {**parar, "aviso": f"O vídeo tem {real:.0f} s (foram declarados {declarados:.0f} s)."}
    nome = _nome_seguro(nome)
    try:
        r = http.post(URL, headers={"xi-api-key": _chave(db)}, files={"file": (nome, dados, "video/mp4")},
                      data={"source_lang": str(args.get("idioma_origem") or "pt"), "target_lang": idioma,
                            "num_speakers": "1", "watermark": "false", "name": f"gaspar-{nome}-{idioma}"},
                      timeout=min(240, ORCAMENTO_S))
        dub_id = r.json().get("dubbing_id") if r.ok else None
    except Exception as e:  # noqa: BLE001 — rede/JSON: nada confirmado, o André decide se tenta de novo
        return {"erro": f"Falha ao enviar ao ElevenLabs ({type(e).__name__}: {str(e)[:200]}). Confira no painel do "
                        "ElevenLabs se a dublagem foi criada antes de tentar de novo, para não pagar duas vezes."}
    if not dub_id:
        return {"erro": f"ElevenLabs recusou a dublagem ({r.status_code}): {r.text[:300]}"}
    from google.cloud import firestore as gcf

    db.collection(COLECAO_JOBS).document(f"eleven-{dub_id}").set({
        "uid": uid, "modelo": "elevenlabs/dubbing", "nome_modelo": f"ElevenLabs Dubbing → {idioma} (sem lip-sync)",
        "entrada": {"arquivo": nome, "idioma": idioma, "segundos": real or declarados}, "custo_estimado_usd": custo,
        "status": "IN_PROGRESS", "task_id": args.get("task_id"), "dubbing_id": dub_id, "criado_em": gcf.SERVER_TIMESTAMP})
    if fontes[0] == "upload_token":
        anexar_arquivo.consumir_upload_token(ctx, args["upload_token"])
    return _acompanhar(db, uid, dub_id, http=http, dormir=dormir, relogio=relogio, inicio=inicio)


def _acompanhar(db, uid: str, dub_id: str, *, http, dormir=None, relogio, inicio) -> dict:
    dormir = dormir or time.sleep
    if not ID_OK.match(dub_id):
        return {"erro": "dubbing_id inválido."}
    ref = db.collection(COLECAO_JOBS).document(f"eleven-{dub_id}")
    job = ref.get().to_dict()
    if not job or job.get("uid") != uid:
        return {"erro": "dubbing_id desconhecido."}
    idioma = (job.get("entrada") or {}).get("idioma", "")
    saida = {"dubbing_id": dub_id, "idioma": idioma, "custo_estimado_usd": job.get("custo_estimado_usd")}
    retomar = f" Chame de novo com dubbing_id={dub_id} (não cobra de novo)."
    if job.get("status") == "COMPLETED" and job.get("urls"):
        return {**saida, "status": "COMPLETED", "urls": job["urls"], "custo_real_usd": job.get("custo_real_usd")}
    cab = {"xi-api-key": _chave(db)}
    st, erros = {}, 0
    while relogio() - inicio < ORCAMENTO_S - 120:  # reserva para baixar e publicar
        try:
            st, erros = http.get(f"{URL}/{dub_id}", headers=cab, timeout=30).json(), 0
        except Exception:  # noqa: BLE001 — consulta passageira não derruba o job
            erros += 1
            if erros >= ERROS_SEGUIDOS_MAX:
                return {**saida, "status": "IN_PROGRESS", "mensagem": "Consulta ao ElevenLabs falhando." + retomar}
        if st.get("status") in ("dubbed", "failed"):
            break
        dormir(10)
    if st.get("status") == "failed":
        ref.update({"status": "FAILED", "erro": st.get("error")})
        return {"erro": f"ElevenLabs falhou: {st.get('error')}", **saida, "status": "FAILED"}
    if st.get("status") != "dubbed":
        return {**saida, "status": "IN_PROGRESS", "mensagem": "Ainda dublando." + retomar}
    try:
        r = http.get(f"{URL}/{dub_id}/audio/{idioma}", headers=cab, timeout=100)
        ok = r.ok and not r.headers.get("content-type", "").startswith("application/json")
    except Exception as e:  # noqa: BLE001
        return {**saida, "status": "IN_PROGRESS", "mensagem": f"Download falhou ({type(e).__name__})." + retomar}
    if not ok:
        return {"erro": f"ElevenLabs não entregou o vídeo dublado ({r.status_code}): {r.text[:200]}", **saida}
    from google.cloud import storage

    from tools.anexar_arquivo import assinar
    from video.midia import BUCKET

    blob = storage.Client().bucket(BUCKET).blob(f"tmp/dublagem/{uid}/{dub_id}-{idioma}.mp4")
    blob.upload_from_string(r.content, content_type="video/mp4")
    url = assinar(blob, minutos=120)
    ref.update({"status": "COMPLETED", "urls": [url], "custo_real_usd": job.get("custo_estimado_usd")})
    return {**saida, "status": "COMPLETED", "custo_real_usd": job.get("custo_estimado_usd"), "urls": [url],
            "proximo_passo": "anexar_arquivo com esta url (e o task_id) para guardar o vídeo dublado na ação."}
