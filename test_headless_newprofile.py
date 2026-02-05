"""Test headless với profile MỚI"""
import undetected_chromedriver as uc
import time
from pathlib import Path
import shutil

# Tạo profile mới hoàn toàn
NEW_PROFILE = str(Path("data/profiles/test-headless-new").absolute())

# Xóa nếu tồn tại
if Path(NEW_PROFILE).exists():
    shutil.rmtree(NEW_PROFILE)
Path(NEW_PROFILE).mkdir(parents=True, exist_ok=True)

print(f"New profile path: {NEW_PROFILE}")

def test_new_profile():
    print("\n=== Test: headless + NEW profile ===")
    try:
        options = uc.ChromeOptions()
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        
        driver = uc.Chrome(
            options=options,
            user_data_dir=NEW_PROFILE,
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
    test_new_profile()
