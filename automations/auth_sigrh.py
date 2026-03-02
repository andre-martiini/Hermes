import tkinter as tk
from tkinter import simpledialog
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def iniciar_sessao_e_navegar():
    # 1. Captura das credenciais via Modal Tkinter
    root = tk.Tk()
    root.withdraw()
    usuario = simpledialog.askstring("Login SIGRH", "Digite seu usuário:")
    senha = simpledialog.askstring("Senha", "Digite sua senha:", show='*')

    # 2. Inicia o navegador e DESATIVA o bloqueador de pop-ups nativo do Chrome
    opcoes_chrome = Options()
    opcoes_chrome.add_argument("--disable-popup-blocking")
    
    driver = webdriver.Chrome(options=opcoes_chrome)
    driver.maximize_window()
    driver.get("https://sigrh.ifes.edu.br/sigrh/login.jsf")

    # 3. Injeta dados e faz o login
    driver.find_element(By.ID, "login").send_keys(usuario)
    driver.find_element(By.ID, "senha").send_keys(senha)
    driver.find_element(By.ID, "logar").click()

    # Remove credenciais da memória
    del usuario
    del senha

    espera = WebDriverWait(driver, 10)

    # 4. Bypass da tela intermediária
    try:
        espera_curta = WebDriverWait(driver, 3)
        botao_continuar = espera_curta.until(
            EC.element_to_be_clickable((By.ID, "idFormDadosEntradaSaida:idBtnContinuar"))
        )
        botao_continuar.click()
        
        alerta = espera_curta.until(EC.alert_is_present())
        alerta.accept()
    except:
        pass

    # 5. NAVEGAÇÃO DIRETA (VIA JAVASCRIPT)
    menu_espelho = espera.until(
        EC.presence_of_element_located((By.ID, "menu:EspelhoPontoServidor"))
    )
    driver.execute_script("arguments[0].click();", menu_espelho)

    return driver, espera