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
from datetime import datetime
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


# --- REAL MYNTRA INDIA WEB SCRAPER ---

def scrape_myntra(url: str) -> dict:
    """
    Scrapes a live Myntra product page using requests + BeautifulSoup.
    Uses regex to extract the window.__myx JSON state block (bypassing fragile HTML parsing).
    """
    print(f"\n📡 Fetching Myntra product page: {url}...")
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-IN,en;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Referer": "https://www.myntra.com/",
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        print(f"   • Response Status Code: {response.status_code}")
        
        if response.status_code != 200:
            print(f"   ❌ Failed to load page. HTTP status: {response.status_code}")
            if response.status_code in [401, 403]:
                print("   ⚠️  Myntra is blocking the request (403/401 Forbidden). Try running again or updating headers.")
            return None
            
        soup = BeautifulSoup(response.content, "lxml")
        
        # Extract title tag as fallback title
        title_tag = soup.find("title")
        fallback_title = title_tag.get_text(strip=True) if title_tag else "Myntra Fashion Item"
        
        # 1. Search for window.__myx JSON script tag
        print("   🔍 Searching for Myntra state JSON block (window.__myx)...")
        # Search the entire HTML page text using our optimized regex
        match = re.search(r"window\.__myx\s*=\s*(\{.+?\});?\s*(?:window\.__INITIAL_STATE__|</script>)", response.text)
        
        if not match:
            print("   ❌ Error: Could not locate window.__myx JSON script tag in the page source.")
            # Save raw HTML to debug to help beginner users see why it failed
            with open("myntra_debug.html", "w", encoding="utf-8") as f:
                f.write(response.text)
            print("   💾 Saved raw page source to 'myntra_debug.html' for diagnostic review.")
            return None
            
        print("   ✅ SUCCESS: JSON state block located! Parsing JSON metadata...")
        state_data = json.loads(match.group(1))
        
        pdp_data = state_data.get("pdpData")
        if not pdp_data:
            print("   ❌ Error: 'pdpData' key not found inside the state JSON.")
            return None
            
        # 2. Extract brand, name, and compile full title
        brand = pdp_data.get("brand", {}).get("name", "")
        item_name = pdp_data.get("name", "")
        product_title = f"{brand} - {item_name}" if brand else item_name
        if not product_title:
            product_title = fallback_title
            
        # 3. Extract Prices
        price_info = pdp_data.get("price", {})
        original_price = float(price_info.get("mrp", 0))
        sale_price = float(price_info.get("discounted", original_price))
        
        # Fallbacks if keys are missing
        if original_price <= 0:
            original_price = float(pdp_data.get("mrp", sale_price))
        if original_price <= 0:
            original_price = sale_price
            
        # 4. Calculate Discount
        if original_price > 0 and sale_price > 0:
            discount_percent = round(((original_price - sale_price) / original_price) * 100, 2)
        else:
            discount_percent = 0.0
            
        # 5. Extract Image URL
        image_url = ""
        albums = pdp_data.get("media", {}).get("albums", [])
        if albums:
            images = albums[0].get("images", [])
            if images:
                img_info = images[0]
                secure_src = img_info.get("secureSrc", "")
                if secure_src:
                    # Replace placeholder variables with realistic dimensions
                    image_url = secure_src.replace("($height)", "720").replace("($qualityPercentage)", "90").replace("($width)", "540")
                else:
                    image_url = img_info.get("imageURL", "")
                    
        print("   🎉 SUCCESS: Product details extracted successfully!")
        print(f"      • Title: {product_title[:50]}...")
        print(f"      • MRP: ₹{original_price} | Deal Price: ₹{sale_price} | Discount: {discount_percent}%")
        if image_url:
            print(f"      • Image Link found: {image_url[:60]}...")
            
        return {
            "name": product_title,
            "original_price": original_price,
            "sale_price": sale_price,
            "discount_percentage": discount_percent,
            "url": url,
            "image_url": image_url
        }
        
    except json.JSONDecodeError as e:
        print(f"   ❌ JSON Decoding Failure: {e}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"   ❌ Connection Failure: {e}")
        return None
    except Exception as e:
        print(f"   ❌ Unexpected Scraping Error: {e}")
        return None


# --- CORE TELEGRAM FORMATTERS ---

def format_deal_message(product: dict, discount_percent: float) -> str:
    """
    Formats a professional, stunning Indian-style Telegram alert in Rupees (₹) using HTML.
    Includes strikethroughs, bolding, clean spacing, and a limited time hurry notice.
    """
    saving_amount = round(product["original_price"] - product["sale_price"], 2)
    
    # Format prices as integers if they are whole numbers (e.g. ₹999 instead of ₹999.00)
    mrp_formatted = f"{int(product['original_price'])}" if product['original_price'].is_integer() else f"{product['original_price']:.2f}"
    deal_formatted = f"{int(product['sale_price'])}" if product['sale_price'].is_integer() else f"{product['sale_price']:.2f}"
    save_formatted = f"{int(saving_amount)}" if saving_amount.is_integer() else f"{saving_amount:.2f}"

    message = (
        "🔥 <b>MEGA DEAL ALERT</b> 🔥\n\n"
        f"📦 <b>{product['name']}</b>\n\n"
        f"💰 <b>MRP:</b> <s>₹{mrp_formatted}</s>\n"
        f"⚡ <b>Deal Price:</b> <span class=\"tg-spoiler\"><b>₹{deal_formatted}</b></span>\n"
        f"🎯 <b>Discount:</b> {discount_percent}% OFF\n"
        f"💸 <b>Save:</b> ₹{save_formatted}\n\n"
        f"🛒 <b>Buy Now:</b>\n"
        f"👉 {product['url']}\n\n"
        "⏳ <i>Hurry! Limited Stock</i>"
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


# --- MAIN WORKFLOW SCANNERS ---

async def scan_for_deals(bot_client: telegram.Bot, channel_chat_id: str, is_dry_run: bool):
    """
    Loads the real Myntra URL from config, crawls it live, parses details,
    and broadcasts to Telegram immediately if successful.
    """
    target_url = config.MYNTRA_PRODUCT_URL
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 🔍 Starting real-time product scan...")
    print(f"🔗 Target URL: {target_url}")
    
    product = scrape_myntra(target_url)
    
    if not product:
        print("❌ Scan failed: Could not scrape Myntra details.")
        return
        
    print(f"✨ Scraped details verified. Preparing Telegram broadcast alert...")
    deal_message = format_deal_message(product, product["discount_percentage"])
    
    try:
        await send_telegram_message(
            bot_client=bot_client,
            channel_chat_id=channel_chat_id,
            message=deal_message,
            image_url=product["image_url"],
            is_dry_run=is_dry_run
        )
        print("🎉 SUCCESS! Real deal alert published to your Telegram channel successfully.")
    except Exception as e:
        print(f"❌ Failed to broadcast live deal: {e}")


# --- MAIN RUNNER & SCHEDULER LOOP ---

async def main():
    print("=" * 60)
    print("🤖 TELEGRAM DEAL AUTOMATION BOT INITIALIZED 🤖")
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
                "The Myntra Real-Scraper Deal Automation Bot is now online! "
                "It will crawl your target Myntra link and post live updates."
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

    # --- Scheduler Continuous Loop (Runs every 5 minutes / 300 seconds) ---
    interval_seconds = 300
    
    print(f"\n🔄 Scheduler active. Running deal scanning loop every {interval_seconds // 60} minutes.")
    
    try:
        while True:
            # Run the deal finder logic
            await scan_for_deals(bot_client, channel_id, is_dry_run=(not is_live_ready))
            
            # Print countdown log
            print(f"⏳ Sleeping for {interval_seconds // 60} minutes. Press Ctrl+C to stop the bot...")
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
