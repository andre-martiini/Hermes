
import os
import re
import json
import asyncio
from playwright.async_api import async_playwright, Page, BrowserContext
from datetime import datetime
import logging

# Configuração de Logs
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("habilitation_rpa.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Diretório base para salvamento
BASE_DIR = os.path.join(os.getcwd(), "fornecedores")

class DownloaderHabilitacao:
    def __init__(self, cnpjs, headless=False):
        self.cnpjs = cnpjs
        self.headless = headless
        if not os.path.exists(BASE_DIR):
            os.makedirs(BASE_DIR)

    async def run(self):
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.headless)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
            )
            
            for cnpj in self.cnpjs:
                cnpj_clean = re.sub(r'\D', '', cnpj)
                output_path = os.path.join(BASE_DIR, cnpj_clean)
                if not os.path.exists(output_path):
                    os.makedirs(output_path)
                
                logger.info(f"[*] Iniciando coleta para o CNPJ: {cnpj}")
                
                # Módulos de Automação
                current_tasks = [
                    self.run_module(self.extrair_sicaf, context, cnpj_clean, output_path),
                    self.run_module(self.extrair_ceis_cnep, context, cnpj_clean, output_path),
                    self.run_module(self.extrair_sefaz_es, context, cnpj_clean, output_path),
                    self.run_module(self.extrair_cnd_vitoria, context, cnpj_clean, output_path),
                    self.run_module(self.extrair_cnd_bsf, context, cnpj_clean, output_path),
                    self.run_module(self.extrair_cndt, context, cnpj_clean, output_path),
                    self.run_module(self.extrair_cnj, context, cnpj_clean, output_path),
                    self.run_module(self.extrair_tcu, context, cnpj_clean, output_path),
                    self.run_module(self.extrair_simples_nacional, context, cnpj_clean, output_path)
                ]
                
                # Executa sequencialmente para evitar sobrecarga e problemas de sessão
                for task in current_tasks:
                    await task
                
                logger.info(f"[OK] Finalizada coleta para o CNPJ: {cnpj}")
                
            await browser.close()

    async def run_module(self, func, context, cnpj, output_path):
        module_name = func.__name__
        try:
            logger.info(f"[Módulo] {module_name} -> Iniciando...")
            await func(context, cnpj, output_path)
            logger.info(f"[Módulo] {module_name} -> Sucesso.")
        except Exception as e:
            logger.error(f"[Módulo] {module_name} -> FALHOU: {str(e)}")

    async def _handle_download(self, page, click_selector, filename, output_path):
        """Helper para capturar downloads"""
        async with page.expect_download() as download_info:
            await page.click(click_selector)
        download = await download_info.value
        final_path = os.path.join(output_path, filename)
        await download.save_as(final_path)
        logger.info(f"Arquivo salvo: {filename}")

    # --- MÓDULOS ESPECÍFICOS ---

    async def extrair_sicaf(self, context, cnpj, output_path):
        """
        ZONA DE INTERVENÇÃO HUMANA:
        - Login no ComprasNet/SICAF via Gov.br
        - Superação de Captcha se houver
        """
        page = await context.new_page()
        await page.goto("https://www3.comprasnet.gov.br/sicaf-web/index.jsf")
        
        logger.info("[HITL] SICAF: Por favor, realize o login e navegue até a consulta de fornecedor se necessário.")
        # Aguarda o elemento de consulta estar disponível (exemplo de seletor genérico)
        await page.wait_for_selector("input[id*='cnpj']", timeout=0)
        
        await page.fill("input[id*='cnpj']", cnpj)
        # Lógica de iteração conforme os níveis do SICAF
        # (Aqui o código seria expandido com seletores reais do sistema)
        # await self._handle_download(page, "button#nivel1", "SICAF_Nivel_1.pdf", output_path)
        
        await page.close()

    async def extrair_ceis_cnep(self, context, cnpj, output_path):
        """Portal da Transparência - CEIS/CNEP"""
        page = await context.new_page()
        await page.goto("https://portaldatransparencia.gov.br/sancoes/ceis?ordenarPor=nome&direcao=asc")
        
        # ZONA DE INTERVENÇÃO HUMANA: Filtro por CNPJ e Captcha do Portal
        await page.wait_for_selector("input#seletor-cnpj", timeout=0)
        await page.fill("input#seletor-cnpj", cnpj)
        # await self._handle_download(page, "button.download", "CEIS_CNEP.pdf", output_path)
        
        await page.close()

    async def extrair_sefaz_es(self, context, cnpj, output_path):
        """SEFAZ-ES - Certidão Negativa Estadual"""
        page = await context.new_page()
        await page.goto("https://internet.sefaz.es.gov.br/agenciavirtual/area_publica/cnd/emissao.php")
        
        await page.fill("input#cnpj", cnpj)
        logger.info("[HITL] SEFAZ-ES: Resolva o Captcha e clique em Emitir.")
        # Espera o botão de download/impressão aparecer após o captcha
        await page.wait_for_selector("button#imprimir", timeout=0)
        await self._handle_download(page, "button#imprimir", "CND_Estadual_ES.pdf", output_path)
        
        await page.close()

    async def extrair_cnd_vitoria(self, context, cnpj, output_path):
        """Prefeitura de Vitória - CND Municipal"""
        page = await context.new_page()
        await page.goto("https://sistemas.vitoria.es.gov.br/certidao/")
        
        await page.fill("input#identificacao", cnpj)
        logger.info("[HITL] Vitória: Resolva o Captcha.")
        await page.wait_for_selector("a#btnDownload", timeout=0)
        await self._handle_download(page, "a#btnDownload", "CND_Municipal_Vitoria.pdf", output_path)
        
        await page.close()

    async def extrair_cnd_bsf(self, context, cnpj, output_path):
        """Barra de São Francisco - CND Municipal"""
        page = await context.new_page()
        await page.goto("https://barradesaofrancisco-es.portaltributario.com.br/certidao-negativa") # URL fictícia/comum em portais tributários
        
        logger.info("[HITL] BSF: Insira o CNPJ e resolva o Captcha.")
        await page.wait_for_selector("button.btn-download", timeout=0)
        await self._handle_download(page, "button.btn-download", "CND_Municipal_BSF.pdf", output_path)
        
        await page.close()

    async def extrair_cndt(self, context, cnpj, output_path):
        """TST - Certidão Negativa de Débitos Trabalhistas"""
        page = await context.new_page()
        await page.goto("https://www.tst.jus.br/certidao")
        
        # Botão 'Emitir Certidão'
        await page.click("text=Emitir Certidão")
        await page.fill("input#cnpj", cnpj)
        logger.info("[HITL] CNDT: Resolva o Captcha.")
        await page.wait_for_selector("text=Baixar Certidão", timeout=0)
        await self._handle_download(page, "text=Baixar Certidão", "CNDT_Trabalhista.pdf", output_path)
        
        await page.close()

    async def extrair_cnj(self, context, cnpj, output_path):
        """CNJ - Improbidade Administrativa"""
        page = await context.new_page()
        await page.goto("https://www.cnj.jus.br/improbidade_adm/consultar_requerido.php")
        
        await page.fill("input#cnpj_cpf", cnpj)
        logger.info("[HITL] CNJ: Clique em Consultar.")
        await page.wait_for_selector("button#exportar_pdf", timeout=0)
        await self._handle_download(page, "button#exportar_pdf", "CNJ_Improbidade.pdf", output_path)
        
        await page.close()

    async def extrair_tcu(self, context, cnpj, output_path):
        """TCU - Licitantes Inidôneos e Inabilitados"""
        page = await context.new_page()
        # Módulo 1: Inidôneos
        await page.goto("https://contas.tcu.gov.br/sagas/Sagas?f=exibirInidoneos")
        await page.fill("input#pesquisa", cnpj)
        logger.info("[HITL] TCU: Verifique o resultado e salve PDF se necessário.")
        # TCUs geralmente não tem um botão 'Download PDF' direto para cada item, mas sim exportação geral.
        # Aqui o RPA aguarda a interação do usuário para decidir o download.
        await page.wait_for_selector("text=Resultado", timeout=0)
        
        await page.close()

    async def extrair_simples_nacional(self, context, cnpj, output_path):
        """Consulta Optantes pelo Simples Nacional"""
        page = await context.new_page()
        await page.goto("https://www8.receita.fazenda.gov.br/SimplesNacional/Aplicacoes/atbhe/ConsultaOptantes.app/ConsultarOpcao.aspx")
        
        await page.fill("input#cnpj", cnpj)
        logger.info("[HITL] Simples Nacional: Resolva o Captcha.")
        await page.wait_for_selector("button#btnImprimir", timeout=0)
        await self._handle_download(page, "button#btnImprimir", "Simples_Nacional.pdf", output_path)
        
        await page.close()

# Execução direto para testes se necessário
if __name__ == "__main__":
    test_cnpjs = ["00.000.000/0001-91"] # Exemplo
    downloader = DownloaderHabilitacao(test_cnpjs, headless=False)
    asyncio.run(downloader.run())
