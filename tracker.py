import requests
from bs4 import BeautifulSoup
import brotli
import gzip
from io import BytesIO
import os
import json
from datetime import datetime

URL = "https://www.autodoc.es/lemforder/1272015"
PRICE_FILE = "price_history.json"

# Simulate an iPhone/iOS Autodoc app request
HEADERS = {
    "User-Agent": "Autodoc/2.6.1 (iPhone; iOS 17.5; Scale/3.00)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Referer": "https://www.autodoc.es/",
}


def fetch_html(url):
    """Fetch page HTML with Brotli/gzip decoding."""
    print(f"Fetching {url} with iOS headers...")
    response = requests.get(url, headers=HEADERS, timeout=15)
    response.raise_for_status()

    encoding = response.headers.get("Content-Encoding", "")
    if "br" in encoding:
        html = brotli.decompress(response.content).decode("utf-8", errors="ignore")
    elif "gzip" in encoding:
        buf = BytesIO(response.content)
        with gzip.GzipFile(fileobj=buf) as f:
            html = f.read().decode("utf-8", errors="ignore")
    else:
        html = response.text

    return html


def parse_price(html):
    """Extract current price from the HTML."""
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


def load_last_price():
    """Load last stored price."""
    if os.path.exists(PRICE_FILE):
        with open(PRICE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if data and isinstance(data, list):
                return data[-1]["price"]
    return None


def save_price(price):
    """Save new price with timestamp."""
    data = []
    if os.path.exists(PRICE_FILE):
        with open(PRICE_FILE, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                data = []

    data.append({"timestamp": datetime.now().isoformat(), "price": price})
    with open(PRICE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def main():
    html = fetch_html(URL)
    current_price = parse_price(html)
    last_price = load_last_price()

    print(f"💰 Current price: {current_price} €")
    if last_price is not None:
        print(f"📈 Last recorded price: {last_price} €")

        if current_price < last_price:
            print(f"📉 Price dropped! ↓ {last_price - current_price:.2f} €")
        elif current_price > last_price:
            print(f"📈 Price increased ↑ {current_price - last_price:.2f} €")
        else:
            print("➖ Price unchanged.")
    else:
        print("🆕 First recorded price.")

    save_price(current_price)
    print("✅ Price history updated.")


if __name__ == "__main__":
    main()
