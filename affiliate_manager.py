import os
import asyncio
import random
import base64
import json
from datetime import datetime
from playwright.async_api import async_playwright
import config

SESSION_FILE = "earnkaro_session.json"

def log_session(emoji: str, level: str, msg: str):
    import sys
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {emoji} [{level}] {msg}")
    sys.stdout.flush()

def restore_session_from_env() -> bool:
    """
    Reads the base64-encoded session state from the EARNKARO_SESSION_BASE64
    environment variable and recreates earnkaro_session.json automatically on startup.
    This allows running Playwright with a persistent OTP session on cloud platforms
    like Render without checking the session file into GitHub.
    """
    b64_data = os.getenv("EARNKARO_SESSION_BASE64")
    if not b64_data:
        log_session("ℹ️", "session restore failure", "No 'EARNKARO_SESSION_BASE64' environment variable found. Reusing local session file if exists.")
        return False
        
    log_session("📡", "session restore success", "EarnKaro session restoration started...")
    try:
        # Clean any whitespace or formatting from the base64 string
        clean_b64 = "".join(b64_data.split())
        
        # Decode the base64 data to bytes, then string
        decoded_bytes = base64.b64decode(clean_b64)
        decoded_str = decoded_bytes.decode("utf-8")
        
        # Verify it's a valid JSON block
        json.loads(decoded_str)
        
        # Write the decoded JSON back to earnkaro_session.json
        with open(SESSION_FILE, "w", encoding="utf-8") as f:
            f.write(decoded_str)
            
        # Log session restored successfully
        log_session("✅", "session restore success", f"EarnKaro session restored successfully! Recreated '{SESSION_FILE}' file.")
        return True
    except base64.binascii.Error as e:
        log_session("❌", "session restore failure", f"Invalid Base64 format: {e}")
    except json.JSONDecodeError as e:
        log_session("❌", "session restore failure", f"Decoded text is not a valid JSON structure: {e}")
    except Exception as e:
        log_session("❌", "session restore failure", f"Session recreation failed: {e}")
    return False

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
        log_session("⚠️", "session restore failure", "EarnKaro credentials not configured in .env. Falling back to original URL.")
        return product_url

    # Check if saved OTP session file exists
    if not os.path.exists(SESSION_FILE):
        log_session("❌", "session restore failure", f"'{SESSION_FILE}' not found! Falling back to original product URL.")
        log_session("👉", "session restore info", "To activate automated affiliate links, please run this setup command locally first:")
        log_session("👉", "session restore info", "   python login_earnkaro.py")
        return product_url

    log_session("🔗", "affiliate generation started", f"Attempting session-based conversion for: '{product_url}'")
    
    async with async_playwright() as p:
        try:
            log_session("🤖", "Playwright active", "Launching headless browser context...")
            browser = await p.chromium.launch(headless=True)
        except Exception as launch_err:
            log_session("❌", "Playwright failure", f"Failed to launch Playwright browser: {launch_err}")
            return product_url
        
        try:
            # Create a context loading the saved storage state (cookies, localStorage)
            log_session("💾", "session restore success", f"Loading saved session state from '{SESSION_FILE}'...")
            context = await browser.new_context(
                storage_state=SESSION_FILE,
                viewport={"width": 1280, "height": 800},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            
            page = await context.new_page()
            
            # Step 1: Navigating directly to Make Links page
            log_session("📡", "website scanning", "Navigating directly to EarnKaro 'Make Links' page...")
            await page.goto("https://earnkaro.com/create-earn-link", timeout=30000, wait_until="load")
            await asyncio.sleep(random.uniform(1.5, 3.0))
            
            # Step 2: Session Validation (check if redirected to login)
            if "/login" in page.url:
                log_session("❌", "EarnKaro session expired", "Persisted EarnKaro OTP session is expired or invalid!")
                log_session("👉", "session restore info", "Please refresh your login session by running 'python login_earnkaro.py' locally.")
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
                log_session("❌", "selector missing", "Could not locate the 'Make Links' input textarea/input field.")
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
                log_session("❌", "selector missing", "Could not locate the 'Make Profit Link' conversion button.")
                raise Exception("Could not locate the 'Make Profit Link' conversion button.")
                
            log_session("🔗", "affiliate generation started", "Clicking the 'Make Profit Link' conversion button...")
            await convert_btn.click()
            
            # Step 5: Wait for generated profit link
            log_session("⏳", "affiliate generation started", "Waiting for profit link generation to complete...")
            
            generated_link = None
            # Wait for input#deallinkshorturl to be visible and have a value
            try:
                # Wait for up to 12 seconds for the element to appear and be loaded
                await page.wait_for_selector("input#deallinkshorturl", state="visible", timeout=12000)
                
                # Poll for up to 10 seconds for a non-empty value in the input
                for attempt in range(20):
                    val = await page.locator("input#deallinkshorturl").get_attribute("value")
                    if val and val.strip().startswith("http"):
                        generated_link = val.strip()
                        break
                    await page.wait_for_timeout(500)
            except Exception as e:
                log_session("⚠️", "selector missing", f"Direct selector wait for 'input#deallinkshorturl' failed: {e}. Trying generic fallbacks...")
                
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
                log_session("❌", "selector missing", "Affiliate link generation timed out or link selector is missing.")
                raise Exception("Affiliate link generation timed out or selectors failed.")
                
            log_session("✅", "affiliate link generated", f"Successfully converted to affiliate link: '{generated_link}'")
            return generated_link
            
        except Exception as e:
            if "Persisted OTP session expired" in str(e):
                log_session("❌", "EarnKaro session expired", "EarnKaro session expired. Skipping affiliate generation.")
            else:
                log_session("❌", "Playwright failure", f"EarnKaro affiliate automation failed: {e}")
            log_session("⚠️", "affiliate generation failed", f"Falling back to original product URL: {product_url}")
            return product_url
        finally:
            await browser.close()

async def generate_affiliate_link(product_url: str) -> str:
    """
    Alias for get_affiliate_link to support user integration requirements.
    """
    return await get_affiliate_link(product_url)
