import asyncio
import os
import re
import requests
from bs4 import BeautifulSoup
import telegram
from dotenv import load_dotenv

# Load env variables for the Telegram bot
load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_USERNAME = os.getenv("TELEGRAM_CHANNEL_USERNAME")

# Import our helper formatter function from main.py to keep the code modular and clean!
from main import format_deal_message

def clean_price(price_str: str) -> float:
    """
    Cleans price strings (e.g. '₹999.00', ' 1,499.00 ', 'MRP: ₹499') and converts to float.
    """
    if not price_str:
        return 0.0
    # Remove currency symbols (₹, $, etc.), commas, and whitespace
    clean_str = re.sub(r"[^\d.]", "", price_str)
    try:
        return float(clean_str)
    except ValueError:
        return 0.0

def scrape_product(url: str) -> dict:
    """
    Scrapes an Amazon India product URL using requests and BeautifulSoup.
    Returns a dictionary of product data or None if scraping fails.
    """
    # 1. Custom Request Headers with User-Agent
    # Mimics a real desktop Google Chrome browser. Without this, Amazon's servers 
    # will detect us as a python bot and return a 503 Service Unavailable / CAPTCHA page.
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-IN,en-US;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Connection": "keep-alive",
        "Device-Memory": "8",
    }
    
    try:
        print(f"📡 Fetching Amazon product page: {url}...")
        response = requests.get(url, headers=headers, timeout=10)
        
        # Check HTTP response status code
        if response.status_code != 200:
            print(f"❌ HTTP Error {response.status_code}: Could not fetch page.")
            if response.status_code == 503:
                print("⚠️  Amazon is currently blocking the scraper (503 Service Unavailable / CAPTCHA protection).")
            return None
            
        # Parse using BeautifulSoup and 'lxml' (faster and more robust than default html.parser)
        soup = BeautifulSoup(response.content, "lxml")
        
        # 2. Extract Product Title
        title_el = soup.find("span", id="productTitle")
        if not title_el:
            print("❌ Title not found. Page layout might have changed, or we got blocked.")
            # Pro tip: Save raw HTML to debug what went wrong (e.g. to check if Amazon sent a CAPTCHA)
            with open("amazon_debug.html", "w", encoding="utf-8") as f:
                f.write(response.text)
            print("💾 Saved raw page to 'amazon_debug.html' for inspection.")
            return None
            
        title = title_el.get_text(strip=True)
        
        # 3. Extract Current Price (Deal Price)
        # Amazon uses a dynamic layout that shifts classes depending on categories or active deal states.
        # We define primary and fallback CSS selectors to search recursively.
        current_price_str = ""
        current_price_selectors = [
            ".priceToPay .a-offscreen",                     # Standard product price
            ".apexPriceToPay .a-offscreen",                 # Deal page price
            ".a-price-whole",                               # Bold price numbers
            ".swatchElement.selected .a-color-price",        # Book selected format price
            ".a-color-price",                               # Generic category price element
            ".a-size-base.a-color-price",                   # Text category price
            "#priceblock_ourprice",                         # Older product layout price
            "#priceblock_dealprice",                        # Older active deal price
        ]
        
        print("\n🔍 DEBUG: Checking Current Price (Deal Price) CSS Selectors:")
        for selector in current_price_selectors:
            price_el = soup.select_one(selector)
            if price_el and price_el.get_text(strip=True):
                current_price_str = price_el.get_text(strip=True)
                print(f"   ✅ SUCCESS: Selector '{selector}' matched! Raw text: '{current_price_str}'")
                break
            else:
                print(f"   ❌ FAILED: Selector '{selector}' found no non-empty match.")
                
        # 4. Extract Original Price (MRP)
        original_price_str = ""
        original_price_selectors = [
            ".basisPrice .a-offscreen",                     # Standard strikethrough original price
            ".a-price.a-text-price .a-offscreen",           # Alternative strikethrough price
            ".listPrice .a-offscreen",                      # List price container
            "#priceblock_listprice",                        # Older layout list price
            ".a-text-strike",                               # Any element with a strikethrough line
        ]
        
        print("\n🔍 DEBUG: Checking Original Price (MRP) CSS Selectors:")
        for selector in original_price_selectors:
            price_el = soup.select_one(selector)
            if price_el and price_el.get_text(strip=True):
                original_price_str = price_el.get_text(strip=True)
                print(f"   ✅ SUCCESS: Selector '{selector}' matched! Raw text: '{original_price_str}'")
                break
            else:
                print(f"   ❌ FAILED: Selector '{selector}' found no non-empty match.")
                
        # Clean the price strings into clean numbers
        current_price = clean_price(current_price_str)
        original_price = clean_price(original_price_str)
        
        print(f"\n📊 DEBUG: Price Conversion Cleanups:")
        print(f"   • Raw Deal Price: '{current_price_str}' -> Parsed Float: ₹{current_price}")
        print(f"   • Raw MRP Price:  '{original_price_str}' -> Parsed Float: ₹{original_price}")
        
        # If original price couldn't be parsed, assume it is same as current price (0% discount)
        if original_price <= 0:
            print("   ⚠️ WARNING: MRP (Original Price) not found. Defaulting MRP to Deal Price.")
            original_price = current_price
            
        # Calculate discount percentage
        if current_price > 0 and original_price > 0:
            discount_percent = round(((original_price - current_price) / original_price) * 100, 2)
        else:
            print("   ⚠️ WARNING: Price is zero or missing. Calculated discount will be 0%.")
            discount_percent = 0.0
            
        return {
            "name": title,
            "original_price": original_price,
            "sale_price": current_price,
            "discount_percentage": discount_percent,
            "url": url
        }
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Connection Error: {e}")
        return None
    except Exception as e:
        print(f"❌ Unexpected Scraping Error: {e}")
        return None

async def broadcast_deal(product: dict):
    """
    Sends the beautifully formatted Indian Rupees deal message to the Telegram channel.
    """
    if not BOT_TOKEN or not CHANNEL_USERNAME:
        print("❌ Telegram credentials not fully configured in your .env file.")
        return
        
    try:
        bot = telegram.Bot(token=BOT_TOKEN)
        # Format the deal message using the helper we updated in main.py
        message = format_deal_message(product, product["discount_percentage"])
        
        print(f"📨 Broadcasting deal to Telegram channel {CHANNEL_USERNAME}...")
        await bot.send_message(
            chat_id=CHANNEL_USERNAME,
            text=message,
            parse_mode="HTML"
        )
        print("🎉 SUCCESS! Alert sent to your Telegram channel successfully.")
    except Exception as e:
        print(f"❌ Failed to send Telegram message: {e}")

async def main():
    print("=" * 60)
    print("🛒 AMAZON INDIA REAL PRODUCT SCRAPER 🛒")
    print("=" * 60)
    
    # Example Amazon India product URL (Atomic Habits - permanently active best-seller)
    # You can swap this with any valid Amazon India URL to test!
    amazon_url = "https://www.amazon.in/dp/1847941834"
    
    product_data = scrape_product(amazon_url)
    
    if product_data:
        print("\n📦 EXTRACTED DETAILS:")
        print("-" * 50)
        print(f"Product Title: {product_data['name'][:60]}...")
        print(f"MRP (Original Price): ₹{product_data['original_price']}")
        print(f"Deal Price: ₹{product_data['sale_price']}")
        print(f"Discount Calculated: {product_data['discount_percentage']}%")
        print(f"Product Link: {product_data['url']}")
        print("-" * 50)
        
        # Checking if discount meets the threshold (TEMPORARILY CHANGED TO 10.0% FOR DEBUG TESTING)
        threshold = 10.0
        print(f"🔍 Checking if discount ({product_data['discount_percentage']}%) >= Threshold ({threshold}%)...")
        
        if product_data['discount_percentage'] >= threshold:
            print("🚨 HOT DEAL DETECTED! Sending Telegram Alert...")
            await broadcast_deal(product_data)
        else:
            print(f"⚖️ Normal discount. Skipping Telegram Alert (must be >= {threshold}%).")
    else:
        print("\n❌ Scraping failed.")
        print("💡 Amazon has high anti-bot protection. Try running the script again or check 'amazon_debug.html'.")
        
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
