"""Account Manager - CRUD operations for X.AI accounts"""
import json
from pathlib import Path
from datetime import datetime
from typing import Optional
from .models import Account
from .encryption import encrypt_password, decrypt_password
from .paths import data_path

class AccountManager:
    def __init__(self):
        self.accounts: dict[str, Account] = {}
        self.load_from_storage()
    
    def add_account(self, email: str, password: str) -> Account:
        encrypted_pwd = encrypt_password(password)
        account = Account(email=email, password=encrypted_pwd)
        self.accounts[email] = account
        self.save_to_storage()
        return account
    
    def update_account(self, email: str, **kwargs) -> Optional[Account]:
        if email not in self.accounts:
            return None
        account = self.accounts[email]
        for key, value in kwargs.items():
            if key == "password":
                value = encrypt_password(value)
            if hasattr(account, key):
                setattr(account, key, value)
        self.save_to_storage()
        return account
    
    def delete_account(self, email: str) -> bool:
        if email in self.accounts:
            del self.accounts[email]
            self.save_to_storage()
            return True
        return False
    
    def get_account(self, email: str) -> Optional[Account]:
        return self.accounts.get(email)
    
    def get_all_accounts(self) -> list[Account]:
        return list(self.accounts.values())
    
    def get_password(self, email: str) -> Optional[str]:
        account = self.accounts.get(email)
        if account:
            try:
                return decrypt_password(account.password)
            except ValueError:
                return None
        return None
    
    def save_to_storage(self) -> None:
        acc_file = data_path("accounts.json")
        acc_file.parent.mkdir(parents=True, exist_ok=True)
        data = {"accounts": []}
        for acc in self.accounts.values():
            data["accounts"].append({
                "email": acc.email,
                "password_encrypted": acc.password,
                "fingerprint_id": acc.fingerprint_id,
                "status": acc.status,
                "cookies": acc.cookies,
                "last_login": acc.last_login.isoformat() if acc.last_login else None,
                "error_message": acc.error_message
            })
        acc_file.write_text(json.dumps(data, indent=2))
    
    def load_from_storage(self) -> None:
        acc_file = data_path("accounts.json")
        if not acc_file.exists():
            return
        try:
            data = json.loads(acc_file.read_text())
            # Handle cả format cũ (list) và mới (dict)
            acc_list = data.get("accounts", []) if isinstance(data, dict) else []
            for acc_data in acc_list:
                account = Account(
                    email=acc_data["email"],
                    password=acc_data["password_encrypted"],
                    fingerprint_id=acc_data.get("fingerprint_id", ""),
                    status=acc_data.get("status", "logged_out"),
                    cookies=acc_data.get("cookies"),
                    last_login=datetime.fromisoformat(acc_data["last_login"]) if acc_data.get("last_login") else None,
                    error_message=acc_data.get("error_message")
                )
                self.accounts[account.email] = account
        except Exception:
            pass

    # --- Login Temp JSON ---

    def export_to_temp(self) -> int:
        """Export all accounts (email + plain password) to login_temp.json.
        Returns number of accounts exported."""
        entries = []
        for acc in self.accounts.values():
            try:
                plain_pwd = decrypt_password(acc.password)
                if plain_pwd:
                    entries.append({"email": acc.email, "password": plain_pwd})
            except ValueError:
                # Key mismatch — skip account
                continue
        temp = data_path("login_temp.json")
        temp.parent.mkdir(parents=True, exist_ok=True)
        temp.write_text(json.dumps({"accounts": entries}, indent=2, ensure_ascii=False))
        return len(entries)

    def import_from_temp(self) -> tuple[int, int]:
        """Import accounts from login_temp.json.
        Returns (added, skipped) counts."""
        temp = data_path("login_temp.json")
        if not temp.exists():
            raise FileNotFoundError("File login_temp.json không tồn tại")
        data = json.loads(temp.read_text())
        added, skipped = 0, 0
        for entry in data.get("accounts", []):
            email = entry.get("email", "").strip()
            password = entry.get("password", "").strip()
            if not email or not password:
                continue
            if email in self.accounts:
                skipped += 1
            else:
                self.add_account(email, password)
                added += 1
        return added, skipped
