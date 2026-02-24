"""
Dynamic x-statsig-id generator cho Grok API.

Thuật toán (ref: eleme @ linux.do):
  base64(
    [1 byte XOR key] +
    XOR(key,
      [48 bytes meta content]  ← từ meta tag grok-site-verification
      [4 bytes timestamp]      ← int(time()) - 1682924400
      [16 bytes SHA256]        ← SHA256("{METHOD}!{path}!{ts}" + fingerprint)[:16]
      [1 byte fixed = 0x03]
    )
  )

Fingerprint được hardcode (match User-Agent Chrome 144 / macOS).
Meta content được fetch và cache từ grok.com HTML.
"""
import base64
import hashlib
import os
import re
import struct
import time
import threading
from typing import Optional

try:
    from curl_cffi import requests as curl_requests
    CURL_AVAILABLE = True
except ImportError:
    CURL_AVAILABLE = False

import platform as _platform
_CURRENT_OS = _platform.system()

from .cf_solver import get_chrome_user_agent, CF_SOLVER_AVAILABLE

USER_AGENT = (
    get_chrome_user_agent() if CF_SOLVER_AVAILABLE
    else (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
        if _CURRENT_OS == "Windows"
        else "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
    )
)

# Epoch offset dùng trong timestamp calculation
EPOCH_OFFSET = 1682924400

# Dynamic fingerprint string — match UA + OS hiện tại
# Grok JS thu thập browser fingerprint (canvas, webgl, fonts, etc.)
# Format: "{UA}|{platform}|false|0|{hardwareConcurrency}|{language}"

def _build_fingerprint() -> str:
    """Build fingerprint string matching current OS + UA."""
    ua = USER_AGENT
    if _CURRENT_OS == "Windows":
        return f"{ua}|Windows|false|0|8|en-US"
    elif _CURRENT_OS == "Darwin":
        return f"{ua}|macOS|false|0|8|en-US"
    else:
        return f"{ua}|Linux|false|0|8|en-US"

HARDCODED_FINGERPRINT = _build_fingerprint()

# Fallback static value — error string mà server vẫn chấp nhận
STATIC_STATSIG_ID = (
    "ZTpUeXBlRXJyb3I6IENhbm5vdCByZWFkIHByb3BlcnRpZXMgb2Yg"
    "dW5kZWZpbmVkIChyZWFkaW5nICdjaGlsZE5vZGVzJyk="
)


class StatsigIdGenerator:
    """
    Generate dynamic x-statsig-id per request.
    
    Fetch meta content từ grok.com 1 lần, cache lại.
    Mỗi request gọi generate() với method + path.
    """

    def __init__(self):
        self._meta_content: Optional[bytes] = None
        self._meta_lock = threading.Lock()
        self._last_fetch_time: float = 0
        self._last_fail_time: float = 0
        # Cache meta content 30 phút
        self._cache_ttl = 30 * 60
        # Cooldown khi fetch fail — không retry liên tục
        self._fail_cooldown = 60

    def _fetch_meta_content(self) -> Optional[bytes]:
        """
        Fetch grok.com HTML → extract meta tag grok-site-verification.
        Returns 48 bytes (hex string decoded) hoặc None.
        """
        if not CURL_AVAILABLE:
            return None

        try:
            resp = curl_requests.get(
                "https://grok.com",
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                },
                impersonate="chrome133a",
                timeout=15,
                allow_redirects=True,
            )

            if resp.status_code != 200:
                print(f"[StatsigId] Fetch grok.com failed: {resp.status_code}")
                return None

            html = resp.text

            # Tìm meta tag: <meta name="grok-site-verification" content="...">
            match = re.search(
                r'<meta\s+name=["\']grok-site-verification["\']\s+content=["\']([^"\']+)["\']',
                html,
                re.IGNORECASE,
            )
            if not match:
                # Thử pattern ngược (content trước name)
                match = re.search(
                    r'<meta\s+content=["\']([^"\']+)["\']\s+name=["\']grok-site-verification["\']',
                    html,
                    re.IGNORECASE,
                )

            if not match:
                print("[StatsigId] Meta tag grok-site-verification not found")
                return None

            content_str = match.group(1).strip()
            print(f"[StatsigId] Meta content: {content_str[:20]}... (len={len(content_str)})")

            # Meta content có thể là hex string (96 chars = 48 bytes)
            # hoặc raw string. Thử decode hex trước.
            try:
                if len(content_str) == 96 and all(c in '0123456789abcdefABCDEF' for c in content_str):
                    meta_bytes = bytes.fromhex(content_str)  # 48 bytes
                else:
                    # Encode raw string thành bytes, pad/truncate to 48
                    meta_bytes = content_str.encode('utf-8')
                    if len(meta_bytes) > 48:
                        meta_bytes = meta_bytes[:48]
                    elif len(meta_bytes) < 48:
                        meta_bytes = meta_bytes.ljust(48, b'\x00')
            except ValueError:
                meta_bytes = content_str.encode('utf-8')[:48].ljust(48, b'\x00')

            return meta_bytes

        except Exception as e:
            print(f"[StatsigId] Error fetching meta: {e}")
            return None

    def _get_meta_content(self) -> Optional[bytes]:
        """Get cached meta content, refresh nếu hết hạn."""
        now = time.time()
        if self._meta_content and (now - self._last_fetch_time) < self._cache_ttl:
            return self._meta_content

        # Nếu fetch fail gần đây → không retry, dùng fallback
        if not self._meta_content and self._last_fail_time and (now - self._last_fail_time) < self._fail_cooldown:
            return None

        with self._meta_lock:
            # Double-check sau khi acquire lock
            if self._meta_content and (now - self._last_fetch_time) < self._cache_ttl:
                return self._meta_content
            if not self._meta_content and self._last_fail_time and (now - self._last_fail_time) < self._fail_cooldown:
                return None

            result = self._fetch_meta_content()
            if result:
                self._meta_content = result
                self._last_fetch_time = now
                self._last_fail_time = 0
            else:
                self._last_fail_time = now
            return self._meta_content

    def generate(self, method: str = "POST", path: str = "/rest/app-chat/conversations/new") -> str:
        """
        Generate x-statsig-id cho 1 request.
        
        Args:
            method: HTTP method (GET/POST)
            path: Request path (e.g. /rest/app-chat/conversations/new)
            
        Returns:
            base64 encoded statsig-id string
        """
        meta = self._get_meta_content()
        if not meta:
            # Fallback về static value nếu không fetch được meta
            return STATIC_STATSIG_ID

        try:
            # 1. Timestamp: current_time - epoch_offset (4 bytes LITTLE-endian)
            ts = int(time.time()) - EPOCH_OFFSET
            ts_bytes = struct.pack("<I", ts & 0xFFFFFFFF)

            # 2. SHA256 của "{METHOD}!{path}!{timestamp}" + fingerprint
            sha_input = f"{method}!{path}!{ts}{HARDCODED_FINGERPRINT}"
            sha_hash = hashlib.sha256(sha_input.encode('utf-8')).digest()
            sha_16 = sha_hash[:16]  # Lấy 16 bytes đầu

            # 3. Build payload: meta(48) + timestamp(4) + sha256(16) + fixed(1) = 69 bytes
            payload = meta + ts_bytes + sha_16 + b'\x03'

            # 4. Random XOR key (1 byte)
            xor_key = os.urandom(1)[0]

            # 5. XOR payload với key
            xored = bytes(b ^ xor_key for b in payload)

            # 6. Prepend key byte → base64
            result = base64.b64encode(bytes([xor_key]) + xored).decode('ascii')
            return result

        except Exception as e:
            print(f"[StatsigId] Generate error: {e}")
            return STATIC_STATSIG_ID


# Singleton instance
_generator = StatsigIdGenerator()


def generate_statsig_id(method: str = "POST", path: str = "/") -> str:
    """Convenience function — generate x-statsig-id."""
    return _generator.generate(method, path)


def prefetch_meta():
    """Pre-fetch meta content (gọi khi app start để warm cache)."""
    _generator._get_meta_content()
