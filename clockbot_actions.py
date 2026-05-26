"""
Humanforce Clock-In / Clock-Out Automation Agent
GitHub Actions version — reads CLOCK_ACTION from environment variable.
"""

import asyncio
import os
import logging
from datetime import datetime
from dotenv import load_dotenv
from playwright.async_api import async_playwright

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[logging.StreamHandler()],
)
log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
load_dotenv()

HUMANFORCE_URL  = "https://panasonic.humanforce.co.uk/Account/LogOn?ReturnUrl=%2FHome"
EMPLOYEE_CODE   = os.getenv("HF_EMPLOYEE_CODE")
PASSWORD        = os.getenv("HF_PASSWORD")
CLOCK_ACTION    = os.getenv("CLOCK_ACTION", "clock_in")  # clock_in or clock_out
SCREENSHOTS_DIR = "screenshots"

os.makedirs(SCREENSHOTS_DIR, exist_ok=True)


# ── Browser automation ────────────────────────────────────────────────────────
async def perform_action(action: str):
    if not EMPLOYEE_CODE or not PASSWORD:
        log.error("Missing HF_EMPLOYEE_CODE or HF_PASSWORD!")
        raise SystemExit(1)

    log.info(f"Starting {action} at {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')} …")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-accelerated-2d-canvas",
                "--no-first-run",
                "--no-zygote",
                "--single-process",
                "--disable-gpu",
            ]
        )
        context = await browser.new_context(viewport={"width": 1280, "height": 800})
        page    = await context.new_page()

        try:
            # ── 1. Navigate to login page ──────────────────────────────────
            log.info("Opening Humanforce login page …")
            await page.goto(HUMANFORCE_URL, wait_until="networkidle", timeout=30_000)

            # ── 2. Fill credentials ────────────────────────────────────────
            log.info("Filling credentials …")
            await page.wait_for_selector(
                'input[type="text"], input[type="email"]',
                state="visible", timeout=10_000
            )
            await page.locator(
                'input[type="text"]:visible, input[type="email"]:visible'
            ).first.fill(EMPLOYEE_CODE)
            await page.wait_for_timeout(1500)

            # Force-fill password via JS (bypasses hidden field)
            await page.evaluate(f"""
                const inputs = document.querySelectorAll('input[type="password"]');
                for (const input of inputs) {{
                    input.removeAttribute('style');
                    input.style.display = 'block';
                    input.style.visibility = 'visible';
                    input.style.opacity = '1';
                    const setter = Object.getOwnPropertyDescriptor(
                        window.HTMLInputElement.prototype, 'value'
                    ).set;
                    setter.call(input, '{PASSWORD}');
                    input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                }}
            """)
            await page.wait_for_timeout(1000)
            log.info("Credentials filled.")

            # ── 3. Click Log In ────────────────────────────────────────────
            log.info("Clicking Log In …")
            await page.locator('button:has-text("Log In")').click()
            try:
                await page.wait_for_load_state("networkidle", timeout=15_000)
            except Exception:
                pass
            await page.wait_for_timeout(2000)

            if "login" in page.url.lower() or "logon" in page.url.lower():
                raise Exception("Login failed – still on login page.")

            log.info(f"Logged in. URL: {page.url}")

            # ── 4. Navigate to Clocking ────────────────────────────────────
            log.info("Navigating to Clocking …")
            await page.locator(
                'a:has-text("Clocking"), span:has-text("Clocking")'
            ).first.click()
            try:
                await page.wait_for_load_state("networkidle", timeout=15_000)
            except Exception:
                pass
            await page.wait_for_timeout(2000)
            log.info(f"Clocking page: {page.url}")

            # ── 5. Click Clock In / Out ────────────────────────────────────
            await _do_clock_action(page, action)

            # ── 6. Screenshot ──────────────────────────────────────────────
            ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            shot = f"{SCREENSHOTS_DIR}/{action}_{ts}.png"
            await page.screenshot(path=shot, full_page=False)
            log.info(f"SUCCESS ✅ Screenshot → {shot}")

        except Exception as e:
            log.error(f"FAILED ❌ {action}: {e}")
            ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            try:
                await page.screenshot(
                    path=f"{SCREENSHOTS_DIR}/ERROR_{action}_{ts}.png",
                    full_page=True
                )
            except Exception:
                pass
            raise SystemExit(1)

        finally:
            await browser.close()


async def _do_clock_action(page, action: str):
    if action == "clock_in":
        patterns = ["Clock In", "Start Shift", "Start Work", "Punch In", "Check In"]
    else:
        patterns = ["Clock Out", "End Shift", "End Work", "Punch Out", "Check Out"]

    await page.wait_for_timeout(3000)

    # Strategy 1: find button on current page
    for text in patterns:
        try:
            btn = page.locator(f'button:has-text("{text}"), a:has-text("{text}")').first
            if await btn.is_visible(timeout=3000):
                log.info(f"Found: '{text}'")
                await btn.click()
                await page.wait_for_timeout(3000)
                log.info(f"{action} clicked ✅")
                return
        except Exception:
            continue

    # Strategy 2: go directly to /Clocking
    log.info("Trying direct /Clocking URL …")
    await page.goto(
        "https://panasonic.humanforce.co.uk/Clocking",
        wait_until="networkidle", timeout=20_000
    )
    await page.wait_for_timeout(2000)

    for text in patterns:
        try:
            btn = page.locator(f'button:has-text("{text}"), a:has-text("{text}")').first
            if await btn.is_visible(timeout=3000):
                log.info(f"Found on /Clocking: '{text}'")
                await btn.click()
                await page.wait_for_timeout(3000)
                return
        except Exception:
            continue

    raise Exception(f"Could not find {action} button.")


# ── Run ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    log.info(f"ClockBot GitHub Actions — action: {CLOCK_ACTION}")
    asyncio.run(perform_action(CLOCK_ACTION))
