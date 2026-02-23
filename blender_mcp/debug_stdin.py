#!/usr/bin/env python3
"""Debug: log what Kiro sends on stdin."""
import os
import select
import json
import time

os.write(2, b"[debug] started\n")

# Try multiple approaches to read stdin
for attempt in range(3):
    os.write(2, f"[debug] attempt {attempt+1}, checking stdin with select...\n".encode())
    r, _, _ = select.select([0], [], [], 10.0)
    if r:
        data = os.read(0, 65536)
        os.write(2, f"[debug] got {len(data)} bytes:\n{data[:500]!r}\n".encode())
        
        # Try to parse and respond
        try:
            # Find JSON in the data
            text = data.decode('utf-8', errors='replace')
            os.write(2, f"[debug] text: {text[:500]}\n".encode())
            
            # Try to respond with initialize
            resp = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2024-11-05", "capabilities": {"tools": {"listChanged": False}}, "serverInfo": {"name": "blender-mcp", "version": "1.0.0"}}}).encode()
            header = f"Content-Length: {len(resp)}\r\n\r\n".encode()
            os.write(1, header + resp)
            os.write(2, b"[debug] sent response\n")
        except Exception as e:
            os.write(2, f"[debug] parse error: {e}\n".encode())
    else:
        os.write(2, b"[debug] no data on stdin after 10s\n")

os.write(2, b"[debug] exiting\n")
