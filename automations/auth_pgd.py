from __future__ import annotations

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait


def iniciar_sessao_pgd():
    """Abre uma sessão visível do Chrome para autenticação manual no Petrvs."""
    opcoes = Options()
    opcoes.add_argument("--disable-popup-blocking")
    opcoes.add_argument("--start-maximized")

    driver = webdriver.Chrome(options=opcoes)
    driver.get("https://pgd.ifes.edu.br/")
    print("Petrvs aberto. Faça o login manualmente, se necessário.")
    return driver, WebDriverWait(driver, 30)
