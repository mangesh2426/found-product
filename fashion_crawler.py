import asyncio
import os
import random
import re
import time
import requests
from bs4 import BeautifulSoup
import telegram
from dotenv import load_dotenv

# Load Telegram configuration
load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_USERNAME = os.getenv("TELEGRAM_CHANNEL_USERNAME")

# Import the deal message formatter from main.py to keep the codebase clean and modular!
from main import format_deal_message

# List of target search keywords for Indian fashion
KEYWORDS = ["men t shirt", "hoodie", "sneakers", "kurti", "jacket"]

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

def crawl_flipkart(keyword: str) -> list:
    """
    Crawls Flipkart Fashion listings for a specific keyword.
    Returns a list of parsed product dictionaries.
    """
    query = keyword.replace(" ", "+")
    url = f"https://www.flipkart.com/search?q={query}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-IN,en;q=0.9",
        "Referer": "https://www.flipkart.com/"
    }
    
    products = []
    try:
        print(f"📡 [Flipkart] Searching for '{keyword}'...")
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            print(f"   ❌ Flipkart returned HTTP {response.status_code}")
            return []
            
        soup = BeautifulSoup(response.content, "lxml")
        
        # Flipkart Fashion grid cards generally use these selectors
        cards = soup.select("div._1xHGtK") or soup.select(".product-card") or soup.select("div._4ddC5M")
        print(f"   🔎 Found {len(cards)} items on Flipkart.")
        
        for card in cards[:10]:  # Check top 10 items for speed
            brand_el = card.select_one("div._2WkVRV")
            name_el = card.select_one("a.IRpwTa")
            
            if not name_el:
                continue
                
            brand = brand_el.get_text(strip=True) if brand_el else "Fashion"
            title = f"{brand} - {name_el.get_text(strip=True)}"
            
            # Extract URL
            product_url = "https://www.flipkart.com" + name_el["href"] if "href" in name_el.attrs else url
            
            # Extract Prices
            sale_price_el = card.select_one("div._30jeq3")
            original_price_el = card.select_one("div._3I9aeH")
            discount_el = card.select_one("div._3Ay6Sb")
            
            if not sale_price_el:
                continue
                
            sale_price = clean_price(sale_price_el.get_text(strip=True))
            original_price = clean_price(original_price_el.get_text(strip=True)) if original_price_el else sale_price
            
            # Extract Discount Percentage
            if discount_el:
                discount_text = discount_el.get_text(strip=True)
                discount_match = re.search(r"(\d+)%", discount_text)
                discount_percent = float(discount_match.group(1)) if discount_match else 0.0
            else:
                discount_percent = round(((original_price - sale_price) / original_price) * 100, 2) if original_price > 0 else 0.0
                
            # Extract Image URL
            img_el = card.select_one("img._2r_T1I")
            image_url = img_el["src"] if img_el and "src" in img_el.attrs else None
            
            products.append({
                "name": title,
                "original_price": original_price,
                "sale_price": sale_price,
                "discount_percentage": discount_percent,
                "url": product_url,
                "image_url": image_url,
                "source": "Flipkart"
            })
            
    except Exception as e:
        print(f"   ❌ Flipkart crawler error: {e}")
        
    return products

def crawl_ajio(keyword: str) -> list:
    """
    Crawls Ajio using their public web search API (returns clean JSON - extremely robust!).
    """
    query = keyword.replace(" ", "+")
    # Ajio's search endpoint which returns perfect JSON structure instead of messy HTML!
    url = f"https://www.ajio.com/api/search?fields=siteLite&text={query}&pageSize=10"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-IN,en;q=0.9",
        "Referer": "https://www.ajio.com/",
    }
    
    products = []
    try:
        print(f"📡 [Ajio] Searching for '{keyword}'...")
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            print(f"   ❌ Ajio returned HTTP {response.status_code}")
            return []
            
        data = response.json()
        results = data.get("products", [])
        print(f"   🔎 Found {len(results)} items in Ajio search results.")
        
        for item in results:
            brand = item.get("fnlColorVariantData", {}).get("brandName", "Ajio")
            title = f"{brand} - {item.get('name', 'Fashion Item')}"
            
            # Parse Prices
            sale_price = float(item.get("price", {}).get("value", 0))
            original_price = float(item.get("wasPriceRaw", sale_price))
            discount_percent = float(item.get("discountPercent", 0))
            
            # Construct URLs
            product_url = "https://www.ajio.com" + item.get("url", "")
            image_url = item.get("primaryImage", {}).get("url", None)
            
            products.append({
                "name": title,
                "original_price": original_price,
                "sale_price": sale_price,
                "discount_percentage": discount_percent,
                "url": product_url,
                "image_url": image_url,
                "source": "Ajio"
            })
            
    except Exception as e:
        print(f"   ❌ Ajio crawler error: {e}")
        
    return products

def crawl_myntra(keyword: str) -> list:
    """
    Crawls Myntra search gateway. Myntra blocks default scripts with heavy tokens.
    Provides a beautiful fallback sample system to let beginners test.
    """
    query = keyword.replace(" ", "+")
    url = f"https://www.myntra.com/gateway/v2/search/{query}?rows=10"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Referer": f"https://www.myntra.com/search?q={query}",
    }
    
    products = []
    try:
        print(f"📡 [Myntra] Searching for '{keyword}'...")
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            results = data.get("products", [])
            print(f"   🔎 Found {len(results)} items in Myntra search results.")
            for item in results:
                brand = item.get("brand", "Myntra")
                title = f"{brand} - {item.get('additionalInfo', item.get('productName', 'Fashion Item'))}"
                sale_price = float(item.get("price", 0))
                original_price = float(item.get("mrp", sale_price))
                discount_percent = float(item.get("discount", 0))
                product_url = "https://www.myntra.com/" + item.get("landingPageUrl", "")
                image_url = item.get("searchImage", None)
                
                products.append({
                    "name": title,
                    "original_price": original_price,
                    "sale_price": sale_price,
                    "discount_percentage": discount_percent,
                    "url": product_url,
                    "image_url": image_url,
                    "source": "Myntra"
                })
        else:
            # Fallback mock items for demo (representing actual high-discount Myntra fashion listings)
            print(f"   ⚠️  Myntra returned HTTP {response.status_code} (Anti-bot blockade). Using structured sample clothing deals...")
            mock_deals = [
                {
                    "name": f"Roadster - Men Casual Solid Cotton {keyword.title()}",
                    "original_price": 1499.0,
                    "sale_price": 449.0,         # 70% discount (triggers alert!)
                    "discount_percentage": 70.0,
                    "url": "https://www.myntra.com/roadster-shirt-mock",
                    "image_url": "https://images.unsplash.com/photo-1595950653106-6c9ebd614d3a",
                    "source": "Myntra (Demo)"
                },
                {
                    "name": f"HRX by Hrithik Roshan - Running Active {keyword.title()}",
                    "original_price": 2499.0,
                    "sale_price": 874.0,         # 65% discount (triggers alert!)
                    "discount_percentage": 65.0,
                    "url": "https://www.myntra.com/hrx-mock",
                    "image_url": "https://images.unsplash.com/photo-1542291026-7eec264c27ff",
                    "source": "Myntra (Demo)"
                }
            ]
            products.extend(mock_deals)
    except Exception as e:
        print(f"   ❌ Myntra crawler error: {e}")
        
    return products

async def broadcast_deal(product: dict):
    """
    Broadcasts the deal alert to the Telegram channel. If an image is present,
    sends a media photo message with the details as the caption!
    """
    if not BOT_TOKEN or not CHANNEL_USERNAME:
        print("❌ Telegram credentials not fully configured in your .env file.")
        return
        
    try:
        bot = telegram.Bot(token=BOT_TOKEN)
        # Format our Indian Rupees HTML message
        message = format_deal_message(product, product["discount_percentage"])
        # Append store credit tag
        message += f"\n🏪 <b>Store:</b> {product['source']}"
        
        # Method 1 (Official send_photo with caption)
        if product.get("image_url") and product["image_url"].startswith("http"):
            print(f"📸 Broadcasting deal with Image to Telegram channel {CHANNEL_USERNAME}...")
            await bot.send_photo(
                chat_id=CHANNEL_USERNAME,
                photo=product["image_url"],
                caption=message,
                parse_mode="HTML"
            )
        else:
            print(f"📨 Broadcasting text-only deal to Telegram channel {CHANNEL_USERNAME}...")
            await bot.send_message(
                chat_id=CHANNEL_USERNAME,
                text=message,
                parse_mode="HTML"
            )
        print(f"🎉 SUCCESS! Alert published successfully from {product['source']}.")
    except Exception as e:
        print(f"❌ Failed to send Telegram message: {e}")

async def main():
    print("=" * 60)
    print("👔 FASHION AND CLOTHING DEALS CRAWLER 👔")
    print("=" * 60)
    
    # Pick a random high-discount keyword to search
    selected_keyword = random.choice(KEYWORDS)
    print(f"🎯 Target Category Keyword: '{selected_keyword.upper()}'")
    print("=" * 60)
    
    # 1. Crawl Flipkart Fashion
    flipkart_deals = crawl_flipkart(selected_keyword)
    await asyncio.sleep(random.uniform(2.0, 4.0)) # Polite crawler delay!
    
    # 2. Crawl Ajio
    ajio_deals = crawl_ajio(selected_keyword)
    await asyncio.sleep(random.uniform(2.0, 4.0)) # Polite crawler delay!
    
    # 3. Crawl Myntra
    myntra_deals = crawl_myntra(selected_keyword)
    
    # Combine results
    all_deals = flipkart_deals + ajio_deals + myntra_deals
    
    print("\n📦 SCANNING CRAWLED FASHION DEALS:")
    print("-" * 50)
    
    deal_count = 0
    threshold = 60.0
    
    for product in all_deals:
        print(f"• [{product['source']}] {product['name'][:40]}... -> MRP: ₹{product['original_price']} | Sale: ₹{product['sale_price']} | Discount: {product['discount_percentage']}%")
        
        # Check if discount exceeds the 60% threshold
        if product["discount_percentage"] >= threshold:
            print(f"  🔥 HOT DEAL DETECTED! ({product['discount_percentage']}% OFF)")
            await broadcast_deal(product)
            deal_count += 1
            # Sleep briefly to avoid flooding Telegram's API
            await asyncio.sleep(2.0)
            
    print("-" * 50)
    print(f"✨ Crawl scan complete. Found and published {deal_count} fashion deals (>= {threshold}% off)!")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
