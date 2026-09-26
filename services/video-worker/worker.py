"""hermes-video-worker: renderiza um projeto do Hermes Vídeo (Cloud Run Job).

Uma execução = um projeto. O projeto vem de VIDEO_PROJETO_ID (ou do 1º argumento):

    gcloud run jobs execute hermes-video-worker --region us-central1 \
        --update-env-vars VIDEO_PROJETO_ID=<id>

O projeto precisa estar em `renderizando` (ou `montando`, ao retomar uma montagem).
Uma execução derrubada no meio é retomada rodando o job de novo com o mesmo id:
clipes prontos não são refeitos e operações já enviadas ao Veo são consultadas,
não reenviadas (ver video/renderizacao.py).

Sai com código 0 mesmo quando a renderização termina em erro — o erro fica no
projeto (e vai para o Telegram). O job é implantado com --max-retries 0: uma
retentativa automática do Cloud Run não traria nada que rodar de novo à mão não traga.
"""
import json
import os
import sys
import uuid

import firebase_admin
from firebase_admin import firestore

from video import midia, renderizacao
from video.veo_provider import VertexVeoProvider


def main() -> int:
    projeto_id = (os.environ.get("VIDEO_PROJETO_ID") or (sys.argv[1] if len(sys.argv) > 1 else "")).strip()
    if not projeto_id:
        print("VIDEO_PROJETO_ID não informado.", file=sys.stderr)
        return 2
    execucao = os.environ.get("CLOUD_RUN_EXECUTION") or f"local-{uuid.uuid4().hex[:8]}"
    firebase_admin.initialize_app()
    db = firestore.client()
    resultado = renderizacao.renderizar(db, projeto_id, execucao, veo=VertexVeoProvider(),
                                        servicos=midia.ServicosVertex(db))
    print(json.dumps({"projeto_id": projeto_id, "execucao": execucao, **resultado}, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
