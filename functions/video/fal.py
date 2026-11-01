"""fal.ai: conector único para geração por IA paga (vídeo V2V, imagem, lip-sync, reframe).

`estimar_custo(modelo, segundos=..., imagens=...)` lê a tabela de preços e devolve US$; `executar` envia
para a fila REST do fal e devolve o `request_id`; `consultar` diz se terminou e traz o resultado.

Preços mudam todo mês: `PRECOS_FAL` é só o ponto de partida; `config/precos_fal` (Firestore) sobrescreve
por modelo, sem deploy. Valores de 01/11/2026 (plano de vídeo nov/2026); conferir na página do modelo.

Chave: campo `fal_key` de `system/api_keys` (o mesmo documento das demais chaves); env FAL_KEY como alternativa.
"""
from __future__ import annotations

import copy
import json
import os
import urllib.error
import urllib.request

FILA = "https://queue.fal.run"
# Teto por job acima do qual a tool pede confirmação (decisão do André, 01/11/2026).
TETO_CONFIRMACAO_USD = 5.0

# unidade: "segundo" (vídeo gerado), "imagem" (por imagem) ou "job" (preço fixo).
PRECOS_FAL: dict = {
    "fal-ai/flux/schnell": {"unidade": "imagem", "usd": 0.003, "nome": "FLUX.1 schnell (imagem de teste)"},
    "fal-ai/nano-banana": {"unidade": "imagem", "usd": 0.039, "nome": "Nano Banana (referência de cenário/figurino)"},
    "fal-ai/wan-vace-apps/video-edit": {"unidade": "segundo", "usd": 0.05, "nome": "Wan VACE video-edit 480p (rascunho V2V)"},
    "fal-ai/kling-video/o3/standard/video-to-video/edit": {"unidade": "segundo", "usd": 0.126, "nome": "Kling O3 Video Edit Std (V2V final; entrada 3-10 s, 720-2160 px)"},
    "fal-ai/kling-video/o3/standard/video-to-video/reference": {"unidade": "segundo", "usd": 0.126, "nome": "Kling O3 Std com imagem de referência"},
    "fal-ai/kling-video/o3/pro/video-to-video/edit": {"unidade": "segundo", "usd": 0.168, "nome": "Kling O3 Video Edit Pro"},
    "fal-ai/luma-dream-machine/ray-3.2/modify": {"unidade": "segundo", "usd": 0.11, "nome": "Luma Ray 3.2 Modify (draft)"},
    "fal-ai/luma-dream-machine/ray-3.2/reframe": {"unidade": "segundo", "usd": 0.12, "nome": "Luma Ray 3.2 Reframe 720p"},
    "fal-ai/sync-lipsync/v2/pro": {"unidade": "segundo", "usd": 0.083, "nome": "Sync lipsync-2-pro"},
    "fal-ai/ltx-2/retake": {"unidade": "segundo", "usd": 0.10, "nome": "LTX-2 Retake"},
    # Gaspar Vídeo v2 (01/11/2026): animação de ilustração e elemento do efeito na mão sem a Vertex, e sons.
    "fal-ai/veo3.1/fast/image-to-video": {"unidade": "segundo", "usd": 0.10, "nome": "Veo 3.1 Fast imagem→vídeo, sem áudio (animar ilustração/elemento)"},
    "fal-ai/veo3.1/image-to-video": {"unidade": "segundo", "usd": 0.20, "nome": "Veo 3.1 imagem→vídeo, sem áudio"},
    "fal-ai/kling-video/o3/pro/image-to-video": {"unidade": "segundo", "usd": 0.168, "nome": "Kling O3 Pro imagem→vídeo"},
    "fal-ai/elevenlabs/sound-effects/v2": {"unidade": "segundo", "usd": 0.002, "nome": "ElevenLabs Sound Effects v2 (ambiente e SFX; 0,5–22 s)"},
}


class ErroFal(RuntimeError):
    pass


def precos(db=None) -> dict:
    """`PRECOS_FAL` com `config/precos_fal` por cima (por modelo, campo a campo)."""
    tabela = copy.deepcopy(PRECOS_FAL)
    if db is not None:
        snap = db.collection("config").document("precos_fal").get()
        for modelo, valor in ((snap.to_dict() or {}) if snap.exists else {}).items():
            if isinstance(valor, dict):
                tabela.setdefault(modelo, {}).update(valor)
    return tabela


def estimar_custo(modelo: str, *, segundos: float = 0, imagens: int = 1, tabela: dict | None = None) -> float:
    p = (tabela or PRECOS_FAL).get(modelo)
    if not p:
        raise ErroFal(f"Sem preço para o modelo {modelo!r}. Cadastre em config/precos_fal antes de usar.")
    unidade, usd = p["unidade"], float(p["usd"])
    if unidade == "segundo":
        if segundos <= 0:
            raise ErroFal(f"{modelo} cobra por segundo: informe a duração.")
        return round(usd * segundos, 2)
    if unidade == "imagem":
        return round(usd * max(imagens, 1), 3)
    return round(usd, 2)


def chave(db=None) -> str:
    valor = None
    if db is not None:
        snap = db.collection("system").document("api_keys").get()
        valor = (snap.to_dict() or {}).get("fal_key") if snap.exists else None
    valor = valor or os.environ.get("FAL_KEY")
    if not valor:
        raise ErroFal("Chave do fal não configurada (system/api_keys.fal_key).")
    return valor


def _http(metodo: str, url: str, api_key: str, corpo: dict | None = None, timeout: float = 60) -> dict:
    dados = json.dumps(corpo).encode() if corpo is not None else None
    req = urllib.request.Request(url, data=dados, method=metodo,
                                 headers={"Authorization": f"Key {api_key}", "Content-Type": "application/json",
                                          "User-Agent": "gaspar-hermes/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        detalhe = e.read().decode("utf-8", "replace")[:300]
        if e.code in (401, 403):
            # 403 também é conta sem saldo ("Exhausted balance"): o detalhe do fal diz qual dos dois.
            raise ErroFal(f"fal recusou o acesso ({e.code}): {detalhe}") from e
        raise ErroFal(f"fal respondeu {e.code}: {detalhe}") from e


def executar(modelo: str, payload: dict, api_key: str, http=_http) -> dict:
    """Envia para a fila. Devolve {request_id, status_url, response_url} (URLs vêm do fal: o modelo
    pode ter subcaminho que não entra nelas)."""
    r = http("POST", f"{FILA}/{modelo}", api_key, payload)
    if not r.get("request_id"):
        raise ErroFal(f"fal não devolveu request_id: {str(r)[:200]}")
    return {k: r.get(k) for k in ("request_id", "status_url", "response_url")}


def consultar(job: dict, api_key: str, http=_http) -> dict:
    """{status: IN_QUEUE|IN_PROGRESS|COMPLETED|FAILED, resultado?, erro?}."""
    st = http("GET", job["status_url"], api_key)
    status = st.get("status")
    if status != "COMPLETED":
        return {"status": status or "IN_QUEUE"}
    if st.get("error"):
        return {"status": "FAILED", "erro": f"{st.get('error_type') or 'erro'}: {st['error']}"[:300]}
    return {"status": "COMPLETED", "resultado": http("GET", job["response_url"], api_key)}


def urls_do_resultado(resultado: dict) -> list[str]:
    """URLs de mídia no resultado (images[], video, audio…), qualquer que seja o modelo."""
    achadas: list[str] = []

    def andar(v):
        if isinstance(v, dict):
            if isinstance(v.get("url"), str) and v["url"].startswith("http"):
                achadas.append(v["url"])
            for x in v.values():
                if isinstance(x, (dict, list)):
                    andar(x)
        elif isinstance(v, list):
            for x in v:
                andar(x)

    andar(resultado)
    return achadas


# ---------------------------------------------------------------- tool video_fal_executar

COLECAO_JOBS = "videoJobs"
ESPERA_MAXIMA_S = 480  # o job MCP tem 540 s; sobra para gravar o resultado


ERROS_SEGUIDOS_MAX = 5  # falha de rede passageira na consulta não é falha do job (o fal segue cobrando)
# Campos de duração que os modelos do fal aceitam na entrada; o custo usa o MAIOR entre eles e `segundos`.
CAMPOS_DURACAO = ("duration", "duration_seconds", "seconds")


def _segundos_cobraveis(args: dict, entrada: dict) -> float:
    declarados = [args.get("segundos")] + [entrada.get(c) for c in CAMPOS_DURACAO]
    return max([float(str(v).rstrip("s")) for v in declarados if v not in (None, "")] or [0.0])


def _duracao_resultado(resultado: dict) -> float | None:
    """Duração do vídeo gerado, quando o fal a informa (video.duration / file_metadata)."""
    for v in (resultado.get("video") or {}, *(resultado.get("videos") or [])):
        if isinstance(v, dict):
            d = v.get("duration") or (v.get("file_metadata") or {}).get("duration")
            if d:
                return float(d)
    return None


def _resolver_arquivos(db, uid: str, arquivos: dict, entrada: dict) -> tuple[dict, list[str]]:
    """`arquivos` = {campo da entrada: {"upload_token": ...} | {"drive_file_id": ...}}: o Hermes busca o arquivo
    (o agente da nuvem não alcança o fal nem tem URL pública), sobe ao bucket do Hermes Vídeo e põe no campo uma
    URL assinada de 2 h. Campo terminado em "_urls" recebe uma lista. Devolve a entrada nova, os tokens a consumir e
    os blobs publicados (para apagar se o envio falhar)."""
    import mimetypes
    import re
    import uuid
    from types import SimpleNamespace

    from google.cloud import storage

    from tools import anexar_arquivo
    from video.midia import BUCKET

    ctx = SimpleNamespace(db=db, user_uid=uid)
    nova, tokens, blobs = copy.deepcopy(entrada), [], []
    if not isinstance(arquivos, dict):
        raise ErroFal("`arquivos` precisa ser um objeto {campo: {upload_token | drive_file_id}}.")
    for campo, ref in arquivos.items():
        fontes = [k for k in ("upload_token", "drive_file_id") if isinstance(ref, dict) and ref.get(k)]
        if len(fontes) != 1:
            raise ErroFal(f"arquivos.{campo}: informe exatamente um de upload_token (preparar_upload) ou drive_file_id.")
        try:
            dados, nome = anexar_arquivo._resolver_conteudo(ctx, {fontes[0]: ref[fontes[0]]})
        except ValueError as e:
            raise ErroFal(f"arquivos.{campo}: {e}") from e
        nome = re.sub(r"[^\w.-]", "_", str(nome).replace("\\", "/").rsplit("/", 1)[-1])[:80] or "arquivo"
        try:
            blob = storage.Client().bucket(BUCKET).blob(f"tmp/fal/{uid}/{uuid.uuid4().hex[:12]}/{nome}")
            blob.upload_from_string(dados, content_type=mimetypes.guess_type(nome)[0] or "application/octet-stream")
            blobs.append(blob)
            url = anexar_arquivo.assinar(blob, minutos=120)
        except Exception as e:  # noqa: BLE001 — storage/IAM: erro legível, não traceback
            _apagar(blobs)
            raise ErroFal(f"arquivos.{campo}: não consegui publicar o arquivo ({type(e).__name__}: {str(e)[:200]})") from e
        if campo.endswith("_urls"):
            nova.setdefault(campo, []).append(url)
        else:
            nova[campo] = url
        if fontes[0] == "upload_token":
            tokens.append(ref["upload_token"])
    return nova, tokens, blobs


def _apagar(blobs):
    for b in blobs:
        try:
            b.delete()
        except Exception:  # noqa: BLE001 — limpeza é melhor esforço
            pass


def executar_tool(db, uid: str, args: dict, *, http=_http, dormir=None, relogio=None) -> dict:
    """Roda um modelo do fal de ponta a ponta: confere custo e teto, envia, espera e registra em videoJobs.

    Acima de TETO_CONFIRMACAO_USD não gasta nada: devolve `confirmation_required` com o custo, e a chamada
    seguinte precisa trazer `aprovado_ate_usd` ≥ custo estimado (aprovação explícita do André).
    Com `job_fal` (de uma chamada que passou do tempo), só volta a consultar aquele job: não envia nem cobra.
    """
    if args.get("job_fal"):
        return _retomar(db, str(args["job_fal"]), http=http, dormir=dormir, relogio=relogio)
    modelo = str(args.get("modelo") or "").strip()
    entrada = args.get("entrada")
    if not modelo or not isinstance(entrada, dict):
        return {"erro": "Informe `modelo` (id do fal) e `entrada` (objeto com o input do modelo)."}
    try:
        tabela = precos(db)
        custo = estimar_custo(modelo, segundos=_segundos_cobraveis(args, entrada),
                              imagens=int(entrada.get("num_images") or 1), tabela=tabela)
    except ErroFal as e:
        return {"erro": str(e)}
    except (ValueError, TypeError, KeyError) as e:
        return {"erro": f"Entrada ou tabela de preços inválida para {modelo}: {e!r}"}
    aprovado = float(args.get("aprovado_ate_usd") or 0)
    if custo > TETO_CONFIRMACAO_USD and aprovado < custo:
        return {"status": "confirmation_required", "modelo": modelo, "custo_estimado_usd": custo,
                "teto_sem_confirmacao_usd": TETO_CONFIRMACAO_USD,
                "mensagem": f"Custo estimado US$ {custo:.2f} passa do teto de US$ {TETO_CONFIRMACAO_USD:.2f}. "
                            f"Mostre ao André e, se ele aprovar, chame de novo com aprovado_ate_usd={custo}."}
    tokens, blobs = [], []
    try:
        if args.get("arquivos"):
            entrada, tokens, blobs = _resolver_arquivos(db, uid, args["arquivos"], entrada)
        api_key = chave(db)
        job = executar(modelo, entrada, api_key, http=http)
    except ErroFal as e:
        _apagar(blobs)  # nada foi enviado: o arquivo publicado não serve a ninguém
        return {"erro": str(e)}
    if tokens:
        from types import SimpleNamespace

        from tools.anexar_arquivo import consumir_upload_token

        for t in tokens:
            consumir_upload_token(SimpleNamespace(db=db, user_uid=uid), t)

    from google.cloud import firestore as gcf

    ref = db.collection(COLECAO_JOBS).document(job["request_id"])
    ref.set({"uid": uid, "modelo": modelo, "nome_modelo": tabela[modelo].get("nome"), "entrada": entrada,
             "custo_estimado_usd": custo, "preco": tabela[modelo], "status": "IN_QUEUE", "task_id": args.get("task_id"),
             "criado_em": gcf.SERVER_TIMESTAMP, **job})
    return _acompanhar(ref, job, modelo, custo, tabela[modelo], api_key, http=http, dormir=dormir, relogio=relogio)


def _retomar(db, request_id: str, **kw) -> dict:
    snap = db.collection(COLECAO_JOBS).document(request_id).get()
    if not snap.exists:
        return {"erro": f"Job {request_id} não encontrado em {COLECAO_JOBS}."}
    d = snap.to_dict()
    job = {k: d.get(k) for k in ("request_id", "status_url", "response_url")}
    try:
        api_key = chave(db)
    except ErroFal as e:
        return {"erro": str(e)}
    return _acompanhar(db.collection(COLECAO_JOBS).document(request_id), job, d["modelo"], d["custo_estimado_usd"],
                       d.get("preco") or {}, api_key, **kw)


def _acompanhar(ref, job, modelo, custo, preco, api_key, *, http=_http, dormir=None, relogio=None) -> dict:
    import time

    from google.cloud import firestore as gcf

    dormir = dormir or time.sleep
    relogio = relogio or time.monotonic
    inicio = relogio()
    r, erros = {"status": "IN_QUEUE"}, 0
    while relogio() - inicio < ESPERA_MAXIMA_S:
        try:
            r, erros = consultar(job, api_key, http=http), 0
        except ErroFal as e:
            erros += 1
            if erros >= ERROS_SEGUIDOS_MAX:
                r = {"status": "IN_PROGRESS", "aviso": f"consulta falhando ({e}); o job pode seguir no fal."}
                break
        if r["status"] in ("COMPLETED", "FAILED"):
            break
        dormir(3)
    resultado = r.get("resultado") or {}
    urls = urls_do_resultado(resultado)
    real = 0.0
    if r["status"] == "COMPLETED":
        dur = _duracao_resultado(resultado)
        # Por segundo e com a duração gerada informada: vale o que saiu, não o declarado.
        real = round(float(preco["usd"]) * dur, 2) if dur and preco.get("unidade") == "segundo" else custo
    ref.update({"status": r["status"], "urls": urls, "erro": r.get("erro"), "custo_real_usd": real,
                "atualizado_em": gcf.SERVER_TIMESTAMP})
    saida = {"job_fal": job["request_id"], "modelo": modelo, "status": r["status"], "custo_estimado_usd": custo,
             "custo_real_usd": real, "urls": urls}
    if real > custo * 1.2:
        saida["alerta_custo"] = f"O fal gerou mais do que o estimado: US$ {real:.2f} contra US$ {custo:.2f}."
    if r["status"] == "FAILED":
        return {"erro": f"O fal falhou: {r.get('erro')}", **saida}
    if r["status"] != "COMPLETED":
        saida["mensagem"] = ((r.get("aviso") or f"Ainda rodando no fal após {ESPERA_MAXIMA_S // 60} min.")
                             + f" Chame de novo com job_fal={job['request_id']} para buscar o resultado (não cobra de novo).")
    return saida
