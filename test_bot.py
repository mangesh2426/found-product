import asyncio
import os
from dotenv import load_dotenv
import telegram

# Load environment variables from the .env file
load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
PUBLIC_CHANNEL = os.getenv("TELEGRAM_CHANNEL_USERNAME") or os.getenv("TELEGRAM_PUBLIC_DEALS_CHANNEL")
PRIVATE_CHANNEL = os.getenv("TELEGRAM_PRIVATE_REVIEW_CHANNEL")

async def test_channel(bot, channel_name, channel_id):
    print(f"\n📨 Sending test message to {channel_name} ({channel_id})...")
    test_message = (
        f"🤖 <b>Bot Connection Test - {channel_name}</b>\n\n"
        f"This is a test message from your bot to verify that the credentials and channel admin permissions are correct!"
    )
    try:
        sent_message = await bot.send_message(
            chat_id=channel_id,
            text=test_message,
            parse_mode="HTML"
        )
        print(f"🎉 SUCCESS! The message was sent successfully to {channel_name}.")
        print(f"💬 Message ID: {sent_message.message_id}")
        return True
    except telegram.error.BadRequest as e:
        print(f"❌ Error: Bad Request - {e}")
        print("   This usually means one of two things:")
        print(f"   1. The channel username '{channel_id}' is incorrect or does not exist.")
        print("   2. The bot is NOT an Administrator of the channel.")
        print("      👉 FIX: Go to your Telegram Channel -> Manage Channel -> Administrators -> Add Administrator -> Search for your bot username -> Save.")
    except Exception as e:
        print(f"❌ Unexpected Error for {channel_name}: {e}")
    return False

async def main():
    print("=" * 60)
    print("🧪 TELEGRAM BOT CONNECTION TEST SCRIPT 🧪")
    print("=" * 60)
    
    # 1. Check if env variables are loaded
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("❌ Error: TELEGRAM_BOT_TOKEN is not configured in .env file!")
        return
        
    token = BOT_TOKEN.strip()
    if " " in token:
        print("⚠️  Warning: Your TELEGRAM_BOT_TOKEN contains a space character in .env:")
        print(f"    '{BOT_TOKEN}'")
        token = token.replace(" ", "")
        
    # Mask token for security in terminal display
    masked_token = f"{token[:10]}...{token[-5:]}" if len(token) > 15 else token
    print(f"🤖 Bot Token Loaded: {masked_token}")
    
    channels_to_test = []
    if PUBLIC_CHANNEL and PUBLIC_CHANNEL not in ["@YOUR_CHANNEL_USERNAME_HERE", "@YOUR_PUBLIC_CHANNEL_HERE"]:
        channels_to_test.append(("Public Deals Channel", PUBLIC_CHANNEL))
    if PRIVATE_CHANNEL and PRIVATE_CHANNEL not in ["@YOUR_PRIVATE_CHANNEL_HERE"]:
        channels_to_test.append(("Private Review Channel", PRIVATE_CHANNEL))
        
    if not channels_to_test:
        print("❌ Error: No valid Telegram channels configured in .env file!")
        print("   Please configure TELEGRAM_PUBLIC_DEALS_CHANNEL or TELEGRAM_PRIVATE_REVIEW_CHANNEL.")
        return
        
    print(f"📢 Configured channels to test: {', '.join([c[1] for c in channels_to_test])}")
    print("\nAttempting to connect to Telegram...")
    
    try:
        # Initialize the bot client
        bot = telegram.Bot(token=token)
        
        # Get bot info to verify connection
        bot_info = await bot.get_me()
        print(f"✅ Connection successful!")
        print(f"🤖 Bot Name: {bot_info.first_name}")
        print(f"🤖 Bot Username: @{bot_info.username}")
        
        # Test each configured channel
        for name, channel_id in channels_to_test:
            await test_channel(bot, name, channel_id)
            
    except telegram.error.InvalidToken:
        print("❌ Error: The Telegram Bot Token is invalid!")
        print("   Please check your .env file and ensure the token is correct.")
    except Exception as e:
        print(f"❌ Connection/Setup Error: {e}")
        print("   Check your internet connection and try again.")
        
    print("\n" + "=" * 60)

if __name__ == "__main__":
    # Ensure correct asyncio execution
    asyncio.run(main())
