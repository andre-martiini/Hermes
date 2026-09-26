"""Prévia do storyboard: narração por cena, quadros-chave, folha de contato e MP3.

Ordem (o áudio vem antes do vídeo): a narração de cada cena, com o silêncio das
pontas aparado, define a duração do clipe (4, 6 ou 8 s); os quadros K0..KN definem
o começo e o fim de cada clipe. A cena i vai de K(i-1) a K(i).

Garantias (revisão adversária da Fase 2, 26/09/2026):
- Só refaz o que falta: narração de cena sem áudio da versão atual, quadro sem
  imagem ou marcado `pendente` por `ajustar` — e objeto que o bucket já apagou
  (`tmp/` some em 30 dias) conta como faltando.
- Antes de gastar, soma o custo de tudo o que vai gerar e recusa se passar do
  teto por prévia ou do teto acumulado de prévias do projeto.
- Cada item pago grava o próprio checkpoint E o próprio custo no mesmo commit:
  uma prévia que cai no meio (erro, job morto no limite de 540 s) nunca paga duas
  vezes pelo que já saiu e nunca deixa custo sem registro.
- Narração ou quadro recusado vira falha daquele item, não da prévia inteira.
- A prévia para sozinha antes do limite do job e pode ser continuada.
"""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

from firebase_admin import firestore

from video import estimativa, folha, midia
from video import projeto as vp

PARALELISMO_TTS = 4
# Um job de prévia dura no máximo 540 s; passado isso sem terminar, outro pode assumir.
PREVIA_TRAVADA_APOS = timedelta(minutes=10)
# Folga para publicar a folha e o MP3 antes do limite de 540 s do job.
PRAZO_GERACAO_S = 420
ESTADOS_DE_ENTRADA = {vp.ROTEIRO, vp.AGUARDANDO_STORYBOARD, vp.ERRO}


class PrazoEsgotado(Exception):
    pass


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


def audio_valido(cena: dict) -> bool:
    return bool(cena.get("audio_gcs")) and cena.get("audio_versao") == cena.get("versao")


def precisa_audio(cena: dict) -> bool:
    return bool(cena.get("narracao")) and not audio_valido(cena)


def precisa_quadro(q: dict | None) -> bool:
    return q is None or not q.get("gcs_uri") or bool(q.get("pendente"))


def _descartar_sumidos(cenas: list[dict], quadros: dict[int, dict], servicos) -> None:
    """Checkpoint que aponta para objeto apagado pelo ciclo de vida do bucket = refazer."""
    for c in cenas:
        if c.get("audio_gcs") and not servicos.existe(c["audio_gcs"]):
            c["audio_gcs"] = None
    for q in quadros.values():
        if q.get("gcs_uri") and not servicos.existe(q["gcs_uri"]):
            q["gcs_uri"] = None


def prompt_quadro(projeto: dict, cenas: list[dict], k: int, instrucao: str | None = None) -> str:
    """Prompt de UM quadro, com a cena primeiro e a bíblia como apoio.

    Duas prévias reais (26/09/2026) mostraram o modelo desenhando a personagem duas
    vezes e acrescentando pessoas que ninguém pediu: (1) o prompt descrevia o fim
    de uma cena e o começo da seguinte — agora cada quadro é um único instante; e
    (2) a lista de personagens da bíblia e as imagens de referência eram lidas
    como "ponha todos estes na imagem" / "copie esta composição". Por isso a cena
    vem antes de tudo, com a ordem de mostrar só o que ela pede, e a bíblia e as
    referências valem só para estilo e aparência.
    """
    b = projeto.get("biblia") or {}
    cena = cenas[0] if k == 0 else cenas[k - 1]
    momento = "Primeiro instante do vídeo" if k == 0 else f"Último instante da cena {k}"
    partes = [
        "Ilustração de UM único quadro de vídeo (uma cena contínua, sem painéis nem montagem).",
        f"{momento}: {cena.get('descricao_visual')}",
        "Mostre SOMENTE o que a descrição acima pede: nenhuma pessoa, objeto ou texto a mais. "
        "Cada pessoa aparece no máximo uma vez.",
        f"Estilo: {b.get('estilo')}.",
    ]
    if b.get("paleta"):
        partes.append(f"Paleta: {b['paleta']}.")
    if b.get("personagens"):
        partes.append("Aparência fixa das personagens — vale SÓ para quem a cena menciona; quem não é "
                      "mencionado não aparece: " + "; ".join(b["personagens"]) + ".")
    if k > 0:
        partes.append("As imagens anexas são referência de estilo e da aparência das personagens: mantenha "
                      "rosto, cabelo, roupa e traço idênticos, mas NÃO copie a composição, o cenário nem as "
                      "outras pessoas delas.")
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
        # `renderizavel` só volta a True quando a folha de contato e o MP3 forem publicados:
        # uma prévia que falha no meio nunca deixa o projeto parecendo aprovado (revisão da Fase 4).
        tx.update(ref, {"status": vp.PREVIA_GERANDO, "previa_iniciada_em": agora, "erro": None,
                        "renderizavel": False, "atualizado_em": firestore.SERVER_TIMESTAMP})

    _txn(transaction)


def _registrar(db, ref, doc_ref, campos: dict, custo: float, *, merge: bool = False, tipo: str = "previa"):
    """Checkpoint do item, custo no projeto e uso do dia — tudo no mesmo commit."""
    from video import uso

    batch = db.batch()
    if merge:
        batch.set(doc_ref, campos, merge=True)
    else:
        batch.update(doc_ref, campos)
    if custo:
        batch.update(ref, {"custo_real_usd": firestore.Increment(round(custo, 4)),
                           "custo_previa_usd": firestore.Increment(round(custo, 4))})
        dia_ref, dia = uso.ref_dia(db)
        batch.set(dia_ref, uso.campos(custo, tipo, dia), merge=True)
    batch.commit()


def gerar_previa(db, projeto_id: str, uid: str | None, servicos: midia.Servicos, *,
                 precos: dict | None = None, agora: datetime | None = None,
                 prazo_s: float = PRAZO_GERACAO_S) -> dict:
    agora = agora or _agora()
    inicio = time.monotonic()
    projeto_id = (projeto_id or "").strip()
    ref, projeto, cenas = _carregar(db, projeto_id, uid)
    if ref is None:
        return {"status": "nao_encontrado", "erro": f"Projeto {projeto_id!r} não encontrado."}
    if not cenas:
        return {"status": "erro", "erro": "Projeto sem cenas."}
    precos = precos or estimativa.carregar_precos(db)
    quadros = _quadros(ref)
    _descartar_sumidos(cenas, quadros, servicos)

    custo, n_tts, n_img = custo_previsto(cenas, quadros, precos)
    teto = float(precos["teto_previa_usd"])
    if custo > teto:
        return {"status": "recusado", "erro": f"Esta prévia custaria US$ {custo:.2f} ({n_tts} narrações, "
                f"{n_img} quadros), acima do teto de US$ {teto:.2f} por prévia."}
    ja_gasto = float(projeto.get("custo_previa_usd") or 0)
    teto_projeto = float(precos["teto_previa_projeto_usd"])
    if ja_gasto + custo > teto_projeto:
        return {"status": "recusado", "erro": f"Prévias deste projeto já custaram US$ {ja_gasto:.2f}; mais "
                f"US$ {custo:.2f} passaria do teto de US$ {teto_projeto:.2f} em prévias por projeto."}
    try:
        _entrar(db, projeto_id, agora)
    except vp.ErroVideo as exc:
        return {"status": "recusado", "erro": str(exc), "estado": projeto.get("status")}

    def restante():
        return prazo_s - (time.monotonic() - inicio)

    gasto, falhas = 0.0, []
    try:
        g, f = _gerar_narracoes(db, ref, projeto, cenas, servicos, precos, projeto_id)
        gasto, falhas = gasto + g, falhas + f
        g, f = _gerar_quadros(db, ref, projeto, cenas, quadros, servicos, precos, projeto_id, restante)
        gasto, falhas = gasto + g, falhas + f
        resultado = _publicar(ref, projeto, cenas, _quadros(ref), servicos, precos, projeto_id, falhas)
    except PrazoEsgotado:
        # O que saiu já está gravado e pago; a próxima chamada continua de onde parou.
        motivo = ("Prévia parcial: o tempo do job acabou antes de gerar todos os quadros. Chame "
                  "video_gerar_previa de novo para continuar — o que já foi gerado não é pago outra vez.")
        _para_erro(db, projeto_id, motivo)
        return {"status": "parcial", "erro": motivo, "gasto_usd": round(gasto, 2)}
    except Exception as exc:  # noqa: BLE001 - qualquer falha vira estado `erro`; o gasto já está registrado
        _para_erro(db, projeto_id, f"prévia: {exc}"[:500])
        return {"status": "erro", "erro": f"A prévia falhou: {exc}", "gasto_usd": round(gasto, 2)}

    try:
        vp.transicionar(db, projeto_id, vp.AGUARDANDO_STORYBOARD, de={vp.PREVIA_GERANDO},
                        campos=resultado["campos"])
    except vp.ErroVideo as exc:
        # Cancelado (ou assumido) enquanto rodava: os arquivos saíram, mas o projeto não é mais nosso.
        return {"status": "erro", "erro": f"O projeto mudou de estado durante a prévia: {exc}",
                "gasto_usd": round(gasto, 2)}
    return {**resultado["resposta"], "gasto_desta_previa_usd": round(gasto, 2),
            "narracoes_geradas": n_tts - sum(1 for f in falhas if f.startswith("cena")),
            "quadros_gerados": n_img - sum(1 for f in falhas if f.startswith("K"))}


def _para_erro(db, projeto_id, motivo):
    try:
        vp.transicionar(db, projeto_id, vp.ERRO, de={vp.PREVIA_GERANDO}, campos={"erro": motivo})
    except vp.ErroVideo:
        pass


def _gerar_narracoes(db, ref, projeto, cenas, servicos, precos, projeto_id) -> tuple[float, list[str]]:
    pendentes = [c for c in cenas if precisa_audio(c)]
    if not pendentes:
        return 0.0, []
    voz, modelo = projeto.get("voz") or {}, precos["modelo_tts"]
    preco = float(precos["tts_por_cena"])
    gasto, falhas = 0.0, []
    with ThreadPoolExecutor(max_workers=PARALELISMO_TTS) as pool:
        futuros = {pool.submit(servicos.gerar_fala, c["narracao"], voz, modelo): c for c in pendentes}
        for fut in as_completed(futuros):
            cena = futuros[fut]
            try:
                fala = fut.result()
            except Exception as exc:  # noqa: BLE001 - uma narração recusada não descarta as outras
                falhas.append(f"cena {cena['ordem']}: narração não gerada ({exc})"[:300])
                continue
            pcm = midia.aparar_silencio(fala.pcm, fala.taxa)
            dur = midia.duracao_pcm(pcm, fala.taxa)
            clipe = estimativa.duracao_clipe(dur)
            uri = servicos.salvar(f"tmp/{projeto_id}/audio/{vp.id_cena(cena['ordem'])}_v{cena['versao']}.wav",
                                  midia.pcm_para_wav(pcm, fala.taxa), "audio/wav")
            campos = {"audio_gcs": uri, "audio_versao": cena["versao"], "audio_duracao_s": round(dur, 2),
                      "duracao_s": clipe or 8, "dividir": clipe is None}
            _registrar(db, ref, ref.collection("cenas").document(vp.id_cena(cena["ordem"])), campos, preco,
                       tipo="narracao")
            gasto += preco
            cena.update(campos)
    return gasto, falhas


def _gerar_quadros(db, ref, projeto, cenas, quadros, servicos, precos, projeto_id, restante) -> tuple[float, list[str]]:
    """Sequencial: cada quadro usa o anterior (e o K0) como referência de identidade."""
    formato, modelo = projeto.get("formato") or "16:9", precos["modelo_imagem"]
    preco = float(precos["imagem"])
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
        if restante() <= 0:
            raise PrazoEsgotado()
        refs = [r for r in (imagem(k - 1) if k > 0 else None, imagem(0) if k > 1 else None) if r]
        instrucao = (q or {}).get("instrucao")
        prompt = prompt_quadro(projeto, cenas, k, instrucao)
        versao = int((q or {}).get("versao") or 0) + 1
        doc = ref.collection("keyframes").document(f"K{k:02d}")
        try:
            bruto = servicos.gerar_imagem(prompt, refs, formato, modelo)
        except Exception as exc:  # noqa: BLE001 - recusado pelo filtro não é cobrado nem derruba a prévia
            falhas.append(f"K{k}: {exc}"[:300])
            _registrar(db, ref, doc, {"indice": k, "pendente": True, "erro": str(exc)[:300]}, 0.0, merge=True)
            continue
        # Daqui para baixo a imagem já foi paga: qualquer falha ainda registra o custo.
        try:
            png = midia.recortar_quadro(bruto, formato)
            uri = servicos.salvar(f"tmp/{projeto_id}/keyframes/K{k:02d}_v{versao}.png", png, "image/png")
        except Exception as exc:  # noqa: BLE001
            falhas.append(f"K{k}: imagem gerada mas não gravada ({exc})"[:300])
            _registrar(db, ref, doc, {"indice": k, "pendente": True, "erro": str(exc)[:300]}, preco, merge=True,
                       tipo="quadro")
            gasto += preco
            continue
        registro = {"indice": k, "prompt": prompt, "versao": versao, "gcs_uri": uri, "pendente": False,
                    "erro": None, "instrucao": None, "instrucao_aplicada": instrucao,
                    "usa_referencias": [f"K{j}" for j in ((k - 1,) if k > 0 else ()) + ((0,) if k > 1 else ())]}
        _registrar(db, ref, doc, registro, preco, merge=True, tipo="quadro")
        gasto += preco
        imagens[k] = png
        quadros[k] = {**(q or {}), **registro}
    return gasto, falhas


def _linha_do_tempo(cenas, servicos) -> tuple[bytes, int]:
    """Narração completa: cada cena ocupa exatamente a duração do seu clipe.

    Só entra o áudio da versão atual do texto: cena com narração removida (ou
    ainda sem áudio novo) vira silêncio, nunca o áudio antigo.
    """
    taxa, partes = None, []
    blocos = []
    for c in cenas:
        pcm, t = b"", None
        if audio_valido(c):
            pcm, t = midia.wav_para_pcm(servicos.ler(c["audio_gcs"]))
            if taxa is None:
                taxa = t
            elif t != taxa:
                raise ValueError(f"Cena {c.get('ordem')}: taxa de amostragem {t} ≠ {taxa}.")
        blocos.append((c, pcm))
    taxa = taxa or 24000
    for c, pcm in blocos:
        total = int(c.get("duracao_s") or 4) * taxa * 2
        partes.append(pcm[:total] + b"\x00" * max(total - len(pcm), 0))
    return b"".join(partes), taxa


def _publicar(ref, projeto, cenas, quadros, servicos, precos, projeto_id, falhas) -> dict:
    n = int(projeto.get("previa_versao") or 0) + 1
    titulo = projeto.get("titulo") or "Vídeo"
    formato = projeto.get("formato") or "16:9"
    cinza = midia.recortar_quadro(_png_cinza(), formato)

    def png(k):
        uri = (quadros.get(k) or {}).get("gcs_uri")
        if not uri or (quadros[k].get("pendente") and not servicos.existe(uri)):
            return cinza  # quadro que não saiu nesta prévia e cujo antigo o bucket já apagou
        return servicos.ler(uri)

    pngs = [png(k) for k in range(len(cenas) + 1)]
    folha_png = folha.montar(pngs, cenas, formato, f"{titulo} — storyboard v{n}")
    pub_folha = servicos.publicar(f"{titulo} — storyboard v{n}.png", folha_png, "image/png")
    pcm, taxa = _linha_do_tempo(cenas, servicos)
    pub_audio = servicos.publicar(f"{titulo} — narração v{n}.mp3",
                                  midia.wav_para_mp3(midia.pcm_para_wav(pcm, taxa)), "audio/mpeg")

    est = estimativa.estimar([int(c.get("duracao_s") or 4) for c in cenas], modo=projeto.get("modo") or "padrao",
                             resolucao=projeto.get("resolucao") or "720p", precos=precos)
    dividir = [c["ordem"] for c in cenas if c.get("dividir")]
    teto_projeto = float(precos["teto_projeto_usd"])
    renderizavel = est["custo_estimado_usd"] <= teto_projeto and not dividir and not falhas
    avisos = []
    if dividir:
        avisos.append(f"Narração longa demais para 8 s nas cenas {dividir}: encurte o texto com video_ajustar.")
    if est["custo_estimado_usd"] > teto_projeto:
        avisos.append(f"Com as durações reais, a estimativa (US$ {est['custo_estimado_usd']:.2f}) passou do teto "
                      f"por projeto (US$ {teto_projeto:.2f}) — encurte antes de renderizar.")
    if falhas:
        avisos.append("Há itens que não saíram (veja `falhas`): ajuste o texto ou gere a prévia de novo.")
    campos = {"previa_versao": n, "folha_contato_drive_id": pub_folha["id"], "folha_contato_link": pub_folha["link"],
              "narracao_drive_id": pub_audio["id"], "narracao_link": pub_audio["link"], "estimativa": est,
              "custo_estimado_usd": est["custo_estimado_usd"], "previa_falhas": falhas, "renderizavel": renderizavel}
    # O orçamento só acompanha a estimativa quando ela cabe no teto; acima dele o
    # projeto fica marcado como não renderizável em vez de ganhar um orçamento menor
    # que a estimativa.
    if est["custo_estimado_usd"] <= teto_projeto:
        campos["orcamento_usd"] = est["teto_projeto_usd"]
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
        "renderizavel": renderizavel,
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

def _inteiro(valor) -> int | None:
    """Só inteiros de verdade: `True` e `1.9` não podem virar a cena/quadro 1."""
    if isinstance(valor, bool):
        return None
    if isinstance(valor, int):
        return valor
    if isinstance(valor, float) and valor.is_integer():
        return int(valor)
    if isinstance(valor, str) and valor.strip().isdigit():
        return int(valor.strip())
    return None


def ajustar(db, projeto_id: str, uid: str | None, servicos: midia.Servicos, *, cenas: list | None = None,
            quadros: list | None = None, precos: dict | None = None) -> dict:
    """Aplica mudanças do storyboard e regera só o que elas afetam.

    - Narração nova → nova versão da cena → a narração dela é refeita. Narração
      vazia remove o áudio (a cena fica em silêncio, com clipe de 4 s).
    - Descrição visual nova da cena i → o quadro final dela (Ki) é refeito; na cena 1, também o K0.
    - Instrução para um quadro (`quadros: [{indice, instrucao}]`) → só esse quadro é refeito.
    Campo ausente ou `null` não muda nada. Repetir o mesmo ajuste não muda nem gasta nada.
    """
    projeto_id = (projeto_id or "").strip()
    ref, projeto, cenas_atuais = _carregar(db, projeto_id, uid)
    if ref is None:
        return {"status": "nao_encontrado", "erro": f"Projeto {projeto_id!r} não encontrado."}
    if projeto.get("status") not in (vp.AGUARDANDO_STORYBOARD, vp.ERRO):
        return {"status": "recusado", "estado": projeto.get("status"),
                "erro": "Ajustes só com o storyboard pronto (estado aguardando_storyboard)."}
    por_ordem = {c["ordem"]: c for c in cenas_atuais}
    quadros_atuais = _quadros(ref)
    n = len(cenas_atuais)
    mudancas, erros = [], []
    batch = db.batch()

    for item in cenas or []:
        item = item if isinstance(item, dict) else {}
        ordem = _inteiro(item.get("ordem"))
        if ordem is None:
            erros.append(f"Cena sem 'ordem' válida: {item!r}")
            continue
        cena = por_ordem.get(ordem)
        if cena is None:
            erros.append(f"Cena {ordem} não existe (o projeto tem {n}).")
            continue
        alteracoes = {}
        nova = item.get("narracao")
        if nova is not None and str(nova).strip() != (cena.get("narracao") or ""):
            alteracoes["narracao"] = str(nova).strip()
            alteracoes["versao"] = int(cena.get("versao") or 1) + 1
            if not alteracoes["narracao"]:
                alteracoes.update({"audio_gcs": None, "audio_versao": None, "audio_duracao_s": None,
                                   "duracao_s": 4, "dividir": False})
        for campo in ("descricao_visual", "prompt_video"):
            valor = item.get(campo)
            if valor is not None and str(valor).strip() != (cena.get(campo) or ""):
                alteracoes[campo] = str(valor).strip()
        if not alteracoes:
            continue
        batch.update(ref.collection("cenas").document(vp.id_cena(ordem)), alteracoes)
        if "descricao_visual" in alteracoes:
            for k in ((0, ordem) if ordem == 1 else (ordem,)):
                batch.set(ref.collection("keyframes").document(f"K{k:02d}"),
                          {"indice": k, "pendente": True, "instrucao": None}, merge=True)
        mudancas.append(f"cena {ordem}: {', '.join(sorted(c for c in alteracoes if c in ('narracao', 'descricao_visual', 'prompt_video')))}")

    for item in quadros or []:
        item = item if isinstance(item, dict) else {}
        k = _inteiro(item.get("indice"))
        if k is None:
            erros.append(f"Quadro sem 'indice' válido: {item!r}")
            continue
        if not 0 <= k <= n:
            erros.append(f"Quadro K{k} não existe (vai de K0 a K{n}).")
            continue
        instrucao = str(item.get("instrucao") or "").strip()
        if not instrucao:
            erros.append(f"K{k}: informe 'instrucao' com o que mudar.")
            continue
        atual = quadros_atuais.get(k) or {}
        if instrucao in (atual.get("instrucao_aplicada"), atual.get("instrucao")):
            continue  # a mesma instrução já foi aplicada (ou já está na fila): não paga de novo
        batch.set(ref.collection("keyframes").document(f"K{k:02d}"),
                  {"indice": k, "pendente": True, "instrucao": instrucao}, merge=True)
        mudancas.append(f"K{k}: {instrucao[:60]}")

    if erros:
        return {"status": "invalido", "erros": erros}
    if mudancas:
        batch.commit()
    else:
        # Sem mudança nova, mas talvez com ajuste de antes que não chegou a ser gerado
        # (prévia recusada ou interrompida): nesse caso gera; senão, nada a fazer.
        if not any(precisa_audio(c) for c in cenas_atuais) and not any(
                precisa_quadro(quadros_atuais.get(k)) for k in range(n + 1)):
            return {"status": "ok", "mensagem": "Nada mudou: o storyboard já está assim.", "projeto_id": projeto_id}
    resultado = gerar_previa(db, projeto_id, uid, servicos, precos=precos)
    resultado = {**resultado, "ajustes_aplicados": mudancas}
    if resultado.get("status") != "ok" and mudancas:
        resultado["erro"] = (f"Ajustes salvos ({'; '.join(mudancas)}), mas a prévia não foi gerada: "
                             f"{resultado.get('erro')} Chame video_gerar_previa para gerar.")
    return resultado


def resposta_tool(resultado: dict):
    """Formato de volta das tools longas (rodam como job e são lidas por `consultar_job`).

    Sucesso vira texto JSON — o `resultado` do `consultar_job` é publicado como
    string. Falha vira dict com `erro`, que o `mcp_jobs` grava como job em erro.
    """
    if resultado.get("status") == "ok":
        return json.dumps(resultado, ensure_ascii=False, default=str)
    motivo = resultado.get("erro") or "; ".join(resultado.get("erros") or []) or "falha sem detalhe"
    return {**resultado, "erro": motivo}
