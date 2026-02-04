"""Test browser download"""
import time
import ssl
import os

# Fix SSL
ssl._create_default_https_context = ssl._create_unverified_context
os.environ['WDM_SSL_VERIFY'] = '0'

import undetected_chromedriver as uc

def test_browser():
    print("Opening browser...")
    
    options = uc.ChromeOptions()
    options.add_argument("--no-first-run")
    options.add_argument("--disable-popup-blocking")
    
    driver = uc.Chrome(options=options)
    print("Browser opened!")
    
    try:
        print("Navigating to grok.com/imagine...")
        driver.get("https://grok.com/imagine")
        
        print(f"Current URL: {driver.current_url}")
        print("Waiting 30 seconds...")
        time.sleep(30)
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        print("Closing browser...")
        driver.quit()
        print("Done!")

if __name__ == "__main__":
    test_browser()
