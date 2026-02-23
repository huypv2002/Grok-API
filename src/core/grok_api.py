"""
Grok API - HTTP client cho video generation qua REST API.

Approach:
- curl_cffi + impersonate="chrome133a" → match TLS fingerprint
- x-statsig-id: dynamic per request (xem statsig.py) — fetch meta từ grok.com,
  XOR + SHA256 + base64. Fallback về static error string nếu fetch fail.
- x-xai-request-id: UUID v4 mỗi request
- Content-Type: text/plain;charset=UTF-8, body = json.dumps()
- Cookie: sso-rw={v};sso={v};cf_clearance={v}

Flow video generation:
1. POST /rest/media/post/create → parentPostId
2. POST /rest/app-chat/conversations/new → stream → postId
3. POST /rest/media/post/create-link → share link
4. Download: imagine-public.x.ai/.../share-videos/{postId}.mp4
"""
import json
import uuid
import time
import re
import base64
import random
import threading
from pathlib import Path
from typing import Optional, Callable, Dict
from urllib.parse import urlparse

try:
    from curl_cffi import requests as curl_requests
    CURL_CFFI_AVAILABLE = True
except ImportError:
    CURL_CFFI_AVAILABLE = False

from .cf_solver import get_chrome_user_agent, CF_SOLVER_AVAILABLE
from .statsig import generate_statsig_id

# API endpoints
API_BASE = "https://grok.com"
CREATE_VIDEO_URL = f"{API_BASE}/rest/media/post/create"
CREATE_LINK_URL = f"{API_BASE}/rest/media/post/create-link"
CONVERSATIONS_URL = f"{API_BASE}/rest/app-chat/conversations/new"
UPLOAD_FILE_URL = f"{API_BASE}/rest/app-chat/upload-file"
USER_SETTINGS_URL = f"{API_BASE}/rest/user-settings"
IMAGINE_URL = f"{API_BASE}/imagine"
ASSETS_BASE = "https://assets.grok.com"

# Video download URL template
VIDEO_DOWNLOAD_URL = "https://imagine-public.x.ai/imagine-public/share-videos/{post_id}.mp4?cache=1&dl=1"

from .paths import output_path as _output_path
OUTPUT_DIR = _output_path()

# Detect OS cho dynamic headers (UA, Sec-Ch-Ua-Platform, fingerprint)
import platform as _platform
_CURRENT_OS = _platform.system()

USER_AGENT = get_chrome_user_agent() if CF_SOLVER_AVAILABLE else (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
    if _CURRENT_OS == "Windows"
    else "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
)

def _get_platform_headers() -> dict:
    """Build Sec-Ch-Ua-* headers matching current OS."""
    if _CURRENT_OS == "Windows":
        return {
            'Sec-Ch-Ua-Arch': '"x86_64"',
            'Sec-Ch-Ua-Platform': '"Windows"',
            'Sec-Ch-Ua-Platform-Version': '"15.0.0"',
        }
    elif _CURRENT_OS == "Darwin":
        return {
            'Sec-Ch-Ua-Arch': '"arm"',
            'Sec-Ch-Ua-Platform': '"macOS"',
            'Sec-Ch-Ua-Platform-Version': '"26.3.0"',
        }
    else:
        return {
            'Sec-Ch-Ua-Arch': '"x86_64"',
            'Sec-Ch-Ua-Platform': '"Linux"',
            'Sec-Ch-Ua-Platform-Version': '"6.5.0"',
        }

# Default headers — match browser fingerprint Chrome 145
# x-statsig-id được generate dynamic per request (xem statsig.py)
DEFAULT_HEADERS = {
    'Accept': '*/*',
    'Accept-Language': 'vi-VN,vi;q=0.9,fr-FR;q=0.8,fr;q=0.7,en-US;q=0.6,en;q=0.5',
    'Accept-Encoding': 'gzip, deflate, br, zstd',
    'Content-Type': 'application/json',
    'Connection': 'keep-alive',
    'Origin': 'https://grok.com',
    'Referer': 'https://grok.com/imagine',
    'Priority': 'u=1, i',
    'User-Agent': USER_AGENT,
    'Sec-Ch-Ua': '"Not:A-Brand";v="99", "Google Chrome";v="145", "Chromium";v="145"',
    'Sec-Ch-Ua-Bitness': '"64"',
    'Sec-Ch-Ua-Full-Version': '"145.0.7632.110"',
    'Sec-Ch-Ua-Full-Version-List': '"Not:A-Brand";v="99.0.0.0", "Google Chrome";v="145.0.7632.110", "Chromium";v="145.0.7632.110"',
    'Sec-Ch-Ua-Mobile': '?0',
    'Sec-Ch-Ua-Model': '""',
    **_get_platform_headers(),
    'Sec-Fetch-Dest': 'empty',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Site': 'same-origin',
    'Baggage': 'sentry-public_key=b311e0f2690c81f25e2c4cf6d4f7ce1c',
}


def _make_cookie_string(cookies: dict) -> str:
    """Convert cookies dict → Cookie header string."""
    return "; ".join(f"{k}={v}" for k, v in cookies.items() if v)


def _get_request_headers(referer: str = None, method: str = "POST", url: str = None) -> dict:
    """Get headers với x-xai-request-id và x-statsig-id mới mỗi request."""
    headers = {**DEFAULT_HEADERS}
    headers['x-xai-request-id'] = str(uuid.uuid4())

    # Dynamic x-statsig-id per request
    path = "/"
    if url:
        parsed = urlparse(url)
        path = parsed.path or "/"
    headers['x-statsig-id'] = generate_statsig_id(method=method, path=path)

    if referer:
        headers['Referer'] = referer
    return headers


class _RateLimiter:
    """
    Shared rate limiter cho tất cả GrokAPI instances / threads.
    
    - min_interval: khoảng cách tối thiểu giữa 2 request (giây)
    - 429 cooldown: khi bất kỳ thread nào nhận 429, tất cả thread pause
    - Jitter: thêm random delay nhỏ để tránh thundering herd
    """

    def __init__(self, min_interval: float = 1.5):
        self._lock = threading.Lock()
        self._last_request_time: float = 0
        self._min_interval = min_interval
        # Global 429 cooldown — shared across all threads
        self._cooldown_until: float = 0

    def wait(self):
        """Chờ đến khi được phép gửi request tiếp."""
        with self._lock:
            now = time.time()
            # Check 429 cooldown
            if now < self._cooldown_until:
                wait_cd = self._cooldown_until - now
                print(f"[RateLimiter] ⏳ 429 cooldown, chờ {wait_cd:.1f}s...")
                time.sleep(wait_cd)
                now = time.time()
            # Enforce min interval
            elapsed = now - self._last_request_time
            if elapsed < self._min_interval:
                wait_time = self._min_interval - elapsed + random.uniform(0.1, 0.5)
                time.sleep(wait_time)
            self._last_request_time = time.time()

    def report_429(self, wait_seconds: float = 15.0):
        """Báo 429 — tất cả threads sẽ pause."""
        with self._lock:
            new_cooldown = time.time() + wait_seconds
            # Chỉ extend cooldown, không rút ngắn
            if new_cooldown > self._cooldown_until:
                self._cooldown_until = new_cooldown
                print(f"[RateLimiter] 🚫 429 detected → global cooldown {wait_seconds:.0f}s")


# Singleton — shared across all GrokAPI instances
_rate_limiter = _RateLimiter(min_interval=1.5)


class GrokAPI:
    """
    HTTP client cho Grok video generation API.
    
    Dùng curl_cffi + impersonate để bypass TLS fingerprinting.
    Không cần browser — chỉ cần cookies (sso, sso-rw, cf_clearance).
    """

    def __init__(self, auto_refresh_cf: bool = False):
        self.auto_refresh_cf = auto_refresh_cf
        self._closed = False

    def _log(self, msg: str, on_status: Optional[Callable] = None):
        """Log helper."""
        print(f"[GrokAPI] {msg}")
        if on_status:
            on_status(msg)


    @staticmethod
    def _find_post_id(obj, depth=0, exclude_ids=None):
        """Recursive search postId/mediaPostId/videoId trong JSON tree."""
        if depth > 10:
            return None
        if exclude_ids is None:
            exclude_ids = set()
        if isinstance(obj, dict):
            for key in ("postId", "mediaPostId", "post_id", "media_post_id", "videoId"):
                val = obj.get(key)
                if val and isinstance(val, str) and len(val) > 8 and val not in exclude_ids:
                    return val
            fa = obj.get("fileAttachments")
            if isinstance(fa, list) and fa:
                for item in fa:
                    if isinstance(item, str) and len(item) > 8 and item not in exclude_ids:
                        return item
            for v in obj.values():
                found = GrokAPI._find_post_id(v, depth + 1, exclude_ids)
                if found:
                    return found
        elif isinstance(obj, list):
            for item in obj:
                found = GrokAPI._find_post_id(item, depth + 1, exclude_ids)
                if found:
                    return found
        return None


    def _post(self, url: str, cookies: dict, payload: dict,
              headers: dict = None, stream: bool = False):
        """
        POST request dùng curl_cffi + impersonate.
        
        Body gửi dạng json.dumps() string với Content-Type: text/plain
        (giống cách grok2api_python làm).
        Rate-limited qua shared _rate_limiter.
        """
        if not CURL_CFFI_AVAILABLE:
            raise RuntimeError("curl_cffi chưa cài. Chạy: pip install curl_cffi")

        # Wait for rate limiter trước khi gửi request
        _rate_limiter.wait()

        req_headers = headers or _get_request_headers(method="POST", url=url)
        cookie_str = _make_cookie_string(cookies)

        return curl_requests.post(
            url,
            headers={**req_headers, "Cookie": cookie_str},
            data=json.dumps(payload),
            impersonate="chrome133a",
            stream=stream,
            timeout=120,
        )

    # ==================== Step 1: Create Media Post ====================
    def create_media_post(
        self,
        cookies: dict,
        prompt: str,
        on_status: Optional[Callable] = None,
        max_retries: int = 3,
    ) -> Optional[str]:
        """
        POST /rest/media/post/create
        → Trả về parentPostId. Retry khi 429.
        """
        self._log(f"📤 Step 1: Creating media post...", on_status)

        payload = {
            "mediaType": "MEDIA_POST_TYPE_VIDEO",
            "prompt": prompt,
        }

        for attempt in range(1, max_retries + 1):
            try:
                resp = self._post(
                    CREATE_VIDEO_URL,
                    cookies,
                    payload,
                    _get_request_headers(
                        referer="https://grok.com/imagine/favorites",
                        method="POST",
                        url=CREATE_VIDEO_URL,
                    ),
                )

                if resp.status_code == 200:
                    data = resp.json()
                    post = data.get("post", {})
                    parent_id = (
                        post.get("id")
                        or data.get("parentPostId")
                        or data.get("postId")
                        or data.get("id")
                    )
                    if parent_id:
                        self._log(f"✅ parentPostId: {parent_id[:12]}...", on_status)
                        return parent_id
                    else:
                        self._log(f"⚠️ Response OK nhưng không tìm thấy parentPostId: {data}", on_status)
                        return None
                elif resp.status_code == 429:
                    wait = 10 * attempt
                    _rate_limiter.report_429(wait)
                    self._log(f"⚠️ 429 Rate limit, đợi {wait}s... ({attempt}/{max_retries})", on_status)
                    time.sleep(wait)
                    continue
                elif resp.status_code == 403:
                    self._log(f"❌ 403 Forbidden — cf_clearance hết hạn hoặc IP bị chặn", on_status)
                    return None
                else:
                    self._log(f"❌ Create failed: {resp.status_code} — {resp.text[:200]}", on_status)
                    return None

            except Exception as e:
                self._log(f"❌ Create error: {e}", on_status)
                return None

        return None

    def upload_image(
        self,
        cookies: dict,
        image_path: str,
        on_status: Optional[Callable] = None,
        max_retries: int = 3,
    ) -> Optional[str]:
        """
        POST /rest/app-chat/upload-file
        Upload ảnh dạng base64 → trả về fileMetadataId (postId).
        Dùng cho Image-to-Video flow. Retry khi 429.
        """
        self._log(f"📤 Upload image: {Path(image_path).name}...", on_status)

        img_path = Path(image_path)
        if not img_path.exists():
            self._log(f"❌ File không tồn tại: {image_path}", on_status)
            return None

        # Đọc file → base64
        with open(img_path, "rb") as f:
            raw = f.read()
        b64_content = base64.b64encode(raw).decode("utf-8")

        # Detect MIME type
        suffix = img_path.suffix.lower()
        mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp", ".gif": "image/gif"}
        mime_type = mime_map.get(suffix, "image/jpeg")

        payload = {
            "fileName": img_path.name,
            "fileMimeType": mime_type,
            "content": b64_content,
            "fileSource": "IMAGINE_SELF_UPLOAD_FILE_SOURCE",
        }

        try:
            for attempt in range(1, max_retries + 1):
                resp = self._post(
                    UPLOAD_FILE_URL,
                    cookies,
                    payload,
                    _get_request_headers(
                        referer="https://grok.com/imagine",
                        method="POST",
                        url=UPLOAD_FILE_URL,
                    ),
                )

                if resp.status_code == 200:
                    data = resp.json()
                    # Response chứa fileMetadataId hoặc postId
                    file_id = (
                        data.get("fileMetadataId")
                        or data.get("postId")
                        or data.get("id")
                    )
                    if not file_id:
                        # Tìm trong nested object
                        post = data.get("post", {})
                        file_id = post.get("id") or post.get("postId")
                    if file_id:
                        self._log(f"✅ Upload OK → fileId: {file_id[:12]}...", on_status)
                        return file_id
                    else:
                        self._log(f"⚠️ Upload OK nhưng không tìm thấy fileId: {json.dumps(data)[:200]}", on_status)
                        return None
                elif resp.status_code == 429:
                    wait = 10 * attempt
                    _rate_limiter.report_429(wait)
                    self._log(f"⚠️ 429 Rate limit upload, đợi {wait}s... ({attempt}/{max_retries})", on_status)
                    time.sleep(wait)
                    continue
                else:
                    self._log(f"❌ Upload failed: {resp.status_code} — {resp.text[:200]}", on_status)
                    return None

            return None

        except Exception as e:
            self._log(f"❌ Upload error: {e}", on_status)
            return None

    def update_user_settings(
        self,
        cookies: dict,
        disable_auto_video: bool = True,
        on_status: Optional[Callable] = None
    ) -> bool:
        """
        POST /rest/user-settings
        Disable auto video generation on upload.
        """
        self._log(f"⚙️ Update user settings (disableAutoVideo={disable_auto_video})...", on_status)

        payload = {
            "preferences": {
                "disableVideoGenerationOnUpload": disable_auto_video,
            }
        }

        try:
            resp = self._post(
                USER_SETTINGS_URL,
                cookies,
                payload,
                _get_request_headers(
                    referer="https://grok.com/imagine",
                    method="POST",
                    url=USER_SETTINGS_URL,
                ),
            )

            if resp.status_code == 200:
                self._log(f"✅ User settings updated", on_status)
                return True
            else:
                self._log(f"⚠️ Settings update failed: {resp.status_code}", on_status)
                return False

        except Exception as e:
            self._log(f"⚠️ Settings error: {e}", on_status)
            return False

    def check_asset_ready(
        self,
        cookies: dict,
        file_id: str,
        max_retries: int = 10,
        delay: float = 2.0,
        on_status: Optional[Callable] = None
    ) -> bool:
        """
        GET /rest/assets/{fileId}
        Poll cho đến khi asset sẵn sàng (upload processed xong).
        Browser gọi endpoint này sau upload để verify trước khi gen video.
        """
        if not CURL_CFFI_AVAILABLE:
            raise RuntimeError("curl_cffi chưa cài")

        url = f"{API_BASE}/rest/assets/{file_id}"
        headers = _get_request_headers(referer="https://grok.com/imagine/favorites", method="GET", url=url)
        # GET request không cần Content-Type json
        headers.pop("Content-Type", None)
        cookie_str = _make_cookie_string(cookies)

        for attempt in range(1, max_retries + 1):
            try:
                self._log(f"   🔍 Check asset ready (attempt {attempt}/{max_retries})...", on_status)
                _rate_limiter.wait()  # Rate limit GET requests too
                resp = curl_requests.get(
                    url,
                    headers={**headers, "Cookie": cookie_str},
                    impersonate="chrome133a",
                    timeout=30,
                )

                if resp.status_code == 200:
                    self._log(f"   ✅ Asset ready!", on_status)
                    return True
                elif resp.status_code == 404:
                    # Chưa sẵn sàng, chờ rồi thử lại
                    self._log(f"   ⏳ Asset chưa sẵn sàng (404), chờ {delay}s...", on_status)
                    time.sleep(delay)
                    continue
                else:
                    self._log(f"   ⚠️ Asset check: {resp.status_code}", on_status)
                    time.sleep(delay)
                    continue

            except Exception as e:
                self._log(f"   ⚠️ Asset check error: {e}", on_status)
                time.sleep(delay)
                continue

        self._log(f"   ❌ Asset không sẵn sàng sau {max_retries} lần thử", on_status)
        return False





    # ==================== Step 2: Conversations New ====================
    def conversations_new(
        self,
        cookies: dict,
        prompt: str,
        parent_post_id: str,
        aspect_ratio: str = "16:9",
        video_length: int = 6,
        resolution: str = "480p",
        on_status: Optional[Callable] = None,
        on_progress: Optional[Callable] = None,
        file_attachment_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> Optional[str]:
        """
        POST /rest/app-chat/conversations/new (streaming)
        → Parse stream → trả về postId (video ID)

        on_progress(percent): callback để update progress bar trong lúc stream

        Image-to-Video mode:
          - file_attachment_id: ID từ upload_image()
          - user_id: từ cookies['x-userid']
          - message sẽ là URL assets + --mode=normal
          - payload có thêm fileAttachments
        """
        is_image_mode = bool(file_attachment_id)
        mode_label = "Image→Video" if is_image_mode else "Text→Video"
        self._log(f"📤 Step 2: Conversations new ({mode_label})...", on_status)
        self._log(f"   🎬 Settings → aspectRatio={aspect_ratio}, videoLength={video_length}, resolutionName={resolution}", on_status)

        # Build message dựa trên mode
        if is_image_mode:
            # Image mode: message = URL assets + --mode=normal (2 spaces trước --mode giống browser)
            message = f"https://assets.grok.com/users/{user_id}/{file_attachment_id}/content  --mode=normal"
        else:
            # Text mode: prompt + --mode=custom
            message = prompt if "--mode=custom" in prompt else f"{prompt} --mode=custom"

        payload = {
            "temporary": True,
            "modelName": "grok-3",
            "message": message,
            "toolOverrides": {"videoGen": True},
            "enableSideBySide": True,
            "responseMetadata": {
                "experiments": [],
                "modelConfigOverride": {
                    "modelMap": {
                        "videoGenModelConfig": {
                            "parentPostId": parent_post_id,
                            "aspectRatio": aspect_ratio,
                            "videoLength": video_length,
                            "isVideoEdit": False,
                            "resolutionName": resolution,
                        }
                    }
                }
            }
        }

        # Image mode: thêm fileAttachments
        if is_image_mode:
            payload["fileAttachments"] = [file_attachment_id]

        headers = _get_request_headers(
            referer=f"https://grok.com/imagine/post/{parent_post_id}",
            method="POST",
            url=CONVERSATIONS_URL,
        )

        for _conv_attempt in range(1, 4):
            try:
                resp = self._post(
                    CONVERSATIONS_URL,
                    cookies,
                    payload,
                    headers=headers,
                    stream=True,
                )

                if resp.status_code == 429:
                    wait = 10 * _conv_attempt
                    _rate_limiter.report_429(wait)
                    self._log(f"⚠️ 429 Rate limit, đợi {wait}s... ({_conv_attempt}/3)", on_status)
                    time.sleep(wait)
                    # Refresh headers cho retry
                    headers = _get_request_headers(
                        referer=f"https://grok.com/imagine/post/{parent_post_id}",
                        method="POST",
                        url=CONVERSATIONS_URL,
                    )
                    continue

                if resp.status_code != 200:
                    self._log(f"❌ Conversations failed: {resp.status_code}", on_status)
                    try:
                        self._log(f"   Response: {resp.text[:300]}", on_status)
                    except:
                        pass
                    return None

                break  # 200 OK → parse stream
            except Exception as e:
                self._log(f"❌ Conversations error: {e}", on_status)
                return None
        else:
            self._log(f"❌ Conversations failed sau 3 lần retry 429", on_status)
            return None

        try:

            # Parse streaming response — tìm postId
            # Progress tăng dần từ 50→68% trong lúc stream (rendering)
            post_id = None
            line_count = 0
            # Image mode: exclude image upload ID khỏi kết quả search
            exclude_ids = {file_attachment_id} if is_image_mode and file_attachment_id else set()

            for line in resp.iter_lines():
                if not line:
                    continue
                line_count += 1

                # Emit progress tăng dần: 50% + (line_count chiếm tối đa 18%)
                # Giới hạn ở 68% để còn chỗ cho share link (70%) và download (90%)
                if on_progress and line_count % 3 == 0:
                    # Mỗi 3 lines tăng 1%, tối đa đến 68%
                    stream_pct = min(50 + (line_count // 3), 68)
                    on_progress(stream_pct)

                try:
                    if isinstance(line, bytes):
                        line = line.decode("utf-8")

                    line_str = line.strip()
                    data = json.loads(line_str)

                    # Deep search postId trong toàn bộ JSON tree
                    found_id = self._find_post_id(data, exclude_ids=exclude_ids)
                    if found_id:
                        post_id = found_id

                except json.JSONDecodeError:
                    continue
                except Exception as e:
                    continue

            self._log(f"   Parsed {line_count} lines", on_status)

            if post_id:
                self._log(f"✅ postId: {post_id}", on_status)
                return post_id
            else:
                self._log(f"⚠️ Stream xong nhưng không tìm thấy postId", on_status)
                return None

        except Exception as e:
            self._log(f"❌ Conversations error: {e}", on_status)
            return None


    # ==================== Step 3: Create Share Link ====================
    def create_share_link(
        self,
        cookies: dict,
        post_id: str,
        on_status: Optional[Callable] = None,
        max_retries: int = 8,
        delay: float = 5.0,
    ) -> bool:
        """
        POST /rest/media/post/create-link
        → Tạo share link để video có thể download public.
        Retry nếu 404 (video chưa render xong).
        """
        self._log(f"🔗 Step 3: Creating share link...", on_status)

        payload = {"postId": post_id}

        for attempt in range(1, max_retries + 1):
            try:
                resp = self._post(
                    CREATE_LINK_URL,
                    cookies,
                    payload,
                    _get_request_headers(
                        referer=f"https://grok.com/imagine/post/{post_id}",
                        method="POST",
                        url=CREATE_LINK_URL,
                    ),
                )

                if resp.status_code == 200:
                    self._log(f"✅ Share link created", on_status)
                    return True
                elif resp.status_code == 404 and attempt < max_retries:
                    self._log(f"   ⏳ Video chưa sẵn sàng, retry {attempt}/{max_retries} sau {delay}s...", on_status)
                    time.sleep(delay)
                    continue
                else:
                    self._log(f"⚠️ Share link failed: {resp.status_code}", on_status)
                    if attempt < max_retries:
                        time.sleep(delay)
                        continue
                    return False

            except Exception as e:
                self._log(f"⚠️ Share link error: {e}", on_status)
                if attempt < max_retries:
                    time.sleep(delay)
                    continue
                return False

        return False

    # ==================== Full Flow ====================
    def generate_video(
        self,
        cookies: dict,
        prompt: str,
        aspect_ratio: str = "16:9",
        video_length: int = 6,
        resolution: str = "480p",
        on_status: Optional[Callable] = None
    ) -> Optional[str]:
        """
        Full video generation flow:
        1. create media post → parentPostId
        2. conversations/new → postId
        3. create share link
        
        Returns: postId nếu thành công, None nếu thất bại
        """
        # Step 1: Create media post
        parent_post_id = self.create_media_post(cookies, prompt, on_status)
        if not parent_post_id:
            return None

        # Delay nhỏ giữa requests
        time.sleep(1)

        # Step 2: Conversations new
        post_id = self.conversations_new(
            cookies, prompt, parent_post_id,
            aspect_ratio, video_length, resolution,
            on_status
        )
        if not post_id:
            return None

        # Step 3: Create share link
        time.sleep(0.5)
        self.create_share_link(cookies, post_id, on_status)

        return post_id

    def close(self):
        """Cleanup."""
        self._closed = True
