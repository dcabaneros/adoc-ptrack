import requests
from bs4 import BeautifulSoup
import brotli
import gzip
from io import BytesIO
import os
from datetime import datetime
import pytz
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# === CONFIG ===

# List of products to track
PRODUCTS = [
    {"name": "Lemforder 3387501", "url": "https://www.autodoc.es/lemforder/1272015"},
    {"name": "Lemforder 3557301", "url": "https://www.autodoc.es/lemforder/1273493"},
    {"name": "Lemforder 3557401", "url": "https://www.autodoc.es/lemforder/1273494"},
    {"name": "HITACHI 2502195", "url": "https://www.autodoc.es/hitachi/13965133"},
    # Add more products here
]

# Price history file (absolute path to avoid working directory issues)
PRICE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "price_history.txt")

# Gmail credentials (from GitHub Secrets)
SENDER_EMAIL = os.getenv("EMAIL_USER")
SENDER_PASS = os.getenv("EMAIL_PASS")
RECEIVER_EMAIL = os.getenv("EMAIL_TO") or SENDER_EMAIL

# iOS Autodoc app headers
HEADERS = {
    "User-Agent": "Autodoc/2.6.1 (iPhone; iOS 17.5; Scale/3.00)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Referer": "https://www.autodoc.es/",
}

MADRID_TZ = pytz.timezone("Europe/Madrid")

# === FETCH HTML ===
def fetch_html(url):
    response = requests.get(url, headers=HEADERS, timeout=15)
    response.raise_for_status()
    encoding = response.headers.get("Content-Encoding", "")
    content = response.content

    try:
        if "br" in encoding:
            try:
                html = brotli.decompress(content).decode("utf-8", errors="ignore")
            except brotli.error:
                html = content.decode("utf-8", errors="ignore")
        elif "gzip" in encoding:
            buf = BytesIO(content)
            with gzip.GzipFile(fileobj=buf) as f:
                html = f.read().decode("utf-8", errors="ignore")
        else:
            html = response.text
    except Exception:
        html = response.text

    return html


# === PARSE PRICE ===
def parse_price(html):
    soup = BeautifulSoup(html, "html.parser")
    selectors = [
        "div.product-block__price-new-wrap",
        "span.product-block__price",
        "div.product-price",
    ]
    for sel in selectors:
        el = soup.select_one(sel)
        if el and el.get_text(strip=True):
            text = el.get_text(strip=True)
            text = text.replace("€", "").replace(",", ".").split()[0]
            try:
                return float(text)
            except ValueError:
                continue
    print("🔍 HTML snippet (first 400 chars):")
    print(html[:400])
    raise ValueError("❌ Could not find price element on the page")


# === PRICE HISTORY ===
def load_last_price(product_name):
    """Return last recorded price for a product."""
    if os.path.exists(PRICE_FILE):
        with open(PRICE_FILE, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]
            for line in reversed(lines):
                parts = line.split("|")
                if len(parts) == 3 and parts[1].strip() == product_name:
                    try:
                        return float(parts[2].strip())
                    except ValueError:
                        continue
    return None


def save_price(product_name, price):
    """Append product price to history file with Madrid timezone, human-readable."""
    timestamp = datetime.now(MADRID_TZ).strftime("%d/%m/%Y %H:%M:%S")  # e.g., 22/10/2025 14:35:00
    try:
        with open(PRICE_FILE, "a", encoding="utf-8") as f:
            f.write(f"{timestamp} | {product_name} | {price}\n")
        print(f"✅ Saved {product_name} price {price} to {PRICE_FILE}")
    except Exception as e:
        print(f"⚠️ Failed to write history: {e}")


# === EMAIL ALERT ===
def send_email(subject, body):
    if not SENDER_EMAIL or not SENDER_PASS:
        print("⚠️ Missing Gmail credentials. Skipping email alert.")
        return

    msg = MIMEMultipart()
    msg["From"] = SENDER_EMAIL
    msg["To"] = RECEIVER_EMAIL
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(SENDER_EMAIL, SENDER_PASS)
            server.send_message(msg)
        print("📧 Email alert sent!")
    except Exception as e:
        print(f"⚠️ Email sending failed: {e}")


# === MAIN ===
def main():
    for product in PRODUCTS:
        name = product["name"]
        url = product["url"]

        print(f"\n🔎 Checking {name}...")
        try:
            html = fetch_html(url)
            current_price = parse_price(html)
        except Exception as e:
            print(f"⚠️ Failed to fetch/parse {name}: {e}")
            continue

        last_price = load_last_price(name)
        print(f"{name}: Current {current_price} €, Last {last_price if last_price is not None else 'N/A'} €")

        if last_price is not None:
            diff = current_price - last_price
            if diff < 0:
                print(f"📉 Price dropped ↓ {abs(diff):.2f} €")
                subject = f"📉 Price Drop Alert: {name}"
                body = f"{name} dropped from {last_price} € to {current_price} €!\n\n{url}"
                send_email(subject, body)
            elif diff > 0:
                print(f"📈 Price increased ↑ {diff:.2f} €")
            else:
                print("➖ Price unchanged.")
        else:
            print("🆕 First recorded price.")

        save_price(name, current_price)

    print("\n✅ All products checked.")


if __name__ == "__main__":
    main()
