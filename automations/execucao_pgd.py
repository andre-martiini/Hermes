import time
import sys
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.webdriver import ActionChains

# Importa o login manual que criamos no outro arquivo
from auth_pgd import iniciar_sessao_pgd

class DualLogger:
    def __init__(self, filename):
        self.file = open(filename, 'w', encoding='utf-8')
        self.stdout = sys.stdout
    def write(self, data):
        self.file.write(data)
        self.file.flush()
        self.stdout.write(data)
    def flush(self):
        self.file.flush()
        self.stdout.flush()

def preencher_execucao_pgd(dados_pgd):
    original_stdout = sys.stdout
    sys.stdout = DualLogger("pgd_automation.log")
    try:
        # 1. Inicia a sessão
        driver, espera = iniciar_sessao_pgd()
    
        mes_referencia = dados_pgd.get('mes_ano', 'Mês não informado')
        entregas = dados_pgd.get('entregas', [])
        
        print(f"Iniciando preenchimento para o período: {mes_referencia}")
        
        try:
            xpath_registro = "//*[contains(text(), 'Registros De Execução') or contains(text(), 'Registros de execução')]"
            btn_registro = WebDriverWait(driver, 300).until(EC.element_to_be_clickable((By.XPATH, xpath_registro)))
            
            cartao_registro = btn_registro.find_element(By.XPATH, "./ancestor-or-self::*[contains(@class, 'card') or contains(@class, 'btn') or @role='button' or position()=1]")
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", cartao_registro)
            time.sleep(1)
            driver.execute_script("arguments[0].click();", cartao_registro)
        except Exception as e:
            print(f"Erro ao acessar painel: {type(e).__name__}")
            return

        # --- EXPANSÃO DAS ABAS ---
        try:
            mes_formatado = f"{mes_referencia.split('-')[1]}/{mes_referencia.split('-')[0]}" if "-" in mes_referencia else mes_referencia
            xpath_painel = f"//button[contains(@class, 'accordion-button') and contains(., '{mes_formatado}')]"
            painel_plano = espera.until(EC.presence_of_element_located((By.XPATH, xpath_painel)))
            
            if "collapsed" in painel_plano.get_attribute("class"):
                driver.execute_script("arguments[0].click();", painel_plano)
                time.sleep(2)

            xpath_btn_quadrado = f"//*[contains(text(), '{mes_formatado}')]/ancestor::*//i[contains(@class, 'bi-plus-square') and @role='button']"
            btn_quadrado = espera.until(EC.presence_of_element_located((By.XPATH, xpath_btn_quadrado)))
            driver.execute_script("arguments[0].click();", btn_quadrado)
            time.sleep(2)
        except Exception as e:
            print(f"Aviso na expansão: {str(e)}")

        # --- LOOP DE ENTREGAS ---
        for entrega in entregas:
            nome_entrega = entrega.get('nome_entrega')
            registros = entrega.get('registros', [])
            
            for reg in registros:
                try:
                    # 1. Localização Dinâmica da Entrega (Evita Stale Element)
                    componentes_entrega = driver.find_elements(By.TAG_NAME, "column-row")
                    melhor_match = None
                    maior_sim = 0
                    
                    for comp in componentes_entrega:
                        texto = driver.execute_script("return arguments[0].innerText;", comp).lower()
                        sim = SequenceMatcher(None, nome_entrega.lower()[:50], texto[:50]).ratio()
                        if sim > maior_sim:
                            maior_sim = sim
                            melhor_match = comp

                    if melhor_match and maior_sim > 0.7:
                        linha = melhor_match.find_element(By.XPATH, "./ancestor::tr[1]")
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", linha)
                        
                        # Abre a gaveta para verificar duplicados
                        btn_expand = linha.find_element(By.XPATH, ".//i[contains(@class, 'bi-plus-square') or contains(@class, 'bi-dash-square')]")
                        if "bi-plus-square" in btn_expand.get_attribute("class"):
                            driver.execute_script("arguments[0].click();", btn_expand)
                            time.sleep(1.5)

                        # --- VERIFICAÇÃO DE DUPLICADO (TEXTO DA ATIVIDADE) ---
                        descricao_alvo = reg.get('descricao_atividade', '').strip().lower()
                        sub_tabela_xpath = "./following-sibling::tr[1]"
                        try:
                            sub_tabela = linha.find_element(By.XPATH, sub_tabela_xpath)
                            if descricao_alvo[:40] in sub_tabela.text.lower():
                                print(f"  > [PULAR] Registro já existe: {descricao_alvo[:30]}...")
                                # Retrai a gaveta para economizar espaço
                                icone_retrair = linha.find_element(By.XPATH, ".//i[contains(@class, 'bi-dash-square')]")
                                driver.execute_script("arguments[0].click();", icone_retrair)
                                continue
                        except:
                            pass # Se não achar sub-tabela, segue para criar

                        # Clica no botão circular de adicionar (+)
                        btn_add = linha.find_element(By.XPATH, "./following-sibling::tr//i[contains(@class, 'bi-plus-circle')]")
                        driver.execute_script("arguments[0].click();", btn_add)
                        print(f"  > Abrindo formulário para: {nome_entrega}")
                        time.sleep(2)

                        # --- PREENCHIMENTO DO FORMULÁRIO ---
                        
                        # 1. Descrição
                        campo_desc = espera.until(EC.element_to_be_clickable((By.XPATH, "//textarea | //input[contains(@class, 'form-control')]")))
                        campo_desc.click()
                        actions = ActionChains(driver)
                        actions.key_down(Keys.CONTROL).send_keys('a').key_up(Keys.CONTROL).send_keys(Keys.BACKSPACE).perform()
                        campo_desc.send_keys(reg.get('descricao_atividade', ''))

                        # 2. Expansão da Seta (Datas)
                        driver.find_element(By.XPATH, "//i[contains(@class, 'bi-arrow-down-circle')]").click()
                        time.sleep(1.2)

                        # Regra André: Se mesmo dia, termina no dia seguinte
                        ini_dt = datetime.fromisoformat(reg.get('data_inicio').replace('Z', ''))
                        fim_dt = datetime.fromisoformat(reg.get('data_fim').replace('Z', ''))
                        if ini_dt.date() == fim_dt.date():
                            fim_dt = fim_dt + timedelta(days=1)
                        
                        data_ini_str = ini_dt.strftime("%d%m%Y")
                        data_fim_str = fim_dt.strftime("%d%m%Y")

                        # 3. Digitação com Estratégia das 5 Setas
                        campo_data_ini = driver.find_element(By.ID, "ID_homeexecucao_datainicio_date")
                        driver.execute_script("arguments[0].click();", campo_data_ini) # Clique via JS para garantir foco
                        time.sleep(0.5)
                        
                        actions = ActionChains(driver)
                        
                        # Estratégia André: Bater no muro da esquerda
                        print("  > Posicionando cursor no início...")
                        for _ in range(7): # Aumentei para 7 para garantir
                            actions.send_keys(Keys.LEFT).perform()
                        
                        # Digita Início número a número
                        for n in data_ini_str:
                            actions.send_keys(n).perform()
                            time.sleep(0.05)
                        
                        # Navega até Fim (4 TABs)
                        for _ in range(4): actions.send_keys(Keys.TAB).perform()
                        time.sleep(0.2)
                        
                        # Digita Fim número a número
                        for n in data_fim_str:
                            actions.send_keys(n).perform()
                            time.sleep(0.05)
                        
                        # Navega até Concluir (4 TABs) e ENTER
                        for _ in range(4): actions.send_keys(Keys.TAB).perform()
                        time.sleep(0.5)
                        actions.send_keys(Keys.ENTER).perform()
                        
                        print(f"  > [SUCESSO] {data_ini_str} -> {data_fim_str}")
                        
                        # Espera Robusta: Aguarda o modal sumir da tela
                        WebDriverWait(driver, 10).until(EC.invisibility_of_element_located((By.CLASS_NAME, "modal-content")))
                        time.sleep(2)

                        # Limpeza Final: Retrai a entrega
                        try:
                            icone_dash = linha.find_element(By.XPATH, ".//i[contains(@class, 'bi-dash-square')]")
                            driver.execute_script("arguments[0].click();", icone_dash)
                            time.sleep(1)
                        except: pass

                except Exception as e:
                    print(f"  > Erro no registro: {str(e)}")
                    # Tenta fechar o modal no botão 'X' para não travar o loop
                    try:
                        driver.execute_script("document.querySelector('.modal-header .btn-close')?.click();")
                    except: pass
                    time.sleep(2)

    except Exception as general_error:
        print(f"\n[FALHA GERAL] A execução foi interrompida: {str(general_error)}")
    finally:
        print("\nProcesso concluído com sucesso!")
        sys.stdout.file.close()
        sys.stdout = original_stdout

if __name__ == "__main__":
    # Para teste, os dados virão do seu sistema React
    pass
