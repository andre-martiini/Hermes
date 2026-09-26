"""Hermes Vídeo Fase 3 — critério de pronto com chamadas reais, fora de produção.

Roteiro de ~30 s → prévia → renderização no Veo 3.1 Lite (em sequência) → montagem.
Veo, Vertex e bucket são reais; o Firestore é o de memória dos testes e a entrega
grava no disco em vez do Drive. Derruba o "worker" depois do clipe 2 e roda de
novo, para provar que a retomada não reenvia (nem paga) clipe pronto.

    python scripts/video_render_local.py --saida DIR     # ~US$ 1,75

Critério (plano): o worker produz um vídeo de 30 s; derrubado no meio, retoma sem
regerar clipes done.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "functions"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from google import genai  # noqa: E402
from google.oauth2 import service_account  # noqa: E402

from video import montagem, previa, renderizacao  # noqa: E402
from video import projeto as vp  # noqa: E402
from video.veo_provider import VertexVeoProvider  # noqa: E402
from video_fakes import FakeDb  # noqa: E402
from video_previa_local import ServicosLocais  # noqa: E402

ROTEIRO = {
    "titulo": "RSC em 30 segundos",
    "formato": "16:9",
    "legenda": True,
    "biblia": {
        "estilo": "ilustração digital flat 2D, iluminação difusa, traço limpo",
        "paleta": "azul-petróleo, laranja suave e branco",
        "personagens": ["Marta: servidora pública de meia-idade, cabelo curto grisalho, óculos redondos, "
                        "blazer azul-marinho, crachá no peito"],
        "evitar": "texto na imagem, logotipos, rostos de pessoas reais",
    },
    "voz": {"nome": "Kore", "estilo": "calmo e didático"},
    "cenas": [
        {"narracao": "Marta sabe fazer muita coisa que nenhum diploma registrou.",
         "descricao_visual": "Marta à mesa do escritório, olhando uma pilha de documentos"},
        {"narracao": "O RSC transforma essa experiência em reconhecimento.",
         "descricao_visual": "Marta segura um certificado e sorri"},
        {"narracao": "Ela reúne os comprovantes e descreve sua trajetória.",
         "descricao_visual": "Marta organiza pastas coloridas sobre a mesa"},
        {"narracao": "A comissão analisa e o resultado sai em poucas semanas.",
         "descricao_visual": "Marta lê um e-mail no computador e comemora discretamente"},
        {"narracao": "Procure a gestão de pessoas do seu campus.",
         "descricao_visual": "Marta acena para a câmera em frente ao prédio do campus"},
    ],
}


class Contador(VertexVeoProvider):
    def __init__(self, cliente):
        super().__init__(cliente=cliente)
        self.enviados = 0

    def gerar_clipe(self, pedido):
        self.enviados += 1
        print(f"  → Veo: clipe de {pedido.duracao_s} s ({self.enviados}º envio)", flush=True)
        return super().gerar_clipe(pedido)


class WorkerDerrubado(BaseException):
    pass


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--saida", type=Path, required=True)
    args = ap.parse_args()
    args.saida.mkdir(parents=True, exist_ok=True)

    cred = service_account.Credentials.from_service_account_file(
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"], scopes=["https://www.googleapis.com/auth/cloud-platform"])
    cliente = genai.Client(vertexai=True, project="gestao-hermes", location="us-central1", credentials=cred)
    db = FakeDb()
    srv = ServicosLocais(db, args.saida)
    pid = vp.criar_projeto(db, "uid-local", ROTEIRO)["projeto_id"]
    t0 = time.monotonic()
    p = previa.gerar_previa(db, pid, "uid-local", srv)
    print("Prévia:", json.dumps({k: p.get(k) for k in ("status", "gasto_desta_previa_usd", "cenas", "falhas")},
                                ensure_ascii=False), flush=True)
    if p["status"] != "ok" or p["falhas"]:
        sys.exit("Prévia incompleta; não renderizo.")
    vp.transicionar(db, pid, vp.RENDERIZANDO)
    veo = Contador(cliente)
    avisos = renderizacao.Avisos(falso=True)

    def derruba(ordem):
        if ordem == 2:
            raise WorkerDerrubado()

    t1 = time.monotonic()
    try:
        renderizacao.renderizar(db, pid, "exec-1", veo=veo, servicos=srv, avisos=avisos, apos_clipe=derruba)
    except WorkerDerrubado:
        print(f"Worker derrubado depois do clipe 2 ({veo.enviados} envios até aqui).", flush=True)
    r = renderizacao.renderizar(db, pid, "exec-2", veo=veo, servicos=srv, avisos=avisos)
    t2 = time.monotonic()
    doc = db.docs[f"video_projetos/{pid}"]
    final = srv.arquivos.get if hasattr(srv, "arquivos") else None
    arq = args.saida / f"{ROTEIRO['titulo']}.mp4"
    resumo = {
        "status": r.get("status"), "erro": r.get("erro"), "estado": doc["status"],
        "envios_veo": veo.enviados, "cenas": len(ROTEIRO["cenas"]),
        "duracao_final_s": montagem.duracao(arq.read_bytes()) if arq.exists() else None,
        "custo_previa_usd": round(doc.get("custo_previa_usd") or 0, 2),
        "custo_render_usd": round(doc.get("custo_render_usd") or 0, 2),
        "custo_real_usd": round(doc.get("custo_real_usd") or 0, 2),
        "tempo_previa_s": round(t1 - t0, 1), "tempo_render_s": round(t2 - t1, 1),
        "mensagem": avisos.mensagens,
    }
    (args.saida / "resultado.json").write_text(json.dumps(resumo, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(resumo, ensure_ascii=False))


if __name__ == "__main__":
    main()
