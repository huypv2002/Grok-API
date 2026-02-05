"""Test headless với profile path như code chính"""
import undetected_chromedriver as uc
import time
from pathlib import Path

PROFILE_ID = "64dd1e20-b25b-47c7-a4cb-65161f79d5dc"
PROFILE_PATH = str(Path(f"data/profiles/{PROFILE_ID}").absolute())

print(f"Profile path: {PROFILE_PATH}")

def test_with_profile():
    print("\n=== Test: headless + user_data_dir ===")
    try:
        options = uc.ChromeOptions()
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--no-first-run")
        options.add_argument("--no-service-autorun")
        options.add_argument("--password-store=basic")
        
        driver = uc.Chrome(
            options=options,
            user_data_dir=PROFILE_PATH,
            headless=True,
        )
        time.sleep(3)
        
        driver.get("https://httpbin.org/headers")
        time.sleep(2)
        print(f"URL: {driver.current_url}")
        print("SUCCESS!")
        driver.quit()
    except Exception as e:
        print(f"FAILED: {e}")

if __name__ == "__main__":
    test_with_profile()
