"""Dispara o worker de renderização (Cloud Run Job `hermes-video-worker`).

Chamada REST à API do Cloud Run (v2 `jobs.run` com override de ambiente), com a
credencial padrão da function — a conta compute padrão, que é Editor do projeto
e por isso pode executar o job. Uma execução por chamada; o próprio worker
garante uma execução ativa por projeto (lease).
"""
from __future__ import annotations

JOB = "hermes-video-worker"
PROJETO = "gestao-hermes"
REGIAO = "us-central1"


def disparar_worker(projeto_id: str, *, sessao=None, projeto: str = PROJETO, regiao: str = REGIAO) -> str:
    """Inicia uma execução do worker para `projeto_id`; devolve o nome da operação do Cloud Run."""
    if sessao is None:
        import google.auth
        from google.auth.transport.requests import AuthorizedSession

        cred, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        sessao = AuthorizedSession(cred)
    url = f"https://run.googleapis.com/v2/projects/{projeto}/locations/{regiao}/jobs/{JOB}:run"
    corpo = {"overrides": {"containerOverrides": [{"env": [{"name": "VIDEO_PROJETO_ID", "value": projeto_id}]}]}}
    resp = sessao.post(url, json=corpo, timeout=30)
    if resp.status_code >= 300:
        raise RuntimeError(f"Cloud Run recusou a execução do worker ({resp.status_code}): {resp.text[:300]}")
    return (resp.json() or {}).get("name") or ""
