"""Quick test for undetected_chromedriver"""
import ssl
import os

ssl._create_default_https_context = ssl._create_unverified_context
os.environ['WDM_SSL_VERIFY'] = '0'

import undetected_chromedriver as uc

print("Testing undetected_chromedriver...")
print(f"Version: {uc.__version__}")

try:
    options = uc.ChromeOptions()
    options.add_argument("--no-first-run")
    options.add_argument("--disable-gpu")
    
    print("Creating Chrome instance...")
    driver = uc.Chrome(options=options, use_subprocess=True)
    print("Success! Browser opened")
    
    driver.get("https://www.google.com")
    print(f"Navigated to: {driver.current_url}")
    print(f"Title: {driver.title}")
    
    import time
    time.sleep(3)
    
    driver.quit()
    print("Browser closed successfully")
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
