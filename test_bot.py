import asyncio
import os
from dotenv import load_dotenv
import telegram

# Load environment variables from the .env file
load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_USERNAME = os.getenv("TELEGRAM_CHANNEL_USERNAME")

async def main():
    print("=" * 60)
    print("🧪 TELEGRAM BOT CONNECTION TEST SCRIPT 🧪")
    print("=" * 60)
    
    # 1. Check if env variables are loaded
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        print("❌ Error: TELEGRAM_BOT_TOKEN is not configured in .env file!")
        return
        
    if not CHANNEL_USERNAME or CHANNEL_USERNAME == "@YOUR_CHANNEL_USERNAME_HERE":
        print("❌ Error: TELEGRAM_CHANNEL_USERNAME is not configured in .env file!")
        return

    # 2. Clean the token of any unexpected spaces
    token = BOT_TOKEN.strip()
    if " " in token:
        print("⚠️  Warning: Your TELEGRAM_BOT_TOKEN contains a space character in .env:")
        print(f"    '{BOT_TOKEN}'")
        print("    Telegram tokens never contain spaces. We will automatically clean it for this test,")
        print("    but you should open your .env file and remove the space.")
        token = token.replace(" ", "")
        
    # Mask token for security in terminal display
    masked_token = f"{token[:10]}...{token[-5:]}" if len(token) > 15 else token
    print(f"🤖 Bot Token Loaded: {masked_token}")
    print(f"📢 Channel Username Loaded: {CHANNEL_USERNAME}")
    print("\nAttempting to connect to Telegram and send a message...")
    
    try:
        # Initialize the bot client
        bot = telegram.Bot(token=token)
        
        # Get bot info to verify connection
        bot_info = await bot.get_me()
        print(f"✅ Connection successful!")
        print(f"🤖 Bot Name: {bot_info.first_name}")
        print(f"🤖 Bot Username: @{bot_info.username}")
        
        # Send a test message
        test_message = (
            "🤖 <b>Bot Connection Test</b>\n\n"
            "This is a test message from your bot to verify that the credentials and channel admin permissions are correct!"
        )
        
        print(f"📨 Sending test message to {CHANNEL_USERNAME}...")
        sent_message = await bot.send_message(
            chat_id=CHANNEL_USERNAME,
            text=test_message,
            parse_mode="HTML"
        )
        
        print("🎉 SUCCESS! The message was sent successfully to your channel.")
        print(f"💬 Message ID: {sent_message.message_id}")
        
    except telegram.error.InvalidToken:
        print("❌ Error: The Telegram Bot Token is invalid!")
        print("   Please check your .env file and ensure the token is correct.")
        
    except telegram.error.BadRequest as e:
        print(f"❌ Error: Bad Request - {e}")
        print("   This usually means one of two things:")
        print(f"   1. The channel username '{CHANNEL_USERNAME}' is incorrect or does not exist.")
        print("   2. The bot is NOT an Administrator of the channel.")
        print("      👉 FIX: Go to your Telegram Channel -> Manage Channel -> Administrators -> Add Administrator -> Search for your bot username -> Save.")
        
    except Exception as e:
        print(f"❌ Unexpected Error: {e}")
        print("   Check your internet connection and try again.")
        
    print("=" * 60)

if __name__ == "__main__":
    # Ensure correct asyncio execution
    asyncio.run(main())
