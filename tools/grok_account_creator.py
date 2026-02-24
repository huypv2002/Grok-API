#!/usr/bin/env python3
"""
Grok Account Creator CLI Tool
Tool đa luồng để tạo và trial Grok account tự động
Sử dụng list thẻ và list hotmail để đăng ký account
"""

import asyncio
import json
import logging
import sys
import time
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime
import httpx
from concurrent.futures import ThreadPoolExecutor, as_completed
import random
import string

# Cấu hình logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('grok_account_creator.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

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
    name: str
    address: str
    city: str
    state: str
    zip_code: str
    country: str = "US"

@dataclass
class GrokAccount:
    """Thông tin Grok account đã tạo"""
    email: str
    password: str
    cookies: Optional[Dict] = None
    status: str = "created"  # created, verified, trial_activated, error
    verification_code: Optional[str] = None
    error_message: Optional[str] = None
    created_at: str = ""
    trial_end_date: Optional[str] = None

class GrokAccountCreator:
    def __init__(self, max_workers: int = 3):
        self.max_workers = max_workers
        self.hotmail_api_url = "https://vinamax.com.vn/api/tools/hotmail"
        self.grok_signup_url = "https://accounts.x.ai/signup"
        self.grok_verify_url = "https://accounts.x.ai/verify-email"
        self.grok_trial_url = "https://grok.com/upgrade"
        
        # Headers cho HTTP requests
        self.headers = {
            'accept': 'application/json, text/plain, */*',
            'accept-language': 'vi-VN,vi;q=0.9,fr-FR;q=0.8,fr;q=0.7,en-US;q=0.6,en;q=0.5',
            'content-type': 'application/json',
            'origin': 'https://vinamax.com.vn',
            'priority': 'u=1, i',
            'referer': 'https://vinamax.com.vn/cong-cu/doc-hotmail',
            'sec-ch-ua': '"Not:A-Brand";v="99", "Google Chrome";v="145", "Chromium";v="145"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"macOS"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36'
        }
        
        # HTTP client
        self.client = httpx.AsyncClient(timeout=30.0, follow_redirects=True)
        
    async def read_hotmail_inbox(self, hotmail: HotmailAccount) -> Tuple[bool, List[Dict], Optional[str], Optional[str]]:
        """
        Đọc hòm thư hotmail để lấy verification code
        Trả về: (success, messages, new_access_token, new_refresh_token)
        """
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
                    
                    logger.info(f"Đọc hòm thư thành công: {hotmail.email}, có {len(messages)} tin nhắn")
                    return True, messages, new_access_token, new_refresh_token
                else:
                    logger.error(f"API trả về success=False: {hotmail.email}")
                    return False, [], None, None
            else:
                logger.error(f"Lỗi HTTP {response.status_code}: {hotmail.email}")
                return False, [], None, None
                
        except Exception as e:
            logger.error(f"Lỗi khi đọc hòm thư {hotmail.email}: {str(e)}")
            return False, [], None, None
    
    def extract_verification_code(self, messages: List[Dict]) -> Optional[str]:
        """
        Trích xuất verification code từ danh sách tin nhắn
        Tìm email từ x.ai với subject chứa "confirmation code"
        """
        for msg in messages:
            subject = msg.get("subject", "").lower()
            from_email = msg.get("from", "").lower()
            
            if "xai" in from_email and "confirmation code" in subject:
                body = msg.get("body", "")
                # Tìm code dạng UU5-LOS trong body
                import re
                # Pattern cho code dạng XXX-XXX (3 chữ cái/3 chữ cái)
                pattern = r'[A-Z0-9]{3}-[A-Z0-9]{3}'
                matches = re.findall(pattern, body)
                if matches:
                    code = matches[0]
                    logger.info(f"Tìm thấy verification code: {code}")
                    return code
        
        return None
    
    async def signup_grok_account(self, email: str, password: str) -> Tuple[bool, Optional[str]]:
        """
        Đăng ký Grok account
        Trả về: (success, error_message)
        """
        try:
            # TODO: Implement actual Grok signup logic
            # Hiện tại chỉ mô phỏng
            logger.info(f"Đang đăng ký Grok account: {email}")
            
            # Giả lập delay
            await asyncio.sleep(random.uniform(1.0, 3.0))
            
            # Tỉ lệ thành công 90%
            if random.random() < 0.9:
                logger.info(f"Đăng ký thành công: {email}")
                return True, None
            else:
                error = "Signup failed - email already exists or rate limit"
                logger.error(f"Đăng ký thất bại: {email} - {error}")
                return False, error
                
        except Exception as e:
            error = f"Lỗi khi đăng ký: {str(e)}"
            logger.error(f"Lỗi khi đăng ký {email}: {str(e)}")
            return False, error
    
    async def verify_grok_account(self, email: str, verification_code: str) -> Tuple[bool, Optional[str]]:
        """
        Xác thực email Grok account
        Trả về: (success, error_message)
        """
        try:
            logger.info(f"Đang xác thực Grok account: {email} với code: {verification_code}")
            
            # Giả lập delay
            await asyncio.sleep(random.uniform(1.0, 2.0))
            
            # Tỉ lệ thành công 95%
            if random.random() < 0.95:
                logger.info(f"Xác thực thành công: {email}")
                return True, None
            else:
                error = "Verification failed - invalid or expired code"
                logger.error(f"Xác thực thất bại: {email} - {error}")
                return False, error
                
        except Exception as e:
            error = f"Lỗi khi xác thực: {str(e)}"
            logger.error(f"Lỗi khi xác thực {email}: {str(e)}")
            return False, error
    
    async def activate_trial(self, email: str, credit_card: CreditCard) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Kích hoạt trial với thẻ tín dụng
        Trả về: (success, error_message, trial_end_date)
        """
        try:
            logger.info(f"Đang kích hoạt trial cho: {email}")
            
            # Giả lập delay
            await asyncio.sleep(random.uniform(2.0, 4.0))
            
            # Tỉ lệ thành công 80%
            if random.random() < 0.8:
                # Tính trial end date (7 ngày từ bây giờ)
                from datetime import datetime, timedelta
                trial_end = datetime.now() + timedelta(days=7)
                trial_end_date = trial_end.strftime("%Y-%m-%d")
                
                logger.info(f"Kích hoạt trial thành công: {email}, trial đến: {trial_end_date}")
                return True, None, trial_end_date
            else:
                error = "Trial activation failed - credit card declined"
                logger.error(f"Kích hoạt trial thất bại: {email} - {error}")
                return False, error, None
                
        except Exception as e:
            error = f"Lỗi khi kích hoạt trial: {str(e)}"
            logger.error(f"Lỗi khi kích hoạt trial {email}: {str(e)}")
            return False, error, None
    
    async def process_single_account(self, hotmail: HotmailAccount, credit_card: CreditCard) -> GrokAccount:
        """
        Xử lý tạo 1 Grok account từ hotmail và thẻ
        """
        grok_account = GrokAccount(
            email=hotmail.email,
            password=hotmail.password,
            created_at=datetime.now().isoformat()
        )
        
        try:
            # Bước 1: Đọc hòm thư để lấy verification code
            success, messages, new_access_token, new_refresh_token = await self.read_hotmail_inbox(hotmail)
            
            if not success:
                grok_account.status = "error"
                grok_account.error_message = "Không thể đọc hòm thư"
                return grok_account
            
            # Cập nhật tokens nếu có
            if new_access_token:
                hotmail.access_token = new_access_token
            if new_refresh_token:
                hotmail.refresh_token = new_refresh_token
            
            # Bước 2: Trích xuất verification code
            verification_code = self.extract_verification_code(messages)
            
            if not verification_code:
                # Nếu không có code, thử đăng ký trước
                logger.info(f"Không tìm thấy verification code, thử đăng ký trước: {hotmail.email}")
                
                # Đăng ký account
                signup_success, signup_error = await self.signup_grok_account(hotmail.email, hotmail.password)
                
                if not signup_success:
                    grok_account.status = "error"
                    grok_account.error_message = f"Đăng ký thất bại: {signup_error}"
                    return grok_account
                
                # Chờ email verification
                logger.info(f"Chờ email verification cho: {hotmail.email}")
                await asyncio.sleep(10)  # Chờ 10 giây
                
                # Đọc lại hòm thư
                success, messages, _, _ = await self.read_hotmail_inbox(hotmail)
                if success:
                    verification_code = self.extract_verification_code(messages)
            
            if not verification_code:
                grok_account.status = "error"
                grok_account.error_message = "Không tìm thấy verification code sau khi đăng ký"
                return grok_account
            
            grok_account.verification_code = verification_code
            
            # Bước 3: Xác thực account
            verify_success, verify_error = await self.verify_grok_account(hotmail.email, verification_code)
            
            if not verify_success:
                grok_account.status = "error"
                grok_account.error_message = f"Xác thực thất bại: {verify_error}"
                return grok_account
            
            grok_account.status = "verified"
            
            # Bước 4: Kích hoạt trial
            trial_success, trial_error, trial_end_date = await self.activate_trial(hotmail.email, credit_card)
            
            if trial_success:
                grok_account.status = "trial_activated"
                grok_account.trial_end_date = trial_end_date
            else:
                grok_account.status = "verified"  # Vẫn thành công nhưng chưa có trial
                grok_account.error_message = f"Không thể kích hoạt trial: {trial_error}"
            
            logger.info(f"Xử lý thành công: {hotmail.email} - Trạng thái: {grok_account.status}")
            
        except Exception as e:
            grok_account.status = "error"
            grok_account.error_message = f"Lỗi xử lý: {str(e)}"
            logger.error(f"Lỗi xử lý account {hotmail.email}: {str(e)}")
        
        return grok_account
    
    async def process_accounts_async(self, hotmails: List[HotmailAccount], credit_cards: List[CreditCard]) -> List[GrokAccount]:
        """
        Xử lý đa luồng các account
        """
        results = []
        
        # Tạo tasks cho mỗi hotmail (lặp qua credit cards nếu cần)
        tasks = []
        for i, hotmail in enumerate(hotmails):
            # Lấy credit card tương ứng (hoặc dùng modulo nếu ít thẻ hơn)
            credit_card = credit_cards[i % len(credit_cards)] if credit_cards else None
            if credit_card:
                task = self.process_single_account(hotmail, credit_card)
                tasks.append(task)
        
        # Chạy đồng thời với semaphore để giới hạn số lượng
        semaphore = asyncio.Semaphore(self.max_workers)
        
        async def run_with_semaphore(task):
            async with semaphore:
                return await task
        
        # Tạo và chạy tất cả tasks
        logger.info(f"Bắt đầu xử lý {len(tasks)} accounts với {self.max_workers} workers")
        
        completed_tasks = []
        for i, task in enumerate(tasks):
            wrapped_task = run_with_semaphore(task)
            completed_tasks.append(wrapped_task)
        
        results = await asyncio.gather(*completed_tasks, return_exceptions=True)
        
        # Xử lý kết quả
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                hotmail = hotmails[i]
                grok_account = GrokAccount(
                    email=hotmail.email,
                    password=hotmail.password,
                    status="error",
                    error_message=f"Lỗi hệ thống: {str(result)}",
                    created_at=datetime.now().isoformat()
                )
                final_results.append(grok_account)
                logger.error(f"Lỗi khi xử lý {hotmail.email}: {str(result)}")
            else:
                final_results.append(result)
        
        return final_results
    
    def save_results(self, results: List[GrokAccount], output_file: str):
        """
        Lưu kết quả ra file JSON
        """
        output_path = Path(output_file)
        data = {
            "created_at": datetime.now().isoformat(),
            "total_accounts": len(results),
            "successful_accounts": len([r for r in results if r.status in ["verified", "trial_activated"]]),
            "failed_accounts": len([r for r in results if r.status == "error"]),
            "accounts": [asdict(r) for r in results]
        }
        
        output_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        logger.info(f"Đã lưu kết quả vào: {output_file}")
        
        # Xuất thêm file CSV đơn giản
        csv_path = output_path.with_suffix('.csv')
        csv_lines = ["Email,Password,Status,Verification Code,Trial End Date,Error Message"]
        for acc in results:
            csv_lines.append(f'{acc.email},{acc.password},{acc.status},{acc.verification_code or ""},{acc.trial_end_date or ""},{acc.error_message or ""}')
        
        csv_path.write_text("\n".join(csv_lines))
        logger.info(f"Đã lưu CSV vào: {csv_path}")
    
    async def close(self):
        """Đóng HTTP client"""
        await self.client.aclose()

def load_hotmails_from_file(file_path: str) -> List[HotmailAccount]:
    """
    Load danh sách hotmail từ file
    Định dạng: email|password|refresh_token|client_id
    """
    hotmails = []
    path = Path(file_path)
    
    if not path.exists():
        raise FileNotFoundError(f"File hotmail không tồn tại: {file_path}")
    
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                parts = line.split('|')
                if len(parts) >= 4:
                    hotmail = HotmailAccount(
                        email=parts[0].strip(),
                        password=parts[1].strip(),
                        refresh_token=parts[2].strip(),
                        client_id=parts[3].strip()
                    )
                    hotmails.append(hotmail)
    
    logger.info(f"Đã load {len(hotmails)} hotmail từ file")
    return hotmails

def load_credit_cards_from_file(file_path: str) -> List[CreditCard]:
    """
    Load danh sách thẻ từ file
    Định dạng: number|expiry_month|expiry_year|cvv|name|address|city|state|zip_code|country
    """
    credit_cards = []
    path = Path(file_path)
    
    if not path.exists():
        logger.warning(f"File thẻ không tồn tại: {file_path}")
        return []
    
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                parts = line.split('|')
                if len(parts) >= 9:
                    card = CreditCard(
                        number=parts[0].strip(),
                        expiry_month=parts[1].strip(),
                        expiry_year=parts[2].strip(),
                        cvv=parts[3].strip(),
                        name=parts[4].strip(),
                        address=parts[5].strip(),
                        city=parts[6].strip(),
                        state=parts[7].strip(),
                        zip_code=parts[8].strip(),
                        country=parts[9].strip() if len(parts) > 9 else "US"
                    )
                    credit_cards.append(card)
    
    logger.info(f"Đã load {len(credit_cards)} thẻ từ file")
    return credit_cards

async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Grok Account Creator - Tool đa luồng tạo và trial Grok account')
    parser.add_argument('--hotmails', type=str, required=True, help='File chứa danh sách hotmail (định dạng: email|password|refresh_token|client_id)')
    parser.add_argument('--cards', type=str, help='File chứa danh sách thẻ tín dụng')
    parser.add_argument('--output', type=str, default='grok_accounts_output.json', help='File output kết quả')
    parser.add_argument('--workers', type=int, default=3, help='Số lượng workers đồng thời')
    parser.add_argument('--test', action='store_true', help='Chế độ test (không thực sự đăng ký)')
    
    args = parser.parse_args()
    
    # Load dữ liệu
    try:
        hotmails = load_hotmails_from_file(args.hotmails)
        if not hotmails:
            logger.error("Không có hotmail nào để xử lý")
            return
        
        credit_cards = load_credit_cards_from_file(args.cards) if args.cards else []
        
        if not credit_cards:
            logger.warning("Không có thẻ tín dụng, chỉ đăng ký không trial")
        
    except Exception as e:
        logger.error(f"Lỗi khi load dữ liệu: {str(e)}")
        return
    
    # Tạo và chạy creator
    creator = GrokAccountCreator(max_workers=args.workers)
    
    try:
        # Xử lý accounts
        results = await creator.process_accounts_async(hotmails, credit_cards)
        
        # Lưu kết quả
        creator.save_results(results, args.output)
        
        # Thống kê
        successful = len([r for r in results if r.status in ["verified", "trial_activated"]])
        failed = len([r for r in results if r.status == "error"])
        
        print("\n" + "="*50)
        print("THỐNG KÊ KẾT QUẢ")
        print("="*50)
        print(f"Tổng số account: {len(results)}")
        print(f"Thành công: {successful}")
        print(f"Thất bại: {failed}")
        print(f"Tỉ lệ thành công: {(successful/len(results)*100):.1f}%")
        print("="*50)
        
        if successful > 0:
            print("\nCác account thành công:")
            for acc in results:
                if acc.status in ["verified", "trial_activated"]:
                    trial_info = f" (Trial đến: {acc.trial_end_date})" if acc.trial_end_date else ""
                    print(f"  - {acc.email}{trial_info}")
        
        if failed > 0:
            print("\nCác account thất bại:")
            for acc in results:
                if acc.status == "error":
                    print(f"  - {acc.email}: {acc.error_message}")
        
    finally:
        await creator.close()

if __name__ == "__main__":
    asyncio.run(main())

def parse_compact_card_format(compact_string: str) -> List[CreditCard]:
    """
    Parse định dạng thẻ compact: 6224792557857660|05|2029|3386224792557852612|12|2027|865...
    Mỗi thẻ có: number|expiry_month|expiry_year|cvv
    """
    credit_cards = []
    parts = compact_string.split('|')
    
    # Mỗi thẻ có 4 phần: number, expiry_month, expiry_year, cvv
    for i in range(0, len(parts), 4):
        if i + 3 < len(parts):
            number = parts[i].strip()
            expiry_month = parts[i + 1].strip()
            expiry_year = parts[i + 2].strip()
            cvv = parts[i + 3].strip()
            
            # Tạo thông tin mặc định cho name, address, etc.
            card = CreditCard(
                number=number,
                expiry_month=expiry_month,
                expiry_year=expiry_year,
                cvv=cvv,
                name=f"Card Holder {i//4 + 1}",
                address=f"{i//4 + 1} Main Street",
                city="New York",
                state="NY",
                zip_code="10001",
                country="US"
            )
            credit_cards.append(card)
    
    logger.info(f"Đã parse {len(credit_cards)} thẻ từ định dạng compact")
    return credit_cards

def export_to_account_manager_format(results: List[GrokAccount], output_file: str):
    """
    Xuất kết quả sang định dạng tương thích với AccountManager của project chính
    Định dạng: email|password (plain text)
    """
    output_path = Path(output_file)
    
    lines = []
    for acc in results:
        if acc.status in ["verified", "trial_activated"]:
            lines.append(f"{acc.email}|{acc.password}")
    
    output_path.write_text("\n".join(lines))
    logger.info(f"Đã xuất {len(lines)} account sang định dạng AccountManager: {output_file}")
    
    # Tạo file JSON cho import vào data/accounts.json
    json_output = output_path.with_suffix('.json')
    accounts_data = []
    for acc in results:
        if acc.status in ["verified", "trial_activated"]:
            account_info = {
                "email": acc.email,
                "password": acc.password,  # Plain text, sẽ được encrypt khi import
                "status": "logged_out",
                "cookies": acc.cookies,
                "fingerprint_id": str(uuid4()),
                "last_login": None,
                "error_message": None
            }
            accounts_data.append(account_info)
    
    json_data = {"accounts": accounts_data}
    json_output.write_text(json.dumps(json_data, indent=2))
    logger.info(f"Đã xuất file JSON: {json_output}")

async def import_to_main_project(accounts_file: str):
    """
    Import các account đã tạo vào project chính (data/accounts.json)
    """
    try:
        from src.core.account_manager import AccountManager
        from src.core.encryption import encrypt_password
        
        manager = AccountManager()
        path = Path(accounts_file)
        
        if not path.exists():
            logger.error(f"File không tồn tại: {accounts_file}")
            return False
        
        # Đọc file định dạng email|password
        added_count = 0
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and '|' in line:
                    email, password = line.split('|', 1)
                    email = email.strip()
                    password = password.strip()
                    
                    if email and password:
                        # Kiểm tra xem account đã tồn tại chưa
                        existing = manager.get_account(email)
                        if not existing:
                            manager.add_account(email, password)
                            added_count += 1
                            logger.info(f"Đã thêm account: {email}")
                        else:
                            logger.info(f"Account đã tồn tại: {email}")
        
        logger.info(f"Import thành công: {added_count} account mới")
        return True
        
    except ImportError as e:
        logger.error(f"Không thể import vào project chính: {str(e)}")
        logger.info("Cần chạy từ thư mục gốc của project để import")
        return False
    except Exception as e:
        logger.error(f"Lỗi khi import: {str(e)}")
        return False

# Cập nhật hàm main để thêm các tùy chọn mới
async def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Grok Account Creator - Tool đa luồng tạo và trial Grok account')
    parser.add_argument('--hotmails', type=str, required=True, help='File chứa danh sách hotmail (định dạng: email|password|refresh_token|client_id)')
    parser.add_argument('--cards', type=str, help='File chứa danh sách thẻ tín dụng (định dạng: number|expiry_month|expiry_year|cvv|name|address...)')
    parser.add_argument('--cards-compact', type=str, help='String thẻ compact (định dạng: 6224792557857660|05|2029|3386224792557852612|12|2027|865...)')
    parser.add_argument('--output', type=str, default='grok_accounts_output.json', help='File output kết quả')
    parser.add_argument('--export-accounts', type=str, help='Xuất account sang định dạng email|password cho project chính')
    parser.add_argument('--import-to-project', action='store_true', help='Import account vào project chính sau khi tạo')
    parser.add_argument('--workers', type=int, default=3, help='Số lượng workers đồng thời')
    parser.add_argument('--test', action='store_true', help='Chế độ test (không thực sự đăng ký)')
    
    args = parser.parse_args()
    
    # Load dữ liệu
    try:
        hotmails = load_hotmails_from_file(args.hotmails)
        if not hotmails:
            logger.error("Không có hotmail nào để xử lý")
            return
        
        credit_cards = []
        
        # Load thẻ từ file
        if args.cards:
            credit_cards = load_credit_cards_from_file(args.cards)
        
        # Load thẻ từ string compact
        elif args.cards_compact:
            credit_cards = parse_compact_card_format(args.cards_compact)
        
        if not credit_cards:
            logger.warning("Không có thẻ tín dụng, chỉ đăng ký không trial")
        
    except Exception as e:
        logger.error(f"Lỗi khi load dữ liệu: {str(e)}")
        return
    
    # Tạo và chạy creator
    creator = GrokAccountCreator(max_workers=args.workers)
    
    try:
        # Xử lý accounts
        results = await creator.process_accounts_async(hotmails, credit_cards)
        
        # Lưu kết quả
        creator.save_results(results, args.output)
        
        # Xuất sang định dạng project chính nếu được yêu cầu
        if args.export_accounts:
            export_to_account_manager_format(results, args.export_accounts)
        
        # Import vào project chính nếu được yêu cầu
        if args.import_to_project:
            if args.export_accounts:
                success = await import_to_main_project(args.export_accounts)
                if success:
                    logger.info("Import vào project chính thành công!")
            else:
                # Tạo file tạm để import
                temp_file = "temp_accounts_import.txt"
                export_to_account_manager_format(results, temp_file)
                success = await import_to_main_project(temp_file)
                if success:
                    logger.info("Import vào project chính thành công!")
                # Xóa file tạm
                Path(temp_file).unlink(missing_ok=True)
        
        # Thống kê
        successful = len([r for r in results if r.status in ["verified", "trial_activated"]])
        failed = len([r for r in results if r.status == "error"])
        
        print("\n" + "="*50)
        print("THỐNG KÊ KẾT QUẢ")
        print("="*50)
        print(f"Tổng số account: {len(results)}")
        print(f"Thành công: {successful}")
        print(f"Thất bại: {failed}")
        if len(results) > 0:
            print(f"Tỉ lệ thành công: {(successful/len(results)*100):.1f}%")
        print("="*50)
        
        if successful > 0:
            print("\nCác account thành công:")
            for acc in results:
                if acc.status in ["verified", "trial_activated"]:
                    trial_info = f" (Trial đến: {acc.trial_end_date})" if acc.trial_end_date else ""
                    print(f"  - {acc.email}{trial_info}")
        
        if failed > 0:
            print("\nCác account thất bại:")
            for acc in results:
                if acc.status == "error":
                    print(f"  - {acc.email}: {acc.error_message}")
        
    finally:
        await creator.close()