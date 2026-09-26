# hermes-video-worker — Cloud Run Job que renderiza projetos do Hermes Vídeo.
# Build a partir da RAIZ do repositório (precisa de functions/video):
#   gcloud builds submit --config services/video-worker/cloudbuild.yaml .
FROM python:3.12-slim

# ffmpeg do Debian: libx264, libass (legenda) e fontconfig; DejaVu é a fonte da legenda.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
ENV FFMPEG_BIN=/usr/bin/ffmpeg \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY services/video-worker/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# O mesmo pacote que as functions usam: nada de lógica duplicada no worker.
COPY functions/video ./video
COPY services/video-worker/worker.py .

CMD ["python", "worker.py"]
