import asyncio, os, logging, json
from datetime import datetime
from dotenv import load_dotenv
from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)s  %(message)s")
log = logging.getLogger(__name__)
load_dotenv()

HUMANFORCE_URL  = "https://panasonic.humanforce.co.uk/Account/LogOn?ReturnUrl=%2FHome"
CLOCK_ACTION    = os.getenv("CLOCK_ACTION", "clock_in")
SCREENSHOTS_DIR = "screenshots"
TEAM_FILE       = "team_members.json"
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)


def load_team_members():
    """Load team members from JSON file."""
    try:
        with open(TEAM_FILE, "r") as f:
            members = json.load(f)
        # Filter only active members
        return [m for m in members if m.get("active", True)]
    except FileNotFoundError:
        log.error(f"Team file {TEAM_FILE} not found!")
        return []
    except json.JSONDecodeError as e:
        log.error(f"Invalid JSON in {TEAM_FILE}: {e}")
        return []


def get_password(member):
    """Get password from member, supporting environment variable substitution."""
    password = member.get("password", "")
    # Support ${VAR_NAME} syntax for environment variables
    if password.startswith("${") and password.endswith("}"):
        env_var = password[2:-1]
        return os.getenv(env_var, password)
    return password


async def perform_action_for_member(member, action):
    """Perform clock in/out action for a single team member."""
    name = member.get("name", "Unknown")
    employee_code = member.get("email", "")
    password = get_password(member)

    if not employee_code or not password:
        log.error(f"Missing credentials for {name}")
        return False

    log.info(f"\n{'='*50}")
    log.info(f"Processing: {name} ({employee_code})")
    log.info(f"Action: {action}")
    log.info(f"{'='*50}")

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox","--disable-setuid-sandbox","--disable-dev-shm-usage","--disable-gpu","--single-process"]
        )
        context = await browser.new_context(
            viewport={"width":1280,"height":800},
            timezone_id="Asia/Kolkata",
            locale="en-IN"
        )
        page = await context.new_page()

        try:
            await page.goto(HUMANFORCE_URL, wait_until="networkidle", timeout=30000)
            await page.wait_for_selector('input[type="text"], input[type="email"]', state="visible", timeout=10000)
            await page.locator('input[type="text"]:visible, input[type="email"]:visible').first.fill(employee_code)
            await page.wait_for_timeout(1500)

            await page.evaluate(f"""
                const inputs = document.querySelectorAll('input[type="password"]');
                for (const input of inputs) {{
                    input.removeAttribute('style');
                    input.style.display = 'block';
                    input.style.visibility = 'visible';
                    input.style.opacity = '1';
                    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                    setter.call(input, '{password}');
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
                raise Exception("Login failed - check credentials")

            log.info(f"Logged in successfully for {name}")

            await page.locator('a:has-text("Clocking"), span:has-text("Clocking")').first.click()
            try:
                await page.wait_for_load_state("networkidle", timeout=15000)
            except:
                pass
            await page.wait_for_timeout(2000)

            patterns = ["Clock In","Start Shift","Start Work","Punch In"] if action=="clock_in" else ["Clock Out","End Shift","End Work","Punch Out"]
            await page.wait_for_timeout(3000)

            action_time = None
            action_verified = False

            # Check if already clocked in/out
            if action == "clock_in":
                # For clock_in, check if "Clock Out" button already exists (means already clocked in)
                try:
                    clock_out_btn = page.locator('button:has-text("Clock Out"), button:has-text("End Shift")').first
                    if await clock_out_btn.is_visible(timeout=2000):
                        log.info(f"Already clocked in for {name} (Clock Out button visible)")
                        # Take screenshot anyway
                        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                        safe_name = name.replace(" ", "_").replace(".", "_")
                        shot_path = f"{SCREENSHOTS_DIR}/{safe_name}_{action}_{ts}.png"
                        await page.screenshot(path=shot_path)
                        log.info(f"Screenshot saved: {shot_path}")
                        action_verified = True
                        action_time = datetime.now()
                except:
                    pass

            if not action_verified:
                for text in patterns:
                    try:
                        btn = page.locator(f'button:has-text("{text}"), a:has-text("{text}")').first
                        if await btn.is_visible(timeout=3000):
                            action_time = datetime.now()
                            log.info(f"Clicking: {text} at {action_time.strftime('%I:%M:%S %p')}")
                            await btn.click()
                            await page.wait_for_timeout(2000)

                            # Screenshot with member name
                            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                            safe_name = name.replace(" ", "_").replace(".", "_")
                            shot_path = f"{SCREENSHOTS_DIR}/{safe_name}_{action}_{ts}.png"
                            await page.screenshot(path=shot_path)
                            log.info(f"Screenshot saved: {shot_path}")

                            # Handle confirmation dialog for clock_out
                            if action == "clock_out":
                                try:
                                    await page.wait_for_timeout(1000)
                                    confirm_selectors = [
                                        'button:has-text("Yes, clock out")',
                                        'button:text-is("Yes, clock out")',
                                        'button:text("Yes")',
                                        '.modal button:has-text("Yes")',
                                        '[role="dialog"] button:has-text("Yes")'
                                    ]
                                    for selector in confirm_selectors:
                                        try:
                                            confirm_btn = page.locator(selector).first
                                            if await confirm_btn.is_visible(timeout=2000):
                                                log.info(f"Confirmation dialog detected, clicking: {selector}")
                                                await confirm_btn.click()
                                                await page.wait_for_timeout(3000)
                                                break
                                        except:
                                            continue
                                except Exception:
                                    pass

                            await page.wait_for_timeout(1000)
                            break
                    except Exception as e:
                        log.warning(f"Failed to find or click '{text}': {e}")
                        continue

            # Verify action (only if not already verified)
            if not action_verified:
                await page.wait_for_timeout(3000)
                verification_patterns = ["Clock Out","End Shift","End Work","Punch Out","Stop","Finish"] if action=="clock_in" else ["Clock In","Start Shift","Start Work","Punch In","Start","Begin"]
                for verify_text in verification_patterns:
                    try:
                        verify_btn = page.locator(f'button:has-text("{verify_text}"), a:has-text("{verify_text}")').first
                        if await verify_btn.is_visible(timeout=3000):
                            log.info(f"✓ Action verified: '{verify_text}' button is now visible")
                            action_verified = True
                            break
                    except:
                        continue

            ts_display = datetime.now().strftime("%d %b %Y - %I:%M:%S %p")
            status = "✅ SUCCESS" if action_verified else "⚠️ COMPLETED"
            log.info(f"{status}: {name} - {action} at {ts_display}")

            if not action_verified:
                ts_verify = datetime.now().strftime("%Y%m%d_%H%M%S")
                safe_name = name.replace(" ", "_").replace(".", "_")
                await page.screenshot(path=f"{SCREENSHOTS_DIR}/VERIFY_FAILED_{safe_name}_{action}_{ts_verify}.png", full_page=True)

            return action_verified

        except Exception as e:
            log.error(f"FAILED for {name}: {e}")
            try:
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                safe_name = name.replace(" ", "_").replace(".", "_")
                await page.screenshot(path=f"{SCREENSHOTS_DIR}/ERROR_{safe_name}_{action}_{ts}.png", full_page=True)
            except:
                pass
            return False
        finally:
            await browser.close()


async def run_for_all_members(action):
    """Run the clock action for all team_members sequentially."""
    members = load_team_members()

    if not members:
        log.error("No active team members found!")
        return

    log.info(f"\n{'#'*60}")
    log.info(f"ClockBot Team Processing")
    log.info(f"Action: {action.upper()}")
    log.info(f"Total members: {len(members)}")
    log.info(f"Time: {datetime.now().strftime('%d %b %Y - %I:%M:%S %p %Z')}")
    log.info(f"{'#'*60}\n")

    results = []
    for member in members:
        success = await perform_action_for_member(member, action)
        results.append({
            "name": member.get("name"),
            "email": member.get("email"),
            "success": success
        })
        # Small delay between members
        await asyncio.sleep(2)

    # Summary
    log.info(f"\n{'#'*60}")
    log.info("SUMMARY")
    log.info(f"{'#'*60}")
    successful = [r for r in results if r["success"]]
    failed = [r for r in results if not r["success"]]

    log.info(f"✅ Successful: {len(successful)}/{len(results)}")
    for r in successful:
        log.info(f"   - {r['name']}")

    if failed:
        log.info(f"❌ Failed: {len(failed)}/{len(results)}")
        for r in failed:
            log.info(f"   - {r['name']}")

    log.info(f"{'#'*60}\n")


if __name__ == "__main__":
    asyncio.run(run_for_all_members(CLOCK_ACTION))
