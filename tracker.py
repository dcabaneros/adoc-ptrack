import requests
from bs4 import BeautifulSoup
import brotli
import gzip
from io import BytesIO
import os
import json
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# === CONFIG ===
URL = "https://www.autodoc.es/lemforder/1272015"
PRICE_FILE = "price_history.json"

# Gmail sender info
SENDER_EMAIL = os.getenv("GMAIL_USER")      # e.g. youraddress@gmail.com
SENDER_PASS = os.getenv("GMAIL_APP_PASS")   # use an App Password, not your main one
RECEIVER_EMAIL = os.getenv("ALERT_RECEIVER") or SENDER_EMAIL

# iOS Autodoc app headers
HEADERS = {
    "User-Agent": "Autodoc/2.6.1 (iPhone; iOS 17.5; Scale/3.00)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Referer": "https://www.autodoc.es/",
}


# === FETCHING ===
def fetch_html(url):
    """Fetch page HTML with Brotli/gzip decoding."""
    print(f"Fetching {url} with iOS headers...")
    response = requests.get(url, headers=HEADERS, timeout=15)
    response.raise_for_status()
    encoding = response.headers.get("Content-Encoding", "")
    content = response.content

    try:
        if "br" in encoding:
            try:
                html = brotli.decompress(content).decode("utf-8", errors="ignore")
            except brotli.error:
                print("⚠️ Brotli decompression failed — using plain text.")
                html = content.decode("utf-8", errors="ignore")
        elif "gzip" in encoding:
            buf = BytesIO(content)
            with gzip.GzipFile(fileobj=buf) as f:
                html = f.read().decode("utf-8", errors="ignore")
        else:
            html = response.text
    except Exception as e:
        print(f"⚠️ Decompression failed: {e}. Falling back to raw text.")
        html = response.text

    return html


# === PARSING ===
def parse_price(html):
    """Extract the product price from HTML."""
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


# === STORAGE ===
def load_last_price():
    """Load last price from local JSON file."""
    if os.path.exists(PRICE_FILE):
        with open(PRICE_FILE, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
                if data:
                    return data[-1]["price"]
            except json.JSONDecodeError:
                pass
    return None


def save_price(price):
    """Save new price record."""
    data = []
    if os.path.exists(PRICE_FILE):
        with open(PRICE_FILE, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                pass
    data.append({"timestamp": datetime.now().isoformat(), "price": price})
    with open(PRICE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# === EMAIL ALERTS ===
def send_email(subject, body):
    """Send email alert through Gmail."""
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
    html = fetch_html(URL)
    current_price = parse_price(html)
    last_price = load_last_price()

    print(f"💰 Current price: {current_price} €")

    if last_price is not None:
        print(f"📈 Last recorded price: {last_price} €")
        diff = current_price - last_price

        if diff < 0:
            print(f"📉 Price dropped ↓ {abs(diff):.2f} €")
            subject = "📉 Autodoc Price Drop Alert"
            body = f"Price dropped from {last_price} € to {current_price} €!\n\n{URL}"
            send_email(subject, body)
        elif diff > 0:
            print(f"📈 Price increased ↑ {diff:.2f} €")
        else:
            print("➖ Price unchanged.")
    else:
        print("🆕 First recorded price.")

    save_price(current_price)
    print("✅ Price history updated.")


if __name__ == "__main__":
    main()
