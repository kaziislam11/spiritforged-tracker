"""
Microcenter Riftbound: Spiritforged Stock Checker
==================================================
Monitors Microcenter for Spiritforged Booster Display Box and Sleeved Boosters.
Sends you a text (via email-to-SMS gateway) when stock is detected.

SETUP (local):
  1. pip install requests beautifulsoup4 python-dotenv
  2. Fill in your .env file (see .env.example)
  3. python mc_riftbound_checker.py

SETUP (Railway):
  1. Push this folder to GitHub (the .env file will NOT be pushed — it's in .gitignore)
  2. Connect repo to Railway
  3. In Railway dashboard > Variables, add GMAIL_ADDRESS and GMAIL_APP_PASS
  4. Deploy — it runs forever automatically
"""

import os
import time
import smtplib
import requests
from bs4 import BeautifulSoup
from email.mime.text import MIMEText
from datetime import datetime
from dotenv import load_dotenv

# Load .env file if it exists (local dev). On Railway, env vars are injected automatically.
load_dotenv()

# ============================================================
#  CONFIG
# ============================================================

STORE_ID       = "145"                  # Microcenter Flushing, NY (71-43 Kissena Blvd)
YOUR_PHONE_SMS = "9296057131@vtext.com" # Verizon SMS gateway
CHECK_INTERVAL = 300                    # Seconds between checks (5 min)

# Loaded from .env locally, or Railway Variables in prod — never hardcoded
GMAIL_ADDRESS  = os.environ.get("GMAIL_ADDRESS")
GMAIL_APP_PASS = os.environ.get("GMAIL_APP_PASS")

# ============================================================
#  PRODUCTS TO WATCH
# ============================================================

PRODUCTS = [
    {
        "name": "Spiritforged Booster Display Box",
        "url":  "https://www.microcenter.com/product/707000/riot-games-riftbound-league-of-legends-tcg-spirit-forged-booster-display-box",
        "sku":  "707000",
    },
    {
        "name": "Spiritforged Sleeved Boosters",
        "url":  "https://www.microcenter.com/product/706995/riot-games-riftbound-league-of-legends-tcg-spirit-forged-sleeved-boosters",
        "sku":  "706995",
    },
]

# ============================================================
#  HEADERS — mimics a real browser visit
# ============================================================

HEADERS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection":      "keep-alive",
    "Referer":         "https://www.microcenter.com/",
}

# ============================================================
#  CORE FUNCTIONS
# ============================================================

def send_text(subject: str, body: str):
    """Send an SMS via email-to-SMS gateway using Gmail."""
    if not GMAIL_ADDRESS or not GMAIL_APP_PASS:
        print("  [SMS SKIPPED] GMAIL_ADDRESS or GMAIL_APP_PASS not set in environment.")
        return
    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"]    = GMAIL_ADDRESS
        msg["To"]      = YOUR_PHONE_SMS

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_ADDRESS, GMAIL_APP_PASS)
            server.sendmail(GMAIL_ADDRESS, YOUR_PHONE_SMS, msg.as_string())

        print(f"  [SMS sent] {subject}")
    except Exception as e:
        print(f"  [SMS FAILED] {e}")


def check_stock(product: dict, session: requests.Session):
    """
    Returns True if in stock, False if out of stock, None on error.
    Sets the storeSelected cookie so we get the right store's data.
    """
    try:
        session.cookies.set("storeSelected", STORE_ID, domain=".microcenter.com")
        resp = session.get(product["url"], headers=HEADERS, timeout=15)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        page_text = soup.get_text(" ", strip=True).lower()

        # Check explicit out-of-stock signals first
        if "out of stock" in page_text or "sold out" in page_text:
            qty_tag = soup.find("span", {"id": "pnlInventory"})
            if qty_tag and "in stock" in qty_tag.get_text().lower():
                return True
            return False

        # Check for positive in-stock signals
        if "in stock" in page_text or "add to cart" in page_text:
            return True

        # Fallback — look for the inventory quantity element
        qty_el = soup.find(id="pnlInventory")
        if qty_el:
            qty_text = qty_el.get_text(strip=True).lower()
            if qty_text and "out" not in qty_text:
                return True

        return False

    except requests.exceptions.RequestException as e:
        print(f"  [Network error for {product['name']}] {e}")
        return None


def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}")


# ============================================================
#  STARTUP VALIDATION
# ============================================================

def validate_config():
    errors = []
    if not GMAIL_ADDRESS:
        errors.append("GMAIL_ADDRESS is not set in your .env file")
    if not GMAIL_APP_PASS:
        errors.append("GMAIL_APP_PASS is not set in your .env file")
    if errors:
        print("\n[ERROR] Missing configuration:")
        for e in errors:
            print(f"  - {e}")
        print("\nCreate a .env file with:")
        print("  GMAIL_ADDRESS=your_email@gmail.com")
        print("  GMAIL_APP_PASS=xxxx xxxx xxxx xxxx")
        print("\nOr set them as environment variables in Railway.\n")
        exit(1)


# ============================================================
#  MAIN LOOP
# ============================================================

def main():
    validate_config()

    print("=" * 55)
    print("  Microcenter Riftbound: Spiritforged Stock Checker")
    print("=" * 55)
    print(f"  Store         : Flushing, NY (ID: {STORE_ID})")
    print(f"  Alert SMS     : {YOUR_PHONE_SMS}")
    print(f"  Gmail         : {GMAIL_ADDRESS}")
    print(f"  Check every   : {CHECK_INTERVAL}s ({CHECK_INTERVAL // 60} min)")
    print(f"  Watching      : {len(PRODUCTS)} product(s)")
    print("  Press Ctrl+C to stop anytime.")
    print("=" * 55)

    prev_state = {p["sku"]: None for p in PRODUCTS}
    session = requests.Session()
    check_count = 0

    # Startup confirmation text
    send_text(
        "Riftbound Checker Started",
        f"Monitoring {len(PRODUCTS)} Spiritforged product(s) at Microcenter Flushing. "
        f"Checking every {CHECK_INTERVAL // 60} min. You'll get a text when stock appears."
    )

    while True:
        check_count += 1
        log(f"Check #{check_count} — scanning {len(PRODUCTS)} product(s)...")

        for product in PRODUCTS:
            in_stock = check_stock(product, session)

            if in_stock is None:
                log(f"  ? {product['name']} — error, skipping")
                continue

            status_str = "IN STOCK ✓" if in_stock else "out of stock"
            log(f"  {'✓' if in_stock else '✗'} {product['name']} — {status_str}")

            # Alert on change to in-stock
            if in_stock and prev_state[product["sku"]] is False:
                send_text(
                    f"IN STOCK: {product['name']}",
                    f"{product['name']} is NOW IN STOCK at Microcenter Flushing!\n"
                    f"Move fast:\n{product['url']}"
                )
            elif not in_stock and prev_state[product["sku"]] is True:
                log(f"  [Note] {product['name']} just went out of stock.")

            # First run — alert if already in stock
            elif in_stock and prev_state[product["sku"]] is None:
                send_text(
                    f"ALREADY IN STOCK: {product['name']}",
                    f"{product['name']} is IN STOCK right now at Microcenter Flushing!\n"
                    f"{product['url']}"
                )

            prev_state[product["sku"]] = in_stock
            time.sleep(3)

        log(f"  Done. Next check in {CHECK_INTERVAL}s...")
        print()

        try:
            time.sleep(CHECK_INTERVAL)
        except KeyboardInterrupt:
            print("\n[Stopped] Goodbye!")
            break


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[Stopped] Goodbye!")
