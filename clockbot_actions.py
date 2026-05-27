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
        context = await browser.new_context(
            viewport={"width":1280,"height":800},
            timezone_id="Asia/Kolkata",
            locale="en-IN"
        )
        page = await context.new_page()
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
            action_time = None
            for text in patterns:
                try:
                    btn = page.locator(f'button:has-text("{text}"), a:has-text("{text}")').first
                    if await btn.is_visible(timeout=3000):
                        action_time = datetime.now()
                        log.info(f"Clicking: {text} at {action_time.strftime('%I:%M:%S %p')}")
                        await btn.click()
                        await page.wait_for_timeout(3000)

                        # Handle confirmation dialog if it appears (e.g., clocking out too soon after clocking in)
                        if action == "clock_out":
                            try:
                                log.info("Checking for confirmation dialog...")
                                # Wait for the confirmation dialog to appear (try multiple selectors)
                                await page.wait_for_timeout(1000)

                                # Try multiple possible selectors for the confirmation button
                                confirm_selectors = [
                                    'button:has-text("Yes, clock out")',
                                    'button:text-is("Yes, clock out")',
                                    'button:text("Yes")',
                                    '.modal button:has-text("Yes")',
                                    '[role="dialog"] button:has-text("Yes")'
                                ]

                                button_clicked = False
                                for selector in confirm_selectors:
                                    try:
                                        confirm_btn = page.locator(selector).first
                                        if await confirm_btn.is_visible(timeout=2000):
                                            log.info(f"Confirmation dialog detected! Clicking button with selector: {selector}")
                                            await confirm_btn.click()
                                            log.info("Clicked confirmation button successfully")
                                            await page.wait_for_timeout(3000)
                                            button_clicked = True
                                            break
                                    except:
                                        continue

                                if not button_clicked:
                                    log.info("No confirmation dialog appeared")

                            except Exception as dialog_err:
                                log.info(f"No confirmation dialog handling needed: {dialog_err}")

                        await page.wait_for_timeout(1000)
                        break
                except:
                    continue

            # Verify the action was successful by checking for the opposite button
            await page.wait_for_timeout(3000)  # Increased wait time
            verification_patterns = ["Clock Out","End Shift","End Work","Punch Out","Stop","Finish"] if action=="clock_in" else ["Clock In","Start Shift","Start Work","Punch In","Start","Begin"]
            action_verified = False
            for verify_text in verification_patterns:
                try:
                    verify_btn = page.locator(f'button:has-text("{verify_text}"), a:has-text("{verify_text}")').first
                    if await verify_btn.is_visible(timeout=3000):  # Increased timeout from 2000ms to 3000ms
                        log.info(f"✓ Action verified: '{verify_text}' button is now visible")
                        action_verified = True
                        break
                except:
                    continue

            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            ts_display = datetime.now().strftime("%d %b %Y - %I:%M:%S %p")
            await page.screenshot(path=f"{SCREENSHOTS_DIR}/{action}_{ts}.png")

            if not action_verified:
                log.warning(f"WARNING: Could not verify {action} was successful. Check screenshot.")
                await page.screenshot(path=f"{SCREENSHOTS_DIR}/VERIFY_FAILED_{action}_{ts}.png", full_page=True)

            action_status = "✅ SUCCESS" if action_verified else "⚠️ COMPLETED"
            clock_action_display = "Clock In" if action == "clock_in" else "Clock Out"
            log.info(f"{action_status}: {clock_action_display} at {ts_display}")
            log.info(f"Screenshot: {action}_{ts}.png")
        except Exception as e:
            log.error(f"FAILED: {e}")
            try:
                await page.screenshot(path=f"{SCREENSHOTS_DIR}/ERROR_{action}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png", full_page=True)
            except:
                pass
            raise SystemExit(1)
        finally:
            await browser.close()

if __name__ == "__main__":
    log.info(f"ClockBot Actions — {CLOCK_ACTION}")
    asyncio.run(perform_action(CLOCK_ACTION))
