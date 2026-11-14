#!/usr/bin/env python3
"""
Opens GitHub, Supabase, Render, Vercel, and your AirbCar platform in your
real Brave profile. Auto-clicks "Continue with GitHub" on the sites that
support it, then jumps straight to your actual project/dashboard page on
each one (instead of leaving you on the generic post-login landing page).
Also auto-logs-in to AirbCar as both partner and admin, plus creates one
random test user via the signup form.

SETUP (one-time):
    pip install playwright
    playwright install chromium

IMPORTANT (how this avoids closing Brave):
    - This script does NOT let Playwright launch/own the Brave process.
      Instead, it launches Brave itself (via subprocess.Popen, detached
      from Playwright's lifecycle) with remote debugging enabled, then
      Playwright just *connects* to it over CDP.
    - Because Playwright never "owns" that Brave process, when this
      script exits it only disconnects and closes the tabs it opened.
      Brave itself (and any other tabs/windows) stays open.
    - This still force-closes any running Brave process first, because
      Chromium-based browsers refuse to open a second instance against
      the same profile folder. That's unavoidable -- but afterwards,
      the single instance it launches is yours to keep using.
    - Edit BRAVE_PATH and USER_DATA_DIR below to match your machine.
    - When you're done, close this terminal window (or press Ctrl+C).
      ONLY the tabs this script opened will close -- Brave itself
      keeps running.

NOTE ON AIRBCAR SELECTORS:
    I don't have access to your actual auth page markup, so the login/
    signup helpers below use generic selectors (input[type=email],
    input[type=password], button text matching "sign in"/"log in"/
    "sign up"/etc.). If your form uses custom field names or the sign-up
    tab needs a different click target, adjust AIRBCAR_SELECTORS or the
    matching regexes near the top of the airbcar section -- everything
    is centralized there so it's a one-spot fix.

Usage:
    python auto_login_profiles.py
    (leave this terminal open while you work; close it when you're done
     -- or just Ctrl+C once the sites are open, Brave will stay up)
"""

from playwright.sync_api import sync_playwright
import os
import re
import sys
import time
import socket
import random
import string
import subprocess
import atexit

# ---- EDIT THESE FOR YOUR MACHINE ----
BRAVE_PATH = r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"
USER_DATA_DIR = os.path.expandvars(r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\User Data")
DEBUG_PORT = 9222
# --------------------------------------

# Goes straight to your repo instead of your profile page.
GITHUB_PROFILE_URL = "https://github.com/mayachee/AirbCar_platform"

# Each entry logs in via "Continue with GitHub" on the generic login page,
# then (after the OAuth redirect settles) navigates straight to the
# project_url below instead of leaving you on the default post-login page.
SITES_WITH_GITHUB_SSO = [
    {
        "name": "Supabase",
        "url": "https://supabase.com/dashboard/sign-in",
        "button_text": "GitHub",
        "project_url": "https://supabase.com/dashboard/project/wtbmqtmmdobfvvecinif",
    },
    {
        "name": "Vercel",
        "url": "https://vercel.com/login",
        "button_text": "GitHub",
        "project_url": "https://vercel.com/siiine-764s-projects/airb-car-platform",
    },
    {
        "name": "Render",
        "url": "https://dashboard.render.com/login",
        "button_text": "GitHub",
        "project_url": "https://dashboard.render.com/web/srv-d4ob2ta4i8rc73evm77g",
    },
]

# How long to wait after clicking the GitHub SSO button before jumping to
# the project_url, so the OAuth redirect + dashboard load has time to
# settle first. Bump this up if a site still lands on the login page.
POST_SSO_SETTLE_SECONDS = 3

# ---- AirbCar config ----
AIRBCAR_AUTH_URL = "https://airb-car-platform.vercel.app/en/auth"
AIRBCAR_ADMIN_DASHBOARD_URL = "https://airb-car-platform.vercel.app/en/admin/dashboard"

AIRBCAR_PARTNER = {"email": os.environ.get("AIRBCAR_PARTNER_EMAIL", ""), "password": os.environ.get("AIRBCAR_PARTNER_PASSWORD", "")}
AIRBCAR_ADMIN = {"email": os.environ.get("AIRBCAR_ADMIN_EMAIL", ""), "password": os.environ.get("AIRBCAR_ADMIN_PASSWORD", "")}

# Regexes used to find buttons/links by their visible text. Tweak these
# if your UI uses different wording.
LOGIN_SUBMIT_RE = re.compile(r"sign in|log in|login", re.I)
SIGNUP_TAB_RE = re.compile(r"^sign up$", re.I)          # the small tab button
SIGNUP_SUBMIT_RE = re.compile(r"sign up|create account|register", re.I)  # the form's submit button

opened_pages = []       # only the pages THIS script opens
_cleaned_up = False


def is_port_open(port, host="127.0.0.1"):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def close_existing_brave():
    """Force-kill any running Brave processes and clear stale lock files.
    Needed because Chromium won't open a second instance against the
    same profile folder -- but note this only runs ONCE at startup,
    it's not part of cleanup(), so it doesn't affect shutdown."""
    print("Closing any running Brave processes...")
    subprocess.run(
        ["taskkill", "/F", "/IM", "brave.exe", "/T"],
        capture_output=True,
        text=True,
    )
    time.sleep(1.5)
    for lock_file in ["SingletonLock", "SingletonCookie", "SingletonSocket"]:
        path = os.path.join(USER_DATA_DIR, lock_file)
        try:
            if os.path.exists(path):
                os.remove(path)
                print(f"  Removed stale lock file: {lock_file}")
        except Exception as e:
            print(f"  Couldn't remove {lock_file}: {e}")


def launch_brave_detached():
    """Launch Brave as an independent OS process (not owned by
    Playwright), with remote debugging enabled so Playwright can
    attach to it via CDP. This is the key change: since Playwright
    never launches this process, it can never terminate it."""
    print("Launching Brave (remote debugging enabled)...")
    creationflags = 0
    if sys.platform == "win32":
        # DETACHED_PROCESS: fully detach from this console/process tree
        creationflags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP

    subprocess.Popen(
        [
            BRAVE_PATH,
            f"--remote-debugging-port={DEBUG_PORT}",
            f"--user-data-dir={USER_DATA_DIR}",
            "--profile-directory=Default",
            "--start-maximized",
            "--no-first-run",
        ],
        creationflags=creationflags,
        close_fds=True,
    )

    for _ in range(40):  # wait up to ~20s for the debug port to come up
        if is_port_open(DEBUG_PORT):
            return True
        time.sleep(0.5)
    return False


def cleanup():
    """Close only the tabs this script opened. Runs on normal exit,
    Ctrl+C, or the terminal window being closed. Never touches the
    Brave process itself."""
    global _cleaned_up
    if _cleaned_up:
        return
    _cleaned_up = True
    print("\nClosing the tabs this script opened (Brave stays open)...")
    for page in opened_pages:
        try:
            if not page.is_closed():
                page.close()
        except Exception:
            pass


atexit.register(cleanup)

# On Windows, clicking the terminal's X button sends a console close
# event that plain atexit doesn't reliably catch -- hook it directly.
if sys.platform == "win32":
    import ctypes

    HANDLER_TYPE = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_uint)

    def _console_handler(event):
        cleanup()
        return False

    _handler_ref = HANDLER_TYPE(_console_handler)
    ctypes.windll.kernel32.SetConsoleCtrlHandler(_handler_ref, True)


def random_email():
    tag = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    return f"testuser.{tag}@mailinator.com"


def random_password():
    chars = string.ascii_letters + string.digits
    return "Aa1" + "".join(random.choices(chars, k=9))


def random_name_part():
    return "Test" + "".join(random.choices(string.ascii_lowercase, k=5)).capitalize()


def random_moroccan_phone():
    # Matches the "+212 6XX-XXXXXX" placeholder shape: a Moroccan mobile
    # number starting with 6, 9 digits total after the country code.
    local = "6" + "".join(random.choices(string.digits, k=8))
    return f"+212{local}"


def airbcar_login(context, url, email, password, label):
    page = context.new_page()
    opened_pages.append(page)
    try:
        page.goto(url, timeout=15000)
        time.sleep(1.5)

        page.locator('input[type="email"]').first.fill(email, timeout=5000)
        page.locator('input[type="password"]').first.fill(password, timeout=5000)
        # .last, not .first — "Sign In" also matches the tab button at the
        # top of the form, which comes before the actual submit button in
        # the DOM. .first was clicking the tab (a no-op), so the form was
        # never submitted.
        page.get_by_role("button", name=LOGIN_SUBMIT_RE).last.click(timeout=5000)
        print(f"[OK] Submitted AirbCar login for {label} ({email})")
        time.sleep(2)
    except Exception as e:
        print(f"[SKIPPED] Couldn't auto-fill AirbCar login for {label}: {e}")
        print(f"          Open it manually and log in: {url}")
    return page


def airbcar_create_random_user(context):
    """Open the AirbCar auth page, switch to the Sign Up tab, and
    register a randomly generated test user (matches the First Name /
    Last Name / Email / Phone Number / Password form)."""
    first_name = random_name_part()
    last_name = random_name_part()
    email = random_email()
    phone = random_moroccan_phone()
    password = random_password()

    generated = (
        f"     first name: {first_name}\n"
        f"     last name:  {last_name}\n"
        f"     email:      {email}\n"
        f"     phone:      {phone}\n"
        f"     password:   {password}"
    )

    page = context.new_page()
    opened_pages.append(page)
    try:
        page.goto(AIRBCAR_AUTH_URL, timeout=15000)
        time.sleep(1.5)

        # Click the "Sign Up" tab button (top of the form) to switch
        # away from the default "Sign In" tab.
        try:
            page.get_by_role("button", name=SIGNUP_TAB_RE).first.click(timeout=5000)
            time.sleep(1)
        except Exception:
            print("[INFO] Couldn't find the Sign Up tab button -- assuming "
                  "the form is already showing the sign-up fields.")

        page.get_by_placeholder(re.compile("first name", re.I)).fill(first_name, timeout=5000)
        page.get_by_placeholder(re.compile("last name", re.I)).fill(last_name, timeout=5000)
        page.get_by_placeholder(re.compile("email", re.I)).fill(email, timeout=5000)
        page.get_by_placeholder(re.compile(r"\+212|phone", re.I)).fill(phone, timeout=5000)
        page.get_by_placeholder(re.compile("password", re.I)).first.fill(password, timeout=5000)

        # Fill a confirm-password field too, if the form has one.
        try:
            pw_fields = page.get_by_placeholder(re.compile("password", re.I))
            if pw_fields.count() > 1:
                pw_fields.nth(1).fill(password, timeout=3000)
        except Exception:
            pass

        # The submit button is below the fields; .last avoids re-hitting
        # the "Sign Up" tab button at the top which has the same text.
        page.get_by_role("button", name=SIGNUP_SUBMIT_RE).last.click(timeout=5000)
        print("[OK] Submitted AirbCar sign-up for random user:")
        print(generated)
        time.sleep(2)
    except Exception as e:
        print(f"[SKIPPED] Couldn't auto-fill AirbCar sign-up: {e}")
        print("          Random credentials that were generated (fill in manually if needed):")
        print(generated)
        print(f"          Open it manually: {AIRBCAR_AUTH_URL}")


def main():
    if not all(account['email'] and account['password'] for account in (AIRBCAR_PARTNER, AIRBCAR_ADMIN)):
        raise SystemExit("Set AIRBCAR_PARTNER_EMAIL, AIRBCAR_PARTNER_PASSWORD, AIRBCAR_ADMIN_EMAIL, and AIRBCAR_ADMIN_PASSWORD before running this personal browser tool")
    if not os.path.exists(BRAVE_PATH):
        print(f"Brave not found at: {BRAVE_PATH}")
        print("Edit BRAVE_PATH in this script to point at your actual brave.exe")
        return

    close_existing_brave()

    if not launch_brave_detached():
        print("Brave didn't open its remote debugging port in time.")
        print("Try closing Brave manually from the system tray, then rerun.")
        return

    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{DEBUG_PORT}")
            context = browser.contexts[0] if browser.contexts else browser.new_context()
        except Exception as e:
            print("Couldn't connect to Brave over CDP.")
            print(f"Details: {e}")
            return

        gh_page = context.new_page()
        opened_pages.append(gh_page)
        gh_page.goto(GITHUB_PROFILE_URL)
        time.sleep(1.5)

        for site in SITES_WITH_GITHUB_SSO:
            page = context.new_page()
            opened_pages.append(page)
            try:
                page.goto(site["url"], timeout=15000)
                time.sleep(1.5)
                page.get_by_text(site["button_text"], exact=False).first.click(timeout=5000)
                print(f"[OK] Clicked GitHub sign-in on {site['name']}")

                project_url = site.get("project_url")
                if project_url:
                    # Give the OAuth redirect + dashboard a moment to settle
                    # before jumping straight to the actual project page.
                    time.sleep(POST_SSO_SETTLE_SECONDS)
                    try:
                        page.goto(project_url, timeout=15000)
                        print(f"[OK] Navigated {site['name']} to project page")
                    except Exception as e:
                        print(f"[SKIPPED] Couldn't navigate {site['name']} to project page: {e}")
                        print(f"          Open it manually: {project_url}")
            except Exception as e:
                print(f"[SKIPPED] Couldn't auto-click GitHub button on {site['name']}: {e}")
                print(f"          Open it manually: {site['url']}")
            time.sleep(1)

        # --- AirbCar: partner login ---
        airbcar_login(
            context, AIRBCAR_AUTH_URL,
            AIRBCAR_PARTNER["email"], AIRBCAR_PARTNER["password"],
            label="partner",
        )

        # --- AirbCar: admin login, then jump to the admin dashboard ---
        admin_page = airbcar_login(
            context, AIRBCAR_AUTH_URL,
            AIRBCAR_ADMIN["email"], AIRBCAR_ADMIN["password"],
            label="admin",
        )
        try:
            admin_page.goto(AIRBCAR_ADMIN_DASHBOARD_URL, timeout=15000)
            print("[OK] Navigated to AirbCar admin dashboard")
        except Exception as e:
            print(f"[SKIPPED] Couldn't navigate to admin dashboard: {e}")
            print(f"          Open it manually: {AIRBCAR_ADMIN_DASHBOARD_URL}")

        # --- AirbCar: create one random test user ---
        airbcar_create_random_user(context)

        print("\nTabs are open. Leave this terminal running while you work.")
        print("Close this window (or press Ctrl+C) to close just those tabs --")
        print("Brave itself will keep running.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass  # cleanup() runs via atexit

        # Disconnect from CDP without closing the browser it's attached to.
        try:
            browser.close()  # for connect_over_cdp this only ends the
                              # Playwright connection, it does not
                              # terminate the (independently-launched)
                              # Brave process
        except Exception:
            pass


if __name__ == "__main__":
    main()
