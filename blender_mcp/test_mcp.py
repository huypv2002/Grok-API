"""Test MCP server - raw fd I/O."""
import subprocess
import json
import os

def send_recv(proc, method, params=None, msg_id=1):
    body = json.dumps({"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params or {}}).encode()
    header = f"Content-Length: {len(body)}\r\n\r\n".encode()
    proc.stdin.write(header + body)
    proc.stdin.flush()

    # Read response header byte by byte
    buf = b''
    while not buf.endswith(b'\r\n\r\n'):
        b = proc.stdout.read(1)
        if not b:
            return None
        buf += b

    length = 0
    for line in buf.decode().split('\r\n'):
        if line.lower().startswith('content-length:'):
            length = int(line.split(':')[1].strip())

    resp_body = proc.stdout.read(length)
    return json.loads(resp_body)

proc = subprocess.Popen(
    ["/opt/homebrew/bin/python3", "-u", "/Users/phamvanhuy/Grok-API/blender_mcp/mcp_server.py"],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE
)

print("1. initialize...")
r = send_recv(proc, "initialize", msg_id=1)
print(f"   OK: {r.get('result', {}).get('serverInfo', {})}")

print("2. tools/list...")
r = send_recv(proc, "tools/list", msg_id=2)
print(f"   Tools: {len(r.get('result', {}).get('tools', []))}")

proc.terminate()
print("Done!")
