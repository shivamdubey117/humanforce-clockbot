"""
Humanforce Clock-In / Clock-Out Automation Agent
Runs on Mac, schedules 10:00 AM clock-in and 10:00 PM clock-out daily.
"""

import asyncio
import os
import schedule
import time
import logging
from datetime import datetime
from dotenv import load_dotenv
from playwright.async_api import async_playwright

# ── Logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[
        logging.FileHandler("clockbot.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
load_dotenv()

HUMANFORCE_URL   = "https://panasonic.humanforce.co.uk/Account/LogOn?ReturnUrl=%2FHome"
EMPLOYEE_CODE    = os.getenv("HF_EMPLOYEE_CODE")
PASSWORD         = os.getenv("HF_PASSWORD")
SCREENSHOTS_DIR  = "screenshots"

os.makedirs(SCREENSHOTS_DIR, exist_ok=True)


# ── Core browser automation ───────────────────────────────────────────────────
async def perform_action(action: str):
    """
    action: "clock_in" | "clock_out"
    Opens Humanforce, logs in, performs the action, saves a screenshot proof.
    """
    if not EMPLOYEE_CODE or not PASSWORD:
        log.error("Missing HF_EMPLOYEE_CODE or HF_PASSWORD in .env file!")
        notify(f"❌ ClockBot: credentials missing – {action} FAILED", error=True)
        return

    log.info(f"Starting {action} …")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
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
            # Wait for dashboard to load (ignore networkidle timeout)
            try:
                await page.wait_for_load_state("networkidle", timeout=15_000)
            except Exception:
                pass  # Dashboard may keep background requests open, that's fine
            await page.wait_for_timeout(2000)

            # Check for failed login
            if "login" in page.url.lower() or "logon" in page.url.lower():
                raise Exception("Login failed – still on login page. Check credentials.")

            log.info(f"Logged in successfully. Current URL: {page.url}")

            # ── 4. Navigate to Clocking page directly ──────────────────────
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
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            shot_path = f"{SCREENSHOTS_DIR}/{action}_{ts}.png"
            await page.screenshot(path=shot_path, full_page=False)
            log.info(f"Screenshot saved → {shot_path}")

            notify(f"✅ ClockBot: {action.replace('_', ' ').title()} successful at {datetime.now().strftime('%H:%M')}")

        except Exception as e:
            log.error(f"{action} failed: {e}")
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            shot_path = f"{SCREENSHOTS_DIR}/ERROR_{action}_{ts}.png"
            try:
                await page.screenshot(path=shot_path, full_page=True)
                log.info(f"Error screenshot saved → {shot_path}")
            except Exception:
                pass
            notify(f"❌ ClockBot: {action.replace('_', ' ').title()} FAILED – {str(e)[:80]}", error=True)

        finally:
            await browser.close()


async def _do_clock_action(page, action: str):
    """
    Tries multiple selector strategies to find and click the clock button.
    Humanforce typically shows a 'Start Shift' / 'End Shift' or clock button on the home dashboard.
    """
    # Text patterns to look for depending on action
    if action == "clock_in":
        patterns = [
            "Start Shift", "Clock In", "Clock-In", "Start Work",
            "Check In", "Start", "Punch In",
        ]
    else:
        patterns = [
            "End Shift", "Clock Out", "Clock-Out", "End Work",
            "Check Out", "Finish", "Punch Out",
        ]

    # Wait a moment for dashboard to fully load
    await page.wait_for_timeout(3000)

    # Strategy 1: button/link with matching text
    for text in patterns:
        try:
            btn = page.locator(f'button:has-text("{text}"), a:has-text("{text}"), input[value*="{text}"]').first
            if await btn.is_visible(timeout=3000):
                log.info(f"Found button with text: '{text}'")
                await btn.click()
                await page.wait_for_load_state("networkidle", timeout=10_000)
                log.info(f"{action} button clicked successfully.")
                return
        except Exception:
            continue

    # Strategy 2: look for clock icon buttons (Humanforce uses icon-based UI)
    try:
        # Humanforce home page often has a large clock-in widget
        clock_widget = page.locator('.clock-widget button, .attendance-widget button, [class*="clock"] button').first
        if await clock_widget.is_visible(timeout=3000):
            log.info("Found clock widget button.")
            await clock_widget.click()
            await page.wait_for_load_state("networkidle", timeout=10_000)
            return
    except Exception:
        pass

    # Strategy 3: navigate directly to attendance/timesheet page
    log.info("Direct button not found on homepage, trying attendance page …")
    await page.goto("https://panasonic.humanforce.co.uk/Attendance", wait_until="networkidle", timeout=20_000)
    await page.wait_for_timeout(2000)

    for text in patterns:
        try:
            btn = page.locator(f'button:has-text("{text}"), a:has-text("{text}")').first
            if await btn.is_visible(timeout=3000):
                log.info(f"Found button on attendance page: '{text}'")
                await btn.click()
                await page.wait_for_load_state("networkidle", timeout=10_000)
                return
        except Exception:
            continue

    # If all strategies fail, take a screenshot and raise
    raise Exception(
        f"Could not find {action} button. Check the screenshot in {SCREENSHOTS_DIR}/ "
        "to see what the page looks like, then update the selectors in _do_clock_action()."
    )


# ── Mac notification ──────────────────────────────────────────────────────────
def notify(message: str, error: bool = False):
    """Send a Mac desktop notification."""
    title = "ClockBot 🤖"
    sound = "Basso" if error else "Glass"
    os.system(
        f'osascript -e \'display notification "{message}" with title "{title}" sound name "{sound}"\''
    )
    log.info(f"Notification sent: {message}")


# ── Scheduler jobs ────────────────────────────────────────────────────────────
def job_clock_in():
    asyncio.run(perform_action("clock_in"))

def job_clock_out():
    asyncio.run(perform_action("clock_out"))


# ── Entry point ───────────────────────────────────────────────────────────────
def main():
    log.info("=" * 60)
    log.info("ClockBot started 🤖")
    log.info("  Clock-IN  scheduled → 10:00 AM daily")
    log.info("  Clock-OUT scheduled → 10:00 PM daily")
    log.info("  Press Ctrl+C to stop.")
    log.info("=" * 60)

    schedule.every().day.at("10:00").do(job_clock_in)
    schedule.every().day.at("22:00").do(job_clock_out)

    # Uncomment the lines below to test immediately on first run:
    #log.info("Running immediate test clock-in …")
    #job_clock_in()

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
