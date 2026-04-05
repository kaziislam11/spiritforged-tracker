"""
Microcenter Riftbound: Spiritforged Stock Checker
==================================================
Runs via GitHub Actions every 10 minutes.
Only sends a text when stock is detected at Microcenter Flushing.

Secrets in GitHub repo Settings > Secrets > Actions:
  - GMAIL_ADDRESS
  - GMAIL_APP_PASS
"""

import os
import json
import smtplib
import requests
from bs4 import BeautifulSoup
from email.mime.text import MIMEText
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# ============================================================
#  CONFIG
# ============================================================

STORE_ID       = "145"                   # Microcenter Flushing, NY
YOUR_PHONE_SMS = "9296057131@vtext.com"  # Verizon SMS gateway
GMAIL_ADDRESS  = os.environ.get("GMAIL_ADDRESS")
GMAIL_APP_PASS = os.environ.get("GMAIL_APP_PASS")
STATE_FILE     = "stock_state.json"

PRODUCTS = [
    {
        "name": "Spiritforged Booster Box",
        "url":  "https://www.microcenter.com/product/707000/riot-games-riftbound-league-of-legends-tcg-spirit-forged-booster-display-box",
        "sku":  "707000",
    },
    {
        "name": "Spiritforged Sleeved Boosters",
        "url":  "https://www.microcenter.com/product/706995/riot-games-riftbound-league-of-legends-tcg-spirit-forged-sleeved-boosters",
        "sku":  "706995",
    },
]

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
#  FUNCTIONS
# ============================================================

def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}")


def send_text(subject, body):
    if not GMAIL_ADDRESS or not GMAIL_APP_PASS:
        log("[SMS SKIPPED] Missing credentials")
        return
    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"]    = GMAIL_ADDRESS
        msg["To"]      = YOUR_PHONE_SMS
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_ADDRESS, GMAIL_APP_PASS)
            server.sendmail(GMAIL_ADDRESS, YOUR_PHONE_SMS, msg.as_string())
        log(f"[SMS SENT] {subject}")
    except smtplib.SMTPAuthenticationError:
        log("[SMS FAILED] Bad app password")
    except Exception as e:
        log(f"[SMS FAILED] {type(e).__name__}: {e}")


def check_stock(product, session):
    try:
        session.cookies.set("storeSelected", STORE_ID, domain=".microcenter.com")
        resp = session.get(product["url"], headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        page_text = soup.get_text(" ", strip=True).lower()

        if "out of stock" in page_text or "sold out" in page_text:
            qty_tag = soup.find("span", {"id": "pnlInventory"})
            if qty_tag and "in stock" in qty_tag.get_text().lower():
                return True
            return False

        if "in stock" in page_text or "add to cart" in page_text:
            return True

        qty_el = soup.find(id="pnlInventory")
        if qty_el:
            qty_text = qty_el.get_text(strip=True).lower()
            if qty_text and "out" not in qty_text:
                return True

        return False

    except requests.exceptions.RequestException as e:
        log(f"[Network error] {product['name']}: {e}")
        return None


def load_state():
    try:
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(state):
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f)
    except Exception as e:
        log(f"[State save failed] {e}")


# ============================================================
#  MAIN
# ============================================================

def main():
    log("Riftbound check — Microcenter Flushing")

    if not GMAIL_ADDRESS or not GMAIL_APP_PASS:
        log("[ERROR] Missing GMAIL_ADDRESS or GMAIL_APP_PASS in secrets")
        exit(1)

    prev_state = load_state()
    new_state  = {}
    session    = requests.Session()

    for product in PRODUCTS:
        in_stock = check_stock(product, session)
        sku      = product["sku"]

        if in_stock is None:
            log(f"? {product['name']} — check failed")
            new_state[sku] = prev_state.get(sku, False)
            continue

        log(f"{'IN STOCK' if in_stock else 'out of stock'} — {product['name']}")

        was_in_stock = prev_state.get(sku, False)

        if in_stock and not was_in_stock:
            send_text(
                f"IN STOCK: {product['name']}",
                f"{product['name']} back at MC Flushing!\n{product['url']}"
            )

        new_state[sku] = in_stock

    save_state(new_state)
    log("Done.")


if __name__ == "__main__":
    main()
