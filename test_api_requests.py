"""
Test 2 API requests của Grok video generation flow.

Request 1: POST /rest/media/post/create → lấy parentPostId
Request 2: POST /rest/app-chat/conversations/new → gửi prompt + video settings

Cách dùng:
  python test_api_requests.py

Cần sửa cookies bên dưới cho đúng session của bạn.
"""
import json
import uuid
import time

try:
    from curl_cffi import requests as curl_requests
    USE_CURL_CFFI = True
except ImportError:
    import httpx
    USE_CURL_CFFI = False
    print("⚠️ curl_cffi chưa cài, dùng httpx fallback. Chạy: pip install curl_cffi")

# ==================== CONFIG ====================
# Sửa cookies cho đúng session
COOKIES = {
    "sso-rw": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzZXNzaW9uX2lkIjoiNzM1YWQ4NjctMThjYS00NTg0LWI4NTAtNDdkOWNjOWE4NmM2In0.3z_FTWh5z37koGtn84coojOg6luTrHCd--9rDg8eTvE",
    "sso": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzZXNzaW9uX2lkIjoiNzM1YWQ4NjctMThjYS00NTg0LWI4NTAtNDdkOWNjOWE4NmM2In0.3z_FTWh5z37koGtn84coojOg6luTrHCd--9rDg8eTvE",
    "x-userid": "15d72486-0dbc-4275-8503-782243ba35eb",
    "cf_clearance": "TRpxq_Ju5_m.vGaCQzyxgsDtaCtQ4izQXlhTLx.nq0k-1771460096-1.2.1.1-swPg9zYj8uHmBjgrCpyYIedEfd5llTJgoqF1e0m0qNvdHsL6cbTitHTDpFUSDMYEH1N62ftq0ZvXjkG7nG38xYlayKJEy_kUcHwzlt7V39MUnG0J.y2FumSfLUI.JKPQkOhTfTCg9QXuTKZtFyk7_1dM_ydfxKgJAnU5kQDSXZePBT.Sa4.fxTJWsAzFBspiyxWQHxsQqUMnbdBcphDkbTgS6JMS67GhpYznacUW7oIXoHr8oKmTqOwO5ULR9TgD",
}

PROMPT = "the girl cry"
ASPECT_RATIO = "3:2"
VIDEO_LENGTH = 6
RESOLUTION = "480p"

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"

# ==================== HEADERS ====================
# Static x-statsig-id — ref: grok2api_python
X_STATSIG_ID = "ZTpUeXBlRXJyb3I6IENhbm5vdCByZWFkIHByb3BlcnRpZXMgb2YgdW5kZWZpbmVkIChyZWFkaW5nICdjaGlsZE5vZGVzJyk="

BASE_HEADERS = {
    "accept": "*/*",
    "accept-language": "vi-VN,vi;q=0.9,fr-FR;q=0.8,fr;q=0.7,en-US;q=0.6,en;q=0.5",
    "content-type": "text/plain;charset=UTF-8",
    "origin": "https://grok.com",
    "referer": "https://grok.com/imagine/favorites",
    "user-agent": USER_AGENT,
    "sec-ch-ua": '"Not:A-Brand";v="99", "Google Chrome";v="145", "Chromium";v="145"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-origin",
    "baggage": "sentry-public_key=b311e0f2690c81f25e2c4cf6d4f7ce1c",
    "x-statsig-id": X_STATSIG_ID,
}


def make_cookie_header(cookies: dict) -> str:
    return "; ".join(f"{k}={v}" for k, v in cookies.items())


# ==================== REQUEST 1: Create Media Post ====================
def test_create_media_post():
    """
    POST /rest/media/post/create
    Body: {"mediaType": "MEDIA_POST_TYPE_VIDEO", "prompt": "..."}
    Response: {"parentPostId": "uuid-..."}
    """
    print("=" * 60)
    print("REQUEST 1: POST /rest/media/post/create")
    print("=" * 60)

    url = "https://grok.com/rest/media/post/create"
    headers = {
        **BASE_HEADERS,
        "x-xai-request-id": str(uuid.uuid4()),
    }

    body = {
        "mediaType": "MEDIA_POST_TYPE_VIDEO",
        "prompt": PROMPT,
    }

    print(f"URL: {url}")
    print(f"Body: {json.dumps(body, indent=2)}")
    print()

    try:
        cookie_str = make_cookie_header(COOKIES)
        if USE_CURL_CFFI:
            resp = curl_requests.post(
                url,
                headers={**headers, "Cookie": cookie_str},
                data=json.dumps(body),
                impersonate="chrome133a",
                timeout=30,
            )
        else:
            with httpx.Client(http2=True, timeout=30) as client:
                resp = client.post(url, headers=headers, cookies=COOKIES, json=body)
        
        print(f"Status: {resp.status_code}")
        print(f"Response: {resp.text[:500]}")

        if resp.status_code == 200:
            data = resp.json()
            # Response format: {"post": {"id": "uuid-...", ...}}
            post = data.get("post", {})
            parent_post_id = post.get("id") or data.get("parentPostId") or data.get("postId") or data.get("id")
            print(f"\n✅ parentPostId: {parent_post_id}")
            return parent_post_id
        else:
            print(f"\n❌ Failed: {resp.status_code}")
            return None
    except Exception as e:
        print(f"\n❌ Error: {e}")
        return None


# ==================== REQUEST 2: Conversations New ====================
def test_conversations_new(parent_post_id: str):
    """
    POST /rest/app-chat/conversations/new
    Body: conversation payload với video settings
    Response: streaming SSE → chứa postId cuối cùng
    """
    print()
    print("=" * 60)
    print("REQUEST 2: POST /rest/app-chat/conversations/new")
    print("=" * 60)

    url = "https://grok.com/rest/app-chat/conversations/new"
    headers = {
        **BASE_HEADERS,
        "referer": f"https://grok.com/imagine/post/{parent_post_id}",
        "x-xai-request-id": str(uuid.uuid4()),
    }

    body = {
        "temporary": True,
        "modelName": "grok-3",
        "message": f"{PROMPT} --mode=custom",
        "toolOverrides": {"videoGen": True},
        "enableSideBySide": True,
        "responseMetadata": {
            "experiments": [],
            "modelConfigOverride": {
                "modelMap": {
                    "videoGenModelConfig": {
                        "parentPostId": parent_post_id,
                        "aspectRatio": ASPECT_RATIO,
                        "videoLength": VIDEO_LENGTH,
                        "resolutionName": RESOLUTION,
                    }
                }
            }
        }
    }

    print(f"URL: {url}")
    print(f"Body: {json.dumps(body, indent=2)}")
    print()

    try:
        cookie_str = make_cookie_header(COOKIES)
        if USE_CURL_CFFI:
            resp = curl_requests.post(
                url,
                headers={**headers, "Cookie": cookie_str},
                data=json.dumps(body),
                impersonate="chrome133a",
                stream=True,
                timeout=120,
            )
        else:
            # httpx fallback (không có TLS impersonate)
            import httpx
            client = httpx.Client(http2=True, timeout=120)
            resp = client.send(
                client.build_request("POST", url, headers=headers, cookies=COOKIES, json=body),
                stream=True,
            )

        print(f"Status: {resp.status_code}")
        print()

        if resp.status_code != 200:
            print(f"❌ Failed: {resp.text[:500]}")
            return None

        # Read streaming response — parse JSON lines
        post_id = None
        full_text = ""
        for line in resp.iter_lines():
            if not line:
                continue
            if isinstance(line, bytes):
                line = line.decode("utf-8")
            full_text += line + "\n"

            try:
                data = json.loads(line.strip())
                if "result" in data:
                    result = data["result"]
                    if isinstance(result, dict):
                        pid = result.get("postId") or result.get("post_id")
                        if pid:
                            post_id = pid
                            print(f"✅ Found postId: {post_id}")
                
                if "mediaPostId" in str(data):
                    print(f"📦 Media data: {json.dumps(data)[:200]}")
            except json.JSONDecodeError:
                pass

        lines = full_text.strip().split("\n")
        print(f"\nTotal lines: {len(lines)}")
        print("Last 3 lines:")
        for l in lines[-3:]:
            print(f"  {l[:200]}")

        if post_id:
            video_url = f"https://imagine-public.x.ai/imagine-public/share-videos/{post_id}.mp4?cache=1&dl=1"
            print(f"\n🎬 Video URL: {video_url}")
        else:
            print("\n⚠️ postId not found in response")

        return post_id

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return None


# ==================== MAIN ====================
if __name__ == "__main__":
    print("🎬 Grok Video API Test")
    print(f"Prompt: {PROMPT}")
    print(f"Settings: {ASPECT_RATIO}, {VIDEO_LENGTH}s, {RESOLUTION}")
    print()

    # Step 1: Create media post
    parent_post_id = test_create_media_post()

    if not parent_post_id:
        print("\n❌ Không lấy được parentPostId, dừng test.")
        exit(1)

    print()
    input("Press Enter để tiếp tục Request 2...")

    # Step 2: Conversations new
    post_id = test_conversations_new(parent_post_id)

    print()
    print("=" * 60)
    if post_id:
        print(f"✅ Test thành công! postId: {post_id}")
    else:
        print("⚠️ Test xong nhưng chưa lấy được postId")
    print("=" * 60)
