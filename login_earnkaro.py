import asyncio
import os
import sys
from playwright.async_api import async_playwright
import config

SESSION_FILE = "earnkaro_session.json"

async def run_otp_login():
    print("=" * 60)
    print("🔑 EARNKARO ONE-TIME OTP LOGIN SETUP 🔑")
    print("=" * 60)
    
    if not config.is_earnkaro_configured():
        print("❌ Error: EARNKARO_MOBILE_OR_EMAIL is not configured in your .env file!")
        print("   Please open '.env' and fill it in before running this script.")
        return
        
    print(f"📢 Target Mobile/Email: {config.EARNKARO_MOBILE_OR_EMAIL}")
    print("📡 Starting Playwright Chromium in headed mode...")
    
    async with async_playwright() as p:
        # Launch headed browser so user can see and complete OTP verification
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        
        try:
            page = await context.new_page()
            print("🔗 Navigating to EarnKaro login page...")
            await page.goto("https://earnkaro.com/login", timeout=45000, wait_until="networkidle")
            
            # Selectors for email/mobile field
            email_selectors = [
                'input[type="email"]',
                'input[name="email"]',
                'input[type="text"]',
                'input[placeholder*="Email"]',
                'input[placeholder*="email"]',
                'input[placeholder*="Mobile"]',
                'input[placeholder*="mobile"]'
            ]
            
            email_input = None
            for sel in email_selectors:
                inp = page.locator(sel).first
                if await inp.is_visible():
                    email_input = inp
                    break
                    
            if email_input:
                print("📝 Pre-filling your email/mobile in the form...")
                await email_input.click()
                await email_input.fill(config.EARNKARO_MOBILE_OR_EMAIL)
                
                # Attempt to click "Get OTP" or "Continue" automatically to trigger the OTP
                btn_selectors = [
                    'button:has-text("Get OTP")',
                    'button:has-text("GET OTP")',
                    'button:has-text("Continue")',
                    'button:has-text("CONTINUE")',
                    'button[type="submit"]',
                    'input[type="submit"]'
                ]
                
                otp_btn = None
                for sel in btn_selectors:
                    btn = page.locator(sel).first
                    if await btn.is_visible():
                        otp_btn = btn
                        break
                        
                if otp_btn:
                    print("⚡ Automatically requesting OTP...")
                    await otp_btn.click()
            else:
                print("⚠️ Could not locate the pre-fill email input field. Please fill it manually in the browser.")
                
            print("\n" + "*" * 60)
            print("👉 STEP 1: Enter the OTP sent to your phone/email in the browser window.")
            print("👉 STEP 2: Complete the login in the browser window.")
            print("👉 STEP 3: Auto-detection will save session once you complete login!")
            print("*" * 60 + "\n")
            
            # Auto-detection loop
            print("⏳ Waiting for you to complete the OTP verification in the browser window...")
            login_success = False
            for attempt in range(120): # Wait up to 120 seconds
                await asyncio.sleep(1.0)
                
                # Verify if we successfully logged in and navigated away from login page
                if "/make-links" in page.url or "/dashboard" in page.url:
                    print("✅ Successful login detected in browser!")
                    login_success = True
                    break
                    
                # Additional check: Is email input hidden and we are on earnkaro home/dashboard
                if "earnkaro.com" in page.url and "/login" not in page.url:
                    # Let's wait a second to confirm it's not a transient state
                    await asyncio.sleep(1.0)
                    if "/login" not in page.url:
                        print("✅ Successful login detected in browser!")
                        login_success = True
                        break
                        
            if login_success:
                # Save storage state to json file
                print(f"\n💾 Saving cookies and local storage state to '{SESSION_FILE}'...")
                await page.wait_for_timeout(2000) # Give 2s to write all tokens
                await context.storage_state(path=SESSION_FILE)
                print(f"🎉 SUCCESS! Session successfully saved to '{SESSION_FILE}'.")
                print("     You can now run the bot headlessly, and it will auto-load this session!")
            else:
                print("\n❌ Timeout: OTP login was not completed within 2 minutes.")
                print("   Please run the script again and complete login.")
            
        except Exception as e:
            print(f"❌ Unexpected Error: {e}")
        finally:
            await browser.close()
            print("=" * 60)

if __name__ == "__main__":
    asyncio.run(run_otp_login())
