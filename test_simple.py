"""Test undetected_chromedriver với chromedriver từ selenium cache"""
import ssl
import os
ssl._create_default_https_context = ssl._create_unverified_context
os.environ['WDM_SSL_VERIFY'] = '0'

import undetected_chromedriver as uc
import time

print("Opening browser...")

# Chromedriver path từ selenium cache
chromedriver_path = "/Users/phamvanhuy/.cache/selenium/chromedriver/mac-arm64/144.0.7559.133/chromedriver"

options = uc.ChromeOptions()
options.add_argument("--no-first-run")

driver = uc.Chrome(
    options=options,
    driver_executable_path=chromedriver_path,
    browser_executable_path="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
)

print("Browser opened!")
driver.get("https://www.google.com")
time.sleep(2)
print(f"URL: {driver.current_url}")

input("Press Enter to close...")
driver.quit()
