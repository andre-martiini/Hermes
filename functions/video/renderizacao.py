"""Renderização: clipes no Veo, em sequência, e montagem do vídeo final.

Roda no worker (Cloud Run Job `hermes-video-worker`, até 1 h), nunca dentro de
uma function. Garantias:

- Sequencial: o clipe 1 sai do K0; o clipe i sai do ÚLTIMO QUADRO REAL do clipe
  i-1 (o Lite não chega ao `lastFrame` pedido — Fase 0), com Ki como alvo final.
- Não paga duas vezes: o `operation_name` é gravado no clipe logo depois do envio
  e antes de esperar; uma execução retomada consulta a operação existente em vez
  de reenviar. Clipe `done` nunca é refeito.
- Trava de gasto antes de cada envio: custo real do projeto + custo do próximo
  clipe não pode passar do orçamento aprovado.
- Uma única execução por projeto (lease renovado a cada clipe); `cancelado` é
  respeitado entre clipes.
- Filtro de segurança: uma reescrita neutra do prompt e nova tentativa; barrado de
  novo, a cena fica `bloqueado` e o projeto vai para `erro` com o motivo.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from firebase_admin import firestore

from video import estimativa, midia, montagem
from video import projeto as vp
from video.veo_provider import PedidoClipe, VeoProvider

CONSULTA_INICIAL_S = 10
CONSULTA_MAXIMA_S = 30
ESPERA_MAXIMA_CLIPE_S = 12 * 60
MAX_TENTATIVAS_ERRO = 2


class Interrompido(Exception):
    """Parada limpa: cancelamento, perda do lease ou orçamento."""


@dataclass
class Avisos:
    """Efeitos da entrega que saem do bucket: vínculo com a ação e Telegram."""
    db: object = None
    anexados: list = field(default_factory=list)
    mensagens: list = field(default_factory=list)
    falso: bool = False

    def anexar(self, acao_id, **kw):
        if self.falso:
            self.anexados.append((acao_id, kw))
            return
        from video.entrega import anexar_na_acao

        anexar_na_acao(self.db, acao_id, **kw)

    def avisar(self, texto):
        if self.falso:
            self.mensagens.append(texto)
            return True
        from video.entrega import avisar_telegram

        return avisar_telegram(self.db, texto)


def prompt_clipe(projeto: dict, cena: dict) -> str:
    b = projeto.get("biblia") or {}
    partes = []
    if cena.get("prompt_video"):
        partes.append(cena["prompt_video"])
    partes.append(f"Cena: {cena.get('descricao_visual')}")
    partes.append(f"Estilo: {b.get('estilo')}.")
    partes.append("Movimento suave e natural do quadro inicial até o quadro final. Mantenha a personagem, a "
                  "roupa, o cenário e o estilo idênticos ao quadro inicial; nenhuma pessoa nova surge.")
    if b.get("evitar"):
        partes.append(f"Evite: {b['evitar']}.")
    partes.append("Sem texto, letreiros ou legendas na tela.")
    return "\n".join(partes)


def id_clipe(cena: dict) -> str:
    return f"{vp.id_cena(cena['ordem'])}_v{int(cena.get('clipe_versao') or 1)}"


def _estado(ref) -> dict:
    snap = ref.get()
    return (snap.to_dict() or {}) if snap.exists else {}


def renderizar(db, projeto_id: str, execucao_id: str, *, veo: VeoProvider, servicos: midia.Servicos,
               avisos: Avisos | None = None, precos: dict | None = None, dormir=time.sleep, relogio=time.monotonic,
               apos_clipe=None) -> dict:
    avisos = avisos or Avisos(db=db)
    ref = db.collection(vp.COLECAO).document(projeto_id)
    projeto = _estado(ref)
    if not projeto:
        return {"status": "nao_encontrado", "erro": f"Projeto {projeto_id!r} não encontrado."}
    if projeto.get("status") not in (vp.RENDERIZANDO, vp.MONTANDO):
        return {"status": "recusado", "erro": f"Projeto em {projeto.get('status')!r}, não em renderização."}
    if not vp.reivindicar_execucao(db, projeto_id, execucao_id):
        return {"status": "recusado", "erro": "Outra execução do worker está com este projeto."}
    precos = precos or estimativa.carregar_precos(db)
    try:
        cenas = sorted((c.to_dict() or {} for c in ref.collection("cenas").stream()), key=lambda c: c["ordem"])
        quadros = {int(q.get("indice")): q for q in (s.to_dict() or {} for s in ref.collection("keyframes").stream())}
        if projeto.get("status") == vp.RENDERIZANDO:
            _gerar_clipes(db, ref, projeto_id, execucao_id, projeto, cenas, quadros, veo, servicos, precos,
                          dormir, relogio, apos_clipe)
            vp.transicionar(db, projeto_id, vp.MONTANDO, de={vp.RENDERIZANDO})
        resultado = _montar_e_entregar(db, ref, projeto_id, _estado(ref), cenas, servicos, avisos)
        vp.transicionar(db, projeto_id, vp.CONCLUIDO, de={vp.MONTANDO}, campos=resultado["campos"])
        avisos.avisar(resultado["mensagem"])
        return resultado["resposta"]
    except Interrompido as exc:
        return {"status": "interrompido", "erro": str(exc)}
    except Exception as exc:  # noqa: BLE001 - falha vira `erro` do projeto; clipes pagos ficam guardados
        try:
            vp.transicionar(db, projeto_id, vp.ERRO, de={vp.RENDERIZANDO, vp.MONTANDO},
                            campos={"erro": f"renderização: {exc}"[:500]})
        except vp.ErroVideo:
            pass
        avisos.avisar(f"⚠️ Hermes Vídeo: a renderização de \"{projeto.get('titulo')}\" parou: {exc}"[:600])
        return {"status": "erro", "erro": f"A renderização falhou: {exc}"}
    finally:
        vp.liberar_execucao(db, projeto_id, execucao_id)


def _gerar_clipes(db, ref, projeto_id, execucao_id, projeto, cenas, quadros, veo, servicos, precos,
                  dormir, relogio, apos_clipe):
    modelo = projeto.get("modelo_video") or estimativa.modelo_do_modo(projeto.get("modo") or "padrao", precos)
    preco_s = estimativa.preco_segundo(modelo, projeto.get("resolucao") or "720p", precos)
    formato = projeto.get("formato") or "16:9"
    anterior: bytes | None = None
    for cena in cenas:
        cid = id_clipe(cena)
        doc = ref.collection("clipes").document(cid)
        snap = doc.get()
        clipe = (snap.to_dict() or {}) if snap.exists else {}
        if clipe.get("status") == "done" and clipe.get("gcs_uri") and servicos.existe(clipe["gcs_uri"]):
            anterior = servicos.ler(clipe["gcs_uri"])
            continue

        atual = _estado(ref)
        if atual.get("status") != vp.RENDERIZANDO:
            raise Interrompido(f"Projeto saiu de renderização ({atual.get('status')}) antes da cena {cena['ordem']}.")
        if not vp.renovar_execucao(db, projeto_id, execucao_id):
            raise Interrompido("Lease perdido para outra execução do worker.")

        inicio = servicos.ler(quadros[0]["gcs_uri"]) if cena["ordem"] == 1 else montagem.ultimo_quadro(anterior)
        fim_uri = (quadros.get(cena["ordem"]) or {}).get("gcs_uri")
        if not fim_uri:
            raise RuntimeError(f"Falta o quadro K{cena['ordem']} (gere a prévia de novo).")
        pedido = PedidoClipe(modelo=modelo, prompt=clipe.get("prompt") or prompt_clipe(projeto, cena),
                             imagem_inicio=midia.recortar_quadro(inicio, formato),
                             imagem_fim=servicos.ler(fim_uri), duracao_s=int(cena["duracao_s"]),
                             aspecto=formato, resolucao=projeto.get("resolucao") or "720p")
        custo = pedido.duracao_s * preco_s

        video = _executar_clipe(db, ref, doc, cid, cena, clipe, pedido, custo, veo, servicos, dormir, relogio,
                                projeto_id)
        anterior = video
        if apos_clipe:
            apos_clipe(cena["ordem"])


def _checar_orcamento(ref, custo: float, ordem: int):
    atual = _estado(ref)
    gasto, teto = float(atual.get("custo_real_usd") or 0), float(atual.get("orcamento_usd") or 0)
    if gasto + custo > teto + 1e-9:
        raise RuntimeError(f"Orçamento: o clipe da cena {ordem} (US$ {custo:.2f}) levaria o gasto de "
                           f"US$ {gasto:.2f} acima do orçamento de US$ {teto:.2f}.")


def _executar_clipe(db, ref, doc, cid, cena, clipe, pedido, custo, veo, servicos, dormir, relogio, projeto_id):
    """Envia (ou retoma) um clipe até ter o MP4 gravado. Devolve os bytes do vídeo."""
    tentativas = int(clipe.get("tentativas") or 0)
    reescrito = bool(clipe.get("reescrito"))
    operacao = clipe.get("operation_name") if clipe.get("status") == "submetido" else None
    while True:
        if not operacao:
            _checar_orcamento(ref, custo, cena["ordem"])
            operacao = veo.gerar_clipe(pedido)
            tentativas += 1
            # Gravado ANTES de esperar: uma execução retomada consulta esta operação em vez de reenviar.
            doc.set({"cena": cena["ordem"], "modelo": pedido.modelo, "prompt": pedido.prompt,
                     "duracao_s": pedido.duracao_s, "operation_name": operacao, "status": "submetido",
                     "tentativas": tentativas, "reescrito": reescrito, "enviado_em": firestore.SERVER_TIMESTAMP,
                     "erro": None}, merge=True)
        res = _esperar(veo, operacao, dormir, relogio)
        if res.bloqueado:
            if reescrito:
                doc.set({"status": "bloqueado", "erro": res.motivo_bloqueio}, merge=True)
                raise RuntimeError(f"Cena {cena['ordem']} barrada pelo filtro de segurança mesmo após reescrita: "
                                   f"{res.motivo_bloqueio}. Ajuste a descrição visual dessa cena.")
            pedido.prompt = servicos.reescrever_prompt(pedido.prompt, res.motivo_bloqueio or "")
            reescrito, operacao = True, None
            continue
        if res.erro:
            doc.set({"status": "erro", "erro": res.erro[:500]}, merge=True)
            if tentativas >= MAX_TENTATIVAS_ERRO:
                raise RuntimeError(f"Cena {cena['ordem']}: o Veo falhou {tentativas} vezes ({res.erro[:200]}).")
            operacao = None
            continue
        video = veo.baixar(res)
        uri = servicos.salvar(f"tmp/{projeto_id}/clipes/{cid}.mp4", video, "video/mp4")
        batch = db.batch()
        batch.set(doc, {"status": "done", "gcs_uri": uri, "custo_usd": round(custo, 4),
                        "concluido_em": firestore.SERVER_TIMESTAMP, "erro": None}, merge=True)
        batch.update(ref, {"custo_real_usd": firestore.Increment(round(custo, 4)),
                           "custo_render_usd": firestore.Increment(round(custo, 4))})
        batch.commit()
        return video


def _esperar(veo, operacao, dormir, relogio):
    inicio, espera = relogio(), CONSULTA_INICIAL_S
    while True:
        res = veo.consultar_operacao(operacao)
        if res.concluida:
            return res
        if relogio() - inicio > ESPERA_MAXIMA_CLIPE_S:
            # O clipe continua `submetido`: a próxima execução volta a consultar, sem reenviar.
            raise RuntimeError(f"O Veo não terminou {operacao} em {ESPERA_MAXIMA_CLIPE_S // 60} min.")
        dormir(espera)
        espera = min(espera + 5, CONSULTA_MAXIMA_S)


def _montar_e_entregar(db, ref, projeto_id, projeto, cenas, servicos, avisos):
    from video.previa import audio_valido

    clipes, narracoes, textos, duracoes = [], [], [], []
    for cena in cenas:
        clipe = (ref.collection("clipes").document(id_clipe(cena)).get().to_dict() or {})
        if clipe.get("status") != "done":
            raise RuntimeError(f"Cena {cena['ordem']} sem clipe pronto para montar.")
        clipes.append(servicos.ler(clipe["gcs_uri"]))
        duracoes.append(float(cena["duracao_s"]))
        narracoes.append(midia.wav_para_pcm(servicos.ler(cena["audio_gcs"])) if audio_valido(cena) else None)
        textos.append(cena.get("narracao") or "")
    musica = None
    clima = (projeto.get("musica") or "nenhuma").strip().lower()
    if clima != "nenhuma":
        uri = f"gs://{midia.BUCKET}/musica/{clima}.mp3"
        musica = servicos.ler(uri) if servicos.existe(uri) else None

    mp4 = montagem.montar(clipes, duracoes, formato=projeto.get("formato") or "16:9", narracoes=narracoes,
                          textos=textos, legenda=bool(projeto.get("legenda")), musica=musica)
    uri_final = servicos.salvar(f"tmp/{projeto_id}/final.mp4", mp4, "video/mp4")
    titulo = projeto.get("titulo") or "Vídeo"
    pub = servicos.publicar(f"{titulo}.mp4", mp4, "video/mp4")
    total = montagem.duracao_total(duracoes)
    custo = float(_estado(ref).get("custo_real_usd") or 0)
    nota = (f"🎬 Hermes Vídeo: \"{titulo}\" pronto — {total:.0f} s, custo real US$ {custo:.2f}. "
            f"Link: {pub['link']}")
    if projeto.get("acao_id"):
        avisos.anexar(projeto["acao_id"], nome=f"{titulo}.mp4", link=pub["link"], drive_id=pub["id"], nota=nota)
    avisos_musica = [] if clima == "nenhuma" or musica else [f"Sem faixa '{clima}' no bucket: vídeo sem música."]
    return {
        "campos": {"video_drive_id": pub["id"], "video_link": pub["link"], "video_gcs": uri_final,
                   "duracao_final_s": total},
        "mensagem": nota,
        "resposta": {"status": "ok", "projeto_id": projeto_id, "estado": vp.CONCLUIDO, "video_link": pub["link"],
                     "duracao_s": total, "custo_real_usd": round(custo, 2), "avisos": avisos_musica},
    }
