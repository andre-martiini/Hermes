"""Download seguro de boletos enviados pela Allcare como link no e-mail."""

from __future__ import annotations

import base64
import html
import re
from email.utils import parseaddr
from urllib.parse import urljoin, urlparse

import requests


ALLCARE_SENDER = "boleto@allcaregestoradesaude.com.br"
TRACKING_HOST = "url1651.allcaregestoradesaude.com.br"
PORTAL_HOST = "comunicado.allcare.com.br"
DOCUMENT_HOST = "comunicados-files-prd.s3.us-east-1.amazonaws.com"
API_BASE = "https://integracoes.allcare.com.br/comunicados"
TOKEN_PATTERN = re.compile(
    r"^/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/?$",
    re.IGNORECASE,
)
MAX_DOCUMENT_BYTES = 20 * 1024 * 1024


class AllcareBillError(RuntimeError):
    """Falha esperada ao abrir um boleto hospedado no portal da Allcare."""


def is_allcare_bill_sender(sender: str | None) -> bool:
    return parseaddr(sender or "")[1].strip().lower() == ALLCARE_SENDER


def _decode_part_data(value: str) -> str:
    try:
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        return raw.decode("utf-8", "replace")
    except Exception:
        return ""


def _html_parts(part: dict) -> list[str]:
    contents = []
    if part.get("mimeType") == "text/html" and part.get("body", {}).get("data"):
        contents.append(_decode_part_data(part["body"]["data"]))
    for child in part.get("parts") or []:
        contents.extend(_html_parts(child))
    return contents


def extract_allcare_tracking_url(payload: dict) -> str:
    """Extrai somente o link oficial de acesso ao boleto no HTML da mensagem."""
    for body in _html_parts(payload):
        for match in re.finditer(r"<a\b[^>]*href=[\"']([^\"']+)[\"']", body, re.IGNORECASE):
            candidate = html.unescape(match.group(1)).strip()
            parsed = urlparse(candidate)
            if parsed.scheme in ("http", "https") and parsed.hostname == TRACKING_HOST and parsed.path == "/ls/click":
                return candidate
    raise AllcareBillError("link_oficial_nao_encontrado")


def _validate_https_host(url: str, expected_host: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != expected_host or parsed.username or parsed.password:
        raise AllcareBillError("destino_nao_permitido")


def _resolve_portal_token(session: requests.Session, tracking_url: str) -> str:
    """Segue o redirecionamento conhecido sem permitir destinos arbitrários."""
    parsed_tracking = urlparse(tracking_url)
    if (
        parsed_tracking.scheme not in ("http", "https")
        or parsed_tracking.hostname != TRACKING_HOST
        or parsed_tracking.path != "/ls/click"
        or parsed_tracking.username
        or parsed_tracking.password
    ):
        raise AllcareBillError("destino_nao_permitido")
    try:
        response = session.get(
            tracking_url,
            allow_redirects=False,
            timeout=30,
            headers={"User-Agent": "Hermes/1.0"},
        )
    except requests.RequestException as exc:
        raise AllcareBillError("falha_no_redirecionamento") from exc
    if response.status_code not in (301, 302, 303, 307, 308):
        raise AllcareBillError("redirecionamento_invalido")
    destination = urljoin(tracking_url, response.headers.get("location") or "")
    _validate_https_host(destination, PORTAL_HOST)
    path = urlparse(destination).path
    if not TOKEN_PATTERN.fullmatch(path):
        raise AllcareBillError("token_invalido")
    return path.strip("/")


def _find_access_code(db, gmail_address: str) -> str:
    """Obtém os cinco primeiros dígitos do CPF sem expô-los fora desta função."""
    normalized_email = str(gmail_address or "").strip().lower()
    if not normalized_email:
        raise AllcareBillError("email_da_conta_ausente")

    snapshots = (
        db.collection("perfil_pessoas")
        .where("email", "==", normalized_email)
        .limit(1)
        .stream()
    )
    profile = next(iter(snapshots), None)
    digits = re.sub(r"\D", "", str((profile.to_dict() if profile else {}).get("cpf") or ""))
    if len(digits) != 11:
        raise AllcareBillError("cpf_do_titular_nao_encontrado")
    return digits[:5]


def download_allcare_bill_pdf(
    payload: dict,
    gmail_address: str,
    db,
    session: requests.Session | None = None,
) -> bytes:
    """Autentica no portal oficial da Allcare e retorna o PDF do boleto."""
    http = session or requests.Session()
    tracking_url = extract_allcare_tracking_url(payload)
    token = _resolve_portal_token(http, tracking_url)
    access_code = _find_access_code(db, gmail_address)

    try:
        login = http.post(
            f"{API_BASE}/login",
            json={"login": access_code, "token": token},
            timeout=30,
        )
    except requests.RequestException as exc:
        raise AllcareBillError("falha_na_autenticacao") from exc
    if not login.ok or login.text.strip().lower() != "true":
        raise AllcareBillError("codigo_de_acesso_rejeitado")

    try:
        generated = http.post(
            f"{API_BASE}/gerar-documento",
            json={"login": access_code, "token": token},
            timeout=60,
        )
    except requests.RequestException as exc:
        raise AllcareBillError("falha_ao_gerar_documento") from exc
    if not generated.ok:
        raise AllcareBillError("documento_nao_gerado")
    try:
        document_url = str(generated.json().get("signedUrl") or "")
    except Exception as exc:
        raise AllcareBillError("resposta_de_documento_invalida") from exc
    _validate_https_host(document_url, DOCUMENT_HOST)

    try:
        document = http.get(document_url, allow_redirects=False, timeout=60)
    except requests.RequestException as exc:
        raise AllcareBillError("falha_no_download") from exc
    if not document.ok:
        raise AllcareBillError("download_do_documento_falhou")
    if len(document.content) > MAX_DOCUMENT_BYTES:
        raise AllcareBillError("documento_muito_grande")
    if not document.content.lstrip().startswith(b"%PDF-"):
        raise AllcareBillError("documento_nao_e_pdf")
    return document.content
