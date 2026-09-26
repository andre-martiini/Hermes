"""Metadados e segredos usados para abrir faturas PDF protegidas."""

from __future__ import annotations

import re
from email.utils import parseaddr
from typing import Any


CONFIG_COLLECTION = "bill_pdf_password_configs"
SECRET_ID_PATTERN = re.compile(r"^bill-pdf-password-[a-z0-9-]+$")


def normalize_sender(value: str | None) -> str:
    return parseaddr(value or "")[1].strip().lower()


def list_password_configs(db: Any) -> list[dict]:
    configs = []
    for snapshot in db.collection(CONFIG_COLLECTION).stream():
        data = snapshot.to_dict() or {}
        if not data.get("active", True):
            continue
        secret_id = str(data.get("secret_id") or "").strip()
        if not SECRET_ID_PATTERN.fullmatch(secret_id):
            continue
        senders = sorted({normalize_sender(sender) for sender in data.get("senders") or [] if normalize_sender(sender)})
        configs.append({
            "id": snapshot.id,
            "label": str(data.get("label") or snapshot.id).strip(),
            "rubric_id": str(data.get("rubric_id") or "").strip(),
            "senders": senders,
            "secret_id": secret_id,
            "kind": str(data.get("kind") or "pdf").strip(),
        })
    return sorted(configs, key=lambda item: item["label"].casefold())


def find_password_config(db: Any, sender: str | None) -> dict | None:
    normalized = normalize_sender(sender)
    if not normalized:
        return None
    return next((
        config for config in list_password_configs(db)
        if config.get("kind") == "pdf" and normalized in config["senders"]
    ), None)


def _secret_name(project_id: str, secret_id: str, version: str = "latest") -> str:
    if not SECRET_ID_PATTERN.fullmatch(secret_id):
        raise ValueError("Identificador de segredo inválido.")
    return f"projects/{project_id}/secrets/{secret_id}/versions/{version}"


def read_password_secret(project_id: str, secret_id: str, client: Any = None) -> str | None:
    from google.api_core.exceptions import NotFound
    from google.cloud import secretmanager

    secret_client = client or secretmanager.SecretManagerServiceClient()
    try:
        response = secret_client.access_secret_version(name=_secret_name(project_id, secret_id))
    except NotFound:
        return None
    value = response.payload.data.decode("utf-8")
    return value if value else None


def password_secret_exists(project_id: str, secret_id: str, client: Any = None) -> bool:
    try:
        return read_password_secret(project_id, secret_id, client=client) is not None
    except Exception:
        return False


def save_password_secret(
    project_id: str,
    secret_id: str,
    password: str,
    client: Any = None,
    destruir_anteriores: bool = False,
) -> None:
    from google.cloud import secretmanager

    if not isinstance(password, str) or not password or len(password) > 128:
        raise ValueError("A senha deve conter entre 1 e 128 caracteres.")
    if not SECRET_ID_PATTERN.fullmatch(secret_id):
        raise ValueError("Identificador de segredo inválido.")

    secret_client = client or secretmanager.SecretManagerServiceClient()
    parent = f"projects/{project_id}/secrets/{secret_id}"
    new_version = secret_client.add_secret_version(
        parent=parent,
        payload={"data": password.encode("utf-8")},
    )
    if destruir_anteriores:
        destroy_previous_secret_versions(secret_client, parent, getattr(new_version, "name", None))


def _version_number(name: str | None) -> int | None:
    """``projects/p/secrets/s/versions/7`` → 7; None se não terminar em número."""
    tail = str(name or "").rsplit("/versions/", 1)
    if len(tail) != 2 or not tail[1].isdigit():
        return None
    return int(tail[1])


def _version_state_name(version: Any) -> str:
    state = getattr(version, "state", None)
    return str(getattr(state, "name", state) or "").upper()


def destroy_previous_secret_versions(secret_client: Any, parent: str, keep_version_name: str | None) -> int:
    """Destrói as versões antigas do segredo, mantendo só a recém-criada.

    O Secret Manager cobra por versão ativa (habilitada ou desabilitada) e cada
    save acrescentava uma versão nova sem apagar as anteriores. A leitura usa
    sempre `versions/latest`, então as antigas não servem para nada.

    Só destrói versões de número MENOR que a nova: se outro save concorrente
    gravou uma versão mais nova nesse meio-tempo, ela é preservada.

    Melhor esforço: a senha nova já foi gravada, então qualquer falha aqui só é
    registrada no log e nunca derruba o save. Sem o número da versão nova não
    destruímos nada — não dá para garantir que ela ficaria de fora.
    Devolve quantas versões foram destruídas.
    """
    keep_number = _version_number(keep_version_name)
    if keep_number is None:
        print(f"[BillPdfPasswords] Versão nova sem número em {parent}; versões antigas mantidas.")
        return 0
    try:
        versions = list(secret_client.list_secret_versions(request={"parent": parent}))
    except Exception as exc:
        print(f"[BillPdfPasswords] Falha ao listar versões de {parent}: {exc}")
        return 0

    destroyed = 0
    for version in versions:
        name = getattr(version, "name", None)
        number = _version_number(name)
        if number is None or number >= keep_number:
            continue
        if _version_state_name(version) == "DESTROYED":
            continue
        try:
            secret_client.destroy_secret_version(request={"name": name})
            destroyed += 1
        except Exception as exc:
            print(f"[BillPdfPasswords] Falha ao destruir {name}: {exc}")
    return destroyed
