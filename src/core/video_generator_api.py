"""Video Generator API - Fast video generation using direct API calls"""
import asyncio
import time
import re
import os
import glob
from pathlib import Path
from datetime import datetime
from typing import Optional, Callable, List, Dict, Any

from .models import Account, VideoSettings, VideoTask
from .grok_api import GrokAPI, VIDEO_DOWNLOAD_URL
from .cf_solver import solve_cloudflare, get_chrome_user_agent, CF_SOLVER_AVAILABLE

try:
    import zendriver
    from zendriver import cdp
    ZENDRIVER_AVAILABLE = True
except ImportError:
    ZENDRIVER_AVAILABLE = False

OUTPUT_DIR = Path("output")


class APIVideoGenerator:
    """
    Fast video generator using direct API calls.
    
    Flow:
    1. Get cf_clearance cookie via browser (once)
    2. Use API to create videos (fast, no browser needed)
    3. Use browser to download videos (need __cf_bm cookie)
    
    Much faster than full browser automation!
    """
    
    def __init__(
        self,
        account: Account,
        headless: bool = True,
        on_status: Optional[Callable] = None
    ):
        self.account = account
        self.headless = headless
        self.on_status = on_status
        
        self.api = GrokAPI(auto_refresh_cf=False)
        self.cookies: Dict[str, str] = {}
        self._cf_valid = False
        
        # Browser for downloads only
        self.browser = None
        self.download_tab = None
    
    def _log(self, msg: str):
        """Log message"""
        prefix = f"[{self.account.email[:15]}]"
        full_msg = f"{prefix} {msg}"
        print(full_msg)
        if self.on_status:
            self.on_status(self.account.email, full_msg)
    
    async def init_cookies(self) -> bool:
        """Initialize cookies - get cf_clearance via browser"""
        if not CF_SOLVER_AVAILABLE:
            self._log("❌ zendriver not installed")
            return False
        
        # Start with account cookies
        self.cookies = dict(self.account.cookies) if self.account.cookies else {}
        
        # Check if cf_clearance exists and valid
        if 'cf_clearance' in self.cookies:
            self._log("✅ Using existing cf_clearance")
            self._cf_valid = True
            return True
        
        # Need to get cf_clearance via browser
        self._log("🔄 Getting cf_clearance...")
        
        result = solve_cloudflare(
            url="https://grok.com/imagine",
            timeout=60,
            headless=self.headless,
            on_status=lambda msg: self._log(msg),
            existing_cookies=self.cookies
        )
        
        if result and result.get('cf_clearance'):
            self.cookies['cf_clearance'] = result['cf_clearance']
            self._cf_valid = True
            self._log("✅ Got cf_clearance!")
            return True
        
        self._log("❌ Failed to get cf_clearance")
        return False
    
    async def generate_video(
        self,
        prompt: str,
        settings: VideoSettings
    ) -> VideoTask:
        """Generate video using API (fast!)"""
        task = VideoTask(
            account_email=self.account.email,
            prompt=prompt,
            settings=settings,
            status="creating"
        )
        
        # Ensure cookies are ready
        if not self._cf_valid:
            if not await self.init_cookies():
                task.status = "failed"
                task.error_message = "Failed to get cf_clearance"
                return task
        
        self._log(f"📤 Creating video: {prompt[:40]}...")
        
        # Use API to create video
        post_id = self.api.generate_video(
            cookies=self.cookies,
            prompt=prompt,
            aspect_ratio=settings.aspect_ratio if settings else "16:9",
            video_length=settings.video_length if settings else 6,
            resolution=settings.resolution if settings else "480p",
            on_status=lambda msg: self._log(msg)
        )
        
        if not post_id:
            # cf_clearance might be expired, try refresh
            if not self._cf_valid or 'cf_clearance' not in self.cookies:
                self._log("⚠️ cf_clearance expired, refreshing...")
                self._cf_valid = False
                if await self.init_cookies():
                    # Retry
                    post_id = self.api.generate_video(
                        cookies=self.cookies,
                        prompt=prompt,
                        aspect_ratio=settings.aspect_ratio if settings else "16:9",
                        video_length=settings.video_length if settings else 6,
                        resolution=settings.resolution if settings else "480p",
                        on_status=lambda msg: self._log(msg)
                    )
        
        if not post_id:
            task.status = "failed"
            task.error_message = "API failed to create video"
            return task
        
        task.post_id = post_id
        task.media_url = VIDEO_DOWNLOAD_URL.format(post_id=post_id)
        
        # Create share link
        self._log("🔗 Creating share link...")
        self.api.create_share_link(self.cookies, post_id, on_status=lambda msg: self._log(msg))
        
        task.status = "completed"
        task.completed_at = datetime.now()
        task.account_cookies = self.cookies
        
        self._log(f"✅ Video created! Post ID: {post_id}")
        
        return task
    
    async def download_video(self, task: VideoTask) -> Optional[str]:
        """Download video using browser (need __cf_bm cookie)"""
        if not task.post_id or not task.media_url:
            return None
        
        if not ZENDRIVER_AVAILABLE:
            self._log("❌ zendriver not installed for download")
            return None
        
        self._log(f"📥 Downloading video {task.post_id[:8]}...")
        
        try:
            # Start browser if not running
            if not self.browser:
                user_agent = get_chrome_user_agent()
                config = zendriver.Config(headless=self.headless)
                config.add_argument(f"--user-agent={user_agent}")
                config.add_argument("--mute-audio")
                
                self.browser = zendriver.Browser(config)
                await self.browser.start()
            
            # Navigate to video URL to get __cf_bm cookie
            video_url = task.media_url
            download_url = f"{video_url}&dl=1" if '?' in video_url else f"{video_url}?dl=1"
            
            download_tab = await self.browser.get(video_url, new_tab=True)
            await asyncio.sleep(3)
            
            # Set download behavior
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            await download_tab.send(cdp.browser.set_download_behavior(
                behavior="allow",
                download_path=str(OUTPUT_DIR.absolute())
            ))
            
            # Trigger download
            self._log("   Triggering download...")
            await download_tab.get(download_url)
            
            # Wait for download
            for i in range(30):
                await asyncio.sleep(5)
                
                mp4_files = glob.glob(str(OUTPUT_DIR / "*.mp4"))
                if mp4_files:
                    newest = max(mp4_files, key=os.path.getctime)
                    size = os.path.getsize(newest)
                    
                    if size > 10000:
                        await asyncio.sleep(2)
                        new_size = os.path.getsize(newest)
                        if new_size == size:
                            try:
                                await download_tab.close()
                            except:
                                pass
                            
                            size_mb = size / (1024 * 1024)
                            self._log(f"✅ Downloaded: {os.path.basename(newest)} ({size_mb:.1f} MB)")
                            return newest
                
                if i % 3 == 0:
                    self._log(f"   Waiting... ({i * 5}s)")
            
            try:
                await download_tab.close()
            except:
                pass
            
            self._log("⚠️ Download timeout")
            return None
            
        except Exception as e:
            self._log(f"⚠️ Download error: {e}")
            return None
    
    async def generate_batch(
        self,
        prompts: List[str],
        settings: VideoSettings,
        download: bool = True,
        on_task_complete: Optional[Callable] = None
    ) -> List[VideoTask]:
        """
        Generate multiple videos using API.
        Much faster than browser automation!
        """
        results: List[VideoTask] = []
        
        # Ensure cookies are ready
        if not self._cf_valid:
            if not await self.init_cookies():
                return [VideoTask(
                    account_email=self.account.email,
                    prompt=p,
                    settings=settings,
                    status="failed",
                    error_message="Failed to get cf_clearance"
                ) for p in prompts]
        
        self._log(f"📋 Starting batch: {len(prompts)} videos")
        
        for i, prompt in enumerate(prompts):
            self._log(f"[{i+1}/{len(prompts)}] Processing...")
            
            # Generate video via API
            task = await self.generate_video(prompt, settings)
            
            # Download if requested and successful
            if download and task.status == "completed":
                output_path = await self.download_video(task)
                if output_path:
                    task.output_path = output_path
            
            results.append(task)
            
            if on_task_complete:
                on_task_complete(task)
            
            # Small delay between requests
            if i < len(prompts) - 1:
                await asyncio.sleep(1)
        
        success_count = len([r for r in results if r.status == 'completed'])
        self._log(f"🎉 Batch complete: {success_count}/{len(results)} OK")
        
        return results
    
    async def stop(self):
        """Stop and cleanup"""
        if self.browser:
            try:
                await self.browser.stop()
            except:
                pass
            self.browser = None
        
        self.api.close()


async def run_api_generation(
    account: Account,
    prompts: List[str],
    settings: VideoSettings,
    headless: bool = True,
    download: bool = True,
    on_status: Optional[Callable] = None,
    on_task_complete: Optional[Callable] = None
) -> List[VideoTask]:
    """
    Run video generation using API (fast mode).
    
    Args:
        account: Account with cookies
        prompts: List of prompts
        settings: Video settings
        headless: Run browser headless
        download: Download videos after creation
        on_status: Status callback
        on_task_complete: Task complete callback
    
    Returns:
        List of VideoTask results
    """
    generator = APIVideoGenerator(
        account=account,
        headless=headless,
        on_status=on_status
    )
    
    try:
        results = await generator.generate_batch(
            prompts=prompts,
            settings=settings,
            download=download,
            on_task_complete=on_task_complete
        )
        return results
    finally:
        await generator.stop()


def run_api_generation_sync(
    account: Account,
    prompts: List[str],
    settings: VideoSettings,
    headless: bool = True,
    download: bool = True,
    on_status: Optional[Callable] = None,
    on_task_complete: Optional[Callable] = None
) -> List[VideoTask]:
    """Synchronous wrapper for API generation"""
    return asyncio.run(run_api_generation(
        account, prompts, settings, headless, download, on_status, on_task_complete
    ))
