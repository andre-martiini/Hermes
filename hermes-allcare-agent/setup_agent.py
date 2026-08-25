"""Configura e valida a credencial Allcare no cofre do Windows."""

from __future__ import annotations

import getpass
import sys

import keyring

import firebase_auth
import hermes_api
from portal import PortalClient, PortalError, current_period

KEYRING_SERVICE = "hermes-allcare-agent"
CPF_USER = "beneficiary-cpf"
PASSWORD_USER = "portal-password"
PLAN_USER = "plan-match"


def main() -> int:
    if not firebase_auth.has_session():
        print("Sessão local do Hermes não encontrada; iniciando login único.")
        from login_hermes import main as login_main
        if login_main() != 0:
            return 1
    config = hermes_api.call("getAllcareLocalAgentConfig", {})
    password = getpass.getpass("Senha do Portal Allcare (máximo 10 caracteres): ")
    if not 1 <= len(password) <= 10:
        print("A senha precisa ter entre 1 e 10 caracteres.")
        return 1
    cpf = str(config["cpf"])
    plan_match = str(config["plan_match"])
    try:
        portal = PortalClient()
        portal.login(cpf, password, plan_match)
        start_month, end_month = current_period()
        bills = portal.list_bills(start_month, end_month)
    except PortalError as error:
        print(f"Não foi possível validar no Portal Allcare: {error}")
        return 1
    keyring.set_password(KEYRING_SERVICE, CPF_USER, cpf)
    keyring.set_password(KEYRING_SERVICE, PASSWORD_USER, password)
    keyring.set_password(KEYRING_SERVICE, PLAN_USER, plan_match)
    password = None
    print(f"Credencial validada e protegida. {len(bills)} boleto(s) disponível(is) no período atual.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
