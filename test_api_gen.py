"""Test API-based video generation (fast mode)"""
import asyncio
from src.core.account_manager import AccountManager
from src.core.video_generator_api import APIVideoGenerator
from src.core.models import VideoSettings

async def main():
    # Load account
    am = AccountManager()
    accounts = am.get_all_accounts()
    
    if not accounts:
        print("No accounts found!")
        return
    
    account = accounts[0]
    print(f"Using account: {account.email}")
    
    # Test prompts
    prompts = [
        "A cat playing piano in a jazz club, cinematic lighting",
        "A robot walking on Mars, sci-fi style",
    ]
    
    settings = VideoSettings(
        aspect_ratio="16:9",
        video_length=6,
        resolution="480p"
    )
    
    def on_status(email, msg):
        print(msg)
    
    def on_complete(task):
        print(f"✅ Task done: {task.status} - {task.post_id}")
    
    # Run API generation
    generator = APIVideoGenerator(
        account=account,
        headless=True,
        on_status=on_status
    )
    
    try:
        results = await generator.generate_batch(
            prompts=prompts,
            settings=settings,
            download=True,
            on_task_complete=on_complete
        )
        
        print(f"\n=== Results ===")
        for r in results:
            print(f"- {r.prompt[:30]}... -> {r.status}")
            if r.output_path:
                print(f"  Downloaded: {r.output_path}")
    finally:
        await generator.stop()


if __name__ == "__main__":
    asyncio.run(main())
