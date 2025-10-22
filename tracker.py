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

# iOS Autodoc app headers (simulate real mobile app)
HEADERS = {
    "User-Agent": "Autodoc/2.6.1 (iPhone; iOS 17.5; Scale/3.00)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Referer": "https://www.autodoc.es/",
}


def fetch_html(url):
    """Fetch page HTML and handle Brotli/gzip decoding robustly."""
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
                print("⚠️ Brotli decompression failed — falling back to plain text.")
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


def load_last_price():
    """Load the last recorded price from JSON."""
    if os.path.exists(PRICE_FILE):
        with open(PRICE_FILE, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
                if isinstance(data, list) and data:
                    return data[-1]["price"]
            except json.JSONDecodeError:
                pass
    return None


def save_price(price):
    """Append a new price to the local history."""
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
            print(f"📉 Price dropped ↓ {last_price - current_price:.2f} €")
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
