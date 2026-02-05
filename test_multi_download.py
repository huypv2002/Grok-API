"""Test multi-tab video generation with download"""
import asyncio
import json
import sys
from pathlib import Path
sys.path.insert(0, '.')

from src.core.video_generator import MultiTabVideoGenerator, OUTPUT_DIR, ZENDRIVER_AVAILABLE
from src.core.models import Account, VideoSettings


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


async def test_multi_download():
    """Generate 2 videos with 2 tabs and download"""
    print("=" * 60)
    print("Multi-Tab Generate + Download Test")
    print("=" * 60)
    
    if not ZENDRIVER_AVAILABLE:
        print("❌ zendriver not installed")
        return
    
    account = load_test_account()
    print(f"✅ Account: {account.email}")
    
    # 2 prompts, 2 tabs
    prompts = [
        "A majestic eagle soaring through mountain peaks",
        "A futuristic city with flying cars at night"
    ]
    settings = VideoSettings(aspect_ratio="16:9", video_length=6)
    
    def on_status(email, msg):
        print(f"[GEN] {msg}")
    
    generator = MultiTabVideoGenerator(
        account=account,
        num_tabs=2,
        headless=True,
        on_status=on_status
    )
    
    try:
        print("\n🚀 Starting browser with 2 tabs...")
        if not await generator.start():
            print("❌ Failed to start browser")
            return
        
        print("\n📋 Generating 2 videos concurrently...")
        results = await generator.generate_batch(prompts, settings)
        
        print("\n" + "=" * 60)
        print("📊 Results:")
        print("=" * 60)
        
        success_count = 0
        for i, task in enumerate(results):
            print(f"\n[{i+1}] Prompt: {task.prompt[:40]}...")
            print(f"    Status: {task.status}")
            print(f"    Post ID: {task.post_id}")
            print(f"    Output: {task.output_path}")
            
            if task.output_path:
                import os
                if os.path.exists(task.output_path):
                    size_mb = os.path.getsize(task.output_path) / (1024 * 1024)
                    print(f"    ✅ File size: {size_mb:.1f} MB")
                    success_count += 1
        
        print(f"\n🎉 Success: {success_count}/{len(results)} videos downloaded")
            
    finally:
        await generator.stop()
        print("\n🛑 Browser closed")


if __name__ == "__main__":
    asyncio.run(test_multi_download())
