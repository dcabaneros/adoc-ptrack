import requests
from bs4 import BeautifulSoup
import smtplib
from email.mime.text import MIMEText
import os

# -------------------
# CONFIGURATION
# -------------------
PRODUCT_URL = "https://www.autodoc.es/lemforder/1272015"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 12; Pixel 6 Pro) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Mobile Safari/537.36"
    ),
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
}
PRICE_FILE = "last_price.txt"


# -------------------
# HELPER FUNCTIONS
# -------------------
def fetch_html(url):
    print(f"Fetching {url} with Android headers...")
    response = requests.get(url, headers=HEADERS, timeout=15)
    response.raise_for_status()
    return response.text


def parse_price(html):
    soup = BeautifulSoup(html, "html.parser")
    price_tag = soup.find("div", class_="product-block__price-new-wrap")
    if not price_tag:
        raise ValueError("❌ Could not find price element on the page")

    # Extract text and clean it
    price_text = price_tag.get_text(strip=True)
    # Remove € symbol and convert to float
    price_value = float(price_text.replace("€", "").replace(",", ".").strip())
    return price_value


def load_price_history():
    if not os.path.exists(PRICE_FILE):
        return []
    with open(PRICE_FILE, "r", encoding="utf-8") as f:
        lines = [float(line.strip()) for line in f if line.strip()]
    return lines


def save_price_history(history):
    with open(PRICE_FILE, "w", encoding="utf-8") as f:
        for price in history:
            f.write(f"{price}\n")


def send_email_notification(current_price, previous_price):
    user = os.getenv("EMAIL_USER")
    password = os.getenv("EMAIL_PASS")
    to_email = os.getenv("EMAIL_TO")

    if not user or not password or not to_email:
        print("⚠️ Email credentials not provided. Skipping email notification.")
        return

    subject = "📉 Price Drop Alert on Autodoc!"
    body = (
        f"The price of your tracked product has dropped!\n\n"
        f"Previous price: {previous_price:.2f} €\n"
        f"New price: {current_price:.2f} €\n\n"
        f"Product link: {PRODUCT_URL}"
    )

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to_email

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(user, password)
            server.send_message(msg)
        print("✅ Email sent successfully.")
    except Exception as e:
        print(f"❌ Failed to send email: {e}")


# -------------------
# MAIN LOGIC
# -------------------
def main():
    html = fetch_html(PRODUCT_URL)
    current_price = parse_price(html)
    print(f"💶 Current price: {current_price:.2f} €")

    price_history = load_price_history()
    if price_history:
        previous_price = price_history[-1]
        print(f"📊 Last recorded price: {previous_price:.2f} €")

        if current_price < previous_price:
            print("📉 Price dropped!")
            send_email_notification(current_price, previous_price)
        elif current_price > previous_price:
            print("📈 Price increased.")
        else:
            print("➡️ Price unchanged.")
    else:
        print("🆕 No previous price recorded — initializing history.")

    # Append new price to history (keep only last 50 entries)
    price_history.append(current_price)
    price_history = price_history[-50:]
    save_price_history(price_history)
    print("💾 Price history updated.")


if __name__ == "__main__":
    main()
