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

                        # 1. Descrição — único textarea da página quando o formulário está aberto
                        campo_desc = WebDriverWait(driver, 15).until(
                            lambda d: d.execute_script("return document.querySelector('textarea');")
                        )
                        driver.execute_script("arguments[0].focus();", campo_desc)
                        time.sleep(0.3)
                        driver.execute_script("arguments[0].value = '';", campo_desc)
                        campo_desc.send_keys(reg.get('descricao_atividade', ''))
                        campo_desc.send_keys(Keys.TAB)  # dispara o blur/change do Angular
                        time.sleep(0.3)

                        # 2. Expansão da Seta (Datas) — clica só se ainda estiver recolhido (down = recolhido)
                        try:
                            arrow_down = driver.find_element(By.XPATH, "//i[contains(@class, 'bi-arrow-down-circle')]")
                            driver.execute_script("arguments[0].click();", arrow_down)
                            time.sleep(1.2)
                        except:
                            pass  # Já expandido (seta virou bi-arrow-up-circle) ou não presente

                        # Regra André: Se mesmo dia, termina no dia seguinte
                        ini_dt = datetime.fromisoformat(reg.get('data_inicio').replace('Z', ''))
                        fim_dt = datetime.fromisoformat(reg.get('data_fim').replace('Z', ''))
                        if ini_dt.date() == fim_dt.date():
                            fim_dt = fim_dt + timedelta(days=1)

                        data_ini_iso = ini_dt.strftime("%Y-%m-%dT%H:%M")
                        data_fim_iso = fim_dt.strftime("%Y-%m-%dT%H:%M")

                        # 3. Injeta datas via JS — busca por type em vez de ID (IDs não são acessíveis)
                        js_set_value = """
                            var el = arguments[0];
                            var setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                            setter.call(el, arguments[1]);
                            el.dispatchEvent(new Event('input', { bubbles: true }));
                            el.dispatchEvent(new Event('change', { bubbles: true }));
                        """
                        campos_data = WebDriverWait(driver, 10).until(
                            lambda d: d.find_elements(By.XPATH, "//input[@type='datetime-local']") or None
                        )
                        driver.execute_script(js_set_value, campos_data[0], data_ini_iso)
                        time.sleep(0.3)
                        driver.execute_script(js_set_value, campos_data[1], data_fim_iso)
                        time.sleep(0.5)

                        # 4. Clica no botão de salvar (check azul)
                        btn_salvar = espera.until(EC.element_to_be_clickable((By.XPATH,
                            "//button[contains(@class, 'btn-outline-primary') and .//i[contains(@class, 'bi-check-circle')]]"
                        )))
                        driver.execute_script("arguments[0].click();", btn_salvar)

                        print(f"  > [SUCESSO] {data_ini_iso} -> {data_fim_iso}")

                        # Aguarda o formulário fechar (textarea some da página)
                        WebDriverWait(driver, 10).until(
                            lambda d: not d.execute_script("return !!document.querySelector('textarea');")
                        )
                        time.sleep(1)

                        # Limpeza Final: Retrai a entrega
                        try:
                            icone_dash = linha.find_element(By.XPATH, ".//i[contains(@class, 'bi-dash-square')]")
                            driver.execute_script("arguments[0].click();", icone_dash)
                            time.sleep(1)
                        except: pass

                except Exception as e:
                    print(f"  > Erro no registro [{type(e).__name__}]: {str(e)[:200]}")
                    # Cancela o formulário aberto (botão vermelho bi-dash-circle)
                    try:
                        btn_cancelar = driver.find_element(By.XPATH,
                            "//button[contains(@class, 'btn-outline-danger') and .//i[contains(@class, 'bi-dash-circle')]]"
                        )
                        driver.execute_script("arguments[0].click();", btn_cancelar)
                        time.sleep(1)
                    except:
                        pass
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
