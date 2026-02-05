#!/usr/bin/env python3
"""Test CloudflareSolver from cf_solver.py"""
import sys
sys.path.insert(0, '.')

from src.core.cf_solver import solve_cloudflare, CF_SOLVER_AVAILABLE

# Test cookies
TEST_COOKIES = {
    "sso": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzZXNzaW9uX2lkIjoiMDIzZTI2Y2UtNmYyYS00YTQ5LThmODktZjRhMmZiYTJiZDAzIn0.jlybbcaGcObXtLwX92yc4TeslxFQFErjVL3cXebY-UM",
    "sso-rw": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJzZXNzaW9uX2lkIjoiMDIzZTI2Y2UtNmYyYS00YTQ5LThmODktZjRhMmZiYTJiZDAzIn0.jlybbcaGcObXtLwX92yc4TeslxFQFErjVL3cXebY-UM",
    "x-userid": "9fb55a0f-3a22-4a37-9b97-44f30e1083e6",
}


def status_callback(msg: str):
    print(f"[STATUS] {msg}")


def main():
    print("=" * 60)
    print("Test CloudflareSolver")
    print("=" * 60)
    
    if not CF_SOLVER_AVAILABLE:
        print("❌ zendriver not installed!")
        print("Run: python -m pip install zendriver latest-user-agents user-agents")
        return
    
    print("\n→ Testing solve_cloudflare with cookies...")
    print("  (Running in headed mode to see what happens)")
    
    result = solve_cloudflare(
        url="https://grok.com/imagine",
        timeout=60,
        headless=False,  # Headed mode to see the challenge
        on_status=status_callback,
        existing_cookies=TEST_COOKIES,
    )
    
    print("\n" + "=" * 60)
    if result:
        print("✅ SUCCESS!")
        print(f"   cf_clearance: {result['cf_clearance'][:40]}...")
        print(f"   user_agent: {result['user_agent'][:60]}...")
        print(f"   cookies: {list(result['cookies'].keys())}")
    else:
        print("❌ FAILED to get cf_clearance")
    print("=" * 60)


if __name__ == "__main__":
    main()
