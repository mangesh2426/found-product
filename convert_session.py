import base64
import os

SESSION_FILE = "earnkaro_session.json"

def main():
    print("=" * 60)
    print("📦 EARNKARO SESSION BASE64 ENCODER TOOL 📦")
    print("=" * 60)
    
    if not os.path.exists(SESSION_FILE):
        print(f"❌ Error: '{SESSION_FILE}' not found in the current directory.")
        print("   Please run 'login_earnkaro.py' first to generate your session file.")
        print("=" * 60)
        return
        
    try:
        # Read session content
        with open(SESSION_FILE, "r", encoding="utf-8") as f:
            session_data = f.read().strip()
            
        # Encode to Base64
        b64_bytes = base64.b64encode(session_data.encode("utf-8"))
        b64_str = b64_bytes.decode("utf-8")
        
        # Save to a text file for easy copying
        output_file = "earnkaro_base64.txt"
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(b64_str)
            
        print("✅ SUCCESS! Your session has been converted to Base64.")
        print(f"\n📁 The encoded text has been saved to: {output_file}")
        print("\n👉 To use this on Render:")
        print("1. Open 'earnkaro_base64.txt' and copy its entire text content.")
        print("2. Go to your Render Dashboard -> Environment Variables.")
        print("3. Add a new variable named: EARNKARO_SESSION_BASE64")
        print("4. Paste the copied text as the value and save!")
        print("=" * 60)
    except Exception as e:
        print(f"❌ Error during conversion: {e}")
        print("=" * 60)

if __name__ == "__main__":
    main()
