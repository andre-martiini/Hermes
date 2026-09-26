"""Cria (ou confere) o bucket do Hermes Vídeo. Idempotente: rodar de novo só confere.

    python scripts/video_bucket.py            # mostra o que faria
    python scripts/video_bucket.py --aplicar  # cria/ajusta

Bucket `gestao-hermes-video` em us-central1 (mesma região do Veo na Vertex), acesso
uniforme, sem acesso público. Regra de ciclo de vida: tudo sob `tmp/` (áudios por
cena, quadros-chave, clipes) é apagado em 30 dias — o vídeo final vai para o
Drive. Credencial: GOOGLE_APPLICATION_CREDENTIALS (service account com Storage Admin).
"""
import argparse

from google.cloud import storage

PROJETO = "gestao-hermes"
BUCKET = "gestao-hermes-video"
LOCAL = "us-central1"
DIAS_TMP = 30


def regra_tmp() -> dict:
    return {"action": {"type": "Delete"}, "condition": {"age": DIAS_TMP, "matchesPrefix": ["tmp/"]}}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--aplicar", action="store_true")
    args = ap.parse_args()

    cli = storage.Client(project=PROJETO)
    bucket = cli.lookup_bucket(BUCKET)
    if bucket is None:
        print(f"Bucket {BUCKET} não existe — {'criando' if args.aplicar else 'seria criado'} em {LOCAL}.")
        if not args.aplicar:
            return
        bucket = cli.bucket(BUCKET)
        bucket.iam_configuration.uniform_bucket_level_access_enabled = True
        bucket.iam_configuration.public_access_prevention = "enforced"
        bucket = cli.create_bucket(bucket, location=LOCAL)
    else:
        print(f"Bucket {BUCKET} já existe ({bucket.location}).")

    regras = list(bucket.lifecycle_rules)
    if any((r.get("condition") or {}).get("matchesPrefix") == ["tmp/"] for r in regras):
        print(f"Regra de {DIAS_TMP} dias em tmp/ já está lá.")
        return
    print(f"Regra de {DIAS_TMP} dias em tmp/ {'adicionada' if args.aplicar else 'seria adicionada'}.")
    if args.aplicar:
        bucket.lifecycle_rules = regras + [regra_tmp()]
        bucket.patch()


if __name__ == "__main__":
    main()
