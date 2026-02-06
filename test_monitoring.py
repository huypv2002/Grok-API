"""Test monitoring gói - kiểm tra SubscriptionChecker flow"""
import httpx
import json
import time

API_BASE = "https://grok-auth-api.kh431248.workers.dev"
ADMIN_KEY = "huyem"

def admin_headers():
    return {"Content-Type": "application/json", "X-Admin-Key": ADMIN_KEY}

def test_login(username, password):
    r = httpx.post(f"{API_BASE}/login", json={"username": username, "password": password}, timeout=10)
    return r.json()

def test_check(username):
    r = httpx.post(f"{API_BASE}/check", json={"username": username}, timeout=10)
    return r.json()

def admin_create(username, password, plan="trial", expires_at=""):
    r = httpx.post(f"{API_BASE}/admin/users",
        json={"username": username, "password": password, "plan": plan, "expires_at": expires_at},
        headers=admin_headers(), timeout=10)
    return r.json()

def admin_update(username, **kwargs):
    r = httpx.put(f"{API_BASE}/admin/users",
        json={"username": username, **kwargs},
        headers=admin_headers(), timeout=10)
    return r.json()

def admin_delete(username):
    r = httpx.delete(f"{API_BASE}/admin/users?username={username}",
        headers=admin_headers(), timeout=10)
    return r.json()

def run_tests():
    user = "test_monitor_py"
    pwd = "pass123"
    passed = 0
    failed = 0

    def check(name, condition, detail=""):
        nonlocal passed, failed
        if condition:
            print(f"  ✅ {name}")
            passed += 1
        else:
            print(f"  ❌ {name} — {detail}")
            failed += 1

    # Cleanup
    admin_delete(user)

    # 1. Tạo account còn hạn
    print("\n🔹 Test 1: Tạo account + Login")
    admin_create(user, pwd, "basic", "2026-03-01")
    r = test_login(user, pwd)
    check("Login OK", r.get("ok") == True)
    check("Plan = basic", r.get("plan") == "basic")
    check("Expires = 2026-03-01", r.get("expires_at") == "2026-03-01")

    # 2. Check subscription
    print("\n🔹 Test 2: Check subscription (còn hạn)")
    r = test_check(user)
    check("Check OK", r.get("ok") == True)
    check("Not expired", r.get("expired") == False)

    # 3. Sai password
    print("\n🔹 Test 3: Login sai password")
    r = test_login(user, "wrong")
    check("Login fail", r.get("ok") == False)

    # 4. Hết hạn
    print("\n🔹 Test 4: Set hết hạn → Check")
    admin_update(user, expires_at="2026-02-01")
    r = test_check(user)
    check("Check expired", r.get("ok") == False)
    check("expired=True", r.get("expired") == True)

    # 5. Khóa account
    print("\n🔹 Test 5: Khóa account → Login + Check")
    admin_update(user, is_active=False, expires_at="2026-12-31")
    r = test_login(user, pwd)
    check("Login bị khóa", r.get("ok") == False and "khóa" in r.get("error", ""))
    r = test_check(user)
    check("Check bị khóa", r.get("ok") == False)

    # 6. Mở khóa + gia hạn
    print("\n🔹 Test 6: Mở khóa + gia hạn → Check OK")
    admin_update(user, is_active=True, expires_at="2026-06-01", plan="premium")
    r = test_check(user)
    check("Check OK sau gia hạn", r.get("ok") == True)
    check("Plan = premium", r.get("plan") == "premium")

    # 7. User không tồn tại
    print("\n🔹 Test 7: User không tồn tại")
    r = test_check("nonexistent_user_xyz")
    check("Check 404", r.get("ok") == False)

    # 8. Test SubscriptionChecker logic (simulate)
    print("\n🔹 Test 8: Simulate SubscriptionChecker (app logic)")
    r = test_check(user)
    ok = r.get("ok", False)
    if not ok:
        check("App sẽ đóng", False, "Unexpected: user should be active")
    else:
        check("App tiếp tục chạy", True)

    # Set hết hạn → app sẽ đóng
    admin_update(user, expires_at="2026-01-01")
    r = test_check(user)
    ok = r.get("ok", False)
    check("App sẽ đóng (hết hạn)", ok == False)

    # Cleanup
    admin_delete(user)

    print(f"\n{'='*40}")
    print(f"  Kết quả: {passed} passed, {failed} failed")
    print(f"{'='*40}")
    return failed == 0

if __name__ == "__main__":
    run_tests()
