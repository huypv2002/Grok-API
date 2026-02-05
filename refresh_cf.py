#!/usr/bin/env python3
"""Refresh cf_clearance using existing browser profile"""
import json
from pathlib import Path
from src.core.browser_controller import BrowserController

print("=" * 60)
print("Refresh cf_clearance using Browser Profile")
print("=" * 60)

# Load accounts
accounts_file = Path("data/accounts.json")
with open(accounts_file) as f:
    data = json.load(f)

accounts = data.get("accounts", [])
if not accounts:
    print("❌ No accounts found")
    exit(1)

# Use first account
account = accounts[0]
fingerprint_id = account.get("fingerprint_id")
email = account.get("email")

print(f"Using account: {email}")
print(f"Profile: {fingerprint_id}")

# Open browser with existing profile
controller = BrowserController(fingerprint_id)

try:
    print("\n→ Opening browser with existing profile...")
    controller.open_browser(headless=False, small_window=False)
    
    print("→ Navigating to grok.com...")
    controller.navigate_to("https://grok.com", wait_time=3)
    
    print("→ Waiting for Cloudflare challenge...")
    cf_clearance = controller.refresh_cf_clearance(timeout=60)
    
    if cf_clearance:
        print(f"\n✅ Got cf_clearance: {cf_clearance[:50]}...")
        
        # Update all accounts with new cf_clearance
        for acc in accounts:
            cookies = acc.get("cookies", {})
            cookies["cf_clearance"] = cf_clearance
            acc["cookies"] = cookies
        
        # Save
        with open(accounts_file, "w") as f:
            json.dump(data, f, indent=2)
        
        print("✅ Updated accounts.json")
        
        # Also get all cookies
        all_cookies = controller.get_cookies()
        print(f"\nAll cookies: {list(all_cookies.keys())}")
    else:
        print("\n❌ Failed to get cf_clearance")

finally:
    print("\n→ Closing browser...")
    controller.close_browser()
    print("Done!")
