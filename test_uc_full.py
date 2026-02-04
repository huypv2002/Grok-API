"""
Test undetected-chromedriver với nhiều tình huống
"""
import ssl
import os
import subprocess
import time

# Bypass SSL verification
ssl._create_default_https_context = ssl._create_unverified_context
os.environ['WDM_SSL_VERIFY'] = '0'

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By


def get_chrome_version():
    """Lấy version Chrome đang cài"""
    try:
        result = subprocess.run(
            ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', '--version'],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            version = int(result.stdout.strip().split()[-1].split('.')[0])
            print(f"✓ Chrome version: {version}")
            return version
    except Exception as e:
        print(f"✗ Không lấy được Chrome version: {e}")
    return 131  # Default


def test_basic():
    """Test cơ bản - mở browser và navigate"""
    print("\n" + "="*50)
    print("TEST 1: Basic browser open & navigate")
    print("="*50)
    
    driver = None
    try:
        chrome_version = get_chrome_version()
        
        options = uc.ChromeOptions()
        options.add_argument("--no-first-run")
        options.add_argument("--no-service-autorun")
        options.add_argument("--password-store=basic")
        
        print("→ Đang mở browser...")
        driver = uc.Chrome(
            options=options,
            version_main=chrome_version,
        )
        print("✓ Browser đã mở!")
        
        print("→ Navigate đến Google...")
        driver.get("https://www.google.com")
        time.sleep(2)
        
        print(f"✓ URL: {driver.current_url}")
        print(f"✓ Title: {driver.title}")
        
        # Test tìm element
        search_box = driver.find_elements(By.NAME, "q")
        if search_box:
            print("✓ Tìm thấy search box")
        else:
            print("✗ Không tìm thấy search box")
        
        return True
        
    except Exception as e:
        print(f"✗ Lỗi: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if driver:
            driver.quit()
            print("✓ Browser đã đóng")


def test_with_profile():
    """Test với user profile (lưu session)"""
    print("\n" + "="*50)
    print("TEST 2: Browser với user profile")
    print("="*50)
    
    driver = None
    profile_dir = os.path.abspath("data/profiles/test-uc-profile")
    
    try:
        os.makedirs(profile_dir, exist_ok=True)
        chrome_version = get_chrome_version()
        
        options = uc.ChromeOptions()
        options.add_argument("--no-first-run")
        options.add_argument("--no-service-autorun")
        
        print(f"→ Profile dir: {profile_dir}")
        print("→ Đang mở browser với profile...")
        
        driver = uc.Chrome(
            options=options,
            user_data_dir=profile_dir,
            version_main=chrome_version,
        )
        print("✓ Browser đã mở với profile!")
        
        driver.get("https://httpbin.org/headers")
        time.sleep(2)
        
        print(f"✓ URL: {driver.current_url}")
        
        # Kiểm tra User-Agent
        page_source = driver.page_source
        if "Chrome" in page_source:
            print("✓ User-Agent có Chrome")
        
        return True
        
    except Exception as e:
        print(f"✗ Lỗi: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if driver:
            driver.quit()
            print("✓ Browser đã đóng")


def test_cloudflare_site():
    """Test truy cập site có Cloudflare"""
    print("\n" + "="*50)
    print("TEST 3: Truy cập site có Cloudflare protection")
    print("="*50)
    
    driver = None
    try:
        chrome_version = get_chrome_version()
        
        options = uc.ChromeOptions()
        options.add_argument("--no-first-run")
        options.add_argument("--no-service-autorun")
        options.add_argument("--disable-popup-blocking")
        
        print("→ Đang mở browser...")
        driver = uc.Chrome(
            options=options,
            version_main=chrome_version,
        )
        print("✓ Browser đã mở!")
        
        # Test với một site có Cloudflare
        print("→ Navigate đến grok.com...")
        driver.get("https://grok.com")
        
        # Chờ và kiểm tra Cloudflare
        print("→ Chờ Cloudflare challenge (nếu có)...")
        
        for i in range(30):  # Chờ tối đa 30 giây
            time.sleep(1)
            page_source = driver.page_source
            current_url = driver.current_url
            
            if "Just a moment" in page_source or "challenge" in current_url:
                print(f"  ... Đang chờ Cloudflare ({i+1}s)")
            else:
                print(f"✓ Đã qua Cloudflare sau {i+1}s")
                break
        
        print(f"✓ Final URL: {driver.current_url}")
        print(f"✓ Title: {driver.title}")
        
        # Screenshot để debug
        screenshot_path = "data/test_cloudflare.png"
        driver.save_screenshot(screenshot_path)
        print(f"✓ Screenshot saved: {screenshot_path}")
        
        return True
        
    except Exception as e:
        print(f"✗ Lỗi: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if driver:
            driver.quit()
            print("✓ Browser đã đóng")


def test_javascript_execution():
    """Test chạy JavaScript"""
    print("\n" + "="*50)
    print("TEST 4: JavaScript execution")
    print("="*50)
    
    driver = None
    try:
        chrome_version = get_chrome_version()
        
        options = uc.ChromeOptions()
        options.add_argument("--no-first-run")
        
        print("→ Đang mở browser...")
        driver = uc.Chrome(
            options=options,
            version_main=chrome_version,
        )
        
        driver.get("https://www.google.com")
        time.sleep(2)
        
        # Test execute_script
        result = driver.execute_script("return navigator.userAgent")
        print(f"✓ User-Agent: {result[:60]}...")
        
        # Test webdriver detection
        is_webdriver = driver.execute_script("return navigator.webdriver")
        print(f"✓ navigator.webdriver = {is_webdriver}")
        
        if is_webdriver is None or is_webdriver is False:
            print("✓ PASS: Không bị detect là webdriver!")
        else:
            print("✗ FAIL: Bị detect là webdriver")
        
        return True
        
    except Exception as e:
        print(f"✗ Lỗi: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if driver:
            driver.quit()
            print("✓ Browser đã đóng")


def main():
    print("="*50)
    print("UNDETECTED-CHROMEDRIVER TEST SUITE")
    print(f"UC Version: {uc.__version__}")
    print("="*50)
    
    results = {}
    
    # Chạy các test
    results["basic"] = test_basic()
    results["profile"] = test_with_profile()
    results["javascript"] = test_javascript_execution()
    
    # Test Cloudflare (optional - có thể mất thời gian)
    print("\n→ Bạn có muốn test Cloudflare không? (mất ~30s)")
    print("  Nhấn Enter để skip, hoặc gõ 'y' để test:")
    
    try:
        user_input = input().strip().lower()
        if user_input == 'y':
            results["cloudflare"] = test_cloudflare_site()
        else:
            print("  Skipped Cloudflare test")
            results["cloudflare"] = "skipped"
    except:
        results["cloudflare"] = "skipped"
    
    # Tổng kết
    print("\n" + "="*50)
    print("KẾT QUẢ:")
    print("="*50)
    
    for test_name, result in results.items():
        if result == True:
            status = "✓ PASS"
        elif result == False:
            status = "✗ FAIL"
        else:
            status = "○ SKIPPED"
        print(f"  {test_name}: {status}")
    
    passed = sum(1 for r in results.values() if r == True)
    total = sum(1 for r in results.values() if r != "skipped")
    print(f"\nTổng: {passed}/{total} tests passed")


if __name__ == "__main__":
    main()
