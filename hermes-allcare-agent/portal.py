"""Cliente local do Portal do Beneficiário Allcare."""

from __future__ import annotations

import unicodedata
from datetime import date, datetime
from typing import Any

import requests

BASE_URL = "https://beneficiario.allcare.com.br"
MAX_PDF_BYTES = 20 * 1024 * 1024


class PortalError(RuntimeError):
    pass


def normalized(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return " ".join("".join(ch for ch in text if not unicodedata.combining(ch)).upper().split())


def current_period(today: date | None = None) -> tuple[str, str]:
    current = today or date.today()
    next_month = 1 if current.month == 12 else current.month + 1
    next_year = current.year + 1 if current.month == 12 else current.year
    return f"{current.month:02d}/{current.year}", f"{next_month:02d}/{next_year}"


class PortalClient:
    def __init__(self, session: requests.Session | None = None):
        self.session = session or requests.Session()
        self.session.headers["User-Agent"] = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
        )

    @staticmethod
    def ajax_headers() -> dict[str, str]:
        return {
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
        }

    def request(self, method: str, path: str, **kwargs) -> requests.Response:
        try:
            response = self.session.request(method, f"{BASE_URL}{path}", timeout=60, **kwargs)
        except requests.RequestException as error:
            raise PortalError("portal_indisponivel") from error
        if not response.ok:
            raise PortalError(f"portal_http_{response.status_code}")
        return response

    def login(self, cpf: str, password: str, plan_match: str) -> dict:
        response = self.request(
            "POST",
            "/Account/ValidarBeneficiario",
            data={"cpf": cpf, "senha": password, "remember": "false"},
            headers=self.ajax_headers(),
        )
        try:
            payload = response.json()
            profiles = ((payload.get("retorno") or {}).get("dadosAtivarBenef") or [])
        except (ValueError, TypeError) as error:
            raise PortalError("resposta_de_login_invalida") from error
        expected = normalized(plan_match)
        profile = next(
            (
                item for item in profiles
                if str(item.get("ind_situacao") or "").upper() == "A"
                and expected in normalized(item.get("nome_plano_cartao"))
            ),
            None,
        )
        if profile is None:
            if not profiles:
                raise PortalError("credenciais_rejeitadas")
            raise PortalError("plano_ativo_nao_encontrado")
        authenticated = self.request(
            "POST",
            "/Account/AutenticarBeneficiario/?returnUrl=",
            data={"usuario": str(profile.get("cod_usuario") or ""), "senha": password, "remember": "false"},
            allow_redirects=True,
            headers={"Accept": "text/html,application/xhtml+xml", "Referer": f"{BASE_URL}/"},
        )
        if "HomePortalBeneficiario" not in authenticated.url:
            raise PortalError("autenticacao_rejeitada")
        return profile

    def list_bills(self, start_month: str, end_month: str) -> list[dict]:
        response = self.request(
            "POST",
            "/TSNMVC/HomePortalBeneficiario/SegundaViaBoleto/FiltrarBoletos",
            params={
                "v_vencidas": "S",
                "v_a_vencer": "S",
                "data_inicial": start_month,
                "data_final": end_month,
            },
            headers={**self.ajax_headers(), "Content-Type": "application/json; charset=utf-8"},
        )
        try:
            payload = response.json()
        except ValueError as error:
            raise PortalError("resposta_de_boletos_invalida") from error
        return list(payload.get("retorno") or []) if payload.get("success") else []

    def download_bill(self, bill: dict) -> bytes:
        charge_id = str(bill.get("num_seq_cobranca") or "").strip()
        contract_id = str(bill.get("cod_ts") or "").strip()
        if not charge_id or not contract_id:
            raise PortalError("identificador_do_boleto_ausente")
        response = self.request(
            "GET",
            "/TSNMVC/HomePortalBeneficiario/SegundaViaBoleto/Gerar",
            params={"num_seq_cobranca": charge_id, "formato_saida": "download", "cod_ts": contract_id},
            headers=self.ajax_headers(),
        )
        try:
            result = response.json()
        except ValueError as error:
            raise PortalError("resposta_de_emissao_invalida") from error
        if not isinstance(result, list) or len(result) < 4 or result[0] != "SUCESSO":
            raise PortalError("emissao_do_boleto_falhou")
        document = self.request(
            "GET",
            "/TSNMVC/HomePortalBeneficiario/FileUtils/FileDownload",
            params={"nome_arquivo": str(result[2]), "ext": str(result[3])},
            allow_redirects=True,
        )
        if len(document.content) > MAX_PDF_BYTES or not document.content.lstrip().startswith(b"%PDF-"):
            raise PortalError("arquivo_do_boleto_invalido")
        return document.content
