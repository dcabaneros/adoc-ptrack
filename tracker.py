import requests
from bs4 import BeautifulSoup
import smtplib
from email.mime.text import MIMEText
import os
from datetime import datetime
from pathlib import Path
import re

# ---- Configuration ----
PRODUCT_URL = "https://www.autodoc.es/lemforder/1272015"  # Replace with your product URL
PRICE_FILE = Path("last_price.txt")

# Emulate Autodoc Android app headers
HEADERS = {
    "User-Agent": (
        "Autodoc/5.34.0 (Android 13; Mobile; rv:113.0) "
        "Gecko/113.0 Firefox/113.0 AutodocApp/5.34.0"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9,en-US;q=0.8,en;q=0.7",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

# ---- Email function ----
def send_email(subject, body):
    sender = os.environ["EMAIL_USER"]
    password = os.environ["EMAIL_PASS"]
    recipient = os.environ["EMAIL_TO"]

    msg = MIMEText(body)
    msg["From"] = sender
    msg["To"] = recipient
    msg["Subject"] = subject

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(sender, password)
        server.send_message(msg)

    print("📧 Email sent successfully.")

# ---- Price scraper ----
def get_current_price():
    print(f"Fetching {PRODUCT_URL} with Android headers...")
    resp = requests.get(PRODUCT_URL, headers=HEADERS, timeout=20)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    price_container = soup.find("div", class_="product-block__price-new-wrap")

    if not price_container:
        raise ValueError("❌ Could not find price element on the page")

    # Extract numeric price
    text = price_container.get_text(strip=True)
    match = re.search(r"(\d+[.,]?\d*)", text)
    if not match:
        raise ValueError("❌ Could not parse price from the text")

    price = float(match.group(1).replace(",", "."))
    return price

# ---- Main logic ----
def main():
    current_price = get_current_price()
    print(f"Current price: €{current_price}")

    last_price = None
    if PRICE_FILE.exists():
        last_price = float(PRICE_FILE.read_text().strip())
        print(f"Last recorded price: €{last_price}")

    PRICE_FILE.write_text(str(current_price))

    if last_price is not None and current_price < last_price:
        diff = last_price - current_price
        subject = f"🔻 Price drop detected! Now €{current_price:.2f} (-{diff:.2f}€)"
        body = f"""
The price of your tracked Autodoc product has dropped!

URL: {PRODUCT_URL}
Old price: €{last_price:.2f}
New price: €{current_price:.2f}
Drop: €{diff:.2f}

Time (UTC): {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}
"""
        send_email(subject, body)
    else:
        print("No price drop detected.")

if __name__ == "__main__":
    main()
