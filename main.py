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
    
    print(f"\n📡 Crawling Myntra Search Page for keyword '{keyword}':")
    print(f"🔗 URL: {url}")
    
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
            print(f"   ⚠️ Myntra returned HTTP {response.status_code}. Retrying in 2s (Attempt {attempt+1}/{max_retries})...")
            time.sleep(2)
        except requests.exceptions.RequestException as e:
            print(f"   ⚠️ Myntra request error: {e}. Retrying in 2s (Attempt {attempt+1}/{max_retries})...")
            time.sleep(2)
            
    if not response or response.status_code != 200:
        print(f"   ❌ Myntra scraping failure after {max_retries} attempts.")
        return []
        
    try:
        soup = BeautifulSoup(response.content, "lxml")
        match = re.search(r"window\.__myx\s*=\s*(\{.+?\});?\s*(?:window\.__INITIAL_STATE__|</script>|$)", response.text)
        if not match:
            print("   ❌ Error: Could not locate window.__myx JSON script tag in Myntra page source.")
            return []
            
        state_data = json.loads(match.group(1))
        search_results = state_data.get("searchData", {}).get("results", {})
        product_list = search_results.get("products", [])
        
        print(f"   🔎 Myntra: Found {len(product_list)} products in search results.")
        
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
        print(f"   ❌ Unexpected Myntra Scraper Error: {e}")
        return []


def scrape_flipkart(keyword: str) -> list:
    """
    Crawls Flipkart search listings using requests + BeautifulSoup.
    Uses resilient multi-selector fallbacks to parse items.
    """
    import time
    
    query = keyword.strip().replace(" ", "+")
    url = f"https://www.flipkart.com/search?q={query}"
    
    print(f"\n📡 Crawling Flipkart Search Page for keyword '{keyword}':")
    print(f"🔗 URL: {url}")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-IN,en;q=0.9,en-US;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Referer": "https://www.flipkart.com/",
    }
    
    products = []
    max_retries = 3
    response = None
    
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, timeout=12)
            if response.status_code == 200:
                break
            print(f"   ⚠️ Flipkart returned HTTP {response.status_code}. Retrying in 2s (Attempt {attempt+1}/{max_retries})...")
            time.sleep(2)
        except requests.exceptions.RequestException as e:
            print(f"   ⚠️ Flipkart request error: {e}. Retrying in 2s (Attempt {attempt+1}/{max_retries})...")
            time.sleep(2)
            
    if not response or response.status_code != 200:
        print(f"   ❌ Flipkart scraping failure or anti-bot blockade (HTTP {response.status_code if response else 'None'}). Skipping...")
        return []
        
    try:
        soup = BeautifulSoup(response.content, "lxml")
        
        # Resilient selection: div[data-id] represents product cards in search grids
        cards = soup.select("div[data-id]") or soup.select("div._1xHGtK") or soup.select("div._4ddC5M")
        print(f"   🔎 Flipkart: Found {len(cards)} item cards in search source.")
        
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
        print(f"   ❌ Unexpected Flipkart Scraper Error: {e}")
        return []


def scrape_amazon(keyword: str) -> list:
    """
    Crawls Amazon India search listings using requests + BeautifulSoup.
    Fails gracefully if CAPTCHA or anti-bot security blockades are served.
    """
    import time
    
    query = keyword.strip().replace(" ", "+")
    url = f"https://www.amazon.in/s?k={query}"
    
    print(f"\n📡 Crawling Amazon India Search Page for keyword '{keyword}':")
    print(f"🔗 URL: {url}")
    
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
                    print(f"   ⚠️ Amazon served a CAPTCHA challenge (Attempt {attempt+1}/{max_retries}). Retrying with sleep...")
                    time.sleep(3)
                    continue
                break
            print(f"   ⚠️ Amazon returned HTTP {response.status_code} (Attempt {attempt+1}/{max_retries})...")
            time.sleep(3)
        except requests.exceptions.RequestException as e:
            print(f"   ⚠️ Amazon request error: {e} (Attempt {attempt+1}/{max_retries})...")
            time.sleep(3)
            
    if not response or response.status_code != 200:
        print(f"   ❌ Amazon scraping failure or anti-bot blockade (HTTP {response.status_code if response else 'None'}). Skipping...")
        return []
        
    # Final check for captcha pages
    if "api-services-support@amazon.com" in response.text or "captcha" in response.text.lower() or "robot check" in response.text.lower():
        print("   ⚠️ [Amazon] CAPTCHA / Robot Check blockade confirmed. Skipping Amazon in this cycle.")
        return []
        
    try:
        soup = BeautifulSoup(response.content, "lxml")
        cards = soup.select('div[data-component-type="s-search-result"]')
        print(f"   🔎 Amazon: Found {len(cards)} item cards in search source.")
        
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
        print(f"   ❌ Unexpected Amazon Scraper Error: {e}")
        return []



# --- CORE TELEGRAM FORMATTERS ---

def format_deal_message(product: dict, discount_percent: float) -> str:
    """
    Formats a shorter, cleaner, and highly professional premium Telegram alert.
    Categorizes dynamically:
    - 90%+ = MEGA DEAL
    - 80%+ = HOT DEAL
    """
    saving = int(round(product["original_price"] - product["sale_price"]))
    mrp = int(round(product["original_price"]))
    deal = int(round(product["sale_price"]))
    
    # Determine the category label based on discount percentage
    if discount_percent >= 90.0:
        label = "🔥 <b>MEGA DEAL ALERT</b> 🔥"
    else:
        label = "⚡ <b>HOT DEAL ALERT</b> ⚡"
        
    # Shorter, cleaner premium layout
    message = (
        f"{label}\n\n"
        f"📦 <b>{product['name']}</b>\n\n"
        f"💰 <b>MRP:</b> <s>₹{mrp}</s> | <b>Deal Price:</b> ₹{deal}\n"
        f"🎯 <b>Discount:</b> {int(round(discount_percent))}% OFF (Save ₹{saving})\n\n"
        f"🛒 <b>Order Here:</b>\n"
        f"👉 {product['url']}"
    )
    return message


async def send_telegram_message(bot_client: telegram.Bot, channel_chat_id: str, message: str, image_url: str, is_dry_run: bool):
    """
    Sends the formatted message to the Telegram channel.
    Supports photo-embedded card layouts if a product photo is successfully scraped!
    """
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
        print("-" * 50)
    else:
        # Broadcast live message. If image exists, send a beautiful photo-caption card
        if image_url and image_url.startswith("http"):
            await bot_client.send_photo(
                chat_id=channel_chat_id,
                photo=image_url,
                caption=message,
                parse_mode="HTML"
            )
        else:
            await bot_client.send_message(
                chat_id=channel_chat_id,
                text=message,
                parse_mode="HTML"
            )


# --- PERSISTENT DUPLICATE FILTER DATABASE ---

def load_posted_deals() -> set:
    """
    Loads previously posted deal IDs or URLs from a local JSON file.
    If the file does not exist, returns an empty set.
    """
    db_file = getattr(config, "DUPLICATE_DB_FILE", "posted_deals.json")
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
    db_file = getattr(config, "DUPLICATE_DB_FILE", "posted_deals.json")
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
        min_discount = getattr(config, "DISCOUNT_THRESHOLD", 80.0)
        max_posts_per_scan = getattr(config, "MAX_DEALS_PER_SCAN", 5)
        delay_min = getattr(config, "REQUEST_DELAY_MIN", 3.0)
        delay_max = getattr(config, "REQUEST_DELAY_MAX", 8.0)
        
        print(f"\n============================================================")
        print(f"🔄 [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Starting live multi-site deal scan...")
        print(f"📊 Settings: Threshold >= {min_discount}% | Rate Limit: {max_posts_per_scan} posts/scan")
        print(f"============================================================")
        
        total_products_scraped = 0
        deals_detected_count = 0
        deals_published_count = 0
        posts_in_this_scan = 0
        max_scrape_retries = 2
        
        for i, keyword in enumerate(config.KEYWORDS):
            print(f"\n🔍 [Category {i+1}/{len(config.KEYWORDS)}] Searching for: '{keyword.upper()}' across all stores")
            
            keyword_products = []
            
            # --- Store 1: Myntra ---
            myntra_items = []
            for attempt in range(max_scrape_retries):
                print(f"   📡 [Myntra Scrape] Starting website scan for '{keyword}' (Attempt {attempt+1}/{max_scrape_retries})...")
                try:
                    myntra_items = scrape_myntra(keyword)
                    if myntra_items:
                        print(f"      ✅ Myntra SUCCESS: Found {len(myntra_items)} products.")
                        break
                    else:
                        print(f"      ⚠️ Myntra returned 0 products. Retrying after delay...")
                except Exception as e:
                    print(f"      ❌ Myntra scraping attempt error: {e}")
                if attempt < max_scrape_retries - 1:
                    await asyncio.sleep(2)
            keyword_products.extend(myntra_items)
            
            # --- Store 2: Flipkart (Disabled for Free-Tier Web Service lightweight scan) ---
            # flipkart_items = []
            # for attempt in range(max_scrape_retries):
            #     print(f"   📡 [Flipkart Scrape] Starting website scan for '{keyword}' (Attempt {attempt+1}/{max_scrape_retries})...")
            #     try:
            #         flipkart_items = scrape_flipkart(keyword)
            #         if flipkart_items:
            #             print(f"      ✅ Flipkart SUCCESS: Found {len(flipkart_items)} products.")
            #             break
            #     except Exception as e:
            #         print(f"      ❌ Flipkart scraping attempt error: {e}")
            # keyword_products.extend(flipkart_items)
            
            # --- Store 3: Amazon India (Disabled for Free-Tier Web Service lightweight scan) ---
            # amazon_items = []
            # for attempt in range(max_scrape_retries):
            #     print(f"   📡 [Amazon Scrape] Starting website scan for '{keyword}' (Attempt {attempt+1}/{max_scrape_retries})...")
            #     try:
            #         amazon_items = scrape_amazon(keyword)
            #         if amazon_items:
            #             print(f"      ✅ Amazon SUCCESS: Found {len(amazon_items)} products.")
            #             break
            #     except Exception as e:
            #         print(f"      ❌ Amazon scraping attempt error: {e}")
            # keyword_products.extend(amazon_items)
            
            product_count = len(keyword_products)
            total_products_scraped += product_count
            
            if not keyword_products:
                print(f"⚠️ Scraping returned 0 items from all stores for keyword: '{keyword}'")
                continue
                
            print(f"   🚀 Aggregated SUCCESS! Found {product_count} total products for '{keyword}'.")
            
            # Iterate and evaluate all combined crawled products
            keyword_deals_count = 0
            for idx, product in enumerate(keyword_products):
                discount = product["discount_percentage"]
                product_key = product.get("id") or product.get("url")
                store_name = product.get("source", "Unknown Store")
                
                # Print periodic progress logs
                if idx % 10 == 0 or discount >= min_discount:
                    print(f"   • [{store_name}] [{idx+1:02d}/{product_count:02d}] {product['name'][:30]}... | Price: ₹{product['sale_price']} | MRP: ₹{product['original_price']} | Discount: {discount}%")
                    
                # Filter criteria 1: Must be >= DISCOUNT_THRESHOLD discount
                if discount >= min_discount:
                    deals_detected_count += 1
                    
                    # Filter criteria 2: Duplicate check
                    if product_key in posted_deals:
                        print(f"     🛡️ [DUPLICATE FILTERED] '{product['name'][:30]}' (ID/ASIN: {product_key}) has already been sent. Skipping...")
                        continue
                    
                    # Classify the deal
                    if discount >= 90.0:
                        category = "MEGA DEAL"
                    else:
                        category = "HOT DEAL"
                        
                    # Filter criteria 3: Rate Limiting (Max 5 Telegram posts per scan)
                    if posts_in_this_scan >= max_posts_per_scan:
                        print(f"     ⚠️ [RATE LIMIT MET] Skipping '{product['name'][:30]}' ({discount}% off) from {store_name} to prevent flooding (max {max_posts_per_scan} posts reached).")
                        continue
                    
                    keyword_deals_count += 1
                    print(f"     🔥 {category} DETECTED: [{store_name}] {product['name'][:35]} has a {discount}% discount!")
                    
                    # Build professional telegram card
                    deal_message = format_deal_message(product, discount)
                    deal_message += f"\n🏪 <b>Store:</b> {store_name}"
                    
                    # Automatically send deal to Telegram
                    try:
                        await send_telegram_message(
                            bot_client=bot_client,
                            channel_chat_id=channel_chat_id,
                            message=deal_message,
                            image_url=product["image_url"],
                            is_dry_run=is_dry_run
                        )
                        deals_published_count += 1
                        posts_in_this_scan += 1
                        
                        # Record to persistent duplicates database immediately
                        save_posted_deal(product_key)
                        posted_deals.add(product_key)
                        
                        print(f"     🎉 [TELEGRAM SEND SUCCESS] Published {category} card to Telegram.")
                        
                        # Polite random delay after sending Telegram message to avoid rate limits
                        post_delay = random.uniform(delay_min, delay_max)
                        print(f"     ⏳ Waiting {post_delay:.2f} seconds before continuing...")
                        await asyncio.sleep(post_delay)
                    except Exception as e:
                        print(f"     ❌ [TELEGRAM SEND FAILURE] Failed to send Telegram card: {e}")
                        
            print(f"   ✨ Category '{keyword}' scan complete. Published {keyword_deals_count} new deals.")
            
        print(f"\n============================================================")
        print(f"📊 SUMMARY OF WORKFLOW SCAN:")
        print(f"   • Total Products Checked: {total_products_scraped}")
        print(f"   • Total Hot Deals Detected (>= {min_discount}%): {deals_detected_count}")
        if deals_detected_count == 0:
            print(f"   • ℹ️ Log: No products matching >= {min_discount}% discount were found during this scan.")
        print(f"   • Successfully Broadcasted This Scan: {posts_in_this_scan}")
        print(f"   • Cumulative Deals Sent in Session: {deals_published_count}")
        print(f"============================================================")
        
    except Exception as e:
        print(f"\n❌ [GLOBAL ERROR] Critical failure inside deal scan handler: {e}")
        print("Please check your network environment, server connections, or selector status!")


# --- MAIN RUNNER & SCHEDULER LOOP ---

async def main():
    print("=" * 60)
    print("🤖 TELEGRAM DEAL AUTOMATION BOT INITIALIZED 🤖")
    print("⚙️ MODE: Render Free Web Service (Lightweight Daemon)")
    print("=" * 60)
    
    # Start Render Free Web Service port-binding health server in the background
    print("📡 Launching background TCP port-binding server for Render health checks...")
    threading.Thread(target=run_health_server, daemon=True).start()
    
    # Check if credentials are configured
    is_live_ready = config.is_configured()
    
    bot_client = None
    channel_id = None
    
    if is_live_ready:
        print("🟢 STATUS: Credentials configured! Starting in LIVE mode.")
        bot_client = telegram.Bot(token=config.BOT_TOKEN)
        channel_id = config.CHANNEL_USERNAME
        
        # Automatically send a startup connection test message to the channel
        print("📨 Sending test connection message to your channel...")
        try:
            startup_test_msg = (
                "🤖 <b>Bot Connection Successful!</b>\n\n"
                "The Myntra Live-Crawler Deal Automation Bot is now online!\n"
                "It will scan live Myntra search results for key categories and automatically post deals with discounts >= 80%!"
            )
            await bot_client.send_message(
                chat_id=channel_id,
                text=startup_test_msg,
                parse_mode="HTML"
            )
            print("✅ Test connection message sent successfully!")
        except Exception as e:
            print(f"❌ Failed to send startup message: {e}")
            print("Please double check that:")
            print("1. Your Bot Token is correct.")
            print(f"2. The bot is added as an Administrator to the channel {config.CHANNEL_USERNAME}.")
            print("Switching back to Dry-Run mode to prevent program crash...\n")
            is_live_ready = False
            
    if not is_live_ready:
        print("🟡 STATUS: RUNNING IN 'DRY-RUN DEMO MODE'")
        print("This allows you to see how the bot behaves without needing actual Telegram tokens!")
        config.print_configuration_help()
        bot_client = None
        channel_id = None

    # --- Scheduler Continuous Loop (Runs every SCAN_INTERVAL minutes) ---
    scan_interval = getattr(config, "SCAN_INTERVAL", 5)
    interval_seconds = scan_interval * 60
    
    print(f"\n🔄 Scheduler active. Running deal scanning loop every {scan_interval} minutes.")
    
    try:
        while True:
            scan_start = datetime.now()
            print(f"\n⏰ [{scan_start.strftime('%Y-%m-%d %H:%M:%S')}] --- SCAN CYCLE STARTED ---")
            
            # Run the deal finder logic
            await scan_for_deals(bot_client, channel_id, is_dry_run=(not is_live_ready))
            
            scan_end = datetime.now()
            duration = scan_end - scan_start
            next_run = scan_end + timedelta(seconds=interval_seconds)
            
            print(f"\n⏰ [{scan_end.strftime('%Y-%m-%d %H:%M:%S')}] --- SCAN CYCLE COMPLETED ---")
            print(f"⏱️ Cycle Duration: {duration.total_seconds():.2f} seconds")
            print(f"⏳ Sleeping for {scan_interval} minutes.")
            print(f"📅 Next scheduled scan cycle at: {next_run.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"Press Ctrl+C to stop the bot...")
            
            await asyncio.sleep(interval_seconds)
            
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped manually by user. Goodbye!")
    except Exception as e:
        print(f"\n⚠️ Unexpected loop error encountered: {e}")

if __name__ == "__main__":
    # Ensure correct asyncio loop execution across platforms
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Bot shutdown cleanly.")
        sys.exit(0)
