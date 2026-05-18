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

# Default search keywords for our real-time fashion product crawler
KEYWORDS = ["men tshirt", "sneakers", "hoodie", "women kurti"]

# Advanced Deal Filtering & Rate Limiting Settings
SCAN_INTERVAL = 10              # Run full product scan every 10 minutes only
DISCOUNT_THRESHOLD = 80.0       # Only send deals with discount >= 80%
MAX_DEALS_PER_SCAN = 3          # Maximum Telegram posts per search scan
REQUEST_DELAY_MIN = 3.0         # Minimum random delay in seconds between scraping pages
REQUEST_DELAY_MAX = 8.0         # Maximum random delay in seconds between scraping pages
DUPLICATE_DB_FILE = "posted_deals.json"  # Persistent database for posted deals



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
