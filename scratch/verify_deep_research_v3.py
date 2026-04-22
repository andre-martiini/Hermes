from playwright.sync_api import sync_playwright

def test_deep_research_ui():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.goto("http://localhost:3001/?test=true") # Mock Wrapper
            page.wait_for_timeout(3000)

            # Navegar para Ações
            acoes_btn = page.locator("text=Ações")
            if acoes_btn.is_visible():
                 acoes_btn.click()
            page.wait_for_timeout(2000)

            # Print page source to debug
            html = page.content()
            with open("/home/jules/verification/page_source.html", "w") as f:
                f.write(html)
            page.screenshot(path="/home/jules/verification/actions_view.png")
            print("Verifique /home/jules/verification/actions_view.png")
        except Exception as e:
            print("Erro no playwright:", e)
        finally:
            browser.close()

if __name__ == "__main__":
    test_deep_research_ui()
