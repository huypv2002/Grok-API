"""
Test script - kiểm tra kết nối Blender MCP server.
Chạy: python mcpblender.py
"""
import socket
import json

HOST = '127.0.0.1'
PORT = 65432

def send(data):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(10)
            s.connect((HOST, PORT))
            s.sendall(json.dumps(data).encode())
            s.shutdown(socket.SHUT_WR)
            resp = b''
            while True:
                chunk = s.recv(4096)
                if not chunk:
                    break
                resp += chunk
            if resp:
                return json.loads(resp.decode())
    except ConnectionRefusedError:
        print("✗ Không kết nối được Blender. Hãy chạy blender_addon.py trong Blender trước.")
        return None
    except Exception as e:
        print(f"✗ Error: {e}")
        return None

print("Testing Blender MCP connection...")
result = send({"action": "get_scene_info"})
if result and result.get("status") == "ok":
    info = result["result"]
    print(f"✓ Connected! Scene có {info['object_count']} objects:")
    for obj in info["objects"]:
        print(f"  - {obj['name']} ({obj['type']}) at {obj['location']}")
    print(f"  Camera: {info['active_camera']}")
    print(f"  Engine: {info['render_engine']}")
elif result:
    print(f"✗ Error: {result.get('error')}")
else:
    print("✗ No response")
