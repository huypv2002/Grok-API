"""Test generate video and download immediately"""
import asyncio
import json
import sys
from pathlib import Path
sys.path.insert(0, '.')

from src.core.video_generator import MultiTabVideoGenerator, OUTPUT_DIR, VIDEO_DOWNLOAD_URL, ZENDRIVER_AVAILABLE
from src.core.models import Account, VideoSettings
from src.core.cf_solver import get_chrome_user_agent
import requests


def load_test_account():
    """Load account from accounts.json"""
    accounts_file = Path("data/accounts.json")
    data = json.loads(accounts_file.read_text())
    acc_data = data["accounts"][0]
    return Account(
        email=acc_data["email"],
        password=acc_data.get("password_encrypted", ""),
        cookies=acc_data["cookies"],
        status=acc_data["status"]
    )


async def test_gen_and_download():
    """Generate 1 video and download immediately"""
    print("=" * 60)
    print("Generate and Download Test")
    print("=" * 60)
    
    if not ZENDRIVER_AVAILABLE:
        print("❌ zendriver not installed")
        return
    
    account = load_test_account()
    print(f"✅ Account: {account.email}")
    
    # Single prompt
    prompts = ["A beautiful golden sunset over calm ocean waves"]
    settings = VideoSettings(aspect_ratio="16:9", video_length=6)
    
    def on_status(email, msg):
        print(f"[GEN] {msg}")
    
    # Generate video
    generator = MultiTabVideoGenerator(
        account=account,
        num_tabs=1,  # Just 1 tab for this test
        headless=True,
        on_status=on_status
    )
    
    try:
        print("\n🚀 Starting browser...")
        if not await generator.start():
            print("❌ Failed to start browser")
            return
        
        print("\n📋 Generating video...")
        results = await generator.generate_batch(prompts, settings)
        
        if not results:
            print("❌ No results returned")
            return
            
        task = results[0]
        
        print(f"\n{'='*60}")
        print(f"📊 Result:")
        print(f"   Status: {task.status}")
        print(f"   Post ID: {task.post_id}")
        print(f"   Media URL: {task.media_url}")
        print(f"   Output Path: {task.output_path}")
        print(f"   Error: {task.error_message}")
        print(f"{'='*60}")
        
        if task.status == "completed" and task.output_path:
            import os
            if os.path.exists(task.output_path):
                size_mb = os.path.getsize(task.output_path) / (1024 * 1024)
                print(f"\n✅ SUCCESS! Video downloaded: {task.output_path} ({size_mb:.1f} MB)")
            else:
                print(f"\n⚠️ Output path set but file not found: {task.output_path}")
        elif task.status == "completed":
            print(f"\n⚠️ Video generated but not downloaded. Post ID: {task.post_id}")
        else:
            print(f"\n❌ Generation failed: {task.error_message}")
            
    finally:
        await generator.stop()
        print("\n🛑 Browser closed")


if __name__ == "__main__":
    asyncio.run(test_gen_and_download())
