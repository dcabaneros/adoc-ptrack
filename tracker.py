import requests
from bs4 import BeautifulSoup
import brotli
import gzip
from io import BytesIO
import os
from datetime import datetime
import pytz
import smtplib
import json
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# === CONFIG ===

# List of products to track
PRODUCTS = [
    {
        "name": "LEMFÖRDER 29633 03",
        "url": "https://www.autodoc.es/lemforder/7618484",
        "motointegrator_url": "https://www.motointegrator.es/productos/537834-brazo-de-control-suspension-de-ruedas-lemfoerder-29633-03-eje-delantero-izquierda-delantero",
    },
    {
        "name": "LEMFÖRDER 29634 03",
        "url": "https://www.autodoc.es/lemforder/7618485",
        "motointegrator_url": "https://www.motointegrator.es/productos/538519-brazo-de-control-suspension-de-ruedas-lemfoerder-29634-03-eje-delantero-derecha-delantero",
    },
    # Add more products here
]

# Price history file (absolute path to avoid working directory issues)
PRICE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "price_history.txt")

# Gmail credentials (from GitHub Secrets)
SENDER_EMAIL = os.getenv("EMAIL_USER")
SENDER_PASS = os.getenv("EMAIL_PASS")
RECEIVER_EMAIL = os.getenv("EMAIL_TO") or SENDER_EMAIL

# Browser headers. The original AUTODOC headers are retained, with a normal browser UA
# so the same request can also be used for Motointegrator.
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
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


# === PARSE AUTODOC PRICE ===
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
    print("🔍 AUTODOC HTML snippet (first 400 chars):")
    print(html[:400])
    raise ValueError("❌ Could not find AUTODOC price element on the page")


# === PARSE MOTOINTEGRATOR PRICE ===
def parse_price_motointegrator(html):
    soup = BeautifulSoup(html, "html.parser")

    # Prefer structured product data, which is less dependent on page layout.
    for script in soup.find_all("script", type="application/ld+json"):
        raw = script.string or script.get_text(strip=True)
        if not raw:
            continue

        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            continue

        objects = data if isinstance(data, list) else [data]
        for obj in objects:
            if not isinstance(obj, dict):
                continue

            # Some pages wrap Product objects inside @graph.
            graph = obj.get("@graph")
            if isinstance(graph, list):
                objects.extend(item for item in graph if isinstance(item, dict))

            offers = obj.get("offers")
            offers = offers if isinstance(offers, list) else [offers]

            for offer in offers:
                if not isinstance(offer, dict):
                    continue
                price = offer.get("price") or offer.get("lowPrice")
                parsed = extract_numeric_price(str(price)) if price is not None else None
                if parsed is not None:
                    return parsed

    # Fallbacks for metadata or visible price elements.
    selectors = [
        'meta[itemprop="price"]',
        'meta[property="product:price:amount"]',
        '[itemprop="price"]',
        '[data-testid*="price"]',
        '[class*="product-price"]',
        '[class*="current-price"]',
        '[class*="price-current"]',
        '[class*="price"]',
    ]

    for selector in selectors:
        for el in soup.select(selector):
            value = (
                el.get("content")
                or el.get("value")
                or el.get("data-price")
                or el.get_text(" ", strip=True)
            )
            price = extract_numeric_price(value)
            if price is not None:
                return price

    print("🔍 Motointegrator HTML snippet (first 400 chars):")
    print(html[:400])
    raise ValueError("❌ Could not find Motointegrator price element on the page")


def extract_numeric_price(text):
    """Convert a price such as '123,45 €' or '123.45' into a float."""
    if not text:
        return None

    clean = text.replace("\xa0", " ").strip()
    matches = re.findall(
        r"\d{1,3}(?:[.\s]\d{3})*(?:,\d{1,2})|\d+(?:[.,]\d{1,2})?",
        clean,
    )

    for match in matches:
        normalized = match.replace(" ", "")
        if "," in normalized:
            normalized = normalized.replace(".", "").replace(",", ".")

        try:
            price = float(normalized)
            if price > 0:
                return price
        except ValueError:
            continue

    return None


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
    timestamp = datetime.now(MADRID_TZ).strftime("%d/%m/%Y %H:%M:%S")
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


# === CHECK PRODUCT IN ONE STORE ===
def check_product(product_name, store_name, url, price_parser):
    if not url or url == "PASTE_MOTOINTEGRATOR_URL_HERE":
        print(f"⚠️ No {store_name} URL supplied for {product_name}. Skipping.")
        return

    print(f"\n🔎 Checking {product_name} at {store_name}...")

    try:
        html = fetch_html(url)
        current_price = price_parser(html)
    except Exception as e:
        print(f"⚠️ Failed to fetch/parse {product_name} at {store_name}: {e}")
        return

    # Include the store in the history key, so prices from both sites do not mix.
    history_name = f"{product_name} [{store_name}]"
    last_price = load_last_price(history_name)

    print(
        f"{history_name}: Current {current_price} €, "
        f"Last {last_price if last_price is not None else 'N/A'} €"
    )

    if last_price is not None:
        diff = current_price - last_price
        if diff < 0:
            print(f"📉 Price dropped ↓ {abs(diff):.2f} €")
            subject = f"📉 Price Drop Alert: {product_name} [{store_name}]"
            body = (
                f"{product_name} dropped at {store_name} "
                f"from {last_price} € to {current_price} €!\n\n{url}"
            )
            send_email(subject, body)
        elif diff > 0:
            print(f"📈 Price increased ↑ {diff:.2f} €")
        else:
            print("➖ Price unchanged.")
    else:
        print("🆕 First recorded price.")

    save_price(history_name, current_price)


# === MAIN ===
def main():
    for product in PRODUCTS:
        name = product["name"]

        # Original AUTODOC check.
        check_product(
            product_name=name,
            store_name="AUTODOC",
            url=product["url"],
            price_parser=parse_price,
        )

        # Additional Motointegrator check using the URL supplied in PRODUCTS.
        check_product(
            product_name=name,
            store_name="Motointegrator",
            url=product.get("motointegrator_url"),
            price_parser=parse_price_motointegrator,
        )

    print("\n✅ All products checked.")


if __name__ == "__main__":
    main()
