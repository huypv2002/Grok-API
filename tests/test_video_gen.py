"""
Test tạo video qua GrokAPI — dùng cookies thật từ curl.

Usage:
  python tests/test_video_gen.py
  python tests/test_video_gen.py --prompt "a cat dancing"
  python tests/test_video_gen.py --step 1        # chỉ test step 1 (create media post)
  python tests/test_video_gen.py --step 2 --parent-id <id>  # test step 2 với parent_id có sẵn
  python tests/test_video_gen.py --step 3 --post-id <id>    # test step 3 (share link)
  python tests/test_video_gen.py --download --post-id <id>  # test download video

Trước khi chạy: cập nhật COOKIES dict bên dưới bằng cookies mới nhất.
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core.grok_api import GrokAPI, VIDEO_DOWNLOAD_URL

# ============================================================
# COOKIES — cập nhật từ curl mới nhất
# ============================================================
COOKIES = {
    "sso-rw": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzZXNzaW9uX2lkIjoiNzM1YWQ4NjctMThjYS00NTg0LWI4NTAtNDdkOWNjOWE4NmM2In0.3z_FTWh5z37koGtn84coojOg6luTrHCd--9rDg8eTvE",
    "sso": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzZXNzaW9uX2lkIjoiNzM1YWQ4NjctMThjYS00NTg0LWI4NTAtNDdkOWNjOWE4NmM2In0.3z_FTWh5z37koGtn84coojOg6luTrHCd--9rDg8eTvE",
    "x-userid": "15d72486-0dbc-4275-8503-782243ba35eb",
    "cf_clearance": "6kpE9F4m828j6N8swnroqWz2kWZpMqYPwOFtCaQOIjg-1771828873-1.2.1.1-JhIAcZApTEoqfbge2bW._EOJYcyhqQK2hikZ_9ogMRkOU45zrSs1UX.XUi6ldsPO7Ig8q1IGjkBIM5OVz9tkM.bDNqL3rzLuOleds4Y78zGo1pDEB99mkzxIYZPlc6Ttlj7nMviIweVROS.Nkslk7yYXUbapFofWV4S.HnfFGqXzWuL4F0Da9HPPlX06_7BhayZ0xrvctzIbSOaHLtIhY5XkqcAl.9yLubJOgca0mi8P1jqzxcuCmAu5I9hOjVTz",
    "__cf_bm": "8EbXgqf23x31Juh0T2zhT5v8ijprKmL_RIoO4czrwPw-1771829910-1.0.1.1-4pen9nGFZEffQelZtzLeyyB_D3oGVMMDLxgqqgqaYhFrPZUIXotT0a8ZilOjQ1OvZumh4Jkauu938woZDxDwM0gTFjTLebE_UFbMreTfe4E",
}

DEFAULT_PROMPT = "the girl smile --mode=custom"


def status_callback(msg: str):
    """Print status messages."""
    print(f"  {msg}")


def test_step1_create_media_post(api: GrokAPI, prompt: str) -> str | None:
    """Step 1: POST /rest/media/post/create → parentPostId"""
    print("\n" + "=" * 60)
    print("STEP 1: Create Media Post")
    print("=" * 60)
    print(f"Prompt: {prompt}")

    parent_id = api.create_media_post(
        cookies=COOKIES,
        prompt=prompt,
        on_status=status_callback,
    )

    if parent_id:
        print(f"\n✅ parentPostId: {parent_id}")
    else:
        print("\n❌ Failed to create media post")
    return parent_id


def test_step2_conversations_new(
    api: GrokAPI, prompt: str, parent_post_id: str,
    aspect_ratio: str = "3:2", video_length: int = 6, resolution: str = "480p",
) -> str | None:
    """Step 2: POST /rest/app-chat/conversations/new → postId (video)"""
    print("\n" + "=" * 60)
    print("STEP 2: Conversations New (video generation)")
    print("=" * 60)
    print(f"parentPostId: {parent_post_id}")
    print(f"Settings: {aspect_ratio}, {video_length}s, {resolution}")

    post_id = api.conversations_new(
        cookies=COOKIES,
        prompt=prompt,
        parent_post_id=parent_post_id,
        aspect_ratio=aspect_ratio,
        video_length=video_length,
        resolution=resolution,
        on_status=status_callback,
    )

    if post_id:
        print(f"\n✅ postId: {post_id}")
        print(f"   Video URL: {VIDEO_DOWNLOAD_URL.format(post_id=post_id)}")
    else:
        print("\n❌ Failed to get postId from stream")
    return post_id


def test_step3_create_share_link(api: GrokAPI, post_id: str) -> bool:
    """Step 3: POST /rest/media/post/create-link → share link"""
    print("\n" + "=" * 60)
    print("STEP 3: Create Share Link")
    print("=" * 60)
    print(f"postId: {post_id}")

    ok = api.create_share_link(
        cookies=COOKIES,
        post_id=post_id,
        on_status=status_callback,
    )

    if ok:
        print(f"\n✅ Share link created")
    else:
        print(f"\n⚠️ Share link failed (video vẫn có thể download được)")
    return ok


def test_full_flow(api: GrokAPI, prompt: str, aspect_ratio: str, video_length: int, resolution: str):
    """Full flow: step 1 → 2 → 3"""
    print("\n" + "#" * 60)
    print("FULL FLOW: Create → Generate → Share")
    print("#" * 60)

    start = time.time()

    # Step 1
    parent_id = test_step1_create_media_post(api, prompt)
    if not parent_id:
        return

    time.sleep(1)

    # Step 2
    post_id = test_step2_conversations_new(
        api, prompt, parent_id, aspect_ratio, video_length, resolution
    )
    if not post_id:
        return

    time.sleep(0.5)

    # Step 3
    test_step3_create_share_link(api, post_id)

    elapsed = time.time() - start
    print(f"\n{'=' * 60}")
    print(f"🎉 Done in {elapsed:.1f}s")
    print(f"   Post ID: {post_id}")
    print(f"   Download: {VIDEO_DOWNLOAD_URL.format(post_id=post_id)}")
    print(f"{'=' * 60}")


def test_download(post_id: str):
    """Test download video bằng curl_cffi"""
    print("\n" + "=" * 60)
    print(f"DOWNLOAD: {post_id}")
    print("=" * 60)

    try:
        from curl_cffi import requests as curl_requests
    except ImportError:
        print("❌ curl_cffi not installed")
        return

    url = VIDEO_DOWNLOAD_URL.format(post_id=post_id)
    print(f"URL: {url}")

    from src.core.grok_api import USER_AGENT
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "*/*",
        "Referer": "https://grok.com/imagine",
    }
    cookie_str = "; ".join(f"{k}={v}" for k, v in COOKIES.items())

    resp = curl_requests.get(
        url,
        headers={**headers, "Cookie": cookie_str},
        impersonate="chrome133a",
        timeout=60,
    )

    if resp.status_code == 200 and len(resp.content) > 10000:
        os.makedirs("output", exist_ok=True)
        filename = f"output/{post_id}.mp4"
        with open(filename, "wb") as f:
            f.write(resp.content)
        size_mb = len(resp.content) / (1024 * 1024)
        print(f"✅ Downloaded: {filename} ({size_mb:.1f} MB)")
    else:
        print(f"❌ Download failed: {resp.status_code}, size={len(resp.content)}")
        if resp.status_code != 200:
            print(f"   Response: {resp.text[:300]}")


def main():
    parser = argparse.ArgumentParser(description="Test Grok Video Generation API")
    parser.add_argument("--prompt", default=DEFAULT_PROMPT, help="Video prompt")
    parser.add_argument("--step", type=int, choices=[1, 2, 3], help="Run specific step only")
    parser.add_argument("--parent-id", help="parentPostId for step 2")
    parser.add_argument("--post-id", help="postId for step 3 or download")
    parser.add_argument("--download", action="store_true", help="Download video by post-id")
    parser.add_argument("--ratio", default="3:2", help="Aspect ratio (default: 3:2)")
    parser.add_argument("--length", type=int, default=6, choices=[6, 10], help="Video length")
    parser.add_argument("--resolution", default="480p", choices=["480p", "720p"])
    args = parser.parse_args()

    # Download mode
    if args.download:
        if not args.post_id:
            print("❌ --post-id required for download")
            return
        test_download(args.post_id)
        return

    api = GrokAPI()

    try:
        if args.step == 1:
            test_step1_create_media_post(api, args.prompt)

        elif args.step == 2:
            if not args.parent_id:
                print("❌ --parent-id required for step 2")
                return
            test_step2_conversations_new(
                api, args.prompt, args.parent_id,
                args.ratio, args.length, args.resolution,
            )

        elif args.step == 3:
            if not args.post_id:
                print("❌ --post-id required for step 3")
                return
            test_step3_create_share_link(api, args.post_id)

        else:
            # Full flow
            test_full_flow(api, args.prompt, args.ratio, args.length, args.resolution)

    finally:
        api.close()


if __name__ == "__main__":
    main()
