"""Adaptador único para o gerador de vídeo (Veo 3.1 na Vertex AI).

O resto do Hermes Vídeo só conhece `VeoProvider`: `gerar_clipe` envia o pedido e
devolve o nome da operação (que o worker grava no clipe antes de esperar, para
retomar sem pagar de novo), `consultar_operacao` diz se terminou e `baixar` traz
os bytes do MP4. Trocar de fornecedor é escrever outra implementação.

Fase 0 (26/09/2026): na Vertex, `lastFrame` e `generate_audio=False` são aceitos
pelo Lite e pelo Fast, o MP4 vem só com vídeo (1280×720, 24 fps) e um clipe de
4 s leva ~52 s. Autenticação por ADC: nas Cloud Functions/Cloud Run é a service
account padrão do projeto, que já tem o papel de Editor.
"""
from __future__ import annotations

from dataclasses import dataclass, field

PROJETO_PADRAO = "gestao-hermes"
LOCAL_PADRAO = "us-central1"


@dataclass
class PedidoClipe:
    modelo: str
    prompt: str
    imagem_inicio: bytes
    duracao_s: int
    aspecto: str = "16:9"
    resolucao: str = "720p"
    imagem_fim: bytes | None = None
    referencias: list[bytes] = field(default_factory=list)
    negativo: str | None = None
    saida_gcs: str | None = None


@dataclass
class ResultadoOperacao:
    concluida: bool
    erro: str | None = None
    # Filtro de segurança: operação terminou sem vídeo. Não é cobrado.
    bloqueado: bool = False
    motivo_bloqueio: str | None = None
    video_bytes: bytes | None = None
    video_uri: str | None = None


class VeoProvider:
    def gerar_clipe(self, pedido: PedidoClipe) -> str:
        raise NotImplementedError

    def consultar_operacao(self, nome: str) -> ResultadoOperacao:
        raise NotImplementedError

    def baixar(self, resultado: ResultadoOperacao) -> bytes:
        raise NotImplementedError


def _png(dados: bytes):
    from google.genai import types

    return types.Image(image_bytes=dados, mime_type="image/png")


class VertexVeoProvider(VeoProvider):
    def __init__(self, projeto: str = PROJETO_PADRAO, local: str = LOCAL_PADRAO, cliente=None):
        if cliente is None:
            from google import genai

            cliente = genai.Client(vertexai=True, project=projeto, location=local)
        self._cli = cliente

    def gerar_clipe(self, pedido: PedidoClipe) -> str:
        from google.genai import types

        cfg = {
            "number_of_videos": 1,
            "duration_seconds": pedido.duracao_s,
            "aspect_ratio": pedido.aspecto,
            "resolution": pedido.resolucao,
            "generate_audio": False,
        }
        if pedido.imagem_fim:
            cfg["last_frame"] = _png(pedido.imagem_fim)
        if pedido.referencias:
            # NÃO TESTADO contra o Veo: a Fase 0 só usou image + lastFrame. A
            # documentação sugere restrições para imagens de referência (clipe de
            # 8 s, 16:9, talvez incompatível com quadro inicial ou com o Lite).
            # Validar com um spike antes de a Fase 3 depender disto.
            cfg["reference_images"] = [
                types.VideoGenerationReferenceImage(image=_png(r), reference_type="asset")
                for r in pedido.referencias[:3]
            ]
        if pedido.negativo:
            cfg["negative_prompt"] = pedido.negativo
        if pedido.saida_gcs:
            cfg["output_gcs_uri"] = pedido.saida_gcs
        op = self._cli.models.generate_videos(
            model=pedido.modelo,
            source=types.GenerateVideosSource(prompt=pedido.prompt, image=_png(pedido.imagem_inicio)),
            config=types.GenerateVideosConfig(**cfg),
        )
        return op.name

    def consultar_operacao(self, nome: str) -> ResultadoOperacao:
        from google.genai import types

        op = self._cli.operations.get(types.GenerateVideosOperation(name=nome))
        if not op.done:
            return ResultadoOperacao(concluida=False)
        if op.error:
            return ResultadoOperacao(concluida=True, erro=str(op.error))
        resp = op.response or op.result
        videos = getattr(resp, "generated_videos", None) or []
        if not videos:
            motivos = getattr(resp, "rai_media_filtered_reasons", None) or []
            return ResultadoOperacao(concluida=True, bloqueado=True,
                                     motivo_bloqueio="; ".join(map(str, motivos)) or "sem vídeo na resposta")
        video = videos[0].video
        return ResultadoOperacao(concluida=True, video_bytes=getattr(video, "video_bytes", None),
                                 video_uri=getattr(video, "uri", None))

    def baixar(self, resultado: ResultadoOperacao) -> bytes:
        if resultado.video_bytes:
            return resultado.video_bytes
        if resultado.video_uri and resultado.video_uri.startswith("gs://"):
            from google.cloud import storage

            bucket, _, caminho = resultado.video_uri[5:].partition("/")
            return storage.Client().bucket(bucket).blob(caminho).download_as_bytes()
        raise ValueError("Operação sem vídeo para baixar.")


class FakeVeoProvider(VeoProvider):
    """Provedor de teste: não chama rede e conta cada pedido (a trava de "não pagar duas vezes")."""

    def __init__(self, *, bloquear_prompts: set[str] | None = None, falhar: set[str] | None = None,
                 consultas_ate_concluir: int = 1):
        self.pedidos: list[PedidoClipe] = []
        self._ops: dict[str, dict] = {}
        self._bloquear = bloquear_prompts or set()
        self._falhar = falhar or set()
        self._consultas = consultas_ate_concluir

    def gerar_clipe(self, pedido: PedidoClipe) -> str:
        self.pedidos.append(pedido)
        nome = f"operations/fake-{len(self.pedidos)}"
        self._ops[nome] = {"pedido": pedido, "consultas": 0}
        return nome

    def consultar_operacao(self, nome: str) -> ResultadoOperacao:
        op = self._ops[nome]
        op["consultas"] += 1
        if op["consultas"] < self._consultas:
            return ResultadoOperacao(concluida=False)
        prompt = op["pedido"].prompt
        if any(p in prompt for p in self._falhar):
            return ResultadoOperacao(concluida=True, erro="falha simulada")
        if any(p in prompt for p in self._bloquear):
            return ResultadoOperacao(concluida=True, bloqueado=True, motivo_bloqueio="filtro simulado")
        return ResultadoOperacao(concluida=True, video_bytes=f"mp4:{nome}:{op['pedido'].duracao_s}s".encode())

    def baixar(self, resultado: ResultadoOperacao) -> bytes:
        if not resultado.video_bytes:
            raise ValueError("Operação sem vídeo para baixar.")
        return resultado.video_bytes
