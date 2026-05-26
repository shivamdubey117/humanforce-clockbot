import asyncio, os, logging
from datetime import datetime
from dotenv import load_dotenv
from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)s  %(message)s")
log = logging.getLogger(__name__)
load_dotenv()

HUMANFORCE_URL  = "https://panasonic.humanforce.co.uk/Account/LogOn?ReturnUrl=%2FHome"
EMPLOYEE_CODE   = os.getenv("HF_EMPLOYEE_CODE")
PASSWORD        = os.getenv("HF_PASSWORD")
CLOCK_ACTION    = os.getenv("CLOCK_ACTION", "clock_in")
SCREENSHOTS_DIR = "screenshots"
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

async def perform_action(action):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, args=["--no-sandbox","--disable-setuid-sandbox","--disable-dev-shm-usage","--disable-gpu","--single-process"])
        page = await (await browser.new_context(viewport={"width":1280,"height":800})).new_page()
        try:
            log.info(f"Starting {action}...")
            await page.goto(HUMANFORCE_URL, wait_until="networkidle", timeout=30000)
            await page.wait_for_selector('input[type="text"], input[type="email"]', state="visible", timeout=10000)
            await page.locator('input[type="text"]:visible, input[type="email"]:visible').first.fill(EMPLOYEE_CODE)
            await page.wait_for_timeout(1500)
            await page.evaluate(f"""
                const inputs = document.querySelectorAll('input[type="password"]');
                for (const input of inputs) {{
                    input.removeAttribute('style');
                    input.style.display = 'block';
                    input.style.visibility = 'visible';
                    input.style.opacity = '1';
                    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                    setter.call(input, '{PASSWORD}');
                    input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                }}
            """)
            await page.wait_for_timeout(1000)
            await page.locator('button:has-text("Log In")').click()
            try:
                await page.wait_for_load_state("networkidle", timeout=15000)
            except:
                pass
            await page.wait_for_timeout(2000)
            if "login" in page.url.lower() or "logon" in page.url.lower():
                raise Exception("Login failed")
            log.info(f"Logged in. URL: {page.url}")
            await page.locator('a:has-text("Clocking"), span:has-text("Clocking")').first.click()
            try:
                await page.wait_for_load_state("networkidle", timeout=15000)
            except:
                pass
            await page.wait_for_timeout(2000)
            patterns = ["Clock In","Start Shift","Start Work","Punch In"] if action=="clock_in" else ["Clock Out","End Shift","End Work","Punch Out"]
            await page.wait_for_timeout(3000)
            for text in patterns:
                try:
                    btn = page.locator(f'button:has-text("{text}"), a:has-text("{text}")').first
                    if await btn.is_visible(timeout=3000):
                        log.info(f"Clicking: {text}")
                        await btn.click()
                        await page.wait_for_timeout(2000)

                        # Handle confirmation dialog if it appears (e.g., clocking out too soon after clocking in)
                        try:
                            confirm_btn = page.locator('button:has-text("Yes, clock out"), button:has-text("Yes"), button:has-text("Confirm")').first
                            if await confirm_btn.is_visible(timeout=3000):
                                log.info("Confirmation dialog detected, clicking Yes/Confirm...")
                                await confirm_btn.click()
                                await page.wait_for_timeout(2000)
                        except:
                            log.info("No confirmation dialog appeared")

                        await page.wait_for_timeout(1000)
                        break
                except:
                    continue
            ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            await page.screenshot(path=f"{SCREENSHOTS_DIR}/{action}_{ts}.png")
            log.info("SUCCESS!")
        except Exception as e:
            log.error(f"FAILED: {e}")
            try:
                await page.screenshot(path=f"{SCREENSHOTS_DIR}/ERROR_{action}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.png", full_page=True)
            except:
                pass
            raise SystemExit(1)
        finally:
            await browser.close()

if __name__ == "__main__":
    log.info(f"ClockBot Actions — {CLOCK_ACTION}")
    asyncio.run(perform_action(CLOCK_ACTION))
