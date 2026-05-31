"""
main.py
-------
This is the entry point for the Telegram Deal Automation Bot.
It has been upgraded to perform REAL product scraping on live Myntra India pages.
The dummy products system has been completely removed.

It calculate prices, formats MRP and Deal prices in Indian Rupees (₹), extracts product images,
and automatically broadcasts rich photo-card deal alerts to your Telegram Channel.
Includes an HTTP port-binding background server to run 100% free on Render Web Service tier!
"""

import asyncio
import sys
import os
import re
import json
import threading
from datetime import datetime, timedelta
from http.server import SimpleHTTPRequestHandler, HTTPServer
import requests
from bs4 import BeautifulSoup
import telegram  # Imported from python-telegram-bot

# Import local configuration and safety checks
import config
import affiliate_manager

def log_event(emoji: str, level: str, msg: str):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {emoji} [{level}] {msg}")

# --- PRODUCTION PORT-BINDING SERVER FOR RENDER (FREE WEB SERVICE TIER HACK) ---
class HealthCheckHandler(SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write("<html><body><h2 style='color:#2ecc71; font-family: sans-serif;'>\n"
                             "🟢 Telegram Deal Bot is online and running successfully!</h2></body></html>".encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    # Disable standard logging in HTTP server to keep Render logs clean and readable
    def log_message(self, format, *args):
        return

def run_health_server():
    try:
        # Render will pass the port dynamically via PORT environment variable
        port = int(os.getenv("PORT", 8080))
        server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
        print(f"📡 Free Tier Port-Binder: Server running on port {port}...")
        server.serve_forever()
    except Exception as e:
        print(f"⚠️ Health Web Server Error: {e}")


# --- UTILITY CLEANING & PARSING HELPERS ---

def clean_price(price_str: str) -> float:
    """
    Cleans price strings (removes ₹, commas, spaces) and returns as float.
    """
    if not price_str:
        return 0.0
    clean_str = re.sub(r"[^\d.]", "", price_str)
    try:
        return float(clean_str)
    except ValueError:
        return 0.0


def scrape_myntra(keyword: str) -> list:
    """
    Crawls Myntra search landing pages and parses their HTML-embedded window.__myx JSON state block.
    """
    import json
    import time
    
    query_dashed = keyword.strip().lower().replace(" ", "-")
    url = f"https://www.myntra.com/{query_dashed}"
    
    log_event("📡", "website scanning", f"[Myntra] Searching keyword '{keyword}'. URL: {url}")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-IN,en;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Referer": "https://www.myntra.com/",
    }
    
    products = []
    max_retries = 3
    response = None
    
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, timeout=12)
            if response.status_code == 200:
                break
            log_event("⚠️", "website scanning", f"[Myntra] HTTP {response.status_code}. Retrying in 2s (Attempt {attempt+1}/{max_retries})...")
            time.sleep(2)
        except requests.exceptions.RequestException as e:
            log_event("⚠️", "website scanning", f"[Myntra] Request error: {e}. Retrying in 2s (Attempt {attempt+1}/{max_retries})...")
            time.sleep(2)
            
    if not response or response.status_code != 200:
        log_event("❌", "scraping blocked", f"[Myntra] Scraping blocked or failure after {max_retries} attempts (HTTP {response.status_code if response else 'None'}).")
        return []
        
    try:
        soup = BeautifulSoup(response.content, "lxml")
        match = re.search(r"window\.__myx\s*=\s*(\{.+?\});?\s*(?:window\.__INITIAL_STATE__|</script>|$)", response.text)
        if not match:
            log_event("❌", "selector missing", "[Myntra] Could not locate 'window.__myx' script block in page source.")
            return []
            
        state_data = json.loads(match.group(1))
        search_results = state_data.get("searchData", {}).get("results", {})
        product_list = search_results.get("products", [])
        
        log_event("🔎", "products found", f"[Myntra] Successfully extracted {len(product_list)} product cards from search state.")
        
        for item in product_list:
            brand = item.get("brand", "")
            product_name = item.get("productName", "")
            product_title = f"{brand} - {product_name}" if brand else product_name
            if not product_title:
                product_title = "Myntra Fashion Item"
                
            mrp = float(item.get("mrp", 0))
            sale_price = float(item.get("price", 0))
            
            # Skip products with missing prices
            if mrp <= 0 or sale_price <= 0:
                continue
                
            discount_percent = round(((mrp - sale_price) / mrp) * 100, 2)
            landing_url = item.get("landingPageUrl", "")
            product_url = f"https://www.myntra.com/{landing_url}" if landing_url else url
            
            image_url = item.get("searchImage", "")
            if image_url and image_url.startswith("http://"):
                image_url = image_url.replace("http://", "https://")
                
            products.append({
                "id": str(item.get("productId", "")),
                "name": product_title,
                "original_price": mrp,
                "sale_price": sale_price,
                "discount_percentage": discount_percent,
                "url": product_url,
                "image_url": image_url,
                "source": "Myntra"
            })
            
        return products
    except Exception as e:
        log_event("❌", "selector missing", f"[Myntra] Unexpected parsing exception: {e}")
        return []


def scrape_flipkart(keyword: str) -> list:
    """
    Crawls Flipkart search listings using requests + BeautifulSoup.
    Uses resilient multi-selector fallbacks to parse items.
    """
    import time
    
    query = keyword.strip().replace(" ", "+")
    url = f"https://www.flipkart.com/search?q={query}"
    
    log_event("📡", "website scanning", f"[Flipkart] Searching keyword '{keyword}'. URL: {url}")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
        "Referer": "https://www.google.com/",
        "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Upgrade-Insecure-Requests": "1"
    }
    
    products = []
    max_retries = 3
    response = None
    
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, timeout=12)
            if response.status_code == 200:
                break
            log_event("⚠️", "website scanning", f"[Flipkart] HTTP {response.status_code}. Retrying in 2s (Attempt {attempt+1}/{max_retries})...")
            time.sleep(2)
        except requests.exceptions.RequestException as e:
            log_event("⚠️", "website scanning", f"[Flipkart] Request error: {e}. Retrying in 2s (Attempt {attempt+1}/{max_retries})...")
            time.sleep(2)
            
    if not response or response.status_code != 200:
        log_event("❌", "scraping blocked", f"[Flipkart] Scraping blocked or failure (HTTP {response.status_code if response else 'None'}).")
        return []
        
    try:
        soup = BeautifulSoup(response.content, "lxml")
        
        # Resilient selection: div[data-id] represents product cards in search grids
        cards = soup.select("div[data-id]") or soup.select("div._1xHGtK") or soup.select("div._4ddC5M")
        if not cards:
            log_event("❌", "selector missing", "[Flipkart] Could not locate any product search cards on page (selectors missing).")
            return []
            
        log_event("🔎", "products found", f"[Flipkart] Successfully extracted {len(cards)} item cards from search source.")
        
        for card in cards[:20]:  # Check top 20 items
            info_div = card.select_one("div.p0C73x")
            if not info_div:
                continue
                
            strings = list(info_div.stripped_strings)
            if len(strings) < 3:
                continue
                
            brand = strings[0]
            # Try to get full title from the first anchor inside info_div to avoid ellipsis
            title_a = info_div.select_one("a")
            name_text = strings[1]
            if title_a and title_a.get("title"):
                name_text = title_a.get("title")
                
            product_title = f"{brand} - {name_text}" if brand else name_text
            
            # Extract prices dynamically from stripped strings
            prices_found = []
            discount_percent = 0.0
            for item in strings:
                if "₹" in item or item.strip().replace(",", "").isdigit():
                    val = clean_price(item)
                    if val > 0:
                        prices_found.append(val)
                elif "%" in item:
                    match = re.search(r"(\d+)%", item)
                    if match:
                        discount_percent = float(match.group(1))
                        
            if len(prices_found) < 2:
                if len(prices_found) == 1:
                    sale_price = prices_found[0]
                    original_price = prices_found[0]
                else:
                    continue
            else:
                sale_price = prices_found[0]
                original_price = prices_found[1]
                
            if sale_price <= 0 or original_price <= 0:
                continue
                
            # If discount percent was not matched, calculate it
            if discount_percent <= 0:
                discount_percent = round(((original_price - sale_price) / original_price) * 100, 2)
                
            # Parse URL
            href = ""
            anchors = card.select("a")
            for a in anchors:
                if a.get("href"):
                    href = a.get("href")
                    break
            if not href:
                continue
            product_url = f"https://www.flipkart.com{href}" if href.startswith("/") else href
            product_url = product_url.split("?")[0]
            
            # Parse Image URL
            img_el = card.select_one("img")
            image_url = ""
            if img_el:
                image_url = img_el.get("src") or img_el.get("data-src") or ""
                
            # Extract unique product ID
            prod_id = card.get("data-id") or ""
            if not prod_id and "pid=" in product_url:
                match = re.search(r"pid=([A-Z0-9]+)", product_url)
                if match:
                    prod_id = match.group(1)
            if not prod_id:
                prod_id = product_url.split("?")[0]
                
            products.append({
                "id": str(prod_id),
                "name": product_title,
                "original_price": original_price,
                "sale_price": sale_price,
                "discount_percentage": discount_percent,
                "url": product_url,
                "image_url": image_url,
                "source": "Flipkart"
            })
            
        return products
    except Exception as e:
        log_event("❌", "selector missing", f"[Flipkart] Unexpected parsing exception: {e}")
        return []


def scrape_amazon(keyword: str) -> list:
    """
    Crawls Amazon India search listings using requests + BeautifulSoup.
    Fails gracefully if CAPTCHA or anti-bot security blockades are served.
    """
    import time
    
    query = keyword.strip().replace(" ", "+")
    url = f"https://www.amazon.in/s?k={query}"
    
    log_event("📡", "website scanning", f"[Amazon] Searching keyword '{keyword}'. URL: {url}")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9,en-IN;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Referer": "https://www.google.com/",
    }
    
    products = []
    max_retries = 3
    response = None
    
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, timeout=12)
            if response.status_code == 200:
                # Double check for Amazon robot check page / CAPTCHA
                if "api-services-support@amazon.com" in response.text or "captcha" in response.text.lower() or "robot check" in response.text.lower():
                    log_event("⚠️", "website scanning", f"[Amazon] Served a CAPTCHA challenge (Attempt {attempt+1}/{max_retries}). Retrying in 3s...")
                    time.sleep(3)
                    continue
                break
            log_event("⚠️", "website scanning", f"[Amazon] HTTP {response.status_code} (Attempt {attempt+1}/{max_retries}). Retrying in 3s...")
            time.sleep(3)
        except requests.exceptions.RequestException as e:
            log_event("⚠️", "website scanning", f"[Amazon] Request error: {e} (Attempt {attempt+1}/{max_retries}). Retrying in 3s...")
            time.sleep(3)
            
    if not response or response.status_code != 200:
        log_event("❌", "scraping blocked", f"[Amazon] Scraping failure or blocked (HTTP {response.status_code if response else 'None'}).")
        return []
        
    # Final check for captcha pages
    if "api-services-support@amazon.com" in response.text or "captcha" in response.text.lower() or "robot check" in response.text.lower():
        log_event("❌", "scraping blocked", "[Amazon] CAPTCHA / Robot Check blockade confirmed. Skipping Amazon in this cycle.")
        return []
        
    try:
        soup = BeautifulSoup(response.content, "lxml")
        cards = soup.select('div[data-component-type="s-search-result"]')
        if not cards:
            log_event("❌", "selector missing", "[Amazon] Could not locate any product search cards on page (selectors missing).")
            return []
            
        log_event("🔎", "products found", f"[Amazon] Successfully extracted {len(cards)} item cards from search source.")
        
        for card in cards[:20]:  # Check top 20 items
            asin = card.get("data-asin") or ""
            if not asin:
                continue
                
            # Parse Title
            title_el = card.select_one("h2 a span") or card.select_one("span.a-size-base-plus") or card.select_one("span.a-size-medium")
            if not title_el:
                continue
            product_title = title_el.get_text(strip=True)
            
            # Parse URL
            href_el = card.select_one("h2 a")
            if not href_el:
                continue
            href = href_el.get("href")
            if not href:
                continue
            product_url = f"https://www.amazon.in{href}" if href.startswith("/") else href
            product_url = product_url.split("?")[0]
            
            # Parse Prices
            sale_price_el = card.select_one("span.a-price span.a-offscreen")
            original_price_el = card.select_one("span.a-price.a-text-price span.a-offscreen") or card.select_one("span.a-text-price")
            
            if not sale_price_el:
                continue
                
            sale_price = clean_price(sale_price_el.get_text(strip=True))
            original_price = clean_price(original_price_el.get_text(strip=True)) if original_price_el else sale_price
            
            # Skip if prices are missing
            if sale_price <= 0 or original_price <= 0:
                continue
                
            discount_percent = round(((original_price - sale_price) / original_price) * 100, 2)
            
            # Parse Image URL
            img_el = card.select_one("img.s-image")
            image_url = img_el.get("src") if img_el else ""
            
            products.append({
                "id": str(asin),
                "name": product_title,
                "original_price": original_price,
                "sale_price": sale_price,
                "discount_percentage": discount_percent,
                "url": product_url,
                "image_url": image_url,
                "source": "Amazon India"
            })
            
        return products
    except Exception as e:
        log_event("❌", "selector missing", f"[Amazon] Unexpected parsing exception: {e}")
        return []



# --- CORE TELEGRAM FORMATTERS ---

def format_deal_message(product: dict, discount_percent: float) -> str:
    """
    Formats a shorter, cleaner, and highly professional premium Telegram alert.
    """
    saving = int(round(product["original_price"] - product["sale_price"]))
    mrp = int(round(product["original_price"]))
    deal = int(round(product["sale_price"]))
    
    keyword = product.get("keyword", "")
    raw_tag = config.KEYWORD_TAGS.get(keyword, "HOT DEAL")
    tag = f"#{raw_tag.replace(' ', '_')}"
    
    if discount_percent >= 90.0:
        label = f"🔥 <b>MEGA DEAL ALERT ({raw_tag})</b> 🔥"
    else:
        label = f"⚡ <b>{raw_tag} ALERT</b> ⚡"
        
    # Shorter, cleaner premium layout
    message = (
        f"{label}\n\n"
        f"📦 <b>{product['name']}</b>\n\n"
        f"💰 <b>MRP:</b> <s>₹{mrp}</s> | <b>Deal Price:</b> ₹{deal}\n"
        f"🎯 <b>Discount:</b> {int(round(discount_percent))}% OFF (Save ₹{saving})\n"
        f"🏷️ <b>Category:</b> {tag}\n\n"
        f"🛒 <b>Order Here:</b>\n"
        f"👉 {product['url']}"
    )
    return message


def format_review_message(product: dict, discount_percent: float) -> str:
    """
    Formats a highly structured message specifically tailored for the PRIVATE review channel.
    Includes all metadata plus clear review/action labels.
    """
    saving = int(round(product["original_price"] - product["sale_price"]))
    mrp = int(round(product["original_price"]))
    deal = int(round(product["sale_price"]))
    
    keyword = product.get("keyword", "")
    raw_tag = config.KEYWORD_TAGS.get(keyword, "HOT DEAL")
    tag = f"#{raw_tag.replace(' ', '_')}"
    
    if discount_percent >= 90.0:
        label = f"🚨 <b>[MEGA DEAL PENDING REVIEW - {raw_tag}]</b> 🚨"
    else:
        label = f"⏳ <b>[{raw_tag} PENDING REVIEW]</b> ⏳"
        
    message = (
        f"{label}\n\n"
        f"📋 <b>Product Name:</b> {product['name']}\n"
        f"🏷️ <b>Brand/Source:</b> {product.get('source', 'Myntra')}\n"
        f"🏷️ <b>Category:</b> {tag}\n\n"
        f"💵 <b>MRP (Original Price):</b> <s>₹{mrp}</s>\n"
        f"💰 <b>Deal Price (Current Price):</b> ₹{deal}\n"
        f"📉 <b>Discount Percentage:</b> {int(round(discount_percent))}% OFF\n"
        f"💸 <b>You Save:</b> ₹{saving}\n\n"
        f"🔗 <b>Product Original URL:</b>\n"
        f"{product['url']}\n\n"
        f"📝 <b>Action Instructions:</b>\n"
        f"1. Generate your affiliate link for this product.\n"
        f"2. Forward/post the approved details to the Public Channel: {config.PUBLIC_DEALS_CHANNEL}."
    )
    return message


async def send_telegram_message(bot_client: telegram.Bot, channel_chat_id: str, message: str, image_url: str, is_dry_run: bool, product_url: str = None):
    """
    Sends the formatted message to the Telegram channel.
    Supports beautiful photo-caption card posts with inline Buy Now button and robust fallback!
    """
    # Build inline keyboard markup if a product URL is provided
    reply_markup = None
    if product_url and not is_dry_run:
        keyboard = [
            [telegram.InlineKeyboardButton("🛒 Buy Now", url=product_url)]
        ]
        reply_markup = telegram.InlineKeyboardMarkup(keyboard)

    if is_dry_run:
        print("\n📢 [DRY-RUN BROADCAST MESSAGE TO TELEGRAM]")
        print("-" * 50)
        # Strip HTML tags for dry-run terminal printing
        clean_msg = message
        clean_msg = clean_msg.replace("<span class=\"tg-spoiler\">", "").replace("</span>", "")
        clean_msg = clean_msg.replace("<b>", "").replace("</b>", "")
        clean_msg = clean_msg.replace("<s>", "~").replace("</s>", "~")
        clean_msg = clean_msg.replace("<i>", "").replace("</i>", "")
        print(clean_msg)
        if image_url:
            print(f"📸 Image attached: {image_url}")
        if product_url:
            print(f"🔘 Button attached: [🛒 Buy Now -> {product_url}]")
        print("-" * 50)
    else:
        # Broadcast live message. If image exists, send a beautiful photo-caption card
        if image_url and image_url.startswith("http"):
            try:
                print(f"📸 [Telegram Photo Upload] Attempting to send product image to channel: {image_url}...")
                await bot_client.send_photo(
                    chat_id=channel_chat_id,
                    photo=image_url,
                    caption=message,
                    parse_mode="HTML",
                    reply_markup=reply_markup
                )
                print(f"✅ [Telegram Photo Upload SUCCESS] Product image published successfully to channel {channel_chat_id}!")
            except Exception as photo_err:
                print(f"⚠️ [Telegram Photo Upload FAILURE] Image upload failed ({photo_err}). Falling back to text message...")
                # Fallback to text message
                await bot_client.send_message(
                    chat_id=channel_chat_id,
                    text=message,
                    parse_mode="HTML",
                    reply_markup=reply_markup
                )
        else:
            print("ℹ️ [Telegram Dispatch] No image URL provided or invalid format. Sending text-only message...")
            await bot_client.send_message(
                chat_id=channel_chat_id,
                text=message,
                parse_mode="HTML",
                reply_markup=reply_markup
            )


# --- PERSISTENT DUPLICATE FILTER DATABASE ---

def load_posted_deals() -> set:
    """
    Loads previously posted deal IDs or URLs from a local JSON file.
    If the file does not exist, returns an empty set.
    """
    db_file = getattr(config, "DUPLICATE_DB_FILE", "posted_products.json")
    if not os.path.exists(db_file):
        return set()
    try:
        with open(db_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Ensure we return a set of strings for extremely fast lookup
            return set(str(item) for item in data)
    except Exception as e:
        print(f"⚠️ Error loading persistent duplicates database: {e}")
        return set()

def save_posted_deal(product_id: str):
    """
    Appends a new successfully published product ID/URL to our local JSON database.
    """
    db_file = getattr(config, "DUPLICATE_DB_FILE", "posted_products.json")
    posted = list(load_posted_deals())
    if product_id not in posted:
        posted.append(product_id)
        try:
            with open(db_file, "w", encoding="utf-8") as f:
                json.dump(posted, f, indent=4)
        except Exception as e:
            print(f"⚠️ Error writing to duplicates database: {e}")


# --- MAIN WORKFLOW SCANNERS ---

async def scan_for_deals(bot_client: telegram.Bot, channel_chat_id: str, is_dry_run: bool):
    """
    Loops through the configured keywords, crawls their live search result pages from
    Myntra, Flipkart, and Amazon India, evaluates all found products, and automatically
    pushes active deals (discount >= DISCOUNT_THRESHOLD) to Telegram.
    Includes rate limits, persistent duplicate filtering, dynamic category tags, and random delays.
    """
    import random
    
    try:
        # 1. Load already posted deals from the JSON database and settings
        posted_deals = load_posted_deals()
        max_posts_per_scan = getattr(config, "MAX_DEALS_PER_SCAN", 5)
        delay_min = getattr(config, "REQUEST_DELAY_MIN", 3.0)
        delay_max = getattr(config, "REQUEST_DELAY_MAX", 8.0)
        
        log_event("🔄", "crawler started", "Starting live multi-site deal scan...")
        log_event("📊", "config info", f"Settings: Category thresholds | Rate Limit: {max_posts_per_scan} posts/scan")
        
        total_products_scraped = 0
        deals_detected_count = 0
        deals_published_count = 0
        posts_in_this_scan = 0
        affiliate_generations_in_scan = 0
        max_scrape_retries = 2
        
        for i, (keyword, category_name) in enumerate(config.KEYWORDS_WITH_CATEGORIES):
            min_discount = config.THRESHOLDS.get(category_name, 50.0)
            log_event("🔍", "category started", f"Searching for: '{keyword.upper()}' ({category_name}) | Threshold: {min_discount}%")
            
            keyword_products = []
            
            # --- Store 1: Myntra ---
            myntra_items = []
            for attempt in range(max_scrape_retries):
                log_event("📡", "website scanning", f"[Myntra] keyword: '{keyword}' (Attempt {attempt+1}/{max_scrape_retries})")
                try:
                    myntra_items = scrape_myntra(keyword)
                    if myntra_items:
                        log_event("🔎", "products found", f"[Myntra] Successfully extracted {len(myntra_items)} products.")
                        break
                    else:
                        log_event("⚠️", "scraping warning", "[Myntra] Scraping returned 0 products. Retrying after delay...")
                except Exception as e:
                    log_event("❌", "scraping error", f"[Myntra] Scraping attempt error: {e}")
                if attempt < max_scrape_retries - 1:
                    await asyncio.sleep(2)
            keyword_products.extend(myntra_items)
            
            # --- Store 2: Flipkart ---
            flipkart_items = []
            for attempt in range(max_scrape_retries):
                log_event("📡", "website scanning", f"[Flipkart] keyword: '{keyword}' (Attempt {attempt+1}/{max_scrape_retries})")
                try:
                    flipkart_items = scrape_flipkart(keyword)
                    if flipkart_items:
                        log_event("🔎", "products found", f"[Flipkart] Successfully extracted {len(flipkart_items)} products.")
                        break
                    else:
                        log_event("⚠️", "scraping warning", "[Flipkart] Scraping returned 0 products. Retrying...")
                except Exception as e:
                    log_event("❌", "scraping error", f"[Flipkart] Scraping attempt error: {e}")
            keyword_products.extend(flipkart_items)
            
            product_count = len(keyword_products)
            total_products_scraped += product_count
            
            if not keyword_products:
                log_event("⚠️", "no deals found", f"Scraping returned 0 items from all stores for keyword: '{keyword}'")
                continue
                
            log_event("🚀", "scrape completed", f"Aggregated SUCCESS! Found {product_count} total products for '{keyword}'.")
            
            # Iterate and evaluate all combined crawled products
            keyword_deals_count = 0
            for idx, product in enumerate(keyword_products):
                product["keyword"] = keyword  # Map keyword to product for tag formatting
                discount = product["discount_percentage"]
                price = product["sale_price"]
                title = product.get("name", "").strip()
                image_url = product.get("image_url", "").strip()
                product_key = product.get("id") or product.get("url")
                store_name = product.get("source", "Unknown Store")
                
                # Print periodic progress logs
                if idx % 10 == 0 or discount >= config.DISCOUNT_THRESHOLD:
                    log_event("📊", "PROGRESS", f"[{store_name}] [{idx+1:02d}/{product_count:02d}] {product['name'][:30]}... | Price: ₹{product['sale_price']} | MRP: ₹{product['original_price']} | Discount: {discount}%")
                
                # Production-safe Quality Filters Check
                is_quality_ok = True
                low_quality_reason = ""
                
                if discount < config.DISCOUNT_THRESHOLD:
                    is_quality_ok = False
                    low_quality_reason = f"Discount ({discount}%) is below threshold ({config.DISCOUNT_THRESHOLD}%)"
                elif not (config.MIN_PRICE <= price <= config.MAX_PRICE):
                    is_quality_ok = False
                    low_quality_reason = f"Price (₹{price}) is not between ₹{config.MIN_PRICE} and ₹{config.MAX_PRICE}"
                elif not title:
                    is_quality_ok = False
                    low_quality_reason = "Product title is empty"
                elif not image_url or not image_url.startswith("http"):
                    is_quality_ok = False
                    low_quality_reason = "Image URL is missing or invalid"
                    
                if not is_quality_ok:
                    # Log low quality skipped as requested
                    log_event("⚠️", "low quality skipped", f"'{title[:30]}' from {store_name}. Reason: {low_quality_reason}")
                    continue
                    
                deals_detected_count += 1
                
                # Duplicate Check
                if product_key in posted_deals:
                    # Log duplicate skipped as requested
                    log_event("🛡️", "duplicate skipped", f"'{title[:30]}' (ID/URL: {product_key}) has already been sent. Skipping...")
                    continue
                
                # Classify the deal
                if discount >= 90.0:
                    deal_type = "MEGA DEAL"
                else:
                    deal_type = "HOT DEAL"
                    
                # Rate Limiting (Max 3 Telegram posts per scan)
                if posts_in_this_scan >= max_posts_per_scan:
                    log_event("⚠️", "RATE_LIMIT", f"Skipping '{product['name'][:30]}' ({discount}% off) from {store_name} to prevent flooding (max {max_posts_per_scan} posts reached).")
                    continue
                
                keyword_deals_count += 1
                log_event("🔥", "high discount detected", f"[{store_name}] {product['name'][:35]} has a {discount}% discount!")
                
                # Log "product found" as requested
                log_event("📢", "product found", f"'{product['name']}' from {store_name} ({discount}% off)")
                
                affiliate_success = False
                affiliate_url = product["url"]
                
                # Generate affiliate link using Playwright and EarnKaro (Myntra products only, initially)
                if config.USE_AFFILIATE_LINKS and config.is_earnkaro_configured():
                    if product.get("source") == "Myntra":
                        max_gens = getattr(config, "MAX_AFFILIATE_GENERATIONS_PER_SCAN", 3)
                        if affiliate_generations_in_scan < max_gens:
                            # Log "affiliate generation started" as requested
                            log_event("🔗", "affiliate generation started", f"for URL: {product['url']}")
                            try:
                                converted_url = await affiliate_manager.generate_affiliate_link(product["url"])
                                
                                # Added delay between affiliate generations: 20 to 40 seconds
                                post_generation_delay = random.uniform(20, 40)
                                log_event("⏳", "DELAY", f"Delay active between affiliate generations: Waiting {post_generation_delay:.2f} seconds...")
                                await asyncio.sleep(post_generation_delay)
                                
                                if converted_url and converted_url != product["url"]:
                                    affiliate_url = converted_url
                                    affiliate_success = True
                                    affiliate_generations_in_scan += 1
                                    # Log "affiliate link generated" as requested
                                    log_event("✅", "affiliate link generated successfully", f"{converted_url}")
                                else:
                                    log_event("⚠️", "AFFILIATE_WARN", "Link conversion returned original link (no changes).")
                            except Exception as aff_err:
                                # Log error as requested
                                log_event("❌", "Playwright failure", f"Affiliate generation failed: {aff_err}")
                        else:
                            log_event("⚠️", "AFFILIATE_LIMIT", f"Maximum affiliate generations per scan reached ({max_gens}/{max_gens}).")
                    else:
                        log_event("ℹ️", "AFFILIATE_SKIP", f"Skipping conversion: Source '{product.get('source')}' is not Myntra.")
                else:
                    log_event("ℹ️", "AFFILIATE_DISABLED", "Affiliate links are disabled or not configured.")
                    
                # Handle failure/fallback or skip posting based on config
                if config.USE_AFFILIATE_LINKS and product.get("source") == "Myntra" and not affiliate_success:
                    # Log affiliate generation failure as requested & skip posting
                    log_event("❌", "affiliate generation failed", f"for URL: {product['url']}. Skipping deal posting.")
                    continue
                else:
                    # Update URL to the converted affiliate URL or original
                    product["url"] = affiliate_url

                # Build professional telegram card for private review
                deal_message = format_review_message(product, discount)
                
                # Automatically send deal to Telegram
                try:
                    await send_telegram_message(
                        bot_client=bot_client,
                        channel_chat_id=channel_chat_id,
                        message=deal_message,
                        image_url=product["image_url"],
                        is_dry_run=is_dry_run,
                        product_url=product["url"]
                    )
                    deals_published_count += 1
                    posts_in_this_scan += 1
                    
                    # Record to persistent duplicates database immediately
                    save_posted_deal(product_key)
                    posted_deals.add(product_key)
                    
                    # Log "Telegram post sent" as requested
                    log_event("🎉", "Telegram post sent successfully", f"to channel {channel_chat_id}")
                    
                    # Polite random delay after sending Telegram message to avoid rate limits
                    post_delay = random.uniform(delay_min, delay_max)
                    log_event("⏳", "TELEGRAM_DELAY", f"Waiting {post_delay:.2f} seconds before continuing...")
                    await asyncio.sleep(post_delay)
                except Exception as e:
                    # Log Telegram post failure as requested
                    log_event("❌", "Telegram post sent failed", f"{e}")
                        
            log_event("✨", "CATEGORY_COMPLETE", f"Category '{keyword}' scan complete. Published {keyword_deals_count} new deals.")
            
        log_event("📊", "SCAN_SUMMARY", "--- FINAL SCAN SUMMARY ---")
        log_event("📈", "total products scanned", f"{total_products_scraped}")
        log_event("🎯", "total qualifying deals", f"{deals_detected_count}")
        log_event("🔗", "total affiliate links generated", f"{affiliate_generations_in_scan}")
        log_event("🎉", "total Telegram posts sent", f"{posts_in_this_scan}")
        print(f"============================================================")
        
    except Exception as e:
        print(f"\n❌ [GLOBAL ERROR] Critical failure inside deal scan handler: {e}")
        print("Please check your network environment, server connections, or selector status!")


# --- MAIN RUNNER & SCHEDULER LOOP ---

async def main():
    log_event("🤖", "bot startup", "Deal Automation Bot initialized successfully.")
    log_event("⚙️", "bot startup", "MODE: Render Free Web Service (Lightweight Daemon)")
    
    # Recreate the EarnKaro session file dynamically if available in environment variables (Render/Cloud support)
    affiliate_manager.restore_session_from_env()
    
    # Start Render Free Web Service port-binding health server in the background
    log_event("📡", "port binder", "Launching background TCP port-binding server for Render health checks...")
    threading.Thread(target=run_health_server, daemon=True).start()
    
    # Check if credentials are configured
    is_live_ready = config.is_configured()
    
    bot_client = None
    private_channel = None
    public_channel = None
    
    if is_live_ready:
        log_event("🟢", "config status", "Credentials configured! Starting in LIVE mode.")
        bot_client = telegram.Bot(token=config.BOT_TOKEN)
        private_channel = config.PRIVATE_REVIEW_CHANNEL
        public_channel = config.PUBLIC_DEALS_CHANNEL
        
        # Automatically send a startup connection test message to the private review channel
        log_event("📨", "telegram", f"Sending test connection message to Private Review Channel ({private_channel})...")
        try:
            startup_test_msg = (
                "🤖 <b>Bot Connection Successful!</b>\n\n"
                "The Myntra Live-Crawler Deal Automation Bot is now online in <b>Review Workflow Mode</b>!\n"
                "It will scan live Myntra search results for key categories and automatically post deals to this channel for your manual review and approval."
            )
            await bot_client.send_message(
                chat_id=private_channel,
                text=startup_test_msg,
                parse_mode="HTML"
            )
            log_event("✅", "telegram", "Test connection message sent successfully!")
        except Exception as e:
            log_event("❌", "Telegram failure", f"Failed to send startup message: {e}")
            log_event("⚠️", "Telegram warning", "Please verify your token is correct and bot is added as Admin.")
            log_event("⚠️", "Telegram warning", "Switching back to Dry-Run mode to prevent program crash...\n")
            is_live_ready = False
            
    if not is_live_ready:
        log_event("🟡", "config status", "RUNNING IN 'DRY-RUN DEMO MODE'")
        log_event("ℹ️", "config status", "This allows you to see how the bot behaves without needing actual Telegram tokens!")
        config.print_configuration_help()
        bot_client = None
        private_channel = None
        public_channel = None

    # --- Scheduler Continuous Loop (Runs every SCAN_INTERVAL minutes) ---
    scan_interval = getattr(config, "SCAN_INTERVAL", 5)
    interval_seconds = scan_interval * 60
    
    log_event("🔄", "scheduler", f"Scheduler active. Running deal scanning loop every {scan_interval} minutes.")
    
    try:
        while True:
            scan_start = datetime.now()
            log_event("⏰", "scan started", "--- SCAN CYCLE STARTED ---")
            
            # Run the deal finder logic
            await scan_for_deals(bot_client, private_channel, is_dry_run=(not is_live_ready))
            
            scan_end = datetime.now()
            duration = scan_end - scan_start
            next_run = scan_end + timedelta(seconds=interval_seconds)
            
            log_event("⏰", "scan completed", f"Cycle completed. Duration: {duration.total_seconds():.2f} seconds.")
            log_event("⏳", "scheduler", f"Sleeping for {scan_interval} minutes.")
            log_event("📅", "scheduler", f"Next scheduled scan cycle at: {next_run.strftime('%Y-%m-%d %H:%M:%S')}")
            log_event("ℹ️", "scheduler", "Press Ctrl+C to stop the bot...")
            
            await asyncio.sleep(interval_seconds)
            
    except KeyboardInterrupt:
        log_event("🛑", "scheduler", "Bot stopped manually by user. Goodbye!")
    except Exception as e:
        log_event("❌", "scheduler", f"Unexpected loop error encountered: {e}")

if __name__ == "__main__":
    # Ensure correct asyncio loop execution across platforms
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Bot shutdown cleanly.")
        sys.exit(0)
