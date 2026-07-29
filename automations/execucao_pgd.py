from __future__ import annotations

import time
from datetime import datetime, timedelta
from difflib import SequenceMatcher

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from auth_pgd import iniciar_sessao_pgd


def _set_native_value(driver, element, value: str) -> None:
    driver.execute_script(
        """
        const element = arguments[0];
        const value = arguments[1];
        const setter = Object.getOwnPropertyDescriptor(
          window.HTMLInputElement.prototype, 'value'
        ).set;
        setter.call(element, value);
        element.dispatchEvent(new Event('input', { bubbles: true }));
        element.dispatchEvent(new Event('change', { bubbles: true }));
        """,
        element,
        value,
    )


def preencher_execucao_pgd(dados_pgd: dict) -> None:
    """Automação histórica de registros de execução, mantida para compatibilidade."""
    driver, espera = iniciar_sessao_pgd()
    mes_referencia = dados_pgd.get("mes_ano", "")
    entregas = dados_pgd.get("entregas", [])
    print(f"Iniciando registros de execução para {mes_referencia}.")

    try:
        menu = WebDriverWait(driver, 300).until(
            EC.element_to_be_clickable(
                (
                    By.XPATH,
                    "//*[contains(text(), 'Registros De Execução') "
                    "or contains(text(), 'Registros de execução')]",
                )
            )
        )
        driver.execute_script("arguments[0].click();", menu)

        mes_formatado = (
            f"{mes_referencia.split('-')[1]}/{mes_referencia.split('-')[0]}"
            if "-" in mes_referencia
            else mes_referencia
        )
        painel = WebDriverWait(driver, 60).until(
            EC.presence_of_element_located(
                (
                    By.XPATH,
                    f"//button[contains(@class,'accordion-button') "
                    f"and contains(.,'{mes_formatado}')]",
                )
            )
        )
        if "collapsed" in painel.get_attribute("class"):
            driver.execute_script("arguments[0].click();", painel)
            time.sleep(1)

        for entrega in entregas:
            nome = str(entrega.get("nome_entrega", "")).strip()
            for registro in entrega.get("registros", []):
                componentes = driver.find_elements(By.TAG_NAME, "column-row")
                candidatos = [
                    (
                        SequenceMatcher(
                            None,
                            nome.lower()[:80],
                            componente.text.lower()[:80],
                        ).ratio(),
                        componente,
                    )
                    for componente in componentes
                ]
                if not candidatos:
                    print(f"[AVISO] Entrega não localizada: {nome}")
                    continue
                similaridade, componente = max(candidatos, key=lambda item: item[0])
                if similaridade < 0.7:
                    print(f"[AVISO] Correspondência insuficiente: {nome}")
                    continue

                linha = componente.find_element(By.XPATH, "./ancestor::tr[1]")
                expandir = linha.find_element(
                    By.XPATH,
                    ".//i[contains(@class,'bi-plus-square') "
                    "or contains(@class,'bi-dash-square')]",
                )
                if "bi-plus-square" in expandir.get_attribute("class"):
                    driver.execute_script("arguments[0].click();", expandir)
                    time.sleep(1)

                adicionar = linha.find_element(
                    By.XPATH,
                    "./following-sibling::tr//i[contains(@class,'bi-plus-circle')]",
                )
                driver.execute_script("arguments[0].click();", adicionar)

                descricao = WebDriverWait(driver, 20).until(
                    EC.visibility_of_element_located((By.XPATH, "//textarea"))
                )
                descricao.send_keys(registro.get("descricao_atividade", ""))
                descricao.send_keys(Keys.TAB)

                inicio = datetime.fromisoformat(
                    str(registro.get("data_inicio", "")).replace("Z", "")
                )
                fim = datetime.fromisoformat(
                    str(registro.get("data_fim", "")).replace("Z", "")
                )
                if inicio.date() == fim.date():
                    fim += timedelta(days=1)
                campos = WebDriverWait(driver, 15).until(
                    lambda d: d.find_elements(By.XPATH, "//input[@type='datetime-local']")
                    or None
                )
                _set_native_value(driver, campos[0], inicio.strftime("%Y-%m-%dT%H:%M"))
                _set_native_value(driver, campos[1], fim.strftime("%Y-%m-%dT%H:%M"))

                salvar = espera.until(
                    EC.element_to_be_clickable(
                        (
                            By.XPATH,
                            "//button[.//i[contains(@class,'bi-check-circle')]]",
                        )
                    )
                )
                driver.execute_script("arguments[0].click();", salvar)
                print(f"[OK] Registro criado: {nome}")
                time.sleep(1)
    finally:
        print("Automação de registros encerrada.")
