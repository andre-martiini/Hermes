from playwright.sync_api import sync_playwright

def test_deep_research_ui():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.goto("http://localhost:3001/?test=true") # Mock Wrapper
            page.wait_for_timeout(3000)

            # Click the main task from mock
            page.locator("text=Finalizar MVP do Hermes").first.click()
            page.wait_for_timeout(2000)

            chat_input = page.locator('input[placeholder="Envie uma mensagem ou comando..."]')
            if chat_input.is_visible():
                chat_input.fill('/pesquisa-profunda Inteligência Artificial')
                page.keyboard.press("Enter")

                page.wait_for_timeout(1000)

                page.screenshot(path="/home/jules/verification/modal_deep_research_v4.png")
                print("Screenshot capturado: /home/jules/verification/modal_deep_research_v4.png")
            else:
                print("Input não encontrado.")
                page.screenshot(path="/home/jules/verification/error_v4.png")
        except Exception as e:
            print("Erro no playwright:", e)
        finally:
            browser.close()

if __name__ == "__main__":
    test_deep_research_ui()
