"""
Humanforce Clock-In / Clock-Out Automation Agent
Cloud version for Railway deployment.
Schedules 10:00 AM clock-in and 10:00 PM clock-out daily (IST).
"""

import asyncio
import os
import schedule
import time
import logging
from datetime import datetime
import pytz
from dotenv import load_dotenv
from playwright.async_api import async_playwright

# ── Logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[
        logging.StreamHandler(),  # Cloud: log to stdout (visible in Railway dashboard)
    ],
)
log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
load_dotenv()

HUMANFORCE_URL  = "https://panasonic.humanforce.co.uk/Account/LogOn?ReturnUrl=%2FHome"
EMPLOYEE_CODE   = os.getenv("HF_EMPLOYEE_CODE")
PASSWORD        = os.getenv("HF_PASSWORD")
SCREENSHOTS_DIR = "screenshots"
IST             = pytz.timezone("Asia/Kolkata")

os.makedirs(SCREENSHOTS_DIR, exist_ok=True)


# ── Core browser automation ───────────────────────────────────────────────────
async def perform_action(action: str):
    """
    action: "clock_in" | "clock_out"
    Opens Humanforce, logs in, performs the action, saves a screenshot proof.
    """
    if not EMPLOYEE_CODE or not PASSWORD:
        log.error("Missing HF_EMPLOYEE_CODE or HF_PASSWORD in environment variables!")
        return

    now_ist = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")
    log.info(f"Starting {action} at {now_ist} …")

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

            # Fill employee code / email
            await page.wait_for_selector('input[type="text"], input[type="email"]', state="visible", timeout=10_000)
            await page.locator('input[type="text"]:visible, input[type="email"]:visible').first.fill(EMPLOYEE_CODE)
            await page.wait_for_timeout(1500)

            # Force-fill password using JavaScript (bypasses hidden field issue)
            await page.evaluate(f"""
                const inputs = document.querySelectorAll('input[type="password"]');
                for (const input of inputs) {{
                    input.removeAttribute('style');
                    input.style.display = 'block';
                    input.style.visibility = 'visible';
                    input.style.opacity = '1';
                    const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                    nativeInputValueSetter.call(input, '{PASSWORD}');
                    input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                }}
            """)
            await page.wait_for_timeout(1000)
            log.info("Credentials filled via JS.")

            # ── 3. Click Log In ────────────────────────────────────────────
            log.info("Clicking Log In …")
            await page.locator('button:has-text("Log In")').click()
            try:
                await page.wait_for_load_state("networkidle", timeout=15_000)
            except Exception:
                pass
            await page.wait_for_timeout(2000)

            # Check for failed login
            if "login" in page.url.lower() or "logon" in page.url.lower():
                raise Exception("Login failed – still on login page. Check credentials.")

            log.info(f"Logged in successfully. Current URL: {page.url}")

            # ── 4. Navigate to Clocking page ───────────────────────────────
            log.info("Navigating to Clocking page …")
            await page.locator('a:has-text("Clocking"), span:has-text("Clocking")').first.click()
            try:
                await page.wait_for_load_state("networkidle", timeout=15_000)
            except Exception:
                pass
            await page.wait_for_timeout(2000)
            log.info(f"On Clocking page: {page.url}")

            # ── 5. Find and click Clock In / Clock Out ─────────────────────
            await _do_clock_action(page, action)

            # ── 6. Screenshot proof ────────────────────────────────────────
            ts = datetime.now(IST).strftime("%Y%m%d_%H%M%S")
            shot_path = f"{SCREENSHOTS_DIR}/{action}_{ts}.png"
            await page.screenshot(path=shot_path, full_page=False)
            log.info(f"SUCCESS! Screenshot saved → {shot_path}")

        except Exception as e:
            log.error(f"{action} FAILED: {e}")
            ts = datetime.now(IST).strftime("%Y%m%d_%H%M%S")
            shot_path = f"{SCREENSHOTS_DIR}/ERROR_{action}_{ts}.png"
            try:
                await page.screenshot(path=shot_path, full_page=True)
                log.info(f"Error screenshot saved → {shot_path}")
            except Exception:
                pass

        finally:
            await browser.close()


async def _do_clock_action(page, action: str):
    """
    Finds and clicks the Clock In / Clock Out button on the Clocking page.
    """
    if action == "clock_in":
        patterns = [
            "Clock In", "Start Shift", "Start Work", "Punch In", "Check In",
        ]
    else:
        patterns = [
            "Clock Out", "End Shift", "End Work", "Punch Out", "Check Out",
        ]

    await page.wait_for_timeout(3000)

    # Strategy 1: button with matching text on current page
    for text in patterns:
        try:
            btn = page.locator(f'button:has-text("{text}"), a:has-text("{text}")').first
            if await btn.is_visible(timeout=3000):
                log.info(f"Found button: '{text}'")
                await btn.click()
                await page.wait_for_timeout(3000)
                log.info(f"{action} clicked successfully.")
                return
        except Exception:
            continue

    # Strategy 2: try /Clocking URL directly
    log.info("Button not found, trying direct /Clocking URL …")
    await page.goto("https://panasonic.humanforce.co.uk/Clocking", wait_until="networkidle", timeout=20_000)
    await page.wait_for_timeout(2000)

    for text in patterns:
        try:
            btn = page.locator(f'button:has-text("{text}"), a:has-text("{text}")').first
            if await btn.is_visible(timeout=3000):
                log.info(f"Found button on /Clocking: '{text}'")
                await btn.click()
                await page.wait_for_timeout(3000)
                return
        except Exception:
            continue

    raise Exception(f"Could not find {action} button. Check screenshots for page state.")


# ── Scheduler ─────────────────────────────────────────────────────────────────
def job_clock_in():
    log.info("⏰ Scheduled clock-in triggered.")
    asyncio.run(perform_action("clock_in"))

def job_clock_out():
    log.info("⏰ Scheduled clock-out triggered.")
    asyncio.run(perform_action("clock_out"))


def ist_now():
    return datetime.now(IST).strftime("%H:%M")


# ── Entry point ───────────────────────────────────────────────────────────────
def main():
    log.info("=" * 60)
    log.info("ClockBot started on Railway ☁️")
    log.info("  Clock-IN  scheduled → 10:00 AM IST daily")
    log.info("  Clock-OUT scheduled → 10:00 PM IST daily")
    log.info("=" * 60)

    # Schedule using IST times
    schedule.every().day.at("04:30").do(job_clock_in)   # 10:00 AM IST = 04:30 UTC
    schedule.every().day.at("16:30").do(job_clock_out)  # 10:00 PM IST = 16:30 UTC

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
