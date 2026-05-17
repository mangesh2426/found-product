"""
main.py
-------
This is the entry point for the Telegram Deal Automation Bot.
It calculates discounts on mock products, detects hot deals (>= 80% off), formats them into 
beautiful HTML alerts, and broadcasts them to a Telegram Channel using a built-in scheduler.

If Telegram credentials are not yet configured, the bot runs in 'Dry-Run Demo Mode' to show 
you exactly what it does in the terminal before you connect it to Telegram!
"""

import asyncio
import sys
import os
import threading
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, HTTPServer
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

# --- SAMPLE PRODUCT DATA DATABASE (INDIAN RUPEES ₹) ---
# A list of dictionaries representing Indian products.
SAMPLE_PRODUCTS = [
    {
        "name": "🚀 Ultra-Fast USB-C Braided Cable (10ft)",
        "original_price": 999.00,
        "sale_price": 149.00,  # (999 - 149)/999 = 85% discount (Alert trigger!)
        "url": "https://example.com/usb-c-cable-deal"
    },
    {
        "name": "⌨️ Ergonomic RGB Mechanical Keyboard",
        "original_price": 4999.00,
        "sale_price": 3999.00,  # 20% discount (Should be skipped)
        "url": "https://example.com/mech-keyboard"
    },
    {
        "name": "⌚ Premium Smart Fitness Watch (Series 5)",
        "original_price": 19999.00,
        "sale_price": 2999.00,  # ~85% discount (Alert trigger!)
        "url": "https://example.com/smart-watch-deal"
    },
    {
        "name": "🔋 Portable 20,000mAh Power Bank",
        "original_price": 2499.00,
        "sale_price": 1999.00,  # 20% discount (Should be skipped)
        "url": "https://example.com/powerbank"
    },
    {
        "name": "🎧 Bluetooth Noise-Cancelling Headphones",
        "original_price": 9999.00,
        "sale_price": 999.00,  # 90% discount (Alert trigger!)
        "url": "https://example.com/noise-cancelling-headphones"
    }
]

# --- CORE FUNCTIONS ---

def calculate_discount_percentage(original_price: float, sale_price: float) -> float:
    """
    Calculates the discount percentage given the original price and sale price.
    Formula: ((Original - Sale) / Original) * 100
    """
    if original_price <= 0:
        return 0.0
    discount = ((original_price - sale_price) / original_price) * 100
    return round(discount, 2)


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


async def send_telegram_message(bot_client: telegram.Bot, channel_chat_id: str, message: str, is_dry_run: bool):
    """
    Sends the formatted message to the Telegram channel.
    If is_dry_run is True, it simulates sending by displaying it in the terminal instead.
    """
    if is_dry_run:
        print("\n📢 [DRY-RUN BROADCAST MESSAGE TO TELEGRAM]")
        print("-" * 50)
        # Strip or format HTML tags for beautiful terminal presentation
        clean_msg = message
        clean_msg = clean_msg.replace("<span class=\"tg-spoiler\">", "").replace("</span>", "")
        clean_msg = clean_msg.replace("<b>", "").replace("</b>", "")
        clean_msg = clean_msg.replace("<s>", "~").replace("</s>", "~")
        clean_msg = clean_msg.replace("<i>", "").replace("</i>", "")
        clean_msg = clean_msg.replace("<a href=\"", "").replace("\">", " -> ").replace("</a>", "")
        print(clean_msg)
        print("-" * 50)
    else:
        # Send live message to Telegram Channel via async python-telegram-bot Client API
        await bot_client.send_message(
            chat_id=channel_chat_id,
            text=message,
            parse_mode="HTML",
            disable_web_page_preview=False
        )


# --- MAIN WORKFLOW SCANNERS ---

async def scan_for_deals(bot_client: telegram.Bot, channel_chat_id: str, is_dry_run: bool):
    """
    Scans the product inventory, calculates discounts, and broadcasts deal alerts
    for items offering an 80% or greater discount.
    """
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 🔍 Starting product scan...")
    deals_found = 0

    for product in SAMPLE_PRODUCTS:
        orig = product["original_price"]
        sale = product["sale_price"]
        name = product["name"]
        
        # Calculate discount
        discount_percent = calculate_discount_percentage(orig, sale)
        
        print(f"   • Checking: {name} (Orig: ${orig:.2f}, Sale: ${sale:.2f}) -> Discount: {discount_percent}%")
        
        # Check if discount is 80% or above
        if discount_percent >= 80.0:
            print(f"     🎉 HOT DEAL DETECTED! ({discount_percent}% off)")
            
            # Format high-quality deal broadcast message
            deal_message = format_deal_message(product, discount_percent)
            
            # Broadcast message
            try:
                await send_telegram_message(bot_client, channel_chat_id, deal_message, is_dry_run)
                deals_found += 1
                # Small safety delay to prevent hitting Telegram API rate limits
                if not is_dry_run:
                    await asyncio.sleep(2)
            except Exception as e:
                print(f"     ❌ Error sending message to Telegram: {e}")
        else:
            print("     ⚖️ Normal price or low discount. Skipping...")

    print(f"✨ Scan completed. Found and published {deals_found} hot deals!\n")


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
                "The Telegram Deal Automation Bot has started successfully and is now active! "
                "It will scan for deals every 5 minutes."
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
        # Create a dummy bot client for interface compliance
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
    # Ensure correct asyncio loop execution across platforms (macOS, Windows, Linux)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Bot shutdown cleanly.")
        sys.exit(0)
