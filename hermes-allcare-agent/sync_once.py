"""Executa uma sincronização local Allcare -> Hermes."""

from __future__ import annotations

import base64
import logging
import os
import sys
from pathlib import Path

import keyring

import hermes_api
from portal import PortalClient, PortalError, current_period
from setup_agent import CPF_USER, KEYRING_SERVICE, PASSWORD_USER, PLAN_USER


def configure_logging() -> None:
    log_dir = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "Hermes"
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(log_dir / "allcare-agent.log", encoding="utf-8"), logging.StreamHandler()],
    )


def main() -> int:
    configure_logging()
    cpf = keyring.get_password(KEYRING_SERVICE, CPF_USER)
    password = keyring.get_password(KEYRING_SERVICE, PASSWORD_USER)
    plan_match = keyring.get_password(KEYRING_SERVICE, PLAN_USER)
    if not cpf or not password or not plan_match:
        logging.error("Credencial Allcare ausente. Execute setup_agent.py.")
        return 1
    try:
        portal = PortalClient()
        portal.login(cpf, password, plan_match)
        start_month, end_month = current_period()
        bills = portal.list_bills(start_month, end_month)
        imported = 0
        for bill in bills:
            pdf_bytes = portal.download_bill(bill)
            result = hermes_api.call(
                "importAllcarePortalBill",
                {
                    "bill": {
                        "num_fatura": bill.get("num_fatura"),
                        "num_seq_cobranca": bill.get("num_seq_cobranca"),
                        "dt_vencimento": bill.get("dt_vencimento"),
                        "val_bruto": bill.get("val_bruto"),
                    },
                    "pdf_base64": base64.b64encode(pdf_bytes).decode("ascii"),
                },
            )
            imported += int(bool(result.get("imported")))
        logging.info("Sincronização concluída: %d boleto(s), %d novo(s).", len(bills), imported)
        return 0
    except (PortalError, hermes_api.HermesApiError, Exception) as error:
        logging.error("Sincronização Allcare falhou: %s", error)
        return 1


if __name__ == "__main__":
    sys.exit(main())
