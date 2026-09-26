"""Prévia do storyboard: narração por cena, quadros-chave, folha de contato e MP3.

Ordem (o áudio vem antes do vídeo): a narração de cada cena, com o silêncio das
pontas aparado, define a duração do clipe (4, 6 ou 8 s); os quadros K0..KN definem
o começo e o fim de cada clipe. A cena i vai de K(i-1) a K(i).

Só refaz o que falta: cena cujo áudio não existe ou foi gerado para outra versão
do texto, quadro sem imagem ou marcado `pendente` por `ajustar`. Antes de gastar,
soma o custo de tudo o que vai gerar e recusa se passar do teto por prévia —
nenhuma chamada paga acontece numa prévia recusada.

Cada resultado é gravado no Firestore assim que sai (checkpoint): uma prévia
interrompida no meio retoma sem pagar de novo pelo que já foi feito.
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from firebase_admin import firestore

from video import estimativa, folha, midia
from video import projeto as vp

PARALELISMO_TTS = 4
# Um job de prévia dura no máximo 540 s; passado isso sem terminar, outro pode assumir.
PREVIA_TRAVADA_APOS = timedelta(minutes=10)
ESTADOS_DE_ENTRADA = {vp.ROTEIRO, vp.AGUARDANDO_STORYBOARD, vp.ERRO}


def _agora():
    return datetime.now(timezone.utc)


def _carregar(db, projeto_id: str, uid: str | None):
    if not vp.id_projeto_valido(projeto_id) or not (uid or "").strip():
        return None, None, None
    ref = db.collection(vp.COLECAO).document(projeto_id)
    snap = ref.get()
    if not snap.exists or (snap.to_dict() or {}).get("uid") != uid:
        return None, None, None
    return ref, snap.to_dict() or {}, sorted(
        (c.to_dict() or {} for c in ref.collection("cenas").stream()), key=lambda c: c.get("ordem", 0))


def _quadros(ref) -> dict[int, dict]:
    return {int(q.get("indice")): q for q in (s.to_dict() or {} for s in ref.collection("keyframes").stream())}


def precisa_audio(cena: dict) -> bool:
    return bool(cena.get("narracao")) and (not cena.get("audio_gcs") or cena.get("audio_versao") != cena.get("versao"))


def precisa_quadro(q: dict | None) -> bool:
    return q is None or not q.get("gcs_uri") or bool(q.get("pendente"))


def prompt_quadro(projeto: dict, cenas: list[dict], k: int, instrucao: str | None = None) -> str:
    b = projeto.get("biblia") or {}
    partes = [f"Estilo: {b.get('estilo')}."]
    if b.get("paleta"):
        partes.append(f"Paleta: {b['paleta']}.")
    if b.get("personagens"):
        partes.append("Personagens (sempre iguais): " + "; ".join(b["personagens"]) + ".")
    if k == 0:
        partes.append(f"Quadro inicial do vídeo. {cenas[0].get('descricao_visual')}")
    else:
        partes.append(f"Quadro final da cena {k}: {cenas[k - 1].get('descricao_visual')}")
        if k < len(cenas):
            partes.append(f"Este quadro também abre a cena seguinte: {cenas[k].get('descricao_visual')}")
    if k > 0:
        partes.append("Mantenha EXATAMENTE a mesma personagem, roupa, cenário e estilo das imagens de "
                      "referência; mude só pose, ação e enquadramento.")
    if b.get("evitar"):
        partes.append(f"Evite: {b['evitar']}.")
    partes.append("Sem texto, letreiros ou legendas na imagem.")
    if instrucao:
        partes.append(f"Ajuste pedido: {instrucao}")
    return "\n".join(partes)


def custo_previsto(cenas: list[dict], quadros: dict[int, dict], precos: dict) -> tuple[float, int, int]:
    n_tts = sum(1 for c in cenas if precisa_audio(c))
    n_img = sum(1 for k in range(len(cenas) + 1) if precisa_quadro(quadros.get(k)))
    return n_tts * float(precos["tts_por_cena"]) + n_img * float(precos["imagem"]), n_tts, n_img


def _entrar(db, projeto_id: str, agora: datetime):
    """Leva o projeto para `previa_gerando` numa transação que relê o estado atual.

    Uma prévia em `previa_gerando` há mais de 10 min é de um job que morreu (o
    limite do job é 540 s) e pode ser assumida; mais nova que isso, é recusada —
    dois jobs não geram a mesma prévia ao mesmo tempo.
    """
    ref = db.collection(vp.COLECAO).document(projeto_id)
    transaction = vp._transacional(db)

    @firestore.transactional
    def _txn(tx):
        snap = ref.get(transaction=tx)
        if not snap.exists:
            raise vp.ProjetoNaoEncontrado(projeto_id)
        atual = snap.to_dict() or {}
        estado = atual.get("status")
        if estado == vp.PREVIA_GERANDO:
            iniciada = atual.get("previa_iniciada_em")
            if isinstance(iniciada, datetime) and agora - iniciada < PREVIA_TRAVADA_APOS:
                raise vp.TransicaoInvalida("Já há uma prévia sendo gerada para este projeto.")
        elif estado not in ESTADOS_DE_ENTRADA:
            raise vp.TransicaoInvalida(f"Prévia não pode começar no estado {estado!r}.")
        tx.update(ref, {"status": vp.PREVIA_GERANDO, "previa_iniciada_em": agora, "erro": None,
                        "atualizado_em": firestore.SERVER_TIMESTAMP})

    _txn(transaction)


def gerar_previa(db, projeto_id: str, uid: str | None, servicos: midia.Servicos, *,
                 precos: dict | None = None, agora: datetime | None = None) -> dict:
    agora = agora or _agora()
    projeto_id = (projeto_id or "").strip()
    ref, projeto, cenas = _carregar(db, projeto_id, uid)
    if ref is None:
        return {"status": "nao_encontrado", "erro": f"Projeto {projeto_id!r} não encontrado."}
    if not cenas:
        return {"status": "erro", "erro": "Projeto sem cenas."}
    precos = precos or estimativa.carregar_precos(db)
    quadros = _quadros(ref)

    custo, n_tts, n_img = custo_previsto(cenas, quadros, precos)
    teto = float(precos["teto_previa_usd"])
    if custo > teto:
        return {"status": "recusado", "erro": f"Esta prévia custaria US$ {custo:.2f} ({n_tts} narrações, "
                f"{n_img} quadros), acima do teto de US$ {teto:.2f} por prévia."}
    try:
        _entrar(db, projeto_id, agora)
    except vp.ErroVideo as exc:
        return {"status": "recusado", "erro": str(exc), "estado": projeto.get("status")}

    gasto = 0.0
    falhas: list[str] = []
    try:
        gasto += _gerar_narracoes(ref, projeto, cenas, servicos, precos, projeto_id)
        g, falhas = _gerar_quadros(ref, projeto, cenas, quadros, servicos, precos, projeto_id)
        gasto += g
        resultado = _publicar(ref, projeto, cenas, _quadros(ref), servicos, precos, projeto_id, falhas)
    except Exception as exc:  # noqa: BLE001 - qualquer falha vira estado `erro`, com o gasto registrado
        ref.update({"custo_real_usd": firestore.Increment(round(gasto, 4))})
        try:
            vp.transicionar(db, projeto_id, vp.ERRO, campos={"erro": f"prévia: {exc}"[:500]})
        except vp.ErroVideo:
            pass
        return {"status": "erro", "erro": f"A prévia falhou: {exc}", "gasto_usd": round(gasto, 2)}

    ref.update({"custo_real_usd": firestore.Increment(round(gasto, 4)),
                "custo_previa_usd": firestore.Increment(round(gasto, 4))})
    vp.transicionar(db, projeto_id, vp.AGUARDANDO_STORYBOARD, de={vp.PREVIA_GERANDO}, campos=resultado["campos"])
    return {**resultado["resposta"], "gasto_desta_previa_usd": round(gasto, 2),
            "narracoes_geradas": n_tts, "quadros_gerados": n_img - len(falhas)}


def _gerar_narracoes(ref, projeto, cenas, servicos, precos, projeto_id) -> float:
    pendentes = [c for c in cenas if precisa_audio(c)]
    if not pendentes:
        return 0.0
    voz, modelo = projeto.get("voz") or {}, precos["modelo_tts"]
    with ThreadPoolExecutor(max_workers=PARALELISMO_TTS) as pool:
        falas = list(pool.map(lambda c: servicos.gerar_fala(c["narracao"], voz, modelo), pendentes))
    for cena, fala in zip(pendentes, falas):
        pcm = midia.aparar_silencio(fala.pcm, fala.taxa)
        dur = midia.duracao_pcm(pcm, fala.taxa)
        clipe = estimativa.duracao_clipe(dur)
        uri = servicos.salvar(f"tmp/{projeto_id}/audio/{vp.id_cena(cena['ordem'])}_v{cena['versao']}.wav",
                              midia.pcm_para_wav(pcm, fala.taxa), "audio/wav")
        campos = {"audio_gcs": uri, "audio_versao": cena["versao"], "audio_duracao_s": round(dur, 2),
                  "duracao_s": clipe or 8, "dividir": clipe is None}
        ref.collection("cenas").document(vp.id_cena(cena["ordem"])).update(campos)
        cena.update(campos)
    return len(pendentes) * float(precos["tts_por_cena"])


def _gerar_quadros(ref, projeto, cenas, quadros, servicos, precos, projeto_id) -> tuple[float, list[str]]:
    """Sequencial: cada quadro usa o anterior (e o K0) como referência de identidade."""
    formato, modelo = projeto.get("formato") or "16:9", precos["modelo_imagem"]
    imagens: dict[int, bytes] = {}
    gasto, falhas = 0.0, []

    def imagem(k):
        if k not in imagens and quadros.get(k, {}).get("gcs_uri"):
            imagens[k] = servicos.ler(quadros[k]["gcs_uri"])
        return imagens.get(k)

    for k in range(len(cenas) + 1):
        q = quadros.get(k)
        if not precisa_quadro(q):
            continue
        refs = [r for r in (imagem(k - 1) if k > 0 else None, imagem(0) if k > 1 else None) if r]
        prompt = prompt_quadro(projeto, cenas, k, (q or {}).get("instrucao"))
        versao = int((q or {}).get("versao") or 0) + 1
        doc = ref.collection("keyframes").document(f"K{k:02d}")
        try:
            png = midia.recortar_quadro(servicos.gerar_imagem(prompt, refs, formato, modelo), formato)
        except Exception as exc:  # noqa: BLE001 - quadro recusado não derruba a prévia inteira
            falhas.append(f"K{k}: {exc}")
            doc.set({"indice": k, "prompt": prompt, "versao": versao - 1, "gcs_uri": (q or {}).get("gcs_uri"),
                     "pendente": True, "erro": str(exc)[:300]}, merge=True)
            continue
        gasto += float(precos["imagem"])
        uri = servicos.salvar(f"tmp/{projeto_id}/keyframes/K{k:02d}_v{versao}.png", png, "image/png")
        imagens[k] = png
        registro = {"indice": k, "prompt": prompt, "versao": versao, "gcs_uri": uri, "pendente": False,
                    "erro": None, "usa_referencias": [f"K{j}" for j in ((k - 1,) if k > 0 else ()) + ((0,) if k > 1 else ())]}
        doc.set(registro, merge=True)
        quadros[k] = {**(q or {}), **registro}
    return gasto, falhas


def _linha_do_tempo(cenas, servicos) -> tuple[bytes, int]:
    """Narração completa: cada cena ocupa exatamente a duração do seu clipe."""
    taxa, partes = 24000, []
    for c in cenas:
        pcm = b""
        if c.get("audio_gcs"):
            pcm, taxa = midia.wav_para_pcm(servicos.ler(c["audio_gcs"]))
        total = int(c.get("duracao_s") or 4) * taxa * 2
        partes.append(pcm[:total] + b"\x00" * max(total - len(pcm), 0))
    return b"".join(partes), taxa


def _publicar(ref, projeto, cenas, quadros, servicos, precos, projeto_id, falhas) -> dict:
    n = int(projeto.get("previa_versao") or 0) + 1
    titulo = projeto.get("titulo") or "Vídeo"
    formato = projeto.get("formato") or "16:9"
    cinza = midia.recortar_quadro(_png_cinza(), formato)
    pngs = [servicos.ler(quadros[k]["gcs_uri"]) if quadros.get(k, {}).get("gcs_uri") else cinza
            for k in range(len(cenas) + 1)]
    folha_png = folha.montar(pngs, cenas, formato, f"{titulo} — storyboard v{n}")
    pub_folha = servicos.publicar(f"{titulo} — storyboard v{n}.png", folha_png, "image/png")
    pcm, taxa = _linha_do_tempo(cenas, servicos)
    pub_audio = servicos.publicar(f"{titulo} — narração v{n}.mp3",
                                  midia.wav_para_mp3(midia.pcm_para_wav(pcm, taxa)), "audio/mpeg")

    est = estimativa.estimar([int(c.get("duracao_s") or 4) for c in cenas], modo=projeto.get("modo") or "padrao",
                             resolucao=projeto.get("resolucao") or "720p", precos=precos)
    dividir = [c["ordem"] for c in cenas if c.get("dividir")]
    avisos = []
    if dividir:
        avisos.append(f"Narração longa demais para 8 s nas cenas {dividir}: encurte o texto com video_ajustar.")
    if est["custo_estimado_usd"] > float(precos["teto_projeto_usd"]):
        avisos.append(f"Com as durações reais, a estimativa (US$ {est['custo_estimado_usd']:.2f}) passou do teto "
                      f"por projeto — encurte antes de renderizar.")
    campos = {"previa_versao": n, "folha_contato_drive_id": pub_folha["id"], "folha_contato_link": pub_folha["link"],
              "narracao_drive_id": pub_audio["id"], "narracao_link": pub_audio["link"], "estimativa": est,
              "custo_estimado_usd": est["custo_estimado_usd"], "orcamento_usd": est["teto_projeto_usd"],
              "previa_falhas": falhas}
    resposta = {
        "status": "ok",
        "projeto_id": projeto_id,
        "estado": vp.AGUARDANDO_STORYBOARD,
        "previa_versao": n,
        "folha_contato": {"drive_id": pub_folha["id"], "link": pub_folha["link"]},
        "narracao": {"drive_id": pub_audio["id"], "link": pub_audio["link"]},
        "cenas": [{"ordem": c["ordem"], "duracao_s": c.get("duracao_s"), "fala_s": c.get("audio_duracao_s"),
                   "dividir": bool(c.get("dividir"))} for c in cenas],
        "estimativa": est,
        "falhas": falhas,
        "avisos": avisos,
    }
    return {"campos": campos, "resposta": resposta}


def _png_cinza() -> bytes:
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (1280, 720), (200, 200, 200)).save(buf, "PNG")
    return buf.getvalue()


# --- ajustes --------------------------------------------------------------------------

def ajustar(db, projeto_id: str, uid: str | None, servicos: midia.Servicos, *, cenas: list | None = None,
            quadros: list | None = None, precos: dict | None = None) -> dict:
    """Aplica mudanças do storyboard e regera só o que elas afetam.

    - Narração nova → nova versão da cena → a narração dela é refeita.
    - Descrição visual nova da cena i → o quadro final dela (Ki) é refeito; na cena 1, também o K0.
    - Instrução para um quadro (`quadros: [{indice, instrucao}]`) → só esse quadro é refeito.
    Repetir o mesmo ajuste não muda nada (texto igual não gera versão nova).
    """
    projeto_id = (projeto_id or "").strip()
    ref, projeto, cenas_atuais = _carregar(db, projeto_id, uid)
    if ref is None:
        return {"status": "nao_encontrado", "erro": f"Projeto {projeto_id!r} não encontrado."}
    if projeto.get("status") not in (vp.AGUARDANDO_STORYBOARD, vp.ERRO):
        return {"status": "recusado", "estado": projeto.get("status"),
                "erro": "Ajustes só com o storyboard pronto (estado aguardando_storyboard)."}
    por_ordem = {c["ordem"]: c for c in cenas_atuais}
    n = len(cenas_atuais)
    mudancas, erros = [], []
    batch = db.batch()

    for item in cenas or []:
        item = item if isinstance(item, dict) else {}
        try:
            ordem = int(item.get("ordem"))
        except (TypeError, ValueError):
            erros.append(f"Cena sem 'ordem' válida: {item!r}")
            continue
        cena = por_ordem.get(ordem)
        if cena is None:
            erros.append(f"Cena {ordem} não existe (o projeto tem {n}).")
            continue
        alteracoes = {}
        if "narracao" in item and str(item["narracao"] or "").strip() != cena.get("narracao"):
            alteracoes["narracao"] = str(item["narracao"] or "").strip()
            alteracoes["versao"] = int(cena.get("versao") or 1) + 1
        for campo in ("descricao_visual", "prompt_video"):
            if campo in item and str(item[campo] or "").strip() != (cena.get(campo) or ""):
                alteracoes[campo] = str(item[campo] or "").strip()
        if not alteracoes:
            continue
        batch.update(ref.collection("cenas").document(vp.id_cena(ordem)), alteracoes)
        if "descricao_visual" in alteracoes:
            for k in ((0, ordem) if ordem == 1 else (ordem,)):
                batch.set(ref.collection("keyframes").document(f"K{k:02d}"), {"indice": k, "pendente": True},
                          merge=True)
        mudancas.append(f"cena {ordem}: {', '.join(sorted(alteracoes))}")

    for item in quadros or []:
        item = item if isinstance(item, dict) else {}
        try:
            k = int(item.get("indice"))
        except (TypeError, ValueError):
            erros.append(f"Quadro sem 'indice' válido: {item!r}")
            continue
        if not 0 <= k <= n:
            erros.append(f"Quadro K{k} não existe (vai de K0 a K{n}).")
            continue
        instrucao = str(item.get("instrucao") or "").strip()
        if not instrucao:
            erros.append(f"K{k}: informe 'instrucao' com o que mudar.")
            continue
        batch.set(ref.collection("keyframes").document(f"K{k:02d}"),
                  {"indice": k, "pendente": True, "instrucao": instrucao}, merge=True)
        mudancas.append(f"K{k}: {instrucao[:60]}")

    if erros:
        return {"status": "invalido", "erros": erros}
    if not mudancas:
        return {"status": "ok", "mensagem": "Nada mudou: o storyboard já está assim.", "projeto_id": projeto_id}
    batch.commit()
    resultado = gerar_previa(db, projeto_id, uid, servicos, precos=precos)
    return {**resultado, "ajustes_aplicados": mudancas}


def resposta_tool(resultado: dict):
    """Formato de volta das tools longas (rodam como job e são lidas por `consultar_job`).

    Sucesso vira texto JSON — o `resultado` do `consultar_job` é publicado como
    string. Falha vira dict com `erro`, que o `mcp_jobs` grava como job em erro.
    """
    if resultado.get("status") == "ok":
        return json.dumps(resultado, ensure_ascii=False, default=str)
    motivo = resultado.get("erro") or "; ".join(resultado.get("erros") or []) or "falha sem detalhe"
    return {**resultado, "erro": motivo}
