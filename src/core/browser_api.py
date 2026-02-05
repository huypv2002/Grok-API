"""Browser API - Hybrid approach using VideoGenerator + cf_solver"""
import asyncio
from pathlib import Path
from datetime import datetime
from typing import Optional, Callable, Dict, Any

from .video_generator import VideoGenerator
from .models import Account, VideoSettings
from .cf_solver import solve_cloudflare, CF_SOLVER_AVAILABLE

VIDEO_DOWNLOAD_URL = "https://imagine-public.x.ai/imagine-public/share-videos/{post_id}.mp4?cache=1&dl=1"
OUTPUT_DIR = Path("output")
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36"


def get_cf_clearance_sync(
    cookies: Dict[str, str],
    headless: bool = False,
    on_status: Optional[Callable] = None,
) -> Optional[Dict[str, str]]:
    """
    Get cf_clearance using CloudflareSolver from cf_solver.py.
    This uses the full detection and solving logic from giaima/deobfuscator.py
    """
    if not CF_SOLVER_AVAILABLE:
        if on_status:
            on_status("❌ zendriver not installed")
        return None
    
    if on_status:
        on_status("🔄 Getting cf_clearance using CloudflareSolver...")
    
    # Use solve_cloudflare which has full challenge detection and solving
    result = solve_cloudflare(
        url="https://grok.com/imagine",
        timeout=60,
        headless=headless,
        on_status=on_status,
        existing_cookies=cookies,
    )
    
    if result and result.get("cf_clearance"):
        return result["cookies"]
    
    return None


def run_video_generation(
    cookies: Dict[str, str],
    prompt: str,
    aspect_ratio: str = "16:9",
    video_length: int = 6,
    resolution: str = "720p",
    headless: bool = True,
    on_status: Optional[Callable] = None,
) -> Dict[str, Any]:
    """
    Run video generation using VideoGenerator (tool chính).
    
    Flow:
    1. Get cf_clearance using CloudflareSolver (with full challenge detection/solving)
    2. Use VideoGenerator to generate video via browser automation (headless)
    """
    result = {"post_id": None, "url": None, "output_path": None, "success": False}
    
    # Step 1: Get cf_clearance using CloudflareSolver
    updated_cookies = get_cf_clearance_sync(cookies, headless=headless, on_status=on_status)
    
    if not updated_cookies:
        if on_status:
            on_status("❌ Could not get cf_clearance")
        return result
    
    # Step 2: Create Account object
    account = Account(
        email="api_user@example.com",
        password="",
        fingerprint_id="browser-api-profile",
        status="logged_in",
        cookies=updated_cookies,
    )
    
    # Step 3: Create VideoSettings
    settings = VideoSettings(
        aspect_ratio=aspect_ratio,
        video_length=video_length,
        resolution=resolution,
    )
    
    # Step 4: Generate video using VideoGenerator (headless)
    if on_status:
        on_status("🎬 Starting video generation...")
    
    generator = VideoGenerator()
    
    try:
        task = generator.generate_video(
            account=account,
            prompt=prompt,
            settings=settings,
            on_status=on_status,
            headless=headless,
        )
        
        result["post_id"] = task.post_id
        result["url"] = task.media_url
        result["output_path"] = task.output_path
        result["success"] = task.status == "completed"
        
        if on_status:
            if task.status == "completed":
                on_status(f"✅ Video generated! Post ID: {task.post_id}")
            else:
                on_status(f"❌ Failed: {task.error_message}")
        
    finally:
        generator.close()
    
    return result


# Alias for backward compatibility
def run_browser_api(
    cookies: Dict[str, str],
    prompt: str,
    aspect_ratio: str = "16:9",
    video_length: int = 6,
    resolution: str = "720p",
    download: bool = True,
    headless: bool = True,
    on_status: Optional[Callable] = None,
) -> Dict[str, Any]:
    """Alias for run_video_generation."""
    return run_video_generation(
        cookies=cookies,
        prompt=prompt,
        aspect_ratio=aspect_ratio,
        video_length=video_length,
        resolution=resolution,
        headless=headless,
        on_status=on_status,
    )
