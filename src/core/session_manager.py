"""Session Manager - Login flow and cookie management using undetected_chromedriver"""
import time
from datetime import datetime
from typing import Optional, Callable
from uuid import uuid4
from selenium.webdriver.common.by import By
from .models import Account
from .browser_controller import BrowserController, LOGIN_URL

REQUIRED_COOKIES = ['sso', 'sso-rw', 'x-userid', 'cf_clearance']

class SessionManager:
    def __init__(self):
        self.browser_controllers: dict[str, BrowserController] = {}
    
    def login(self, account: Account, password: str, on_status: Callable = None) -> bool:
        """Full login flow for an account (synchronous)"""
        controller = BrowserController(account.fingerprint_id)
        self.browser_controllers[account.email] = controller
        
        try:
            if on_status:
                on_status("Opening browser...")
            controller.open_browser(headless=False)
            
            if on_status:
                on_status("Navigating to login page...")
            controller.navigate_to(LOGIN_URL, wait_time=5)
            
            # Wait for email input
            if on_status:
                on_status("Waiting for login form...")
            if not controller.wait_for_element('input[name="email"]', timeout=15):
                raise Exception("Email field not found")
            
            # Fill email
            if on_status:
                on_status("Filling email...")
            controller.fill_input('input[name="email"]', account.email)
            time.sleep(1)
            
            # Click Next
            if on_status:
                on_status("Clicking Next...")
            controller.click_button('button[type="submit"]')
            time.sleep(2)
            
            # Wait for password field
            if on_status:
                on_status("Waiting for password field...")
            if not controller.wait_for_element('input[name="password"]', timeout=15):
                raise Exception("Password field not found")
            
            # Fill password
            if on_status:
                on_status("Filling password...")
            controller.fill_input('input[name="password"]', password)
            time.sleep(1)
            
            # Handle Turnstile if present
            if on_status:
                on_status("Checking for Cloudflare challenge...")
            controller.handle_turnstile(timeout=60)
            
            # Click Login
            if on_status:
                on_status("Clicking Login...")
            controller.click_button('button[type="submit"]')
            
            # Wait for redirect
            if on_status:
                on_status("Waiting for login completion...")
            time.sleep(5)
            
            # Check if logged in - kiểm tra nhiều điều kiện
            current_url = controller.get_current_url()
            cookies = controller.get_cookies()
            
            if on_status:
                on_status(f"URL: {current_url}")
            
            # Login thành công nếu:
            # 1. URL chứa grok.com hoặc x.ai
            # 2. Hoặc có cookie sso/sso-rw
            is_logged_in = (
                'grok.com' in current_url or 
                'x.ai' in current_url or
                'sso' in cookies or 
                'sso-rw' in cookies
            )
            
            if is_logged_in:
                account.cookies = cookies
                account.status = "logged_in"
                account.last_login = datetime.now()
                if on_status:
                    on_status("Login successful!")
                return True
            
            account.status = "error"
            account.error_message = f"Login failed - URL: {current_url}"
            return False
            
        except Exception as e:
            account.status = "error"
            account.error_message = str(e)
            if on_status:
                on_status(f"Error: {e}")
            return False
        finally:
            controller.close_browser()
    
    def login_and_keep_open(self, account: Account, password: str, on_status: Callable = None) -> Optional[BrowserController]:
        """Login and return browser controller (keep browser open)"""
        controller = BrowserController(account.fingerprint_id)
        self.browser_controllers[account.email] = controller
        
        try:
            if on_status:
                on_status("Opening browser...")
            controller.open_browser(headless=False)
            
            if on_status:
                on_status("Navigating to login page...")
            controller.navigate_to(LOGIN_URL, wait_time=5)
            
            # Wait for email input
            if on_status:
                on_status("Waiting for login form...")
            if not controller.wait_for_element('input[name="email"]', timeout=15):
                raise Exception("Email field not found")
            
            # Fill email
            if on_status:
                on_status("Filling email...")
            controller.fill_input('input[name="email"]', account.email)
            time.sleep(1)
            
            # Click Next
            if on_status:
                on_status("Clicking Next...")
            controller.click_button('button[type="submit"]')
            time.sleep(2)
            
            # Wait for password field
            if on_status:
                on_status("Waiting for password field...")
            if not controller.wait_for_element('input[name="password"]', timeout=15):
                raise Exception("Password field not found")
            
            # Fill password
            if on_status:
                on_status("Filling password...")
            controller.fill_input('input[name="password"]', password)
            time.sleep(1)
            
            # Handle Turnstile if present
            if on_status:
                on_status("Checking for Cloudflare challenge...")
            controller.handle_turnstile(timeout=60)
            
            # Click Login
            if on_status:
                on_status("Clicking Login...")
            controller.click_button('button[type="submit"]')
            
            # Wait for redirect
            if on_status:
                on_status("Waiting for login completion...")
            time.sleep(5)
            
            # Check if logged in - kiểm tra nhiều điều kiện
            current_url = controller.get_current_url()
            cookies = controller.get_cookies()
            
            if on_status:
                on_status(f"URL: {current_url}")
            
            # Login thành công nếu:
            # 1. URL chứa grok.com hoặc x.ai
            # 2. Hoặc có cookie sso/sso-rw
            is_logged_in = (
                'grok.com' in current_url or 
                'x.ai' in current_url or
                'sso' in cookies or 
                'sso-rw' in cookies
            )
            
            if is_logged_in:
                account.cookies = cookies
                account.status = "logged_in"
                account.last_login = datetime.now()
                if on_status:
                    on_status("Login successful! Browser kept open.")
                return controller
            
            account.status = "error"
            account.error_message = f"Login failed - URL: {current_url}"
            controller.close_browser()
            return None
            
        except Exception as e:
            account.status = "error"
            account.error_message = str(e)
            if on_status:
                on_status(f"Error: {e}")
            controller.close_browser()
            return None
    
    def extract_cookies(self, cookies: dict) -> dict:
        """Extract important cookies"""
        return {k: v for k, v in cookies.items() if k in REQUIRED_COOKIES}
    
    def is_session_valid(self, account: Account) -> bool:
        """Check if account has valid cookies"""
        if not account.cookies:
            return False
        required = set(REQUIRED_COOKIES)
        return required.issubset(set(account.cookies.keys()))
    
    def get_headers(self, account: Account) -> dict:
        """Generate headers for API requests"""
        headers = {
            'accept': '*/*',
            'accept-language': 'vi-VN,vi;q=0.9',
            'content-type': 'application/json',
            'origin': 'https://grok.com',
            'referer': 'https://grok.com/imagine',
            'sec-ch-ua': '"Not(A:Brand";v="8", "Chromium";v="144", "Google Chrome";v="144"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"macOS"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36',
            'x-xai-request-id': str(uuid4())
        }
        return headers
    
    def get_cookie_string(self, account: Account) -> str:
        """Convert cookies dict to cookie header string"""
        if not account.cookies:
            return ""
        return "; ".join([f"{k}={v}" for k, v in account.cookies.items()])
