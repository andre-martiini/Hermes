from playwright.sync_api import sync_playwright

def test_deep_research_ui():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.goto("http://localhost:3001/?test=true") # Mock Wrapper
            page.wait_for_timeout(3000)
            page.screenshot(path="/home/jules/verification/login_screen.png")
            print("Verifique /home/jules/verification/login_screen.png")
        except Exception as e:
            print("Erro no playwright:", e)
        finally:
            browser.close()

if __name__ == "__main__":
    test_deep_research_ui()
