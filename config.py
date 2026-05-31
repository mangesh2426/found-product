"""
config.py
---------
This module handles loading and validating configuration settings for the Telegram Deal Bot.
It uses 'python-dotenv' to securely read credentials from a local '.env' file, keeping sensitive
data out of the main code repository.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Find the directory containing this config file
BASE_DIR = Path(__file__).resolve().parent

# Load environment variables from the .env file in the base directory
env_path = BASE_DIR / '.env'
if env_path.exists():
    load_dotenv(dotenv_path=env_path)

# Telegram Bot Token (obtained from @BotFather)
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")

# Telegram Private Review Channel (where crawler sends raw deals for review)
PRIVATE_REVIEW_CHANNEL = os.getenv("TELEGRAM_PRIVATE_REVIEW_CHANNEL", "@YOUR_PRIVATE_CHANNEL_HERE")

# Telegram Public Deals Channel (where approved deals are published manually)
PUBLIC_DEALS_CHANNEL = os.getenv("TELEGRAM_PUBLIC_DEALS_CHANNEL", "@YOUR_PUBLIC_CHANNEL_HERE")

# Target Real Myntra Product URL to scrape
MYNTRA_PRODUCT_URL = os.getenv("MYNTRA_PRODUCT_URL", "https://www.myntra.com/1364628")

# EarnKaro Credentials
EARNKARO_MOBILE_OR_EMAIL = os.getenv("EARNKARO_MOBILE_OR_EMAIL", "YOUR_EARNKARO_MOBILE_OR_EMAIL_HERE")

# EarnKaro Affiliate Automation Config
USE_AFFILIATE_LINKS = os.getenv("USE_AFFILIATE_LINKS", "True").strip().lower() in ("true", "1", "yes")
AFFILIATE_FALLBACK_TO_ORIGINAL = os.getenv("AFFILIATE_FALLBACK_TO_ORIGINAL", "False").strip().lower() in ("true", "1", "yes")
try:
    MAX_AFFILIATE_GENERATIONS_PER_SCAN = int(os.getenv("MAX_AFFILIATE_GENERATIONS_PER_SCAN", "3"))
except ValueError:
    MAX_AFFILIATE_GENERATIONS_PER_SCAN = 3

def is_earnkaro_configured() -> bool:
    """
    Checks if EarnKaro credentials are configured in .env.
    """
    return bool(EARNKARO_MOBILE_OR_EMAIL and EARNKARO_MOBILE_OR_EMAIL != "YOUR_EARNKARO_MOBILE_OR_EMAIL_HERE")

# Default search keywords with their categories
KEYWORDS_WITH_CATEGORIES = [
    # Fashion
    ("men tshirt", "Fashion"),
    ("sneakers", "Fashion"),
    ("hoodie", "Fashion"),
    ("women kurti", "Fashion"),
    # Kitchen & Home
    ("vegetable chopper", "Kitchen"),
    ("air fryer", "Kitchen"),
    ("lunch box", "Kitchen"),
    ("water bottle", "Kitchen"),
    ("kitchen storage", "Kitchen"),
    ("cookware", "Kitchen")
]

# Flat keywords list for compatibility with older code
KEYWORDS = [k[0] for k in KEYWORDS_WITH_CATEGORIES]

# Category-specific discount thresholds
THRESHOLDS = {
    "Fashion": 80.0,
    "Kitchen": 50.0
}

# Tag mapping for Telegram deal cards
KEYWORD_TAGS = {
    # Fashion
    "men tshirt": "HOT DEAL",
    "sneakers": "HOT DEAL",
    "hoodie": "HOT DEAL",
    "women kurti": "HOT DEAL",
    # Kitchen
    "vegetable chopper": "KITCHEN DEAL",
    "air fryer": "KITCHEN DEAL",
    "cookware": "KITCHEN DEAL",
    # Home
    "lunch box": "HOME DEAL",
    "water bottle": "HOME DEAL",
    "kitchen storage": "HOME DEAL"
}

# Advanced Deal Rate Limiting & Scheduler Settings
SCAN_INTERVAL = 10              # Run full product scan every 30 minutes only
MAX_DEALS_PER_SCAN = 3          # Maximum Telegram posts per search scan
REQUEST_DELAY_MIN = 3.0         # Minimum random delay in seconds between scraping pages
REQUEST_DELAY_MAX = 8.0         # Maximum random delay in seconds between scraping pages
DUPLICATE_DB_FILE = "posted_products.json"  # Persistent database for posted deals

# Production-safe Quality Filters
DISCOUNT_THRESHOLD = float(os.getenv("DISCOUNT_THRESHOLD", "80.0"))
MIN_PRICE = float(os.getenv("MIN_PRICE", "200.0"))
MAX_PRICE = float(os.getenv("MAX_PRICE", "5000.0"))



def is_configured() -> bool:
    """
    Validates if the user has replaced the default placeholder values
    with their real Telegram bot credentials.
    """
    has_token = BOT_TOKEN and BOT_TOKEN != "YOUR_BOT_TOKEN_HERE"
    has_private = PRIVATE_REVIEW_CHANNEL and PRIVATE_REVIEW_CHANNEL != "@YOUR_PRIVATE_CHANNEL_HERE"
    has_public = PUBLIC_DEALS_CHANNEL and PUBLIC_DEALS_CHANNEL != "@YOUR_PUBLIC_CHANNEL_HERE"
    
    return bool(has_token and has_private and has_public)

def print_configuration_help():
    """
    Prints a clean, formatted helper message to the console if the
    credentials are still using default values.
    """
    print("=" * 60)
    print("❌ TELEGRAM BOT CONFIGURATION ERROR ❌")
    print("=" * 60)
    print("It looks like you haven't set up your credentials yet!")
    print("\nTo fix this:")
    print("1. Open the '.env' file in the base directory.")
    print("2. Replace 'YOUR_BOT_TOKEN_HERE' with the token from @BotFather.")
    print("3. Set 'TELEGRAM_PRIVATE_REVIEW_CHANNEL' with your Private Review Channel username.")
    print("4. Set 'TELEGRAM_PUBLIC_DEALS_CHANNEL' with your Public Deals Channel username.")
    print("\nOnce configured correctly, restart the script to start automated review posts!")
    print("=" * 60)
