"""Test multi-tab video generation"""
import asyncio
import json
import sys
from pathlib import Path
sys.path.insert(0, '.')

from src.core.video_generator import MultiTabVideoGenerator, ZENDRIVER_AVAILABLE
from src.core.models import Account, VideoSettings


def load_test_account():
    """Load account from accounts.json"""
    accounts_file = Path("data/accounts.json")
    if not accounts_file.exists():
        print("   accounts.json not found")
        return None
    
    try:
        data = json.loads(accounts_file.read_text())
        accounts = data.get("accounts", [])
        print(f"   Found {len(accounts)} accounts")
        
        for acc_data in accounts:
            status = acc_data.get("status", "")
            has_cookies = bool(acc_data.get("cookies"))
            print(f"   - {acc_data.get('email')}: status={status}, has_cookies={has_cookies}")
            
            if status == "logged_in" and has_cookies:
                return Account(
                    email=acc_data["email"],
                    password=acc_data.get("password_encrypted", ""),
                    cookies=acc_data["cookies"],
                    status=acc_data["status"]
                )
    except Exception as e:
        print(f"   Error loading accounts: {e}")
        import traceback
        traceback.print_exc()
    return None


async def test_multi_tab():
    """Test multi-tab video generation"""
    print("=" * 60)
    print("Multi-Tab Video Generation Test")
    print("=" * 60)
    
    if not ZENDRIVER_AVAILABLE:
        print("❌ zendriver not installed")
        return
    
    # Load real account
    account = load_test_account()
    if not account:
        print("❌ No logged-in account found in data/accounts.json")
        print("   Please login first using the GUI")
        return
    
    print(f"✅ Using account: {account.email}")
    
    # Test prompts
    prompts = [
        "A beautiful sunset over the ocean with waves crashing on the beach",
        "A cute cat playing with a ball of yarn in a cozy living room",
        "A futuristic city skyline with flying cars and neon lights at night",
    ]
    
    settings = VideoSettings(aspect_ratio="16:9", video_length=6)
    
    def on_status(email, msg):
        print(f"[STATUS] {msg}")
    
    def on_task_complete(task):
        status_icon = "✅" if task.status == "completed" else "❌"
        print(f"[TASK] {status_icon} {task.status}: {task.post_id or task.error_message}")
    
    # Create generator
    generator = MultiTabVideoGenerator(
        account=account,
        num_tabs=3,
        headless=True,
        on_status=on_status
    )
    
    try:
        print("\n🚀 Starting browser with 3 tabs...")
        if not await generator.start():
            print("❌ Failed to start browser")
            return
        
        print("\n📋 Generating 3 videos concurrently...")
        results = await generator.generate_batch(
            prompts,
            settings,
            on_task_complete
        )
        
        print("\n" + "=" * 60)
        print("Results:")
        print("=" * 60)
        for i, task in enumerate(results):
            status_icon = "✅" if task.status == "completed" else "❌"
            print(f"{status_icon} Prompt {i+1}: {task.status}")
            if task.post_id:
                print(f"   Post ID: {task.post_id}")
                print(f"   URL: {task.media_url}")
                print(f"   user_data_dir: {task.user_data_dir}")
                print(f"   has_cookies: {bool(task.account_cookies)}")
            elif task.error_message:
                print(f"   Error: {task.error_message}")
        
        completed = len([t for t in results if t.status == "completed"])
        print(f"\n🎉 Done: {completed}/{len(results)} successful")
        
    finally:
        await generator.stop()
        print("\n🛑 Browser closed")


if __name__ == "__main__":
    asyncio.run(test_multi_tab())
