#!/usr/bin/env python3
"""
Grok Account Creator với Zendriver thực tế
Tool đa luồng tạo Grok account bằng zendriver
"""

import asyncio
import json
import logging
import re
import sys
import time
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime
import httpx

# Thử import zendriver
try:
    import zendriver
    ZENDRIVER_AVAILABLE = True
except ImportError:
    ZENDRIVER_AVAILABLE = False

# Cấu hình logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('grok_account_creator_zendriver.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

FIXED_USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36"

@dataclass
class HotmailAccount:
    """Thông tin hotmail account"""
    email: str
    password: str
    refresh_token: str
    client_id: str
    access_token: str = ""
    use_oauth2: bool = False
    use_graph_api: bool = True

@dataclass
class CreditCard:
    """Thông tin thẻ tín dụng"""
    number: str
    expiry_month: str
    expiry_year: str
    cvv: str

@dataclass
class GrokAccount:
    """Thông tin Grok account đã tạo"""
    email: str
    password: str
    cookies: Optional[Dict] = None
    status: str = "created"  # created, email_sent, verified, trial_activated, error
    verification_code: Optional[str] = None
    error_message: Optional[str] = None
    created_at: str = ""


class ZendriverGrokAccountCreator:
    def __init__(self, max_workers: int = 3, headless: bool = False):
        self.max_workers = max_workers
        self.headless = headless
        self.hotmail_api_url = "https://vinamax.com.vn/api/tools/hotmail"
        
        self.headers = {
            'accept': 'application/json, text/plain, */*',
            'accept-language': 'vi-VN,vi;q=0.9,fr-FR;q=0.8,fr;q=0.7,en-US;q=0.6,en;q=0.5',
            'content-type': 'application/json',
            'origin': 'https://vinamax.com.vn',
            'referer': 'https://vinamax.com.vn/cong-cu/doc-hotmail',
            'user-agent': FIXED_USER_AGENT
        }
        
        self.client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)

    async def read_hotmail_inbox(self, hotmail: HotmailAccount) -> Tuple[bool, List[Dict], Optional[str], Optional[str]]:
        """Đọc hòm thư hotmail để lấy verification code"""
        try:
            payload = {
                "email": hotmail.email,
                "password": hotmail.password,
                "refreshToken": hotmail.refresh_token,
                "clientId": hotmail.client_id,
                "accessToken": hotmail.access_token,
                "useOAuth2": hotmail.use_oauth2,
                "useGraphAPI": hotmail.use_graph_api
            }
            
            logger.info(f"Đang đọc hòm thư: {hotmail.email}")
            response = await self.client.post(self.hotmail_api_url, json=payload, headers=self.headers)
            
            if response.status_code == 200:
                data = response.json()
                if data.get("success"):
                    messages = data.get("messages", [])
                    new_access_token = data.get("newAccessToken")
                    new_refresh_token = data.get("newRefreshToken")
                    logger.info(f"Đọc hòm thư OK: {hotmail.email}, {len(messages)} tin nhắn")
                    return True, messages, new_access_token, new_refresh_token
                else:
                    logger.error(f"API trả về success=False: {hotmail.email}")
                    return False, [], None, None
            else:
                logger.error(f"Lỗi HTTP {response.status_code}: {hotmail.email}")
                return False, [], None, None
        except Exception as e:
            logger.error(f"Lỗi đọc hòm thư {hotmail.email}: {e}")
            return False, [], None, None

    def extract_verification_code(self, messages: List[Dict]) -> Optional[str]:
        """Trích xuất verification code từ danh sách tin nhắn"""
        for msg in messages:
            subject = msg.get("subject", "")
            body = msg.get("body", "")
            
            # Pattern cho code dạng XXX-XXX hoặc XXXXXX (alphanumeric)
            for text in [subject, body]:
                # Tìm dạng ABC-DEF
                matches = re.findall(r'[A-Za-z0-9]{3}-[A-Za-z0-9]{3}', text)
                if matches:
                    code = matches[0].upper()
                    logger.info(f"Tìm thấy verification code: {code}")
                    return code
                
                # Tìm dạng 6 ký tự liền
                matches = re.findall(r'\b[A-Za-z0-9]{6}\b', text)
                for match in matches:
                    if match.isalnum():
                        logger.info(f"Tìm thấy verification code 6 ký tự: {match}")
                        return match.upper()
        
        return None

    async def _start_browser(self):
        """Khởi tạo browser zendriver"""
        browser = await zendriver.start(
            headless=self.headless,
            user_agent=FIXED_USER_AGENT,
        )
        return browser

    async def signup_with_zendriver(self, email: str) -> Tuple[bool, Optional[str], Optional[object]]:
        """
        Đăng ký Grok account bằng zendriver.
        Trả về: (success, error_message, browser) - giữ browser mở để verify sau
        """
        browser = None
        try:
            logger.info(f"Bắt đầu đăng ký: {email}")
            browser = await self._start_browser()
            tab = browser.main_tab
            
            # 1. Navigate tới trang sign-up
            await tab.get("https://accounts.x.ai/sign-up")
            await tab.sleep(3)
            
            # 2. Click nút "Sign up with email"
            signup_btn = await tab.find_element_by_text("Sign up with email")
            if not signup_btn:
                # Thử tìm bằng selector
                signup_btn = await tab.select("button:has(svg.lucide-mail)")
            
            if not signup_btn:
                return False, "Không tìm thấy nút 'Sign up with email'", browser
            
            await signup_btn.click()
            logger.info("Clicked 'Sign up with email'")
            await tab.sleep(1.5)
            
            # 3. Điền email
            email_input = await tab.select('input[data-testid="email"]')
            if not email_input:
                email_input = await tab.select('input[type="email"]')
            
            if not email_input:
                return False, "Không tìm thấy input email", browser
            
            await email_input.click()
            await email_input.send_keys(email)
            logger.info(f"Đã điền email: {email}")
            await tab.sleep(0.5)
            
            # 4. Click nút "Sign up" (submit)
            submit_btn = await tab.find_element_by_text("Sign up")
            if not submit_btn:
                submit_btn = await tab.select('button[type="submit"]')
            
            if not submit_btn:
                return False, "Không tìm thấy nút 'Sign up'", browser
            
            await submit_btn.click()
            logger.info("Clicked 'Sign up' submit")
            await tab.sleep(3)
            
            # 5. Kiểm tra đã chuyển tới trang verify email chưa
            verify_heading = await tab.find_element_by_text("Verify your email")
            if verify_heading:
                logger.info(f"Đăng ký OK, chờ verification code cho: {email}")
                return True, None, browser
            
            # Kiểm tra lỗi (email đã tồn tại, etc.)
            error_el = await tab.select('[class*="error"], .text-red-500, .text-destructive')
            if error_el:
                error_text = error_el.text or "Unknown error"
                logger.error(f"Lỗi đăng ký: {error_text}")
                return False, f"Signup error: {error_text}", browser
            
            # Có thể trang chưa load xong, chờ thêm
            await tab.sleep(3)
            verify_heading = await tab.find_element_by_text("Verify your email")
            if verify_heading:
                logger.info(f"Đăng ký OK (chờ thêm): {email}")
                return True, None, browser
            
            logger.warning(f"Không rõ trạng thái sau signup, thử tiếp: {email}")
            return True, None, browser
            
        except Exception as e:
            logger.error(f"Lỗi signup zendriver {email}: {e}")
            return False, f"Zendriver error: {e}", browser

    async def enter_verification_code(self, browser, verification_code: str) -> Tuple[bool, Optional[str]]:
        """
        Điền verification code vào form OTP trên browser đang mở.
        Trả về: (success, error_message)
        """
        try:
            tab = browser.main_tab
            logger.info(f"Điền verification code: {verification_code}")
            
            # Tìm input OTP
            otp_input = await tab.select('input[data-input-otp]')
            if not otp_input:
                otp_input = await tab.select('input[autocomplete="one-time-code"]')
            
            if not otp_input:
                return False, "Không tìm thấy input OTP"
            
            # Click vào input trước rồi gõ code
            await otp_input.click()
            await tab.sleep(0.3)
            
            # Gõ từng ký tự code (bỏ dấu gạch nếu có)
            clean_code = verification_code.replace("-", "")
            await otp_input.send_keys(clean_code)
            logger.info(f"Đã điền code: {clean_code}")
            await tab.sleep(1)
            
            # Click nút "Confirm email"
            confirm_btn = await tab.find_element_by_text("Confirm email")
            if not confirm_btn:
                confirm_btn = await tab.select('button[type="submit"]')
            
            if not confirm_btn:
                return False, "Không tìm thấy nút 'Confirm email'"
            
            await confirm_btn.click()
            logger.info("Clicked 'Confirm email'")
            await tab.sleep(5)
            
            # Kiểm tra kết quả
            current_url = await tab.evaluate("window.location.href")
            logger.info(f"URL sau verify: {current_url}")
            
            # Nếu URL chuyển sang trang khác (không còn sign-up) → thành công
            if "sign-up" not in current_url and "verify" not in current_url:
                logger.info("Xác thực thành công!")
                return True, None
            
            # Kiểm tra lỗi
            error_el = await tab.select('[class*="error"], .text-red-500, .text-destructive')
            if error_el:
                error_text = error_el.text or "Unknown error"
                logger.error(f"Lỗi verify: {error_text}")
                return False, f"Verify error: {error_text}"
            
            # Chờ thêm và check lại
            await tab.sleep(3)
            current_url = await tab.evaluate("window.location.href")
            if "sign-up" not in current_url and "verify" not in current_url:
                return True, None
            
            return False, "Không rõ trạng thái sau verify"
            
        except Exception as e:
            logger.error(f"Lỗi enter verification code: {e}")
            return False, f"Error: {e}"

    async def process_single_account(self, hotmail: HotmailAccount, credit_card: Optional[CreditCard] = None) -> GrokAccount:
        """Xử lý tạo 1 Grok account từ hotmail"""
        grok_account = GrokAccount(
            email=hotmail.email,
            password=hotmail.password,
            created_at=datetime.now().isoformat()
        )
        
        browser = None
        try:
            # Bước 1: Đăng ký
            logger.info(f"=== Bước 1: Đăng ký {hotmail.email} ===")
            signup_ok, signup_err, browser = await self.signup_with_zendriver(hotmail.email)
            
            if not signup_ok:
                grok_account.status = "error"
                grok_account.error_message = f"Đăng ký thất bại: {signup_err}"
                return grok_account
            
            grok_account.status = "email_sent"
            logger.info(f"Đăng ký OK, chờ email verification: {hotmail.email}")
            
            # Bước 2: Chờ và đọc email verification
            logger.info(f"=== Bước 2: Chờ email verification (15s) ===")
            await asyncio.sleep(15)
            
            verification_code = None
            for attempt in range(3):
                logger.info(f"Đọc hòm thư lần {attempt + 1}...")
                success, messages, new_at, new_rt = await self.read_hotmail_inbox(hotmail)
                
                if new_at:
                    hotmail.access_token = new_at
                if new_rt:
                    hotmail.refresh_token = new_rt
                
                if success and messages:
                    verification_code = self.extract_verification_code(messages)
                    if verification_code:
                        break
                
                if attempt < 2:
                    logger.info("Chưa có code, chờ thêm 10s...")
                    await asyncio.sleep(10)
            
            if not verification_code:
                grok_account.status = "error"
                grok_account.error_message = "Không tìm thấy verification code"
                return grok_account
            
            grok_account.verification_code = verification_code
            logger.info(f"Tìm thấy code: {verification_code}")
            
            # Bước 3: Điền verification code
            logger.info(f"=== Bước 3: Xác thực với code {verification_code} ===")
            verify_ok, verify_err = await self.enter_verification_code(browser, verification_code)
            
            if not verify_ok:
                grok_account.status = "error"
                grok_account.error_message = f"Xác thực thất bại: {verify_err}"
                return grok_account
            
            grok_account.status = "verified"
            logger.info(f"Xác thực thành công: {hotmail.email}")
            
            # TODO: Bước 4 - Kích hoạt trial với credit card
            if credit_card:
                logger.info("Bước 4: Trial activation (chưa implement)")
            
        except Exception as e:
            grok_account.status = "error"
            grok_account.error_message = f"Lỗi: {e}"
            logger.error(f"Lỗi xử lý {hotmail.email}: {e}")
        finally:
            if browser:
                try:
                    browser.stop()
                except:
                    pass
        
        return grok_account

    async def process_accounts_async(self, hotmails: List[HotmailAccount], credit_cards: List[CreditCard]) -> List[GrokAccount]:
        """Xử lý đa luồng các account"""
        semaphore = asyncio.Semaphore(self.max_workers)
        
        async def run_with_semaphore(hotmail, card):
            async with semaphore:
                return await self.process_single_account(hotmail, card)
        
        tasks = []
        for i, hotmail in enumerate(hotmails):
            card = credit_cards[i % len(credit_cards)] if credit_cards else None
            tasks.append(run_with_semaphore(hotmail, card))
        
        logger.info(f"Bắt đầu xử lý {len(tasks)} accounts với {self.max_workers} workers")
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        final = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                final.append(GrokAccount(
                    email=hotmails[i].email,
                    password=hotmails[i].password,
                    status="error",
                    error_message=f"Lỗi hệ thống: {result}",
                    created_at=datetime.now().isoformat()
                ))
            else:
                final.append(result)
        return final

    def save_results(self, results: List[GrokAccount], output_file: str):
        """Lưu kết quả ra file JSON + CSV"""
        output_path = Path(output_file)
        data = {
            "created_at": datetime.now().isoformat(),
            "total": len(results),
            "success": len([r for r in results if r.status in ["verified", "trial_activated"]]),
            "failed": len([r for r in results if r.status == "error"]),
            "accounts": [asdict(r) for r in results]
        }
        output_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        logger.info(f"Đã lưu JSON: {output_file}")
        
        csv_path = output_path.with_suffix('.csv')
        lines = ["Email,Password,Status,Code,Error"]
        for acc in results:
            lines.append(f'{acc.email},{acc.password},{acc.status},{acc.verification_code or ""},{acc.error_message or ""}')
        csv_path.write_text("\n".join(lines))
        logger.info(f"Đã lưu CSV: {csv_path}")

    async def close(self):
        await self.client.aclose()


def load_hotmails_from_file(file_path: str) -> List[HotmailAccount]:
    """Load hotmail từ file. Format: email|password|refresh_token|client_id"""
    hotmails = []
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File không tồn tại: {file_path}")
    
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if line and not line.startswith('#'):
            parts = line.split('|')
            if len(parts) >= 4:
                hotmails.append(HotmailAccount(
                    email=parts[0].strip(),
                    password=parts[1].strip(),
                    refresh_token=parts[2].strip(),
                    client_id=parts[3].strip()
                ))
    logger.info(f"Đã load {len(hotmails)} hotmail từ file")
    return hotmails


def parse_compact_card_format(compact_string: str) -> List[CreditCard]:
    """Parse thẻ compact: number|month|year|cvv|number|month|year|cvv|..."""
    cards = []
    parts = compact_string.split('|')
    for i in range(0, len(parts) - 3, 4):
        cards.append(CreditCard(
            number=parts[i].strip(),
            expiry_month=parts[i + 1].strip(),
            expiry_year=parts[i + 2].strip(),
            cvv=parts[i + 3].strip()
        ))
    logger.info(f"Đã parse {len(cards)} thẻ")
    return cards


async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Grok Account Creator - Zendriver')
    parser.add_argument('--hotmails', type=str, required=True, help='File hotmail (email|password|refresh_token|client_id)')
    parser.add_argument('--cards-compact', type=str, help='String thẻ compact')
    parser.add_argument('--output', type=str, default='grok_accounts_zendriver.json', help='File output')
    parser.add_argument('--workers', type=int, default=3, help='Số workers')
    parser.add_argument('--headless', action='store_true', help='Headless mode')
    parser.add_argument('--test', action='store_true', help='Test 1 account')
    
    args = parser.parse_args()
    
    if not ZENDRIVER_AVAILABLE:
        logger.error("Zendriver không khả dụng. Cần cài đặt: pip install zendriver")
        return
    
    try:
        hotmails = load_hotmails_from_file(args.hotmails)
        if not hotmails:
            logger.error("Không có hotmail nào")
            return
        
        credit_cards = parse_compact_card_format(args.cards_compact) if args.cards_compact else []
        
        if args.test:
            hotmails = [hotmails[0]]
            credit_cards = [credit_cards[0]] if credit_cards else []
    except Exception as e:
        logger.error(f"Lỗi load dữ liệu: {e}")
        return
    
    creator = ZendriverGrokAccountCreator(max_workers=args.workers, headless=args.headless)
    try:
        results = await creator.process_accounts_async(hotmails, credit_cards)
        creator.save_results(results, args.output)
        
        ok = len([r for r in results if r.status in ["verified", "trial_activated"]])
        fail = len([r for r in results if r.status == "error"])
        
        print(f"\n{'='*50}")
        print(f"KẾT QUẢ: {len(results)} accounts | OK: {ok} | Fail: {fail}")
        print(f"{'='*50}")
        for acc in results:
            icon = "✓" if acc.status == "verified" else "✗"
            print(f"  {icon} {acc.email} [{acc.status}] {acc.error_message or ''}")
        print(f"\nOutput: {args.output}")
    finally:
        await creator.close()


if __name__ == "__main__":
    asyncio.run(main())
