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
CHANNEL_USERNAME = os.getenv("TELEGRAM_CHANNEL_USERNAME") or os.getenv("TELEGRAM_PUBLIC_DEALS_CHANNEL") or os.getenv("TELEGRAM_PRIVATE_REVIEW_CHANNEL")

# Import settings and helper modules from main.py and config.py to keep everything clean and modular!
import config
from main import format_deal_message, load_posted_deals, save_posted_deal

# Re-use target search keywords from our central configuration
KEYWORDS = config.KEYWORDS

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
    Crawls Myntra search result pages from the live site using requests + BeautifulSoup.
    """
    import json
    query_dashed = keyword.strip().lower().replace(" ", "-")
    url = f"https://www.myntra.com/{query_dashed}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "en-IN,en;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Referer": "https://www.myntra.com/",
    }
    
    products = []
    try:
        print(f"📡 [Myntra] Searching for '{keyword}' via {url}...")
        response = requests.get(url, headers=headers, timeout=12)
        if response.status_code != 200:
            print(f"   ❌ Failed to load Myntra page. HTTP status: {response.status_code}")
            return []
            
        soup = BeautifulSoup(response.content, "lxml")
        match = re.search(r"window\.__myx\s*=\s*(\{.+?\});?\s*(?:window\.__INITIAL_STATE__|</script>|$)", response.text)
        if not match:
            print("   ❌ Error: Could not locate window.__myx JSON script tag in Myntra search source.")
            return []
            
        state_data = json.loads(match.group(1))
        search_results = state_data.get("searchData", {}).get("results", {})
        product_list = search_results.get("products", [])
        print(f"   🔎 Found {len(product_list)} items in Myntra search results.")
        
        for item in product_list:
            brand = item.get("brand", "Myntra")
            product_name = item.get("productName", "")
            title = f"{brand} - {product_name}" if brand else product_name
            
            sale_price = float(item.get("price", 0))
            original_price = float(item.get("mrp", sale_price))
            if original_price <= 0:
                original_price = sale_price
                
            if original_price > 0 and sale_price > 0:
                discount_percent = round(((original_price - sale_price) / original_price) * 100, 2)
            else:
                discount_percent = 0.0
                
            landing_url = item.get("landingPageUrl", "")
            product_url = f"https://www.myntra.com/{landing_url}" if landing_url else url
            
            image_url = item.get("searchImage", "")
            if image_url and image_url.startswith("http://"):
                image_url = image_url.replace("http://", "https://")
                
            products.append({
                "name": title,
                "original_price": original_price,
                "sale_price": sale_price,
                "discount_percentage": discount_percent,
                "url": product_url,
                "image_url": image_url,
                "source": "Myntra"
            })
            
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
    
    posted_deals = load_posted_deals()
    threshold = getattr(config, "MIN_DISCOUNT", 80.0)
    max_posts = getattr(config, "MAX_POSTS_PER_SCAN", 5)
    
    deal_count = 0
    posts_in_this_scan = 0
    
    for product in all_deals:
        discount = product["discount_percentage"]
        product_key = product.get("id") or product.get("url")
        
        print(f"• [{product['source']}] {product['name'][:40]}... -> MRP: ₹{product['original_price']} | Sale: ₹{product['sale_price']} | Discount: {discount}%")
        
        # Check if discount exceeds the threshold
        if discount >= threshold:
            # Duplicate check
            if product_key in posted_deals:
                print(f"  🛡️ [DUPLICATE] '{product['name'][:30]}' already sent. Skipping...")
                continue
                
            # Rate limit check
            if posts_in_this_scan >= max_posts:
                print(f"  ⚠️ [RATE LIMIT MET] Skipping '{product['name'][:30]}' (max {max_posts} reached).")
                continue
                
            # Determine dynamic label to log
            category = "MEGA DEAL" if discount >= 90.0 else "HOT DEAL"
            print(f"  🔥 {category} DETECTED! ({discount}% OFF)")
            
            await broadcast_deal(product)
            deal_count += 1
            posts_in_this_scan += 1
            
            # Save to persistent database
            save_posted_deal(product_key)
            posted_deals.add(product_key)
            
            # Random delay to prevent rate issues
            post_delay = random.uniform(3.0, 7.0)
            print(f"  ⏳ Waiting {post_delay:.2f} seconds before continuing...")
            await asyncio.sleep(post_delay)
            
    print("-" * 50)
    print(f"✨ Crawl scan complete. Found and published {posts_in_this_scan} new fashion deals (>= {threshold}% off)!")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
