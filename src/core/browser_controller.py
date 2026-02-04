"""Browser Controller - Simple undetected ChromeDriver"""
import time
import os
import subprocess
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from typing import Optional
from pathlib import Path

LOGIN_URL = "https://accounts.x.ai/sign-in?redirect=grok-com&email=true"
PROFILES_DIR = Path("data/profiles")


class BrowserController:
    def __init__(self, fingerprint_id: str):
        self.fingerprint_id = fingerprint_id
        self.driver: Optional[uc.Chrome] = None
        self.profile_dir = PROFILES_DIR / fingerprint_id
    
    def open_browser(self, headless: bool = False) -> uc.Chrome:
        """Open Chrome browser - simple version"""
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        profile_path = str(self.profile_dir.absolute())
        
        # Get Chrome version
        chrome_version = 144
        try:
            result = subprocess.run(
                ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', '--version'],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                chrome_version = int(result.stdout.strip().split()[-1].split('.')[0])
        except:
            pass
        
        print(f"Opening browser with Chrome {chrome_version}...")
        
        # Simple options
        options = uc.ChromeOptions()
        options.add_argument("--no-first-run")
        options.add_argument("--no-service-autorun") 
        options.add_argument("--password-store=basic")
        options.add_argument("--disable-popup-blocking")
        
        # Create driver
        self.driver = uc.Chrome(
            options=options,
            user_data_dir=profile_path,
            version_main=chrome_version,
        )
        
        print("Browser opened successfully!")
        return self.driver
    
    def navigate_to(self, url: str, wait_time: int = 5) -> None:
        """Navigate to URL"""
        if self.driver:
            print(f"Navigating to: {url}")
            self.driver.get(url)
            time.sleep(wait_time)
            print(f"Current URL: {self.driver.current_url}")
    
    def fill_input(self, selector: str, value: str, by: str = By.CSS_SELECTOR) -> None:
        """Fill input field"""
        if self.driver:
            element = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((by, selector))
            )
            element.clear()
            element.send_keys(value)
    
    def click_button(self, selector: str, by: str = By.CSS_SELECTOR) -> None:
        """Click button"""
        if self.driver:
            element = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((by, selector))
            )
            element.click()
    
    def wait_for_element(self, selector: str, timeout: int = 30, by: str = By.CSS_SELECTOR) -> bool:
        """Wait for element"""
        if self.driver:
            try:
                WebDriverWait(self.driver, timeout).until(
                    EC.presence_of_element_located((by, selector))
                )
                return True
            except:
                return False
        return False
    
    def get_cookies(self) -> dict:
        """Get cookies"""
        if self.driver:
            cookies = self.driver.get_cookies()
            return {c['name']: c['value'] for c in cookies}
        return {}
    
    def set_cookies(self, cookies: dict, domain: str = ".grok.com") -> None:
        """Set cookies"""
        if self.driver:
            for name, value in cookies.items():
                try:
                    self.driver.add_cookie({
                        'name': name,
                        'value': str(value),
                        'domain': domain,
                        'path': '/'
                    })
                except Exception as e:
                    print(f"Cookie error {name}: {e}")
    
    def close_browser(self) -> None:
        """Close browser"""
        if self.driver:
            try:
                self.driver.quit()
            except:
                pass
            self.driver = None
    
    def get_current_url(self) -> str:
        """Get current URL"""
        if self.driver:
            return self.driver.current_url
        return ""
    
    def get_page_source(self) -> str:
        """Get page source"""
        if self.driver:
            return self.driver.page_source
        return ""
    
    def find_element(self, selector: str, by: str = By.CSS_SELECTOR):
        """Find element"""
        if self.driver:
            try:
                return self.driver.find_element(by, selector)
            except:
                return None
        return None
    
    def find_elements(self, selector: str, by: str = By.CSS_SELECTOR):
        """Find elements"""
        if self.driver:
            try:
                return self.driver.find_elements(by, selector)
            except:
                return []
        return []
    
    def execute_script(self, script: str, *args):
        """Execute JavaScript"""
        if self.driver:
            return self.driver.execute_script(script, *args)
        return None
    
    def send_keys(self, keys: str) -> None:
        """Send keys"""
        if self.driver:
            from selenium.webdriver.common.action_chains import ActionChains
            actions = ActionChains(self.driver)
            actions.send_keys(keys)
            actions.perform()
    
    def screenshot(self, filename: str = "screenshot.png") -> str:
        """Take screenshot"""
        if self.driver:
            path = Path("data") / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            self.driver.save_screenshot(str(path))
            return str(path)
        return ""
