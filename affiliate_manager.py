import os
import asyncio
import random
from playwright.async_api import async_playwright
import config

SESSION_FILE = "earnkaro_session.json"

async def get_affiliate_link(product_url: str) -> str:
    """
    Automates the EarnKaro workflow using Playwright with saved OTP sessions:
    1. Checks if earnkaro_session.json exists.
    2. Opens browser headlessly loading the storage state.
    3. Navigates directly to "Make Links" page.
    4. Detects if redirected to login (meaning session expired).
    5. Inputs e-commerce product URL, triggers conversion, and copies link.
    Falls back gracefully to product_url if any failure occurs.
    """
    if not config.is_earnkaro_configured():
        print("⚠️ EarnKaro: Credentials not configured in .env. Falling back to original URL.")
        return product_url

    # Check if saved OTP session file exists
    if not os.path.exists(SESSION_FILE):
        print(f"⚠️ EarnKaro: '{SESSION_FILE}' not found!")
        print("   👉 To activate automated affiliate links, please run this setup command in your terminal first:")
        print("      venv\\Scripts\\python login_earnkaro.py")
        print("   Falling back to original product URL.")
        return product_url

    print(f"\n📡 EarnKaro Automation: Attempting session-based conversion for: '{product_url}'")
    
    async with async_playwright() as p:
        # Launch Chromium browser
        browser = await p.chromium.launch(headless=True)
        
        try:
            # Create a context loading the saved storage state (cookies, localStorage)
            print(f"💾 EarnKaro: Loading saved session from '{SESSION_FILE}'...")
            context = await browser.new_context(
                storage_state=SESSION_FILE,
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            
            page = await context.new_page()
            
            # Step 1: Navigating directly to Make Links page
            print("🔗 EarnKaro: Navigating directly to Make Links page...")
            await page.goto("https://earnkaro.com/create-earn-link", timeout=30000, wait_until="load")
            await asyncio.sleep(random.uniform(1.5, 3.0))
            
            # Step 2: Session Validation (check if redirected to login)
            if "/login" in page.url:
                print("⚠️ EarnKaro: Saved session has EXPIRED or is invalid!")
                print("   👉 Please refresh your OTP login session by running this command in your terminal:")
                print("      venv\\Scripts\\python login_earnkaro.py")
                raise Exception("Persisted OTP session expired.")
                
            # Step 3: Input the product URL in the textarea
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
                raise Exception("Could not locate the 'Make Links' input textarea/input field.")
                
            await textarea.click()
            await page.wait_for_timeout(300)
            await textarea.fill(product_url)
            await asyncio.sleep(random.uniform(1.0, 2.0))
            
            # Step 4: Click the conversion button
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
                raise Exception("Could not locate the 'Make Profit Link' conversion button.")
                
            print("🔗 EarnKaro: Clicking conversion button...")
            await convert_btn.click()
            
            # Step 5: Wait for generated profit link
            print("🔗 EarnKaro: Waiting for profit link generation...")
            
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
                print(f"⚠️ EarnKaro: Direct selector wait failed: {e}. Trying generic fallbacks...")
                
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
                        
            if not generated_link:
                raise Exception("Affiliate link generation timed out or selectors failed.")
                
            print(f"🎉 EarnKaro SUCCESS: Successfully converted to affiliate link: '{generated_link}'")
            return generated_link
            
        except Exception as e:
            print(f"❌ EarnKaro Error: Link generation failed: {e}")
            print("⚠️ Falling back to original product URL.")
            return product_url
        finally:
            await browser.close()

async def generate_affiliate_link(product_url: str) -> str:
    """
    Alias for get_affiliate_link to support user integration requirements.
    """
    return await get_affiliate_link(product_url)
