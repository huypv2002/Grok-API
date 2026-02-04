"""Test download video via browser - simple version"""
import time
import ssl
import os
import subprocess

ssl._create_default_https_context = ssl._create_unverified_context
os.environ['WDM_SSL_VERIFY'] = '0'

VIDEO_URL = "https://imagine-public.x.ai/imagine-public/share-videos/6a489f05-0270-44e9-98b1-68df708c7c4f_hd.mp4?cache=1"

def test_download():
    # Open URL in default browser
    print(f"Opening URL in browser: {VIDEO_URL}")
    subprocess.run(["open", VIDEO_URL])
    print("Check your browser!")

if __name__ == "__main__":
    test_download()
