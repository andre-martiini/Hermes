from __future__ import annotations

import time
import traceback
import unicodedata
from typing import Any

from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from auth_pgd import iniciar_sessao_pgd


PAUSA_ENTRE_ETAPAS = 1.0


def _normalizar(texto: str) -> str:
    return "".join(
        char
        for char in unicodedata.normalize("NFD", texto or "")
        if unicodedata.category(char) != "Mn"
    ).casefold()


def _set_native_value(driver, element, value: str) -> None:
    tag = element.tag_name.lower()
    prototype = (
        "window.HTMLTextAreaElement.prototype"
        if tag == "textarea"
        else "window.HTMLInputElement.prototype"
    )
    driver.execute_script(
        f"""
        const element = arguments[0];
        const setter = Object.getOwnPropertyDescriptor(
          {prototype}, 'value'
        ).set;
        setter.call(element, arguments[1]);
        element.dispatchEvent(new Event('input', {{ bubbles: true }}));
        element.dispatchEvent(new Event('change', {{ bubbles: true }}));
        element.dispatchEvent(new Event('blur', {{ bubbles: true }}));
        """,
        element,
        value,
    )


def _clicar(driver, element) -> None:
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
    driver.execute_script("arguments[0].click();", element)
    time.sleep(PAUSA_ENTRE_ETAPAS)


def _dialogo(driver):
    return WebDriverWait(driver, 30).until(
        lambda d: next(
            (
                item
                for item in d.find_elements(
                    By.XPATH,
                    "//div[@role='dialog' or contains(@class,'modal-content')]",
                )
                if item.is_displayed()
            ),
            None,
        )
    )


def _selecionar_opcao(driver, raiz, botao_xpath: str, texto: str) -> None:
    botao = WebDriverWait(raiz, 20).until(
        lambda _: next(
            (
                item
                for item in raiz.find_elements(By.XPATH, botao_xpath)
                if item.is_displayed() and item.is_enabled()
            ),
            None,
        )
    )
    _clicar(driver, botao)
    alvo = _normalizar(texto)
    opcoes = WebDriverWait(raiz, 20).until(
        lambda _: raiz.find_elements(
            By.XPATH,
            ".//*[self::a or self::button or self::li]"
            "[contains(@class,'dropdown-item') or @role='option']"
            "[not(ancestor-or-self::*[contains(@style,'display: none')])]",
        )
        or None
    )
    correspondencias = [
        opcao
        for opcao in opcoes
        if alvo in _normalizar(opcao.text) and opcao.is_displayed()
    ]
    if not correspondencias:
        raise RuntimeError(f"Opção não encontrada: {texto}")
    correspondencias.sort(key=lambda item: len(item.text))
    _clicar(driver, correspondencias[0])
    WebDriverWait(raiz, 10).until(lambda _: alvo in _normalizar(botao.text))


def _ultima_linha_entrega(dialogo):
    return WebDriverWait(dialogo, 20).until(
        lambda _: next(
            (
                linha
                for linha in reversed(
                    dialogo.find_elements(
                        By.XPATH,
                        ".//tr[.//button[contains(@id,'_origem')]]",
                    )
                )
                if linha.is_displayed()
            ),
            None,
        )
        or next(
            (
                linha
                for linha in reversed(
                    dialogo.find_elements(
                        By.XPATH,
                        ".//table[.//*[contains(.,'% CHD')]]/tbody/tr",
                    )
                )
                if linha.is_displayed()
            ),
            None,
        )
    )


def _adicionar_linha(driver, dialogo):
    botao = WebDriverWait(driver, 30).until(
        lambda _: next(
            (
                candidato
                for candidato in dialogo.find_elements(
                    By.XPATH,
                    ".//button["
                    "contains(@id,'_add_button') "
                    "or .//i[contains(@class,'bi-plus-circle')]"
                    "]",
                )
                if candidato.is_displayed() and candidato.is_enabled()
            ),
            None,
        )
    )
    _clicar(driver, botao)
    return _ultima_linha_entrega(dialogo)


def _selecionar_origem(driver, linha, origem: str) -> None:
    botao = WebDriverWait(linha, 15).until(
        lambda _: next(
            (
                item
                for item in linha.find_elements(
                    By.XPATH,
                    ".//td[1]//button[contains(@id,'_origem')]",
                )
                if item.is_displayed() and item.is_enabled()
            ),
            None,
        )
    )
    _clicar(driver, botao)
    alvo = _normalizar(origem)
    opcoes = WebDriverWait(linha, 15).until(
        lambda _: linha.find_elements(
            By.XPATH,
            ".//td[1]//*[self::a or self::button or self::li]"
            "[contains(@class,'dropdown-item') or @role='option']",
        )
        or None
    )
    correspondencias = [
        opcao
        for opcao in opcoes
        if opcao.is_displayed() and alvo == _normalizar(opcao.text.strip())
    ]
    if not correspondencias:
        raise RuntimeError(f"Origem não encontrada: {origem}")
    correspondencias.sort(key=lambda item: len(item.text.strip()))
    _clicar(driver, correspondencias[0])
    try:
        WebDriverWait(linha, 10).until(
            lambda _: alvo == _normalizar(botao.text.strip())
        )
    except TimeoutException as exc:
        raise RuntimeError(
            f"A origem '{origem}' foi acionada, mas não ficou selecionada."
        ) from exc


def _selecionar_plano_externo(driver, linha, codigo: str) -> None:
    campo = WebDriverWait(linha, 15).until(
        lambda _: linha.find_element(
            By.XPATH,
            ".//input[contains(@placeholder,'Plano de entrega')]",
        )
    )
    campo.send_keys(Keys.CONTROL, "a")
    campo.send_keys(codigo)
    botoes = linha.find_elements(
        By.XPATH,
        ".//button[.//i[contains(@class,'search')]]",
    )
    if botoes:
        _clicar(driver, botoes[-1])
    time.sleep(1)

    modais = driver.find_elements(
        By.XPATH,
        "//div[@role='dialog' or contains(@class,'modal-content')]",
    )
    seletor = modais[-1]
    candidatos = seletor.find_elements(
        By.XPATH,
        f".//*[contains(normalize-space(.),'{codigo}')]",
    )
    candidatos = [
        item
        for item in candidatos
        if item.is_displayed() and len(item.text.strip()) < 220
    ]
    if not candidatos:
        raise RuntimeError(f"Plano externo {codigo} não localizado.")
    candidatos.sort(key=lambda item: len(item.text.strip()))
    _clicar(driver, candidatos[0])
    time.sleep(0.5)


def _selecionar_entrega(driver, linha, nome: str) -> None:
    botoes = linha.find_elements(
        By.XPATH,
        ".//td[2]//button["
        "contains(@id,'planoentregaentregaid') "
        "or (contains(@class,'dropdown-toggle') and not(.//i))"
        "]",
    )
    if not botoes:
        raise RuntimeError("Seletor de entrega não encontrado.")
    _clicar(driver, botoes[0])
    alvo = _normalizar(nome)
    opcoes = WebDriverWait(linha, 20).until(
        lambda _: linha.find_elements(
            By.XPATH,
            ".//td[2]//*[self::a or self::button or self::li]"
            "[contains(@class,'dropdown-item') or @role='option']",
        )
        or None
    )
    correspondencias = [
        opcao
        for opcao in opcoes
        if opcao.is_displayed() and alvo == _normalizar(opcao.text.strip())
    ]
    if not correspondencias:
        correspondencias = [
            opcao
            for opcao in opcoes
            if opcao.is_displayed() and alvo in _normalizar(opcao.text.strip())
        ]
    if not correspondencias:
        raise RuntimeError(f"Entrega não encontrada: {nome}")
    correspondencias.sort(key=lambda item: len(item.text.strip()))
    _clicar(driver, correspondencias[0])
    try:
        WebDriverWait(linha, 10).until(
            lambda _: alvo in _normalizar(botoes[0].text.strip())
        )
    except TimeoutException as exc:
        raise RuntimeError(
            f"A entrega '{nome}' foi acionada, mas não ficou selecionada."
        ) from exc


def _preencher_linha(driver, linha, entrega: dict[str, Any]) -> None:
    origem = entrega["origem"]
    _selecionar_origem(driver, linha, origem)

    if _normalizar(origem) == _normalizar("Outra Unidade"):
        _selecionar_plano_externo(
            driver,
            linha,
            str(entrega.get("plano_entrega_codigo") or "2568"),
        )
        _selecionar_entrega(driver, linha, entrega["entrega"])
    elif _normalizar(origem) == _normalizar("Própria Unidade"):
        _selecionar_entrega(driver, linha, entrega["entrega"])

    campos_numero = linha.find_elements(By.XPATH, ".//input[@type='number']")
    if not campos_numero:
        campos_numero = linha.find_elements(
            By.XPATH,
            ".//td[contains(.,'%')]//input",
        )
    if not campos_numero:
        raise RuntimeError("Campo de percentual não encontrado.")
    _set_native_value(driver, campos_numero[0], str(entrega["percentual"]))

    descricoes = linha.find_elements(By.XPATH, ".//textarea")
    if descricoes:
        _set_native_value(driver, descricoes[0], entrega["descricao"])

    confirmar = linha.find_elements(
        By.XPATH,
        ".//button[.//i[contains(@class,'check-circle')]]",
    )
    if confirmar:
        _clicar(driver, confirmar[-1])
        time.sleep(0.5)


def _encontrar_menu_planos(driver):
    candidatos = driver.find_elements(
        By.XPATH,
        "//*[self::button or self::a]"
        "[contains(normalize-space(.),'Planos de Trabalho')]",
    )
    return next((item for item in candidatos if item.is_displayed()), None)


def _garantir_menu_planos_visivel(driver):
    menu = _encontrar_menu_planos(driver)
    if menu:
        return menu
    toggles = driver.find_elements(
        By.XPATH,
        "//button[contains(@class,'navbar-toggler')]",
    )
    toggle = next((item for item in toggles if item.is_displayed()), None)
    if toggle and toggle.get_attribute("aria-expanded") != "true":
        _clicar(driver, toggle)
    return _encontrar_menu_planos(driver)


def _abrir_formulario(driver, dados: dict[str, Any]):
    WebDriverWait(driver, 300).until(
        lambda d: next(
            (
                item
                for item in d.find_elements(By.ID, "ID_homeexecucao_Incluir")
                if item.is_displayed()
            ),
            None,
        )
        or _garantir_menu_planos_visivel(d)
    )
    incluir_visivel = next(
        (
            item
            for item in driver.find_elements(By.ID, "ID_homeexecucao_Incluir")
            if item.is_displayed()
        ),
        None,
    )
    if not incluir_visivel:
        menu_planos = _garantir_menu_planos_visivel(driver)
        if not menu_planos:
            raise RuntimeError(
                "Menu Planos de Trabalho não encontrado após o login."
            )
        _clicar(driver, menu_planos)
    incluir = WebDriverWait(driver, 60).until(
        EC.element_to_be_clickable((By.ID, "ID_homeexecucao_Incluir"))
    )
    _clicar(driver, incluir)
    dialogo = _dialogo(driver)

    _selecionar_opcao(
        driver,
        dialogo,
        ".//button[contains(@id,'_unidadeid')]",
        dados.get("unidade", "CLC-BSF"),
    )
    inicio = dialogo.find_element(
        By.XPATH,
        ".//input[@type='date' and contains(@id,'datainicio')]",
    )
    fim = dialogo.find_element(
        By.XPATH,
        ".//input[@type='date' and contains(@id,'datafim')]",
    )
    _set_native_value(driver, inicio, dados["data_inicio"])
    _set_native_value(driver, fim, dados["data_fim"])
    time.sleep(0.8)
    return dialogo


def _consultar_catalogo_entregas(driver, dialogo) -> list[str]:
    linha = _adicionar_linha(driver, dialogo)
    botoes = linha.find_elements(By.XPATH, ".//td[2]//button")
    if not botoes:
        raise RuntimeError("O Petrvs não exibiu o seletor de entregas.")
    _clicar(driver, botoes[0])
    time.sleep(0.4)

    opcoes = linha.find_elements(
        By.XPATH,
        ".//td[2]//*[self::li or self::div or self::span]",
    )
    catalogo: list[str] = []
    for opcao in opcoes:
        texto = opcao.text.strip()
        if (
            opcao.is_displayed()
            and texto
            and texto != "- Selecione -"
            and 8 <= len(texto) <= 240
            and texto not in catalogo
        ):
            catalogo.append(texto)

    _clicar(driver, botoes[0])
    remover = linha.find_elements(
        By.XPATH,
        ".//button["
        "contains(@class,'danger') "
        "or contains(@id,'_delete_button') "
        "or .//i[contains(@class,'dash-circle') or contains(@class,'minus-circle')]"
        "]",
    )
    remover = [
        botao
        for botao in remover
        if botao.is_displayed() and botao.is_enabled()
    ]
    if not remover:
        raise RuntimeError(
            "A entrega temporária foi consultada, mas o botão para removê-la "
            "não foi localizado."
        )
    _clicar(driver, remover[-1])
    WebDriverWait(driver, 10).until(EC.staleness_of(linha))
    if not catalogo:
        raise RuntimeError(
            "Nenhuma entrega foi encontrada no dropdown para o mês selecionado."
        )
    return catalogo


def preparar_plano_pgd(dados: dict[str, Any]):
    driver, _ = iniciar_sessao_pgd()
    print(
        f"Consultando entregas do plano de {dados['data_inicio']} "
        f"a {dados['data_fim']}."
    )
    try:
        dialogo = _abrir_formulario(driver, dados)
        catalogo = _consultar_catalogo_entregas(driver, dialogo)
        print(f"[OK] {len(catalogo)} entregas disponíveis encontradas.")
        try:
            driver.minimize_window()
        except Exception:
            pass
        return driver, catalogo
    except Exception as exc:
        driver.quit()
        print(
            f"[ERRO] Não foi possível consultar as entregas no Petrvs: "
            f"{type(exc).__name__}: {exc}"
        )
        traceback.print_exc()
        raise


def finalizar_plano_pgd(driver, dados: dict[str, Any]) -> None:
    entregas = dados.get("entregas") or []
    if not entregas:
        raise ValueError("O plano precisa ter ao menos uma entrega.")
    if sum(int(item.get("percentual", 0)) for item in entregas) != 100:
        raise ValueError("A soma dos percentuais precisa ser 100%.")

    try:
        driver.maximize_window()
    except Exception:
        pass
    print(f"Preenchendo {len(entregas)} entregas no plano.")
    dialogo = _dialogo(driver)
    for indice, entrega in enumerate(entregas, start=1):
        print(f"[{indice}/{len(entregas)}] {entrega.get('entrega')}")
        linha = _adicionar_linha(driver, dialogo)
        _preencher_linha(driver, linha, entrega)

    gravar = dialogo.find_element(
        By.XPATH,
        ".//button[contains(@id,'_submit') or contains(.,'Gravar')]",
    )
    _clicar(driver, gravar)
    try:
        confirmacao = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable(
                (
                    By.XPATH,
                    "//button[contains(.,'Sim') or contains(.,'Confirmar')]",
                )
            )
        )
        _clicar(driver, confirmacao)
    except TimeoutException:
        pass
    WebDriverWait(driver, 30).until(
        lambda d: not d.find_elements(
            By.XPATH,
            "//div[@role='dialog']//button[contains(.,'Gravar')]",
        )
    )
    print("[SUCESSO] Plano de trabalho gravado no Petrvs.")


def criar_plano_pgd(dados: dict[str, Any]) -> None:
    driver, _ = preparar_plano_pgd(dados)
    try:
        finalizar_plano_pgd(driver, dados)
    except Exception:
        print("[ERRO] A criação do plano foi interrompida.")
        raise
