"""Renderização: clipes no Veo, em sequência, e montagem do vídeo final.

Roda no worker (Cloud Run Job `hermes-video-worker`, até 1 h), nunca dentro de
uma function.

Sequencial: o clipe 1 sai do K0; o clipe i sai do ÚLTIMO QUADRO REAL do clipe i-1
(o Lite não chega ao `lastFrame` pedido — Fase 0), com Ki como alvo final.

Assinatura: cada clipe é identificado por um hash de tudo de que ele depende —
narração/versão da cena, duração, descrição, prompt de movimento, versão dos
quadros e o clipe anterior (de onde sai o quadro inicial). Ajustou a cena? É
outro clipe (documento novo, prompt novo). Refez o clipe i? O i+1 muda de
assinatura também, porque começa no fim do i. Clipe velho nunca entra no vídeo.

Nunca paga duas vezes (revisão adversária da Fase 3, 26/09/2026):
- Antes de enviar, grava a intenção (`enviando`, nº da tentativa) e manda o Veo
  gravar a saída num prefixo próprio da tentativa no bucket (testado: a Vertex
  grava em `{prefixo}/{id}/sample_0.mp4`). Numa retomada, antes de qualquer envio,
  procura saída nos prefixos das tentativas anteriores e a adota.
- Com o `operation_name` gravado, a retomada consulta a operação em vez de reenviar.
- A marcação `done` + custo é transacional: só conta se o clipe ainda estava na
  mesma tentativa e o lease ainda é desta execução.
- Status (cancelado?), lease e orçamento são conferidos antes de CADA envio,
  inclusive nas novas tentativas depois de bloqueio ou erro; o lease é renovado
  durante a espera.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from firebase_admin import firestore

from video import estimativa, midia, montagem
from video import projeto as vp
from video.veo_provider import PedidoClipe, VeoProvider

CONSULTA_INICIAL_S = 10
CONSULTA_MAXIMA_S = 30
ESPERA_MAXIMA_CLIPE_S = 12 * 60
# Tentativa em `enviando` sem saída no bucket há mais que isto: o envio não foi
# aceito (ou a operação morreu sem gerar) — pode tentar de novo.
ENVIO_ORFAO_APOS = timedelta(minutes=20)
MAX_ERROS_POR_EXECUCAO = 2
TOLERANCIA_DURACAO_S = 0.15

# Versão do contrato entre as functions e o worker. O worker roda numa imagem que
# a CI NÃO reconstrói (deploy_video_worker.bat): quando as functions passam a
# depender de algo novo no worker, sobem este número e gravam
# `worker_min_versao` no projeto; um worker mais velho recusa em vez de fazer a
# coisa errada em silêncio. 4 = Fase 4 (refação por cena e uso diário).
VERSAO_WORKER = 4


class Interrompido(Exception):
    """Parada limpa: cancelamento ou perda do lease."""


@dataclass
class Avisos:
    """Efeitos da entrega fora do bucket: vínculo com a ação e Telegram."""
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
    if cena.get("instrucao_video"):
        partes.append(f"Ajuste pedido: {cena['instrucao_video']}")
    partes.append(f"Cena: {cena.get('descricao_visual')}")
    partes.append(f"Estilo: {b.get('estilo')}.")
    partes.append("Movimento suave e natural do quadro inicial até o quadro final. Mantenha a personagem, a "
                  "roupa, o cenário e o estilo idênticos ao quadro inicial; nenhuma pessoa nova surge.")
    if b.get("evitar"):
        partes.append(f"Evite: {b['evitar']}.")
    partes.append("Sem texto, letreiros ou legendas na tela.")
    return "\n".join(partes)


def _hash(valores) -> str:
    return hashlib.sha1(json.dumps(valores, ensure_ascii=False, default=str).encode()).hexdigest()[:10]


def cadeia(projeto: dict, cena: dict, quadros: dict, cadeia_anterior: str | None) -> str:
    """O CONTEÚDO de que a cena depende (e que muda o quadro inicial da cena seguinte).

    Refazer uma cena com `video_refazer_cena` NÃO muda a cadeia: a cena seguinte
    continua com o seu clipe (e pode sobrar um salto pequeno na emenda — por isso
    a tool oferece `refazer_seguintes`). Mudar narração, duração, descrição ou
    quadros muda a cadeia, e a partir daí todas as cenas seguintes são outras.
    """
    k = cena["ordem"]
    return _hash([projeto.get("modelo_video"), projeto.get("formato"), projeto.get("resolucao"),
                  (projeto.get("biblia") or {}).get("estilo"), cena.get("versao"), cena.get("duracao_s"),
                  cena.get("descricao_visual"), cena.get("prompt_video"), (quadros.get(k) or {}).get("gcs_uri"),
                  (quadros.get(0) or {}).get("gcs_uri") if k == 1 else cadeia_anterior])


def assinatura(projeto: dict, cena: dict, quadros: dict, cadeia_anterior: str | None) -> str:
    """Identidade do clipe: a cadeia mais as refações pedidas para esta cena."""
    return _hash([cadeia(projeto, cena, quadros, cadeia_anterior), int(cena.get("refacao") or 0),
                  cena.get("instrucao_video")])


def clipes_pendentes(ref, projeto: dict, cenas: list[dict], quadros: dict) -> list[dict]:
    """Cenas cujo clipe ATUAL (pela assinatura) ainda não está pronto — o que o worker vai pagar."""
    faltam, cadeia_anterior = [], None
    for cena in cenas:
        cid = f"{vp.id_cena(cena['ordem'])}_{assinatura(projeto, cena, quadros, cadeia_anterior)}"
        cadeia_anterior = cadeia(projeto, cena, quadros, cadeia_anterior)
        snap = ref.collection("clipes").document(cid).get()
        if not (snap.exists and (snap.to_dict() or {}).get("status") == "done"):
            faltam.append(cena)
    return faltam


def pendencias(cenas: list[dict], quadros: dict) -> list[str]:
    """O que impede renderizar: tudo isso a prévia precisa resolver antes."""
    from video.previa import audio_valido

    faltas = []
    for c in cenas:
        if c.get("dividir"):
            faltas.append(f"cena {c['ordem']}: narração não cabe em 8 s")
        if c.get("narracao") and not audio_valido(c):
            faltas.append(f"cena {c['ordem']}: narração sem áudio da versão atual")
    for k in range(len(cenas) + 1):
        q = quadros.get(k) or {}
        if not q.get("gcs_uri") or q.get("pendente"):
            faltas.append(f"K{k}: quadro ausente ou pendente")
    return faltas


def _estado(ref) -> dict:
    snap = ref.get()
    return (snap.to_dict() or {}) if snap.exists else {}


def renderizar(db, projeto_id: str, execucao_id: str, *, veo: VeoProvider, servicos: midia.Servicos,
               avisos: Avisos | None = None, precos: dict | None = None, dormir=time.sleep, relogio=time.monotonic,
               agora=None, apos_clipe=None) -> dict:
    avisos = avisos or Avisos(db=db)
    agora = agora or (lambda: datetime.now(timezone.utc))
    ref = db.collection(vp.COLECAO).document(projeto_id)
    projeto = _estado(ref)
    if not projeto:
        return {"status": "nao_encontrado", "erro": f"Projeto {projeto_id!r} não encontrado."}
    if projeto.get("status") not in (vp.RENDERIZANDO, vp.MONTANDO):
        return {"status": "recusado", "erro": f"Projeto em {projeto.get('status')!r}, não em renderização."}
    if int(projeto.get("worker_min_versao") or 0) > VERSAO_WORKER:
        motivo = (f"Worker desatualizado (versão {VERSAO_WORKER}; o projeto exige "
                  f"{projeto.get('worker_min_versao')}): rode deploy_video_worker.bat e dispare de novo.")
        avisos.avisar(f"⚠️ Gaspar Vídeo: {motivo}")
        return {"status": "recusado", "erro": motivo}
    cenas = sorted((c.to_dict() or {} for c in ref.collection("cenas").stream()), key=lambda c: c["ordem"])
    quadros = {int(q.get("indice")): q for q in (s.to_dict() or {} for s in ref.collection("keyframes").stream())}
    faltas = pendencias(cenas, quadros)
    if projeto.get("status") == vp.RENDERIZANDO and (faltas or projeto.get("renderizavel") is False):
        return {"status": "recusado", "erro": "Projeto não está pronto para renderizar: "
                + ("; ".join(faltas) or "a prévia marcou renderizavel=false") + ". Gere a prévia de novo."}
    if not vp.reivindicar_execucao(db, projeto_id, execucao_id):
        return {"status": "recusado", "erro": "Outra execução do worker está com este projeto."}
    try:
        precos = precos or estimativa.carregar_precos(db)
        ctx = _Contexto(db, ref, projeto_id, execucao_id, veo, servicos, dormir, relogio, agora)
        if projeto.get("status") == vp.RENDERIZANDO:
            atuais = _gerar_clipes(ctx, projeto, cenas, quadros, precos, apos_clipe)
            vp.transicionar(db, projeto_id, vp.MONTANDO, de={vp.RENDERIZANDO}, campos={"clipes_atuais": atuais})
        resultado = _montar_e_entregar(ctx, _estado(ref), cenas, avisos)
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
        avisos.avisar(f"⚠️ Gaspar Vídeo: a renderização de \"{projeto.get('titulo')}\" parou: {exc}"[:600])
        return {"status": "erro", "erro": f"A renderização falhou: {exc}"}
    finally:
        vp.liberar_execucao(db, projeto_id, execucao_id)


@dataclass
class _Contexto:
    db: object
    ref: object
    projeto_id: str
    execucao_id: str
    veo: VeoProvider
    servicos: midia.Servicos
    dormir: object
    relogio: object
    agora: object

    def conferir(self, ordem: int):
        """Antes de qualquer envio pago e durante a espera: ainda é nosso e ainda está valendo?"""
        atual = _estado(self.ref)
        if atual.get("status") != vp.RENDERIZANDO:
            raise Interrompido(f"Projeto saiu de renderização ({atual.get('status')}) na cena {ordem}.")
        if not vp.renovar_execucao(self.db, self.projeto_id, self.execucao_id, agora=self.agora()):
            raise Interrompido("Lease perdido para outra execução do worker.")
        return atual


def _gerar_clipes(ctx: _Contexto, projeto, cenas, quadros, precos, apos_clipe) -> dict:
    modelo = projeto.get("modelo_video") or estimativa.modelo_do_modo(projeto.get("modo") or "padrao", precos)
    preco_s = estimativa.preco_segundo(modelo, projeto.get("resolucao") or "720p", precos)
    formato = projeto.get("formato") or "16:9"
    anterior_uri, anterior, cadeia_anterior = None, None, None
    atuais = {}
    for cena in cenas:
        cid = f"{vp.id_cena(cena['ordem'])}_{assinatura(projeto, cena, quadros, cadeia_anterior)}"
        cadeia_anterior = cadeia(projeto, cena, quadros, cadeia_anterior)
        doc = ctx.ref.collection("clipes").document(cid)
        snap = doc.get()
        clipe = (snap.to_dict() or {}) if snap.exists else {}
        if clipe.get("status") == "done" and clipe.get("gcs_uri") and ctx.servicos.existe(clipe["gcs_uri"]):
            anterior_uri, anterior = clipe["gcs_uri"], None
            atuais[vp.id_cena(cena["ordem"])] = cid
            continue
        if anterior is None and anterior_uri:
            anterior = ctx.servicos.ler(anterior_uri)
        inicio = ctx.servicos.ler(quadros[0]["gcs_uri"]) if cena["ordem"] == 1 else montagem.ultimo_quadro(anterior)
        pedido = PedidoClipe(modelo=modelo, prompt=prompt_clipe(projeto, cena),
                             imagem_inicio=midia.recortar_quadro(inicio, formato),
                             imagem_fim=ctx.servicos.ler(quadros[cena["ordem"]]["gcs_uri"]),
                             duracao_s=int(cena["duracao_s"]), aspecto=formato,
                             resolucao=projeto.get("resolucao") or "720p")
        uri = _executar_clipe(ctx, doc, cid, cena, clipe, pedido, pedido.duracao_s * preco_s)
        anterior_uri, anterior = uri, None
        atuais[vp.id_cena(cena["ordem"])] = cid
        if apos_clipe:
            apos_clipe(cena["ordem"])
    return atuais


def _prefixo(ctx: _Contexto, cid: str, tentativa: int) -> str:
    return f"gs://{midia.BUCKET}/tmp/{ctx.projeto_id}/veo/{cid}/t{tentativa}/"


def _saida_existente(ctx: _Contexto, cid: str, tentativas: int) -> tuple[str, int] | None:
    """Saída já gravada pelo Veo em alguma tentativa anterior (paga, mas talvez sem registro)."""
    for t in range(tentativas, 0, -1):
        mp4 = [u for u in ctx.servicos.listar(_prefixo(ctx, cid, t)) if u.endswith(".mp4")]
        if mp4:
            return mp4[0], t
    return None


def _executar_clipe(ctx: _Contexto, doc, cid, cena, clipe, pedido, custo) -> str:
    """Leva um clipe até `done` (ou erro/bloqueio) e devolve o `gs://` do MP4."""
    ordem = cena["ordem"]
    tentativas = int(clipe.get("tentativas") or 0)
    reescrito = bool(clipe.get("reescrito"))
    if clipe.get("prompt") and clipe.get("status") in ("enviando", "submetido", "bloqueado", "erro"):
        pedido.prompt = clipe["prompt"]  # mesma assinatura = mesma cena: continua a mesma tentativa
    if clipe.get("status") == "bloqueado" and reescrito:
        raise RuntimeError(f"Cena {ordem} barrada pelo filtro de segurança mesmo após reescrita: "
                           f"{clipe.get('erro')}. Ajuste a descrição visual dessa cena.")
    operacao = clipe.get("operation_name") if clipe.get("status") == "submetido" else None
    erros = 0

    achada = _saida_existente(ctx, cid, tentativas)
    if achada:
        return _concluir(ctx, doc, achada[0], custo, achada[1], None)
    if clipe.get("status") == "enviando" and not operacao:
        enviado = clipe.get("enviado_em")
        if isinstance(enviado, datetime) and ctx.agora() - enviado < ENVIO_ORFAO_APOS:
            raise RuntimeError(f"Cena {ordem}: envio da tentativa {tentativas} sem registro de operação há menos "
                               f"de {int(ENVIO_ORFAO_APOS.total_seconds() // 60)} min — pode estar gerando. Tente "
                               "de novo mais tarde; a saída será adotada sem novo pagamento.")

    while True:
        if not operacao:
            atual = ctx.conferir(ordem)
            gasto, teto = float(atual.get("custo_real_usd") or 0), float(atual.get("orcamento_usd") or 0)
            if gasto + custo > teto + 1e-9:
                raise RuntimeError(f"Orçamento: o clipe da cena {ordem} (US$ {custo:.2f}) levaria o gasto de "
                                   f"US$ {gasto:.2f} acima do orçamento de US$ {teto:.2f}.")
            tentativas += 1
            pedido.saida_gcs = _prefixo(ctx, cid, tentativas)
            # Intenção gravada ANTES de enviar: se o registro da operação se perder, a retomada
            # procura a saída neste prefixo em vez de pagar de novo.
            doc.set({"cena": ordem, "modelo": pedido.modelo, "prompt": pedido.prompt, "duracao_s": pedido.duracao_s,
                     "status": "enviando", "tentativas": tentativas, "reescrito": reescrito,
                     "saida_gcs": pedido.saida_gcs, "operation_name": None, "enviado_em": ctx.agora(),
                     "erro": None}, merge=True)
            # Só 429 (cota, pedido recusado de saída) repete o envio; um 503 pode chegar depois de
            # o pedido ter sido aceito, e repetir pagaria duas vezes.
            operacao = midia.com_retentativa(lambda: ctx.veo.gerar_clipe(pedido), dormir=ctx.dormir,
                                             passageiro=midia.cota_esgotada)
            midia.com_retentativa(lambda: doc.set({"operation_name": operacao, "status": "submetido"}, merge=True),
                                  esperas=(1, 3, 9), dormir=ctx.dormir)
            print(f"[video] cena {ordem} tentativa {tentativas}: {operacao}", flush=True)
        res = _esperar(ctx, operacao, ordem)
        if res.bloqueado:
            if reescrito:
                doc.set({"status": "bloqueado", "erro": res.motivo_bloqueio}, merge=True)
                raise RuntimeError(f"Cena {ordem} barrada pelo filtro de segurança mesmo após reescrita: "
                                   f"{res.motivo_bloqueio}. Ajuste a descrição visual dessa cena.")
            pedido.prompt = ctx.servicos.reescrever_prompt(pedido.prompt, res.motivo_bloqueio or "")
            reescrito, operacao = True, None
            doc.set({"status": "bloqueado", "reescrito": True, "prompt": pedido.prompt,
                     "erro": res.motivo_bloqueio}, merge=True)
            continue
        if res.erro:
            erros += 1
            doc.set({"status": "erro", "erro": res.erro[:500]}, merge=True)
            if erros >= MAX_ERROS_POR_EXECUCAO:
                raise RuntimeError(f"Cena {ordem}: o Veo falhou {erros} vezes seguidas ({res.erro[:200]}).")
            operacao = None
            continue
        uri = res.video_uri if (res.video_uri or "").startswith(f"gs://{midia.BUCKET}/") else None
        if uri is None:
            uri = ctx.servicos.salvar(f"tmp/{ctx.projeto_id}/clipes/{cid}.mp4", ctx.veo.baixar(res), "video/mp4")
        return _concluir(ctx, doc, uri, custo, tentativas, operacao)


def _concluir(ctx: _Contexto, doc, uri: str, custo: float, tentativa: int, operacao: str | None) -> str:
    """`done` + custo numa transação: só conta uma vez, e só se o lease ainda é desta execução."""
    transaction = vp._transacional(ctx.db)

    @firestore.transactional
    def _txn(tx):
        clipe = (doc.get(transaction=tx).to_dict() or {})
        projeto = (ctx.ref.get(transaction=tx).to_dict() or {})
        if clipe.get("status") == "done":
            return False  # outra execução já contou
        if (projeto.get("worker_execucao") or {}).get("id") != ctx.execucao_id:
            raise Interrompido("Lease perdido antes de registrar o clipe.")
        tx.set(doc, {"status": "done", "gcs_uri": uri, "custo_usd": round(custo, 4), "tentativa_final": tentativa,
                     "operation_name": operacao or clipe.get("operation_name"),
                     "concluido_em": firestore.SERVER_TIMESTAMP, "erro": None}, merge=True)
        tx.update(ctx.ref, {"custo_real_usd": firestore.Increment(round(custo, 4)),
                            "custo_render_usd": firestore.Increment(round(custo, 4))})
        tx.set(dia_ref, uso.campos(custo, "clipe", dia), merge=True)
        return True

    from video import uso

    dia_ref, dia = uso.ref_dia(ctx.db, ctx.agora())

    _txn(transaction)
    return uri


def _esperar(ctx: _Contexto, operacao: str, ordem: int):
    inicio, espera = ctx.relogio(), CONSULTA_INICIAL_S
    while True:
        res = ctx.veo.consultar_operacao(operacao)
        if res.concluida:
            return res
        if ctx.relogio() - inicio > ESPERA_MAXIMA_CLIPE_S:
            # O clipe fica `submetido`: a próxima execução volta a consultar, sem reenviar.
            raise RuntimeError(f"O Veo não terminou a cena {ordem} em {ESPERA_MAXIMA_CLIPE_S // 60} min.")
        ctx.dormir(espera)
        espera = min(espera + 5, CONSULTA_MAXIMA_S)
        # Renova o lease durante a espera (uma espera longa não pode entregar o projeto a outra execução).
        if not vp.renovar_execucao(ctx.db, ctx.projeto_id, ctx.execucao_id, agora=ctx.agora()):
            raise Interrompido("Lease perdido durante a espera do Veo.")


def _montar_e_entregar(ctx: _Contexto, projeto, cenas, avisos):
    from video.previa import audio_valido

    atuais = projeto.get("clipes_atuais") or {}
    clipes, narracoes, textos, duracoes = [], [], [], []
    for cena in cenas:
        cid = atuais.get(vp.id_cena(cena["ordem"]))
        clipe = (ctx.ref.collection("clipes").document(cid).get().to_dict() or {}) if cid else {}
        if clipe.get("status") != "done":
            raise RuntimeError(f"Cena {cena['ordem']} sem clipe pronto para montar.")
        dados = ctx.servicos.ler(clipe["gcs_uri"])
        medido = montagem.duracao(dados)
        if abs(medido - float(cena["duracao_s"])) > TOLERANCIA_DURACAO_S:
            raise RuntimeError(f"Cena {cena['ordem']}: o clipe tem {medido:.2f} s e a cena pede {cena['duracao_s']} s "
                               "(storyboard mudou depois da renderização?).")
        clipes.append(dados)
        duracoes.append(float(cena["duracao_s"]))
        narracoes.append(midia.wav_para_pcm(ctx.servicos.ler(cena["audio_gcs"])) if audio_valido(cena) else None)
        textos.append(cena.get("narracao") or "")
    musica = None
    clima = (projeto.get("musica") or "nenhuma").strip().lower()
    if clima != "nenhuma":
        uri = f"gs://{midia.BUCKET}/musica/{clima}.mp3"
        musica = ctx.servicos.ler(uri) if ctx.servicos.existe(uri) else None

    titulo = projeto.get("titulo") or "Vídeo"
    total = montagem.duracao_total(duracoes)
    avisos_resp = [] if clima == "nenhuma" or musica else [f"Sem faixa '{clima}' no bucket: vídeo sem música."]
    if projeto.get("video_drive_id"):
        # Retomada depois de publicar: não sobe outra cópia para o Drive.
        pub = {"id": projeto["video_drive_id"], "link": projeto.get("video_link")}
        uri_final = projeto.get("video_gcs")
    else:
        mp4 = montagem.montar(clipes, duracoes, formato=projeto.get("formato") or "16:9", narracoes=narracoes,
                              textos=textos, legenda=bool(projeto.get("legenda")), musica=musica)
        uri_final = ctx.servicos.salvar(f"tmp/{ctx.projeto_id}/final.mp4", mp4, "video/mp4")
        if _estado(ctx.ref).get("status") != vp.MONTANDO:
            raise Interrompido("Projeto saiu de montagem antes da publicação (cancelado?).")
        pub = ctx.servicos.publicar(f"{titulo}.mp4", mp4, "video/mp4")
        ctx.ref.update({"video_drive_id": pub["id"], "video_link": pub["link"], "video_gcs": uri_final})
    custo = float(_estado(ctx.ref).get("custo_real_usd") or 0)
    nota = (f"🎬 Gaspar Vídeo: \"{titulo}\" pronto — {total:.0f} s, custo real US$ {custo:.2f}. "
            f"Link: {pub['link']}")
    if projeto.get("acao_id") and not projeto.get("video_anexado"):
        try:
            avisos.anexar(projeto["acao_id"], nome=f"{titulo}.mp4", link=pub["link"], drive_id=pub["id"], nota=nota)
            ctx.ref.update({"video_anexado": True})
        except Exception as exc:  # noqa: BLE001 - o vídeo está pronto; ação ausente não o invalida
            avisos_resp.append(f"Não consegui anexar à ação {projeto['acao_id']}: {exc}")
    return {
        "campos": {"duracao_final_s": total},
        "mensagem": nota,
        "resposta": {"status": "ok", "projeto_id": ctx.projeto_id, "estado": vp.CONCLUIDO, "video_link": pub["link"],
                     "duracao_s": total, "custo_real_usd": round(custo, 2), "avisos": avisos_resp},
    }
