"""Password encryption/decryption using Fernet"""
import os
from pathlib import Path
from cryptography.fernet import Fernet
from .paths import data_path

def _get_or_create_key() -> bytes:
    key_file = data_path(".key")
    key_file.parent.mkdir(parents=True, exist_ok=True)
    if key_file.exists():
        return key_file.read_bytes()
    key = Fernet.generate_key()
    key_file.write_bytes(key)
    return key

def _get_fernet() -> Fernet:
    return Fernet(_get_or_create_key())

def encrypt_password(password: str) -> str:
    return _get_fernet().encrypt(password.encode()).decode()

def decrypt_password(encrypted: str) -> str:
    """Decrypt password. Raises InvalidToken if key mismatch."""
    try:
        return _get_fernet().decrypt(encrypted.encode()).decode()
    except Exception:
        raise ValueError(
            "Không thể giải mã password — file data/.key đã thay đổi.\n"
            "Xóa data/accounts.json và data/.key rồi thêm lại tài khoản."
        )
