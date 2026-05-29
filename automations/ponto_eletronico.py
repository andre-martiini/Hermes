import time
import datetime
import calendar
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import StaleElementReferenceException, TimeoutException

# Importa a função de login e navegação do arquivo auth_sigrh.py
from auth_sigrh import iniciar_sessao_e_navegar

def preencher_ponto_eletronico():
    # Inicia o navegador e recupera as variáveis (DRIVER É DEFINIDO AQUI)
    driver, espera = iniciar_sessao_e_navegar()
    
    try:
        # -------------------------------------------------------------
        # 1. CÁLCULO E SELEÇÃO DO MÊS ALVO
        # -------------------------------------------------------------
        hoje = datetime.date.today()
        primeiro_dia_mes_atual = hoje.replace(day=1)
        ultimo_dia_mes_anterior = primeiro_dia_mes_atual - datetime.timedelta(days=1)

        # Se estiver na segunda quinzena (dia >= 15), registra o mês atual
        if hoje.day >= 15:
            mes_alvo = hoje.month
            print(f"Segunda quinzena detectada ({hoje.day}/_). Registrando ponto do mês atual ({mes_alvo}).")
        else:
            mes_alvo = ultimo_dia_mes_anterior.month
            print(f"Primeira quinzena detectada ({hoje.day}/_). Registrando ponto do mês anterior ({mes_alvo}).")

        select_mes_el = espera.until(EC.presence_of_element_located((
            By.XPATH, "//select[contains(@id, 'mes') or contains(@name, 'mes') or contains(@id, 'Mes') or contains(@name, 'Mes')]"
        )))
        
        Select(select_mes_el).select_by_value(str(mes_alvo))
        print(f"Mês {mes_alvo} selecionado.")
        
        btn_buscar = driver.find_element(By.XPATH, "//input[@value='Buscar'] | //button[contains(text(), 'Buscar')]")
        btn_buscar.click()

        # -------------------------------------------------------------
        # 2. SELECIONAR O SERVIDOR
        # -------------------------------------------------------------
        try:
            btn_selecionar = espera.until(
                EC.element_to_be_clickable((By.XPATH, "//a[contains(@id, 'selecionar')] | //img[contains(@title, 'Selecionar Servidor')]/parent::a"))
            )
            btn_selecionar.click()
            print("Servidor selecionado.")
        except:
            print("Seleção de servidor ignorada (já selecionado).")

        # -------------------------------------------------------------
        # 3. LOOP DE PREENCHIMENTO
        # -------------------------------------------------------------
        espera.until(EC.presence_of_element_located((By.ID, "tabela")))
        print("Iniciando processamento dos relógios...")

        while True:
            janela_principal = driver.current_window_handle
            time.sleep(1.5)
            
            relogios = driver.find_elements(By.XPATH, "//table[@id='tabela']//img[contains(@src, 'pendencias_ponto.png')]")
            
            if not relogios:
                print("Fim dos registros! Todos os dias foram preenchidos.")
                break
                
            print(f"Restam {len(relogios)} registros. Processando próximo...")
            
            try:
                relogio_atual = relogios[0]
                linha_atual = relogio_atual.find_element(By.XPATH, "./ancestor::tr")
                btn_mais = linha_atual.find_element(By.XPATH, ".//img[contains(@src, 'adiciona.gif')]")
                
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn_mais)
                time.sleep(1) 
                
                # Clica no "+"
                driver.execute_script("arguments[0].click();", btn_mais)
                time.sleep(2)
                
                # Seleção da opção exata
                xpath_opcao_exata = "//*[text()='PGD. TELETRABALHO INTEGRAL']"
                opcoes_pgd = driver.find_elements(By.XPATH, xpath_opcao_exata)
                
                clicou_pgd = False
                for opcao in opcoes_pgd:
                    if opcao.is_displayed():
                        driver.execute_script("arguments[0].click();", opcao)
                        clicou_pgd = True
                        print("Opção 'PGD. TELETRABALHO INTEGRAL' selecionada.")
                        break
                
                if not clicou_pgd:
                    driver.execute_script("arguments[0].click();", opcoes_pgd[0])

                # --- JANELA POP-UP (AJUSTE FINAL PELO ID) ---
                WebDriverWait(driver, 15).until(EC.number_of_windows_to_be(2))
                janela_popup = [h for h in driver.window_handles if h != janela_principal][0]
                driver.switch_to.window(janela_popup)
                
                # Espera o botão carregar usando o ID exato que você encontrou
                # O XPath com @id é a forma mais segura para IDs que contêm ':'
                id_botao = "cadastroAusencia:cadastrarAusencia"
                
                print(f"Buscando botão pelo ID: {id_botao}")
                
                # Aguarda o botão estar presente e visível
                btn_cadastrar = WebDriverWait(driver, 20).until(
                    EC.visibility_of_element_located((By.XPATH, f"//*[@id='{id_botao}']"))
                )
                
                # Vamos usar um clique duplo: Foco + Clique Real
                driver.execute_script("arguments[0].focus();", btn_cadastrar)
                time.sleep(1)
                
                # Clique nativo (simula o mouse real)
                try:
                    btn_cadastrar.click()
                except:
                    # Backup via Javascript se o clique nativo for bloqueado
                    driver.execute_script("arguments[0].click();", btn_cadastrar)

                print("Botão Cadastrar acionado! Aguardando 15 segundos de processamento...")
                
                # Mantém a janela aberta pelos 15 segundos solicitados
                time.sleep(15)
                
                # Tenta fechar o pop-up (se ele já não tiver fechado sozinho)
                if len(driver.window_handles) > 1:
                    driver.close()
                
                driver.switch_to.window(janela_principal)
                driver.refresh()
                print("Página principal atualizada.")
                
                # Espera a folha de ponto carregar novamente
                WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.ID, "tabela")))
                
                # Volta para a principal e dá F5
                driver.switch_to.window(janela_principal)
                driver.refresh()
                print("Página atualizada. Verificando próximo...")
                
                WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.ID, "tabela")))

            except Exception as e:
                print(f"Erro no ciclo: {type(e).__name__}. Recuperando...")
                for handle in driver.window_handles:
                    if handle != janela_principal:
                        driver.switch_to.window(handle)
                        driver.close()
                driver.switch_to.window(janela_principal)
                driver.refresh()
                time.sleep(2)
                continue

    finally:
        print("Automação finalizada.")
        # driver.quit() # Descomente se quiser que o Chrome feche sozinho ao terminar

if __name__ == "__main__":
    preencher_ponto_eletronico()