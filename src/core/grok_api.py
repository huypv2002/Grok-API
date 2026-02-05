"""Grok API - Direct API calls for video generation"""
import httpx
import uuid
import json
import time
import re
from pathlib import Path
from datetime import datetime
from typing import Optional, Callable

# Import CF solver
try:
    from .cf_solver import solve_cloudflare, save_cf_clearance, CF_SOLVER_AVAILABLE
except ImportError:
    try:
        from src.core.cf_solver import solve_cloudflare, save_cf_clearance, CF_SOLVER_AVAILABLE
    except ImportError:
        CF_SOLVER_AVAILABLE = False
        solve_cloudflare = None
        save_cf_clearance = None

# API endpoints
API_BASE = "https://grok.com"
CREATE_VIDEO_URL = f"{API_BASE}/rest/media/post/create"
CREATE_LINK_URL = f"{API_BASE}/rest/media/post/create-link"
CONVERSATIONS_URL = f"{API_BASE}/rest/app-chat/conversations/new"

# Video download URL template (thêm dl=1 để download)
VIDEO_DOWNLOAD_URL = "https://imagine-public.x.ai/imagine-public/share-videos/{post_id}.mp4?cache=1&dl=1"

OUTPUT_DIR = Path("output")


class GrokAPI:
    def __init__(self, auto_refresh_cf: bool = True):
        self.client = httpx.Client(timeout=300.0, verify=False)
        self.auto_refresh_cf = auto_refresh_cf
        self._cf_refresh_attempted = False
        self._user_agent = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36'
    
    def _refresh_cf_clearance(
        self,
        cookies: dict,
        on_status: Optional[Callable] = None,
    ) -> dict:
        """Refresh cf_clearance cookie using CloudflareSolver."""
        if not CF_SOLVER_AVAILABLE or not solve_cloudflare:
            if on_status:
                on_status("⚠️ CF solver not available. Install: pip install zendriver latest-user-agents user-agents")
            return cookies
        
        if on_status:
            on_status("🔄 Refreshing cf_clearance...")
        
        result = solve_cloudflare(
            url="https://grok.com",
            timeout=30,
            headless=False,  # Need headed mode for interactive challenges
            on_status=on_status,
            existing_cookies=cookies,  # Pass existing cookies (sso, sso-rw)
        )
        
        if result and result.get("cf_clearance"):
            cookies["cf_clearance"] = result["cf_clearance"]
            # Update user agent to match the one used to get cf_clearance
            if result.get("user_agent"):
                self._user_agent = result["user_agent"]
            if save_cf_clearance:
                save_cf_clearance(result)
            if on_status:
                on_status(f"✅ cf_clearance refreshed!")
        else:
            if on_status:
                on_status("❌ Failed to refresh cf_clearance")
        
        return cookies
    
    def _get_headers(self, cookies: dict) -> dict:
        """Generate headers for API request"""
        return {
            'accept': '*/*',
            'accept-language': 'vi-VN,vi;q=0.9,fr-FR;q=0.8,fr;q=0.7,en-US;q=0.6,en;q=0.5',
            'content-type': 'application/json',
            'origin': 'https://grok.com',
            'referer': 'https://grok.com/imagine',
            'sec-ch-ua': '"Not(A:Brand";v="8", "Chromium";v="144", "Google Chrome";v="144"',
            'sec-ch-ua-arch': '"arm"',
            'sec-ch-ua-bitness': '"64"',
            'sec-ch-ua-full-version': '"144.0.7559.132"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-model': '""',
            'sec-ch-ua-platform': '"macOS"',
            'sec-ch-ua-platform-version': '"26.2.0"',
            'sec-fetch-dest': 'empty',
            'sec-fetch-mode': 'cors',
            'sec-fetch-site': 'same-origin',
            'user-agent': self._user_agent,
            'x-xai-request-id': str(uuid.uuid4()),
        }
    
    def generate_video(
        self,
        cookies: dict,
        prompt: str,
        aspect_ratio: str = "16:9",
        video_length: int = 6,
        resolution: str = "480p",
        on_status: Optional[Callable] = None,
    ) -> Optional[str]:
        """
        Full video generation flow:
        1. Create initial post → get parentPostId
        2. Generate video with settings using parentPostId
        Returns final post_id if successful
        """
        if not cookies:
            if on_status:
                on_status("No cookies provided")
            return None
        
        # Check required cookies
        required = ['cf_clearance', 'sso', 'sso-rw']
        missing = [c for c in required if c not in cookies]
        if missing:
            # Try to refresh cf_clearance if missing
            if 'cf_clearance' in missing and self.auto_refresh_cf:
                cookies = self._refresh_cf_clearance(cookies, on_status)
                missing = [c for c in required if c not in cookies]
            
            if missing:
                if on_status:
                    on_status(f"Missing cookies: {missing}")
                return None
        
        headers = self._get_headers(cookies)
        
        # Step 1: Create initial post
        if on_status:
            on_status(f"Step 1: Creating initial post...")
        
        payload1 = {
            "mediaType": "MEDIA_POST_TYPE_VIDEO",
            "prompt": prompt
        }
        
        try:
            response = self.client.post(
                CREATE_VIDEO_URL,
                headers=headers,
                cookies=cookies,
                json=payload1,
                timeout=60.0
            )
            
            # Auto refresh cf_clearance on 403
            if response.status_code == 403 and self.auto_refresh_cf and not self._cf_refresh_attempted:
                self._cf_refresh_attempted = True
                if on_status:
                    on_status("403 Forbidden - cf_clearance expired, refreshing...")
                cookies = self._refresh_cf_clearance(cookies, on_status)
                
                # Retry request
                headers = self._get_headers(cookies)
                response = self.client.post(
                    CREATE_VIDEO_URL,
                    headers=headers,
                    cookies=cookies,
                    json=payload1,
                    timeout=60.0
                )
            
            if response.status_code == 403:
                if on_status:
                    on_status("403 Forbidden - cf_clearance expired")
                return None
            
            if response.status_code != 200:
                if on_status:
                    on_status(f"Create post failed: HTTP {response.status_code}")
                return None
            
            # Reset refresh flag on success
            self._cf_refresh_attempted = False
            
            # Extract parentPostId
            data = response.json()
            parent_post_id = data.get('postId') or data.get('id')
            
            if not parent_post_id:
                text = response.text
                uuid_pattern = r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}'
                matches = re.findall(uuid_pattern, text)
                if matches:
                    parent_post_id = matches[-1]
            
            if not parent_post_id:
                if on_status:
                    on_status("Failed to get parentPostId")
                return None
            
            if on_status:
                on_status(f"Got parentPostId: {parent_post_id}")
            
        except Exception as e:
            if on_status:
                on_status(f"Step 1 error: {e}")
            return None
        
        # Step 2: Generate video with settings
        if on_status:
            on_status(f"Step 2: Generating video with settings...")
        
        headers['referer'] = f'https://grok.com/imagine/post/{parent_post_id}'
        
        video_config = {
            "parentPostId": parent_post_id,
            "aspectRatio": aspect_ratio,
            "videoLength": video_length,
            "resolutionName": resolution
        }
        
        payload2 = {
            "temporary": True,
            "modelName": "grok-3",
            "message": f"{prompt} --mode=custom",
            "toolOverrides": {"videoGen": True},
            "enableSideBySide": True,
            "responseMetadata": {
                "experiments": [],
                "modelConfigOverride": {
                    "modelMap": {
                        "videoGenModelConfig": video_config
                    }
                }
            }
        }
        
        try:
            # Stream response
            with self.client.stream(
                "POST",
                CONVERSATIONS_URL,
                headers=headers,
                cookies=cookies,
                json=payload2,
                timeout=300.0
            ) as response:
                
                if response.status_code == 403:
                    if on_status:
                        on_status("403 Forbidden - cf_clearance expired")
                    return None
                
                if response.status_code != 200:
                    if on_status:
                        on_status(f"Generate video failed: HTTP {response.status_code}")
                    return None
                
                # Read streaming response
                full_text = ""
                for chunk in response.iter_text():
                    full_text += chunk
                
                # Extract final postId
                uuid_pattern = r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}'
                matches = re.findall(uuid_pattern, full_text)
                
                # Filter out parentPostId, get the new one
                final_post_id = None
                for m in reversed(matches):
                    if m != parent_post_id:
                        final_post_id = m
                        break
                
                if not final_post_id:
                    final_post_id = parent_post_id  # Fallback
                
                if on_status:
                    on_status(f"✅ Video created! Post ID: {final_post_id}")
                
                return final_post_id
                
        except Exception as e:
            if on_status:
                on_status(f"Step 2 error: {e}")
            return None
            
    def create_share_link(
        self,
        cookies: dict,
        post_id: str,
        on_status: Optional[Callable] = None,
    ) -> bool:
        """
        Create share link for video (required before download)
        """
        if not cookies or not post_id:
            return False
        
        headers = self._get_headers(cookies)
        headers['referer'] = f'https://grok.com/imagine/post/{post_id}'
        
        payload = {
            "postId": post_id,
            "source": "post-page",
            "platform": "web"
        }
        
        if on_status:
            on_status(f"Creating share link for {post_id[:8]}...")
        
        try:
            response = self.client.post(
                CREATE_LINK_URL,
                headers=headers,
                cookies=cookies,
                json=payload,
                timeout=30.0
            )
            
            if response.status_code == 200:
                if on_status:
                    on_status(f"✅ Share link created!")
                return True
            else:
                if on_status:
                    on_status(f"Create link failed: HTTP {response.status_code}")
                return False
                
        except Exception as e:
            if on_status:
                on_status(f"Create link error: {e}")
            return False
    
    def generate_and_share(
        self,
        cookies: dict,
        prompt: str,
        aspect_ratio: str = "16:9",
        video_length: int = 6,
        resolution: str = "480p",
        on_status: Optional[Callable] = None,
    ) -> Optional[str]:
        """
        Full flow: Create video + Create share link
        Returns post_id if successful
        """
        # Step 1: Create video
        post_id = self.generate_video(
            cookies, prompt, 
            aspect_ratio=aspect_ratio,
            video_length=video_length,
            resolution=resolution,
            on_status=on_status
        )
        
        if not post_id:
            return None
        
        # Step 2: Create share link
        time.sleep(1)
        self.create_share_link(cookies, post_id, on_status=on_status)
        
        return post_id
    
    def get_video_url(self, post_id: str) -> str:
        """Get download URL from post_id"""
        return VIDEO_DOWNLOAD_URL.format(post_id=post_id)
    
    def download_video(
        self,
        post_id: str,
        cookies: dict = None,
        filename: Optional[str] = None,
        on_status: Optional[Callable] = None
    ) -> Optional[str]:
        """Download video from post_id"""
        url = self.get_video_url(post_id)
        
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        
        if not filename:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{ts}_{post_id[:8]}.mp4"
        
        path = OUTPUT_DIR / filename
        
        if on_status:
            on_status(f"Downloading video...")
        
        try:
            headers = {
                'accept': '*/*',
                'accept-language': 'vi-VN,vi;q=0.9',
                'origin': 'https://grok.com',
                'referer': 'https://grok.com/',
                'sec-ch-ua': '"Not(A:Brand";v="8", "Chromium";v="144", "Google Chrome";v="144"',
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': '"macOS"',
                'sec-fetch-dest': 'empty',
                'sec-fetch-mode': 'cors',
                'sec-fetch-site': 'cross-site',
                'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36',
            }
            
            with self.client.stream("GET", url, headers=headers, timeout=180.0) as r:
                if r.status_code != 200:
                    if on_status:
                        on_status(f"Download failed: HTTP {r.status_code}")
                    return None
                
                total = int(r.headers.get('content-length', 0))
                downloaded = 0
                
                with open(path, "wb") as f:
                    for chunk in r.iter_bytes(chunk_size=8192):
                        f.write(chunk)
                        downloaded += len(chunk)
                        if on_status and total > 0 and downloaded % (100 * 1024) < 8192:
                            pct = int(downloaded * 100 / total)
                            on_status(f"Downloading... {pct}%")
            
            if path.exists() and path.stat().st_size > 10000:
                size_kb = path.stat().st_size // 1024
                if on_status:
                    on_status(f"✅ Downloaded: {filename} ({size_kb}KB)")
                return str(path)
            
            return None
            
        except Exception as e:
            if on_status:
                on_status(f"Download error: {e}")
            return None
    
    def full_flow(
        self,
        cookies: dict,
        prompt: str,
        aspect_ratio: str = "16:9",
        video_length: int = 6,
        resolution: str = "480p",
        download: bool = True,
        on_status: Optional[Callable] = None
    ) -> dict:
        """
        Complete flow: Create video → Create share link → Download
        Returns dict with post_id, url, output_path
        """
        result = {
            'post_id': None,
            'url': None,
            'output_path': None,
            'success': False
        }
        
        # Step 1 & 2: Create video with settings
        post_id = self.generate_video(
            cookies, prompt,
            aspect_ratio=aspect_ratio,
            video_length=video_length,
            resolution=resolution,
            on_status=on_status
        )
        if not post_id:
            return result
        
        result['post_id'] = post_id
        result['url'] = self.get_video_url(post_id)
        
        # Step 3: Create share link
        time.sleep(1)
        self.create_share_link(cookies, post_id, on_status=on_status)
        
        # Step 4: Download (optional)
        if download:
            time.sleep(1)
            output_path = self.download_video(post_id, on_status=on_status)
            result['output_path'] = output_path
        
        result['success'] = True
        return result
    
    def close(self):
        self.client.close()


def parse_cookies_from_curl(curl_command: str) -> dict:
    """Parse cookies from curl command"""
    cookies = {}
    
    # Find -b or --cookie
    import re
    match = re.search(r"-b\s+'([^']+)'", curl_command)
    if not match:
        match = re.search(r'-b\s+"([^"]+)"', curl_command)
    if not match:
        match = re.search(r'--cookie\s+[\'"]([^\'"]+)[\'"]', curl_command)
    
    if match:
        cookie_str = match.group(1)
        for part in cookie_str.split('; '):
            if '=' in part:
                key, value = part.split('=', 1)
                cookies[key.strip()] = value.strip()
    
    return cookies
