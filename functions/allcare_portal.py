"""Cliente do Portal do Beneficiário Allcare para sincronização de boletos."""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from typing import Any

import requests


BASE_URL = "https://beneficiario.allcare.com.br"
PLAN_MATCH = "PARTICIPATIVO ESTADUAL ADESAO"
MAX_PDF_BYTES = 20 * 1024 * 1024


class AllcarePortalError(RuntimeError):
    """Erro esperado e sanitizado do Portal do Beneficiário."""


def _normalized(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return " ".join("".join(ch for ch in text if not unicodedata.combining(ch)).upper().split())


def parse_brl_amount(value: Any) -> float:
    text = str(value or "").strip().replace("R$", "").replace(" ", "")
    if not text:
        raise AllcarePortalError("valor_ausente")
    if "," in text:
        text = text.replace(".", "").replace(",", ".")
    try:
        amount = float(text)
    except ValueError as exc:
        raise AllcarePortalError("valor_invalido") from exc
    if amount <= 0:
        raise AllcarePortalError("valor_invalido")
    return amount


def parse_portal_date(value: Any) -> date:
    try:
        return datetime.strptime(str(value or "").strip(), "%d/%m/%Y").date()
    except ValueError as exc:
        raise AllcarePortalError("data_invalida") from exc


def select_active_profile(payload: dict, plan_match: str = PLAN_MATCH) -> dict:
    profiles = ((payload.get("retorno") or {}).get("dadosAtivarBenef") or [])
    expected = _normalized(plan_match)
    active = [profile for profile in profiles if str(profile.get("ind_situacao") or "").upper() == "A"]
    selected = next(
        (
            profile for profile in active
            if expected in _normalized(profile.get("nome_plano_cartao"))
        ),
        None,
    )
    if selected is None:
        raise AllcarePortalError("perfil_ativo_nao_encontrado")
    if not str(selected.get("cod_usuario") or "").strip():
        raise AllcarePortalError("usuario_do_perfil_ausente")
    return selected


def find_holder_cpf(db, gmail_address: str) -> str:
    email = str(gmail_address or "").strip().lower()
    snapshots = (
        db.collection("perfil_pessoas")
        .where("email", "==", email)
        .limit(1)
        .stream()
    )
    profile = next(iter(snapshots), None)
    cpf = re.sub(r"\D", "", str((profile.to_dict() if profile else {}).get("cpf") or ""))
    if len(cpf) != 11:
        raise AllcarePortalError("cpf_do_titular_nao_encontrado")
    return cpf


class AllcarePortalClient:
    def __init__(self, session: requests.Session | None = None):
        self.session = session or requests.Session()
        self.session.headers.update({
            "User-Agent": "Hermes/1.0",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
        })

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        try:
            response = self.session.request(method, f"{BASE_URL}{path}", timeout=60, **kwargs)
        except requests.RequestException as exc:
            raise AllcarePortalError("portal_indisponivel") from exc
        if not response.ok:
            raise AllcarePortalError(f"portal_http_{response.status_code}")
        return response

    def login(self, cpf: str, password: str, plan_match: str = PLAN_MATCH) -> dict:
        self._request("GET", "/")
        response = self._request(
            "POST",
            "/Account/ValidarBeneficiario",
            data={"cpf": cpf, "senha": password, "remember": "false"},
        )
        try:
            profile = select_active_profile(response.json(), plan_match)
        except (ValueError, TypeError) as exc:
            raise AllcarePortalError("resposta_de_login_invalida") from exc

        authenticated = self._request(
            "POST",
            "/Account/AutenticarBeneficiario/?returnUrl=",
            data={
                "usuario": str(profile["cod_usuario"]),
                "senha": password,
                "remember": "false",
            },
            allow_redirects=True,
        )
        if "HomePortalBeneficiario" not in authenticated.url or "Sair" not in authenticated.text:
            raise AllcarePortalError("autenticacao_rejeitada")
        return profile

    def list_bills(self, start_month: str, end_month: str) -> list[dict]:
        response = self._request(
            "POST",
            "/TSNMVC/HomePortalBeneficiario/SegundaViaBoleto/FiltrarBoletos",
            params={
                "v_vencidas": "S",
                "v_a_vencer": "S",
                "data_inicial": start_month,
                "data_final": end_month,
            },
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        try:
            payload = response.json()
        except ValueError as exc:
            raise AllcarePortalError("resposta_de_boletos_invalida") from exc
        if not payload.get("success"):
            return []
        return list(payload.get("retorno") or [])

    def download_bill(self, bill: dict) -> bytes:
        charge_id = str(bill.get("num_seq_cobranca") or "").strip()
        contract_id = str(bill.get("cod_ts") or "").strip()
        if not charge_id or not contract_id:
            raise AllcarePortalError("identificador_do_boleto_ausente")
        generated = self._request(
            "GET",
            "/TSNMVC/HomePortalBeneficiario/SegundaViaBoleto/Gerar",
            params={
                "num_seq_cobranca": charge_id,
                "formato_saida": "download",
                "cod_ts": contract_id,
            },
        )
        try:
            result = generated.json()
        except ValueError as exc:
            raise AllcarePortalError("resposta_de_emissao_invalida") from exc
        if not isinstance(result, list) or not result or result[0] != "SUCESSO":
            raise AllcarePortalError("emissao_do_boleto_falhou")
        if len(result) < 4 or not result[2] or not result[3]:
            raise AllcarePortalError("arquivo_do_boleto_ausente")

        document = self._request(
            "GET",
            "/TSNMVC/HomePortalBeneficiario/FileUtils/FileDownload",
            params={"nome_arquivo": str(result[2]), "ext": str(result[3])},
            allow_redirects=True,
        )
        if len(document.content) > MAX_PDF_BYTES:
            raise AllcarePortalError("boleto_muito_grande")
        if not document.content.lstrip().startswith(b"%PDF-"):
            raise AllcarePortalError("arquivo_nao_e_pdf")
        return document.content


def current_portal_period(today: date | None = None) -> tuple[str, str]:
    current = today or date.today()
    next_month = 1 if current.month == 12 else current.month + 1
    next_year = current.year + 1 if current.month == 12 else current.year
    return f"{current.month:02d}/{current.year}", f"{next_month:02d}/{next_year}"
