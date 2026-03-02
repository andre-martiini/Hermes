from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait

def iniciar_sessao_pgd():
    opcoes_chrome = Options()
    opcoes_chrome.add_argument("--disable-popup-blocking")
    
    driver = webdriver.Chrome(options=opcoes_chrome)
    driver.maximize_window()
    driver.get("https://pgd.ifes.edu.br/")
    
    espera = WebDriverWait(driver, 15)
    
    print("Navegador aberto. Faça o login manualmente no sistema Petrvs.")
    print("A automação continuará automaticamente após detectar o painel principal...")
    
    return driver, espera

if __name__ == "__main__":
    iniciar_sessao_pgd()