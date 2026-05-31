import asyncio
import os
import sys
import random
from playwright.async_api import async_playwright

# Load configuration if possible to check setup
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import config

SESSION_FILE = "earnkaro_session.json"
TEST_MYNTRA_URL = "https://www.myntra.com/1364628" # Hardcoded Myntra product URL

async def run_affiliate_test():
    print("=" * 60)
    print("🧪 EARNKARO AFFILIATE AUTOMATION STANDALONE TEST 🧪")
    print("=" * 60)
    
    # Check if session file exists
    if not os.path.exists(SESSION_FILE):
        print(f"❌ Error: '{SESSION_FILE}' not found in the directory!")
        print("   👉 Please run the OTP login setup script first:")
        print("      venv\\Scripts\\python login_earnkaro.py")
        print("   Then run this test script again.")
        print("=" * 60)
        return

    print(f"📡 Test Product URL: '{TEST_MYNTRA_URL}'")
    print(f"💾 Loading session state from '{SESSION_FILE}'...")
    
    # Initialize Playwright
    async with async_playwright() as p:
        # Launch headed browser so you can visually see the automation happening
        print("\n🚀 [STEP 1/7] Launching Chromium browser in headed mode...")
        browser = await p.chromium.launch(headless=False, slow_mo=1000) # 1000ms slow_mo adds delays between actions
        
        try:
            # Create browser context with saved storage state
            print("🔐 [STEP 2/7] Loading saved session cookies and state...")
            context = await browser.new_context(
                storage_state=SESSION_FILE,
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            
            page = await context.new_page()
            
            # Navigate to Make Links page
            print("🔗 [STEP 3/7] Navigating to EarnKaro 'Make Links' page...")
            await page.goto("https://earnkaro.com/create-earn-link", timeout=30000, wait_until="networkidle")
            await page.wait_for_timeout(2000) # Visual delay
            
            # Check if session is expired (redirected to login)
            if "/login" in page.url:
                print("\n❌ Error: Session expired! Redirected to login page.")
                print("   👉 Please refresh your OTP login session by running:")
                print("      venv\\Scripts\\python login_earnkaro.py")
                return
                
            print("✅ Login/Session check successful (dashboard active)!")
            
            # Locate input area
            print("📝 [STEP 4/7] Locating input area and pasting test Myntra URL...")
            textarea_selectors = [
                'input#deallink',
                'input[name="deallink"]',
                '#deallink',
                'textarea',
                'input[placeholder*="Paste"]'
            ]
            
            textarea = None
            for sel in textarea_selectors:
                inp = page.locator(sel).first
                if await inp.is_visible():
                    textarea = inp
                    break
                    
            if not textarea:
                print("❌ Error: Could not locate the 'Make Links' text area/input selector.")
                return
                
            # Click and fill URL with visual delay
            await textarea.click()
            await page.wait_for_timeout(500)
            await textarea.fill(TEST_MYNTRA_URL)
            await page.wait_for_timeout(2000) # Visual delay so user can see pasted URL
            
            # Click conversion button
            print("⚡ [STEP 5/7] Locating and clicking 'Make Profit Link' button...")
            btn_selectors = [
                'button#Btn_Make_Profit_Button',
                '#Btn_Make_Profit_Button',
                'button:has-text("Make Profit Link")',
                'button:has-text("MAKE PROFIT LINK")',
                'button.showdealpp'
            ]
            
            convert_btn = None
            for sel in btn_selectors:
                btn = page.locator(sel).first
                if await btn.is_visible():
                    convert_btn = btn
                    break
                    
            if not convert_btn:
                print("❌ Error: Could not locate the 'Make Profit Link' conversion button.")
                return
                
            await convert_btn.click()
            
            # Wait for generated link
            print("⏳ [STEP 6/7] Waiting for affiliate link generation...")
            
            generated_link = None
            # Wait for input#deallinkshorturl to be visible and have a value
            try:
                # Wait for up to 10 seconds for the element to appear and be loaded
                await page.wait_for_selector("input#deallinkshorturl", state="visible", timeout=12000)
                
                # Poll for up to 10 seconds for a non-empty value in the input
                for attempt in range(20):
                    val = await page.locator("input#deallinkshorturl").get_attribute("value")
                    if val and val.strip().startswith("http"):
                        generated_link = val.strip()
                        break
                    await page.wait_for_timeout(500)
            except Exception as e:
                print(f"⚠️ Direct selector wait failed: {e}. Trying generic fallbacks...")
                
            # Generic fallbacks if direct ID check fails
            if not generated_link:
                # Poll for up to 10 seconds
                for attempt in range(20):
                    await page.wait_for_timeout(500)
                    
                    # Check any text inputs containing http
                    inputs = await page.locator('input[type="text"]').all()
                    for inp in inputs:
                        val = await inp.get_attribute("value")
                        # Ignore the source input #deallink
                        el_id = await inp.get_attribute("id")
                        if el_id == "deallink":
                            continue
                        if val and val.strip().startswith("http"):
                            generated_link = val.strip()
                            break
                    if generated_link:
                        break
            
            # Output Results
            print("🎉 [STEP 7/7] Finalizing extraction...")
            await page.wait_for_timeout(2000) # Let browser stay open a bit for viewing
            
            print("\n" + "=" * 60)
            if generated_link:
                print("✅ GENERATED AFFILIATE LINK SUCCESSFUL!")
                print("\nGENERATED AFFILIATE LINK:")
                print(generated_link)
            else:
                print("❌ Error: Affiliate link generation timed out or selectors failed.")
            print("=" * 60 + "\n")
            
        except Exception as e:
            print(f"\n❌ Unexpected Browser Automation Error: {e}")
        finally:
            print("👋 Closing headed browser. Test completed.")
            await browser.close()
            print("=" * 60)

if __name__ == "__main__":
    # Ensure correct asyncio loop execution
    asyncio.run(run_affiliate_test())
