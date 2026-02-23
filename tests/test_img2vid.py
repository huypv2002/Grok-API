"""
Test Image-to-Video flow — debug từng bước.
Chạy: python -m tests.test_img2vid <image_path>

Mục đích: xem stream response trả về gì, tìm đúng postId/videoId,
và test share_link + download.
"""
import sys
import os
import json
import time
import uuid
import base64
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from curl_cffi import requests as curl_requests
from src.core.grok_api import (
    GrokAPI, _make_cookie_string, _get_request_headers,
    UPLOAD_FILE_URL, CONVERSATIONS_URL, CREATE_LINK_URL,
    VIDEO_DOWNLOAD_URL, USER_AGENT, ASSETS_BASE,
)


def load_cookies():
    """Load cookies từ accounts.json"""
    with open("data/accounts.json") as f:
        data = json.load(f)
    acc = data["accounts"][0]
    print(f"Account: {acc['email']}")
    return acc["cookies"]


def step1_upload(cookies, image_path):
    """Upload image → fileMetadataId"""
    print("\n" + "="*60)
    print("STEP 1: Upload image")
    print("="*60)

    api = GrokAPI()
    file_id = api.upload_image(cookies=cookies, image_path=image_path)
    api.close()

    if file_id:
        print(f"✅ file_id = {file_id}")
    else:
        print("❌ Upload failed")
        sys.exit(1)
    return file_id


def step2_check_asset(cookies, file_id):
    """Check asset ready"""
    print("\n" + "="*60)
    print("STEP 2: Check asset ready")
    print("="*60)

    api = GrokAPI()
    ok = api.check_asset_ready(cookies=cookies, file_id=file_id, max_retries=10, delay=2.0)
    api.close()

    if ok:
        print("✅ Asset ready")
    else:
        print("❌ Asset not ready")
        sys.exit(1)


def step3_update_settings(cookies):
    """Update user settings"""
    print("\n" + "="*60)
    print("STEP 3: Update user settings")
    print("="*60)

    api = GrokAPI()
    api.update_user_settings(cookies=cookies, disable_auto_video=True)
    api.close()
    print("✅ Done")


def step4_conversations_new(cookies, file_id, parent_post_id=None):
    """Conversations new — dump ALL stream lines"""
    print("\n" + "="*60)
    print("STEP 4: Conversations new (Image→Video) — RAW STREAM")
    print("="*60)

    user_id = cookies.get("x-userid", "")
    message = f"https://assets.grok.com/users/{user_id}/{file_id}/content  --mode=normal"

    # parentPostId: dùng media post ID nếu có, fallback về file_id
    ppid = parent_post_id or file_id

    payload = {
        "temporary": True,
        "modelName": "grok-3",
        "message": message,
        "fileAttachments": [file_id],
        "toolOverrides": {"videoGen": True},
        "enableSideBySide": True,
        "responseMetadata": {
            "experiments": [],
            "modelConfigOverride": {
                "modelMap": {
                    "videoGenModelConfig": {
                        "parentPostId": ppid,
                        "aspectRatio": "16:9",
                        "videoLength": 6,
                        "resolutionName": "480p",
                    }
                }
            }
        }
    }

    headers = _get_request_headers(
        referer=f"https://grok.com/imagine/post/{ppid}",
        method="POST",
        url=CONVERSATIONS_URL,
    )
    cookie_str = _make_cookie_string(cookies)

    print(f"Message: {message[:100]}...")
    print(f"Payload keys: {list(payload.keys())}")
    print()

    resp = curl_requests.post(
        CONVERSATIONS_URL,
        headers={**headers, "Cookie": cookie_str},
        data=json.dumps(payload),
        impersonate="chrome133a",
        stream=True,
        timeout=180,
    )

    print(f"Response status: {resp.status_code}")
    if resp.status_code != 200:
        print(f"Response body: {resp.text[:500]}")
        sys.exit(1)

    # Collect ALL IDs found in stream
    all_ids = {}  # key_name → value
    line_count = 0

    for line in resp.iter_lines():
        if not line:
            continue
        line_count += 1

        if isinstance(line, bytes):
            line = line.decode("utf-8")
        line_str = line.strip()

        print(f"\n--- Line {line_count} ---")
        print(f"RAW: {line_str[:300]}")

        try:
            data = json.loads(line_str)
            # Extract ALL UUID-like values
            _extract_ids(data, "", all_ids)
        except json.JSONDecodeError:
            print("  (not JSON)")

    print(f"\n{'='*60}")
    print(f"STREAM SUMMARY: {line_count} lines")
    print(f"{'='*60}")
    print(f"All IDs found:")
    for path, val in all_ids.items():
        print(f"  {path} = {val}")

    return all_ids


def _extract_ids(obj, prefix, result):
    """Recursively extract all string values that look like UUIDs."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            path = f"{prefix}.{k}" if prefix else k
            if isinstance(v, str) and len(v) > 8 and "-" in v:
                # Có thể là UUID
                result[path] = v
            elif isinstance(v, (dict, list)):
                _extract_ids(v, path, result)
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            _extract_ids(item, f"{prefix}[{i}]", result)


def step5_test_share_link(cookies, post_id, label=""):
    """Test create share link"""
    print(f"\n--- Test share link: {label} = {post_id} ---")

    headers = _get_request_headers(
        referer=f"https://grok.com/imagine/post/{post_id}",
        method="POST",
        url=CREATE_LINK_URL,
    )
    cookie_str = _make_cookie_string(cookies)

    resp = curl_requests.post(
        CREATE_LINK_URL,
        headers={**headers, "Cookie": cookie_str},
        data=json.dumps({"postId": post_id}),
        impersonate="chrome133a",
        timeout=30,
    )
    print(f"  Status: {resp.status_code}")
    if resp.status_code == 200:
        print(f"  ✅ Share link OK")
        return True
    else:
        print(f"  Body: {resp.text[:200]}")
        return False


def step6_test_download(cookies, post_id, label=""):
    """Test download video"""
    video_url = VIDEO_DOWNLOAD_URL.format(post_id=post_id)
    print(f"\n--- Test download: {label} ---")
    print(f"  URL: {video_url}")

    cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items() if v)
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "*/*",
        "Referer": "https://grok.com/",
        "Origin": "https://grok.com",
    }

    resp = curl_requests.get(
        video_url,
        headers={**headers, "Cookie": cookie_str},
        impersonate="chrome133a",
        timeout=60,
    )
    size = len(resp.content) if resp.content else 0
    ctype = resp.headers.get("content-type", "?")
    print(f"  Status: {resp.status_code}, Size: {size}, Type: {ctype}")

    if resp.status_code == 200 and size > 10000:
        out = f"output/test_img2vid_{post_id[:8]}.mp4"
        Path("output").mkdir(exist_ok=True)
        with open(out, "wb") as f:
            f.write(resp.content)
        print(f"  ✅ Saved: {out} ({size/1024/1024:.1f}MB)")
        return True
    return False


def step6b_test_assets_download(cookies, user_id, video_id, file_id):
    """Test download từ assets.grok.com với nhiều URL patterns."""
    print(f"\n{'='*60}")
    print("STEP 6B: Test download từ assets.grok.com")
    print(f"{'='*60}")
    print(f"  user_id  = {user_id}")
    print(f"  video_id = {video_id}")
    print(f"  file_id  = {file_id}")

    # Tất cả URL patterns có thể — video nằm ở đâu?
    url_patterns = [
        # Pattern 1: videoId trên imagine-public (giống text-to-video)
        f"https://imagine-public.x.ai/imagine-public/share-videos/{video_id}.mp4?cache=1&dl=1",
        # Pattern 2: videoId content
        f"https://assets.grok.com/users/{user_id}/{video_id}/content",
        # Pattern 3: generated video
        f"https://assets.grok.com/users/{user_id}/generated/{video_id}/generated_video.mp4",
        # Pattern 4: video.mp4
        f"https://assets.grok.com/users/{user_id}/{video_id}/video.mp4",
        # Pattern 5: imagine-public trên assets
        f"https://assets.grok.com/imagine-public/share-videos/{video_id}.mp4",
        # Pattern 6: file_id + generated video (video stored under parent post)
        f"https://assets.grok.com/users/{user_id}/{file_id}/generated_video.mp4",
        # Pattern 7: file_id + video.mp4
        f"https://assets.grok.com/users/{user_id}/{file_id}/video.mp4",
        # Pattern 8: grok.com/rest/media/post/{videoId} (API endpoint)
        f"https://grok.com/rest/media/post/{video_id}",
        # Pattern 9: grok.com imagine post page (scrape video URL)
        f"https://grok.com/imagine/post/{video_id}",
    ]

    cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items() if v)
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "*/*",
        "Referer": "https://grok.com/",
        "Origin": "https://grok.com",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
    }

    for i, url in enumerate(url_patterns):
        print(f"\n  Pattern {i+1}: {url}")
        try:
            is_grok = "grok.com" in url
            req_headers = {**headers}
            if is_grok:
                req_headers["Sec-Fetch-Site"] = "same-origin"

            resp = curl_requests.get(
                url,
                headers={**req_headers, "Cookie": cookie_str},
                impersonate="chrome133a",
                timeout=30,
                allow_redirects=True,
            )
            size = len(resp.content) if resp.content else 0
            ctype = resp.headers.get("content-type", "?")
            print(f"    Status: {resp.status_code}, Size: {size}, Type: {ctype}")

            # Check nếu là video (content-type video/* hoặc size > 1MB)
            is_video = "video" in ctype.lower() or (resp.status_code == 200 and size > 500000 and "image" not in ctype.lower())

            if resp.status_code == 200 and is_video and size > 100000:
                out = f"output/test_img2vid_p{i+1}_{video_id[:8]}.mp4"
                Path("output").mkdir(exist_ok=True)
                with open(out, "wb") as f:
                    f.write(resp.content)
                print(f"    ✅ VIDEO FOUND! Saved: {out} ({size/1024/1024:.1f}MB)")
                return url
            elif resp.status_code == 200 and size > 0:
                # Log body nếu nhỏ (có thể là JSON/HTML chứa video URL)
                if size < 5000:
                    print(f"    Body: {resp.text[:500]}")
                elif "json" in ctype.lower():
                    print(f"    JSON: {resp.text[:500]}")
                elif "html" in ctype.lower():
                    # Tìm video URL trong HTML
                    import re
                    video_urls = re.findall(r'https?://[^"\']+\.mp4[^"\']*', resp.text)
                    if video_urls:
                        print(f"    Found video URLs in HTML: {video_urls[:3]}")
                    else:
                        print(f"    HTML page, no video URLs found (size={size})")
                else:
                    print(f"    ⚠️ Not video: type={ctype}, size={size}")
        except Exception as e:
            print(f"    ❌ Error: {e}")
        time.sleep(1)

    print("\n  ❌ Không tìm được URL pattern nào hoạt động")
    return None


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m tests.test_img2vid <image_path>")
        print("Example: python -m tests.test_img2vid /path/to/image.jpg")
        sys.exit(1)

    image_path = sys.argv[1]
    if not Path(image_path).exists():
        print(f"File not found: {image_path}")
        sys.exit(1)

    cookies = load_cookies()

    # Step 1-3: Upload + check + settings
    file_id = step1_upload(cookies, image_path)
    step2_check_asset(cookies, file_id)
    step3_update_settings(cookies)

    time.sleep(1)

    # Step 3b: Tạo media post (giống text-to-video) — lấy parentPostId
    print("\n" + "="*60)
    print("STEP 3B: Create media post (lấy parentPostId cho share link)")
    print("="*60)
    api = GrokAPI()
    parent_post_id = api.create_media_post(
        cookies=cookies,
        prompt="image to video",
    )
    api.close()
    print(f"parentPostId = {parent_post_id}")

    if not parent_post_id:
        print("⚠️ create_media_post failed, tiếp tục với file_id...")
        parent_post_id = None

    time.sleep(1)

    # Step 4: Conversations new — dùng parent_post_id nếu có
    all_ids = step4_conversations_new(cookies, file_id, parent_post_id=parent_post_id)

    video_id = all_ids.get("result.response.streamingVideoGenerationResponse.videoId")
    user_id = cookies.get("x-userid", "")

    # Step 5: Test share link
    print("\n" + "="*60)
    print("STEP 5: Test share link")
    print("="*60)

    ids_to_test = {}
    if video_id:
        ids_to_test["videoId"] = video_id
    if parent_post_id:
        ids_to_test["parentPostId (media post)"] = parent_post_id
    ids_to_test["file_id (upload)"] = file_id

    share_ok_id = None
    for label, test_id in ids_to_test.items():
        ok = step5_test_share_link(cookies, test_id, label=label)
        if ok:
            share_ok_id = test_id
            break
        time.sleep(1)

    # Step 6: Download
    print("\n" + "="*60)
    print("STEP 6: Download video")
    print("="*60)

    if share_ok_id:
        # Share link thành công → download từ imagine-public
        video_url = VIDEO_DOWNLOAD_URL.format(post_id=share_ok_id)
        print(f"Downloading: {video_url}")
        cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items() if v)
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "*/*",
            "Referer": "https://grok.com/",
            "Origin": "https://grok.com",
        }
        for attempt in range(1, 6):
            resp = curl_requests.get(
                video_url,
                headers={**headers, "Cookie": cookie_str},
                impersonate="chrome133a",
                timeout=120,
            )
            size = len(resp.content) if resp.content else 0
            ctype = resp.headers.get("content-type", "?")
            print(f"  Attempt {attempt}: status={resp.status_code}, size={size}, type={ctype}")
            if resp.status_code == 200 and size > 100000:
                out = f"output/test_img2vid_{share_ok_id[:8]}.mp4"
                Path("output").mkdir(exist_ok=True)
                with open(out, "wb") as f:
                    f.write(resp.content)
                print(f"  ✅ Saved: {out} ({size/1024/1024:.1f}MB)")
                break
            print(f"  ⏳ Đợi 10s...")
            time.sleep(10)
    else:
        print("❌ Không có share link thành công")
        # Fallback: thử assets patterns
        if video_id:
            step6b_test_assets_download(cookies, user_id, video_id, file_id)

    print("\n✅ Test hoàn tất!")


if __name__ == "__main__":
    main()
