"""Test headless mode với undetected_chromedriver"""
import undetected_chromedriver as uc
import time

def test_headless():
    print("=== Test 1: headless=True parameter ===")
    try:
        options = uc.ChromeOptions()
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        
        driver = uc.Chrome(options=options, headless=True)
        time.sleep(2)
        
        driver.get("https://httpbin.org/headers")
        time.sleep(2)
        print(f"URL: {driver.current_url}")
        print(f"Title: {driver.title}")
        print("Test 1: SUCCESS")
        driver.quit()
    except Exception as e:
        print(f"Test 1 FAILED: {e}")

def test_headless_new():
    print("\n=== Test 2: --headless=new argument ===")
    try:
        options = uc.ChromeOptions()
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        
        driver = uc.Chrome(options=options)
        time.sleep(2)
        
        driver.get("https://httpbin.org/headers")
        time.sleep(2)
        print(f"URL: {driver.current_url}")
        print(f"Title: {driver.title}")
        print("Test 2: SUCCESS")
        driver.quit()
    except Exception as e:
        print(f"Test 2 FAILED: {e}")

def test_no_headless():
    print("\n=== Test 3: No headless (normal) ===")
    try:
        options = uc.ChromeOptions()
        options.add_argument("--window-size=400,300")
        
        driver = uc.Chrome(options=options)
        time.sleep(2)
        
        driver.get("https://httpbin.org/headers")
        time.sleep(2)
        print(f"URL: {driver.current_url}")
        print(f"Title: {driver.title}")
        print("Test 3: SUCCESS")
        driver.quit()
    except Exception as e:
        print(f"Test 3 FAILED: {e}")

if __name__ == "__main__":
    test_headless()
    test_headless_new()
    test_no_headless()
    print("\n=== Done ===")
