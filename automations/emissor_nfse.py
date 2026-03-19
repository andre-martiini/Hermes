import asyncio
from playwright.async_api import async_playwright
import sys

async def safe_fill(page, selector, value, timeout=5000):
    try:
        locator = page.locator(selector).first
        await locator.wait_for(state="visible", timeout=timeout)
        await locator.fill(value)
        return True
    except:
        return False

async def safe_click(page, selector, timeout=5000):
    try:
        locator = page.locator(selector).first
        await locator.wait_for(state="visible", timeout=timeout)
        # Verifica se o elemento está habilitado antes de clicar
        if await locator.is_enabled():
            await locator.click()
            return True
        else:
            print(f"Nota: Elemento {selector} já está selecionado ou desabilitado.")
            return True # Consideramos sucesso se já estiver no estado certo
    except:
        return False

async def run_nfse_automation(data):
    user_ready = asyncio.Event()
    async def on_hermes_ready(source): user_ready.set()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()
        await context.expose_binding("onHermesReady", on_hermes_ready)

        await context.add_init_script("""() => {
            const injectButton = () => {
                if (document.getElementById('hermes-automation-trigger')) return;
                const btn = document.createElement('button');
                btn.id = 'hermes-automation-trigger';
                btn.innerText = '✅ LOGADO: INICIAR PREENCHIMENTO';
                btn.style.cssText = `position: fixed; top: 20px; left: 50%; transform: translateX(-50%); z-index: 100000; padding: 15px 30px; background-color: #059669; color: white; font-weight: bold; border: 4px solid white; border-radius: 50px; box-shadow: 0 10px 15px -3px rgba(0,0,0,0.3); cursor: pointer; font-family: sans-serif;`;
                btn.onclick = () => { btn.innerText = '⬇️ INICIANDO...'; btn.style.backgroundColor = '#0284c7'; window.onHermesReady(); };
                document.body.appendChild(btn);
            };
            injectButton(); setInterval(injectButton, 1500); 
        }""")

        print(f"Navegando para: {data['url']}")
        try:
            await page.goto(data['url'], wait_until='commit', timeout=60000)
        except Exception as e:
            print(f"Nota: Navegação inicial interrompida, mas continuando... ({e})")

        # TENTATIVA DE LOGIN AUTOMÁTICO
        login_auto = data.get('portal_login')
        senha_auto = data.get('portal_senha')
        login_successful_transition = False
        
        if login_auto and senha_auto:
            print(f"📍 URL Atual: {page.url}")
            print(f"🔐 Tentando login automático para {login_auto}...")
            try:
                # Aguarda o campo de inscrição com paciência redobrada
                await page.wait_for_selector('#Inscricao', timeout=20000)
                
                # Preenchimento do Usuário (CPC/CNPJ)
                print("Limpando e preenchendo Usuário...")
                await page.focus('#Inscricao')
                await page.keyboard.press("Control+A")
                await page.keyboard.press("Backspace")
                await page.keyboard.type(login_auto, delay=100)
                
                # Preenchimento da Senha
                print("Preenchendo Senha...")
                await page.focus('#Senha')
                await page.keyboard.type(senha_auto, delay=100)
                
                # Clique no Botão Entrar específico da seção de Senha
                print("Clicando no botão 'Entrar' (Usuário/Senha)...")
                # O seletor abaixo busca o botão que está próximo ao campo de Senha para não clicar no botao do Gov.br
                await page.locator('div:has(> #Senha) ~ button, button:has-text("Entrar")').nth(0).click(force=True)
                
                # Aguarda transição ou erro
                await asyncio.sleep(3)
                if "#Inscricao" in await page.content():
                     print("⚠️ Login ainda na mesma tela. Pode ser erro de senha ou Captcha.")
                else:
                     print("✅ Transição de página detectada.")
                     login_successful_transition = True # Define a flag como True se houve transição

            except Exception as e:
                print(f"Nota: Login automático falhou. ({e})")

        # Lógica de Prosseguimento: Automática (se login_auto e houve transição) ou Manual
        if login_auto and senha_auto and login_successful_transition:
            print("\n🚀 LOGIN AUTOMÁTICO DETECTADO!")
            print("Aguardando 4 segundos para estabilização do portal e prosseguindo automaticamente...")
            await asyncio.sleep(4)
        else:
            print("\n" + "="*40)
            print("💡 AGUARDANDO LOGIN MANUAL (ENTER)...")
            print("1. Verifique se o login foi concluído.")
            print("2. Se estiver logado, pressione ENTER aqui ou use o botão no Hermes.")
            print("="*40 + "\n")
            
            # Aguarda o ENTER (via teclado real ou via sinal da ponte STDIN)
            # Ou aguarda o clique no botão injetado pelo Hermes
            loop = asyncio.get_event_loop()
            terminal_task = asyncio.ensure_future(loop.run_in_executor(None, sys.stdin.readline))
            button_task = asyncio.ensure_future(user_ready.wait())
            await asyncio.wait([terminal_task, button_task], return_when=asyncio.FIRST_COMPLETED)
            for t in [terminal_task, button_task]: t.cancel()

        print("🚀 Iniciando preenchimento automático...")
        
        try:
            # NAVEGAÇÃO DO DASHBOARD PARA EMISSÃO
            if "DPS/Pessoas" not in page.url:
                print("Detectado Dashboard. Indo para 'Emissão Completa'...")
                await page.goto("https://www.nfse.gov.br/EmissorNacional/DPS/Pessoas", wait_until="domcontentloaded")

            # TELA 1: PESSOAS
            print("--- Tela 1: Identificação ---")
            await page.wait_for_selector('#DataCompetencia', timeout=30000)
            
            # Data de Competência
            campo_data = page.locator('#DataCompetencia')
            val_data = data['data_competencia'].replace("/", "")
            print(f"Preenchendo data: {val_data}")
            await campo_data.click()
            await campo_data.fill(val_data)
            await page.keyboard.press("Enter")
            await asyncio.sleep(1) # Espera o sistema processar a data

            # Tomador: Brasil
            print("Selecionando Tomador no Brasil (via JS)...")
            try:
                # O rádio button as vezes tem overlays. O evaluate via JS costuma ser infalível para disparar o evento.
                await page.evaluate("document.querySelector('input#Tomador_LocalDomicilio[value=\"1\"]').click()")
                
                # Aguarda o campo de CNPJ ficar visível
                print("Aguardando campo de CNPJ...")
                campo_cnpj = page.locator('#Tomador_Inscricao')
                
                # Tentativa de clique no label se o JS não funcionar de primeira
                for _ in range(5):
                    if await campo_cnpj.is_visible():
                        break
                    print("Campo CNPJ ainda oculto, tentando clicar no label 'Brasil'...")
                    await page.locator('label:has-text("Brasil")').first.click(force=True)
                    await asyncio.sleep(2)
                
            except Exception as e:
                print(f"Aviso ao selecionar Brasil: {e}")

            # CNPJ do Tomador
            print(f"Preenchendo CNPJ: {data['cnpj_tomador']}")
            await campo_cnpj.fill(data['cnpj_tomador'])
            await page.keyboard.press("Tab")
            
            # Espera o AJAX carregar os dados (Razão Social aparecer)
            print("Aguardando consulta do CNPJ...")
            await asyncio.sleep(4) 

            # Intermediário: Não informado (geralmente value 0)
            try:
                await page.locator('input#Intermediario_LocalDomicilio[value="0"], label:has-text("Intermediário não informado")').first.click(force=True)
            except: pass

            # Avançar
            print("Avançando para Tela 2...")
            await page.click('#btnAvancar')
            await page.wait_for_load_state("networkidle")

            # TELA 2: SERVIÇO
            print("--- Tela 2: Serviço Prestado ---")
            # Aguarda a tela 2 carregar via container principal do Select2
            print("Aguardando carregamento da Tela 2...")
            await page.wait_for_selector('.select2-selection', timeout=30000)

            # Município (Select2)
            print("Preenchendo Município (Select2)...")
            try:
                # ESTRATEGIA 1: Clique via JavaScript (Ignora viewport)
                print("Tentando clique via JS...")
                await page.evaluate("document.querySelector('span[id*=\"select2-LocalPrestacao_CodigoMunicipioPrestacao-container\"]').click()")
                await asyncio.sleep(1)
                
                # Verifica se o campo de busca apareceu
                search_field = page.locator('input.select2-search__field')
                if not await search_field.is_visible():
                    print("Clique JS não abriu busca. Tentando ESTRATÉGIA 2: Foco e Enter...")
                    # ESTRATEGIA 2: Focar no elemento e apertar Enter
                    await page.locator('.select2-selection').first.focus()
                    await page.keyboard.press("Enter")
                    await asyncio.sleep(1)
                
                # Se ainda não abriu, tenta a ESTRATÉGIA 3: Tabulação (sugerida pelo usuário)
                if not await search_field.is_visible():
                    print("Tentando ESTRATÉGIA 3: Tabulações...")
                    await page.keyboard.press("Home") # Volta ao topo
                    for _ in range(21):
                        await page.keyboard.press("Tab")
                    await page.keyboard.press("Enter")
                    await asyncio.sleep(1)

                # Preenchimento do campo de busca
                await search_field.fill("Vitória")
                await asyncio.sleep(2)
            except Exception as e:
                print(f"Aviso ao abrir campo de Município: {e}")
            
            # Seleciona a opção que contém especificamente 'Vitória/ES'
            opcoes = page.locator('li.select2-results__option')
            vitoria_es = opcoes.filter(has_text="Vitória/ES").first
            if await vitoria_es.count() > 0:
                await vitoria_es.click()
            else:
                await page.keyboard.press("Enter")
            
            await asyncio.sleep(2) # Pausa para fechar o seletor

            # Código de Tributação Nacional (Select2)
            # USANDO A ESTRATEGIA DE TABULAÇÃO SUGERIDA PELO USUÁRIO
            print("Navegando para Código de Tributação via TAB...")
            await page.keyboard.press("Tab") # Pula do Município para Tributação
            await asyncio.sleep(0.5)
            await page.keyboard.press("Enter") # Abre a busca do Tributação
            await asyncio.sleep(1)
            
            # O campo de busca costuma ser o mesmo elemento reaproveitado
            print("Preenchendo 17.01.01...")
            await search_field.fill("17.01.01")
            await asyncio.sleep(2)
            await page.keyboard.press("Enter") # Seleciona a primeira (e única)
            
            await asyncio.sleep(1)

            # O serviço prestado é um caso de: Não
            print("Selecionando 'Não' para imunidade/exportação (via JS)...")
            try:
                # Usando o mesmo método JS que funcionou no Tomador
                await page.evaluate("document.querySelector('input#ServicoPrestado_HaExportacaoImunidadeNaoIncidencia[value=\"0\"]').click()")
                await asyncio.sleep(1)
            except Exception as e:
                print(f"Aviso ao selecionar 'Não': {e}")
                # Fallback: tentar clicar no label pelo texto
                await page.locator('label:has-text("Não")').first.click(force=True)

            # Descrição do Serviço
            print("Preenchendo Descrição...")
            # Usando o ID exato fornecido: ServicoPrestado_Descricao
            await page.locator('textarea#ServicoPrestado_Descricao').fill(data['descricao'])

            # Avançar para Tela 3
            print("Avançando para Tela 3...")
            await page.click('button:has-text("Avançar"), button[type="submit"]')
            await page.wait_for_load_state("networkidle")

            # TELA 3: VALORES E TRIBUTOS (ESTRATEGIA COMPLETA + SHIFT+TAB REVERSO)
            print("--- Tela 3: Valores e Tributos (Preenchimento Completo) ---")
            campo_valor = page.locator('#Valores_ValorServico')
            await campo_valor.wait_for(state="visible", timeout=30000)
            
            # 1. PREENCHIMENTO LINEAR: Valor Bruto
            print(f"Preenchendo Valor Bruto: {data['valor_bruto']}")
            await campo_valor.click()
            await page.keyboard.press("Control+A")
            await page.keyboard.press("Backspace")
            # Enviamos o valor formatado com vírgula para que a máscara do site reconheça os decimais corretamente
            await page.keyboard.type(data['valor_bruto'].replace(".", ","))
            await page.keyboard.press("Tab")
            await asyncio.sleep(1)

            # 2. RADIOS ISSQN (Não / Não / Não)
            print("Selecionando 'Não' nos rádios ISSQN...")
            await page.evaluate("document.querySelectorAll('input#ISSQN_HaSuspensao[value=\"0\"], input#ISSQN_HaRetencao[value=\"0\"], input#ISSQN_HaBeneficioMunicipal[value=\"0\"]').forEach(el => { el.disabled=false; el.click(); })")
            await asyncio.sleep(1)

            # 3. SITUAÇÃO TRIBUTÁRIA E RETENÇÃO PIS/COFINS
            print("Configurando Situação Tributária (08) e 'Não Retido'...")
            try:
                # Situação: 08 e Retenção: 0 (Não)
                await page.evaluate("""() => {
                    let s = document.querySelector('#TributacaoFederal_PISCofins_SituacaoTributaria');
                    if(s) { s.value = '8'; s.dispatchEvent(new Event('change', {bubbles: true})); }
                    
                    let r = document.querySelector('input#TributacaoFederal_PISCofins_HaRetencao[value="0"]');
                    if(r) { r.click(); }
                }""")
                await asyncio.sleep(1)
            except: pass

            # 4. IMPOSTOS APROXIMADOS (Preenchimento de base)
            print("Configurando impostos aproximados (Federal, Estadual, Municipal)...")
            try:
                await page.evaluate("document.querySelector('input#ValorTributos_TipoValorTributos[value=\"1\"]').click()")
                await asyncio.sleep(1)
                for id_campo in ['#ValorTributos_ValorTotalFederal', '#ValorTributos_ValorTotalEstadual', '#ValorTributos_ValorTotalMunicipal']:
                    campo = page.locator(id_campo)
                    await campo.fill("0,00")
            except: pass

            # --- MANOBRA DE REFORÇO: O SHIFT+TAB REVERSO ---
            print("--- Iniciando Reforço Visual (Shift+Tab Reverso) ---")
            campo_municipal = page.locator('#ValorTributos_ValorTotalMunicipal')
            await campo_municipal.focus()
            await asyncio.sleep(1)

            # Voltar 6 TABS para CP
            print("Voltando 6 (Shift+Tab) para CP Retida...")
            for _ in range(6): 
                await page.keyboard.down("Shift")
                await page.keyboard.press("Tab")
                await page.keyboard.up("Shift")
                await asyncio.sleep(0.1)
            # Usando vírgula para evitar o erro de interpretação de escala (800,00 vs 80.000,00)
            val_cp = data.get('valor_cp', '0,00').replace(".", ",")
            await page.keyboard.type(val_cp)
            await asyncio.sleep(0.5)

            # Voltar 4 TABS para IRRF
            print("Voltando 4 (Shift+Tab) para IRRF...")
            for _ in range(4): 
                await page.keyboard.down("Shift")
                await page.keyboard.press("Tab")
                await page.keyboard.up("Shift")
                await asyncio.sleep(0.1)
            val_irrf = data.get('valor_irrf', '0,00').replace(".", ",")
            await page.keyboard.type(val_irrf)
            await asyncio.sleep(0.5)

            # Voltar 2 TABS para Tipo de Retenção
            print("Voltando 2 (Shift+Tab) para Tipo de Retenção...")
            for _ in range(2): 
                await page.keyboard.down("Shift")
                await page.keyboard.press("Tab")
                await page.keyboard.up("Shift")
                await asyncio.sleep(0.1)
            await page.keyboard.press("ArrowDown")
            await page.keyboard.press("ArrowDown")
            await page.keyboard.press("Enter")
            await asyncio.sleep(1)

            # FINAL: Avançar
            print("Avançando para Resumo Final (Clique Direto)...")
            await page.click('button:has-text("Avançar"), button[type="submit"]')
            await page.wait_for_load_state("networkidle")

            # Finalização
            print("\n" + "⭐"*10)
            print("AUTOMAÇÃO CONCLUÍDA COM SUCESSO!")
            print("Agora você está na tela de RESUMO.")
            print("Confira tudo e clique no botão final de EMITIR.")
            print("⭐"*10 + "\n")

        except Exception as e:
            print(f"❌ Erro durante a automação: {e}")
            import traceback
            traceback.print_exc()
        
        print("O navegador ficará aberto para sua revisão.")
        await asyncio.Event().wait()

if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument("--data", help="JSON data for the automation")
    args = parser.parse_args()

    if args.data:
        try:
            data = json.loads(args.data)
        except Exception as e:
            print(f"Erro ao parsear JSON: {e}")
            sys.exit(1)
    else:
        # Fallback para teste manual
        data = {
            'url': "https://www.nfse.gov.br/EmissorNacional/Login?ReturnUrl=%2fEmissorNacional",
            'data_competencia': "10/03/2026",
            'cnpj_tomador': "51.070.478/0001-29",
            'descricao': "Teste de automação via CLI.",
            'valor_bruto': "100,00",
            'valor_irrf': "0,00",
            'valor_cp': "0,00"
        }
    
    try:
        asyncio.run(run_nfse_automation(data))
    except KeyboardInterrupt:
        print("\nAutomação interrompida pelo usuário.")
    except KeyboardInterrupt:
        print("\nInterrompido.")
