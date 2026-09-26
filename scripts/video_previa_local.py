"""Hermes Vídeo Fase 2 — critério de pronto com chamadas reais, fora de produção.

Roteiro de ~60 s → narração por cena + quadros-chave (Vertex AI e bucket reais) →
folha de contato + MP3. O Firestore é o de memória dos testes (video_fakes) e a
"publicação" grava no disco em vez do Drive: nada toca os dados de produção.

    python scripts/video_previa_local.py --saida DIR     # ~US$ 0,50

Critério (plano): roteiro de 60 s vira folha de contato + MP3 em menos de 3 min,
com custo abaixo de US$ 1.
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "functions"))

from video import midia, previa  # noqa: E402
from video import projeto as vp  # noqa: E402
from video_fakes import FakeDb  # noqa: E402

ROTEIRO = {
    "titulo": "RSC em 1 minuto",
    "formato": "16:9",
    "biblia": {
        "estilo": "ilustração digital flat 2D, iluminação difusa, traço limpo",
        "paleta": "azul-petróleo, laranja suave e branco",
        "personagens": ["Marta: servidora pública de meia-idade, cabelo curto grisalho, óculos redondos, "
                        "blazer azul-marinho, crachá no peito"],
        "evitar": "texto na imagem, logotipos, rostos de pessoas reais",
    },
    "voz": {"nome": "Kore", "estilo": "calmo e didático"},
    "cenas": [
        {"narracao": "Você já sabe fazer muita coisa que nenhum diploma registrou.",
         "descricao_visual": "Marta à mesa do escritório, pensativa, olhando uma pilha de documentos"},
        {"narracao": "O RSC transforma essa experiência em reconhecimento na carreira.",
         "descricao_visual": "Marta segura um certificado e sorri, câmera se aproxima"},
        {"narracao": "Primeiro, reúna os comprovantes do que você já fez.",
         "descricao_visual": "Marta organiza pastas coloridas sobre a mesa"},
        {"narracao": "Depois, preencha o memorial descrevendo sua trajetória.",
         "descricao_visual": "Marta digita no computador, tela com um formulário genérico"},
        {"narracao": "A comissão analisa cada item com base na pontuação prevista.",
         "descricao_visual": "Três colegas em volta de uma mesa de reunião examinando papéis"},
        {"narracao": "Se estiver tudo certo, o resultado sai em poucas semanas.",
         "descricao_visual": "Marta abre um e-mail no computador e comemora discretamente"},
        {"narracao": "E o reconhecimento passa a valer na sua remuneração.",
         "descricao_visual": "Marta caminha pelo corredor do campus com passos confiantes"},
        {"narracao": "Procure a gestão de pessoas do seu campus e comece hoje.",
         "descricao_visual": "Marta acena para a câmera em frente ao prédio do campus"},
    ],
}


class ServicosLocais(midia.ServicosVertex):
    """Vertex e bucket reais; publicação no disco em vez do Drive."""

    def __init__(self, db, destino: Path):
        from google.oauth2 import service_account
        import os

        cred = service_account.Credentials.from_service_account_file(
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"], scopes=["https://www.googleapis.com/auth/cloud-platform"])
        from google import genai

        super().__init__(db, cliente=genai.Client(vertexai=True, project="gestao-hermes", location="us-central1",
                                                  credentials=cred))
        self._destino = destino
        self.chamadas = {"fala": 0, "imagem": 0}

    def gerar_fala(self, *a, **k):
        self.chamadas["fala"] += 1
        return super().gerar_fala(*a, **k)

    def gerar_imagem(self, *a, **k):
        self.chamadas["imagem"] += 1
        return super().gerar_imagem(*a, **k)

    def publicar(self, nome, dados, mime):
        arq = self._destino / nome.replace("/", "-")
        arq.write_bytes(dados)
        return {"id": arq.name, "link": str(arq)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--saida", type=Path, required=True)
    args = ap.parse_args()
    args.saida.mkdir(parents=True, exist_ok=True)

    db = FakeDb()
    criado = vp.criar_projeto(db, "uid-local", ROTEIRO)
    print("Projeto:", json.dumps({k: criado.get(k) for k in ("status", "cenas", "estimativa", "avisos", "erros")},
                                  ensure_ascii=False))
    if criado["status"] != "ok":
        sys.exit(1)
    srv = ServicosLocais(db, args.saida)
    t0 = time.monotonic()
    r = previa.gerar_previa(db, criado["projeto_id"], "uid-local", srv)
    dur = time.monotonic() - t0
    r["tempo_total_s"] = round(dur, 1)
    r["chamadas"] = srv.chamadas
    (args.saida / "resultado.json").write_text(json.dumps(r, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps({k: r.get(k) for k in ("status", "erro", "tempo_total_s", "gasto_desta_previa_usd", "chamadas",
                                            "cenas", "falhas", "avisos")}, ensure_ascii=False, default=str))
    print("Estimativa refeita:", json.dumps(r.get("estimativa"), ensure_ascii=False))


if __name__ == "__main__":
    main()
