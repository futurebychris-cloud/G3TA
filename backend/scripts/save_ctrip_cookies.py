#!/usr/bin/env python3
"""Launch a VISIBLE browser to log into Ctrip manually, then persist cookies.

Ctrip blocks automated login (CAPTCHA, SMS verification, QR code). This script:
  1. Launches a *visible* (non-headless) Chromium browser.
  2. Navigates to the Ctrip login page.
  3. Waits for YOU to log in manually (password, SMS code, or QR scan).
  4. Detects successful login by watching for redirect to hotels.ctrip.com.
  5. Saves all Ctrip-domain cookies to ``cookies.json`` for headless reuse.

Usage:
    cd backend
    python scripts/save_ctrip_cookies.py

Then the headless pipeline in ``booking/ctrip.py`` will automatically load
cookies from ``cookies.json`` when ``CTRIP_COOKIE`` env var is not set.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

# Ensure we're running from the backend dir
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Load .env if dotenv is installed
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

COOKIE_FILE = ROOT / "cookies.json"


def save_cookies():
    from playwright.sync_api import sync_playwright

    email = os.environ.get("CTRIP_EMAIL", "")
    phone = os.environ.get("CTRIP_PHONE", "")
    print(f"📧 Email: {email or '(not set in .env)'}")
    print(f"📱 Phone: {phone or '(not set in .env)'}")
    print()

    pw = sync_playwright().start()

    # Launch VISIBLE browser (headless=False) — user must interact
    try:
        browser = pw.chromium.launch(
            headless=False,
            channel="chrome",
            args=["--disable-blink-features=AutomationControlled"],
        )
        print("✅ Chrome launched (visible window)")
    except Exception:
        browser = pw.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        print("✅ Chromium launched (visible window)")

    context = browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1280, "height": 900},
        locale="zh-CN",
        timezone_id="Asia/Shanghai",
    )

    page = context.new_page()

    # Navigate to Ctrip login
    login_url = "https://passport.ctrip.com/user/login?backurl=https%3A%2F%2Fhotels.ctrip.com%2F"
    print(f"\n🌐 Opening: {login_url}")
    print()
    print("=" * 60)
    print("  ⚠️  PLEASE LOG IN MANUALLY in the browser window")
    print("     - Enter password + SMS verification code")
    print("     - OR scan the QR code with WeChat/Alipay")
    print()
    if email:
        print(f"  📧 Use: {email}")
    if phone:
        print(f"  📱 Use: {phone}")
    print()
    print("  This script will auto-detect successful login and")
    print("  save your cookies. Close the browser when done.")
    print("=" * 60)

    page.goto(login_url, timeout=30000, wait_until="domcontentloaded")

    # Wait for the user to log in (max 120 seconds)
    print("\n⏳ Waiting for login (2 minute timeout)...")
    logged_in = False
    for i in range(240):  # 120 seconds, checking every 0.5s
        time.sleep(0.5)
        try:
            url = page.url
            title = page.title()
            # Detect successful login: redirected away from passport/login
            if "passport" not in url.lower() and "login" not in url.lower():
                if "携程" in title or "hotel" in url.lower() or "ctrip" in url.lower():
                    logged_in = True
                    print(f"\n✅ Login detected! URL: {url[:100]}")
                    print(f"   Title: {title}")
                    break
            # Also detect if we're on the hotels page directly
            if "hotels.ctrip.com" in url and "passport" not in url:
                logged_in = True
                print(f"\n✅ Login detected (hotels page)! URL: {url[:100]}")
                break
        except Exception:
            pass

    if not logged_in:
        print("\n⚠️  Login not auto-detected. Saving whatever cookies exist...")

    # Extract all Ctrip-related cookies
    all_cookies = context.cookies()
    ctrip_cookies = [c for c in all_cookies if "ctrip" in c.get("domain", "")]

    if not ctrip_cookies:
        print("❌ No Ctrip cookies found. Did you log in?")
        browser.close()
        pw.stop()
        return

    # Save to JSON file
    cookie_data = {
        "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "email": email,
        "phone": phone,
        "cookie_string": "; ".join(
            f"{c['name']}={c['value']}" for c in ctrip_cookies
        ),
        "cookies": ctrip_cookies,
    }

    COOKIE_FILE.write_text(json.dumps(cookie_data, ensure_ascii=False, indent=2))
    COOKIE_FILE.chmod(0o600)
    print(f"\n💾 {len(ctrip_cookies)} cookies saved to: {COOKIE_FILE}")
    print()
    print("✅ Done! The headless pipeline will now use these cookies.")
    print("   Cookies typically expire after a few hours/days.")
    print("   Re-run this script when they expire.")

    # Keep the browser open for a few seconds so the user can see the result
    print("\nClosing browser in 3 seconds...")
    time.sleep(3)

    browser.close()
    pw.stop()


if __name__ == "__main__":
    save_cookies()
