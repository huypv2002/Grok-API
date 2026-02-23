#!/usr/bin/env python3
"""Blender MCP Server - Kiro <-> Blender bridge via stdio (newline-delimited JSON)."""
import sys
import json
import socket
import os

HOST = '127.0.0.1'
PORT = 65432
TIMEOUT = 300


def log(msg):
    os.write(2, f"[blender-mcp] {msg}\n".encode())


def write_msg(obj):
    """Write JSON message followed by newline."""
    line = json.dumps(obj) + "\n"
    os.write(1, line.encode('utf-8'))


def read_msg():
    """Read one line of JSON from stdin."""
    buf = b''
    while True:
        b = os.read(0, 1)
        if not b:
            return None
        if b == b'\n':
            break
        buf += b
    if not buf.strip():
        return None
    return json.loads(buf)


def send_to_blender(data):
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(TIMEOUT)
            s.connect((HOST, PORT))
            s.sendall(json.dumps(data).encode())
            s.shutdown(socket.SHUT_WR)
            resp = b''
            while True:
                chunk = s.recv(8192)
                if not chunk:
                    break
                resp += chunk
            return json.loads(resp) if resp else {"status": "error", "error": "No response"}
    except ConnectionRefusedError:
        return {"status": "error", "error": "Blender not connected. Run blender_addon.py first."}
    except Exception as e:
        return {"status": "error", "error": str(e)}


TOOLS = [
    {"name": "blender_execute_code", "description": "Run Python/bpy code in Blender. Set 'result' var to return.", "inputSchema": {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]}},
    {"name": "blender_get_scene_info", "description": "Get scene objects, camera, render settings.", "inputSchema": {"type": "object", "properties": {}}},
    {"name": "blender_create_object", "description": "Create: cube/sphere/plane/cylinder/cone/torus/monkey/text/light/camera.", "inputSchema": {"type": "object", "properties": {"obj_type": {"type": "string"}, "name": {"type": "string"}, "location": {"type": "array", "items": {"type": "number"}}, "rotation": {"type": "array", "items": {"type": "number"}}, "scale": {"type": "array", "items": {"type": "number"}}, "params": {"type": "object"}}, "required": ["obj_type"]}},
    {"name": "blender_modify_object", "description": "Move/rotate/scale/hide object.", "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}, "location": {"type": "array", "items": {"type": "number"}}, "rotation": {"type": "array", "items": {"type": "number"}}, "scale": {"type": "array", "items": {"type": "number"}}, "visible": {"type": "boolean"}}, "required": ["name"]}},
    {"name": "blender_set_material", "description": "Set material on object.", "inputSchema": {"type": "object", "properties": {"obj_name": {"type": "string"}, "color": {"type": "array", "items": {"type": "number"}}, "metallic": {"type": "number"}, "roughness": {"type": "number"}, "emission_color": {"type": "array", "items": {"type": "number"}}, "emission_strength": {"type": "number"}, "mat_name": {"type": "string"}}, "required": ["obj_name"]}},
    {"name": "blender_delete_objects", "description": "Delete by name or all.", "inputSchema": {"type": "object", "properties": {"names": {"type": "array", "items": {"type": "string"}}, "all_objects": {"type": "boolean"}}}},
    {"name": "blender_set_keyframe", "description": "Set keyframe.", "inputSchema": {"type": "object", "properties": {"obj_name": {"type": "string"}, "frame": {"type": "integer"}, "location": {"type": "array", "items": {"type": "number"}}, "rotation": {"type": "array", "items": {"type": "number"}}, "scale": {"type": "array", "items": {"type": "number"}}}, "required": ["obj_name", "frame"]}},
    {"name": "blender_set_animation_range", "description": "Set frame range/FPS.", "inputSchema": {"type": "object", "properties": {"start": {"type": "integer"}, "end": {"type": "integer"}, "fps": {"type": "integer"}}, "required": ["start", "end"]}},
    {"name": "blender_render_image", "description": "Render to PNG.", "inputSchema": {"type": "object", "properties": {"output_path": {"type": "string"}, "engine": {"type": "string"}, "width": {"type": "integer"}, "height": {"type": "integer"}, "samples": {"type": "integer"}}, "required": ["output_path"]}},
    {"name": "blender_render_animation", "description": "Render animation to MP4.", "inputSchema": {"type": "object", "properties": {"output_path": {"type": "string"}, "engine": {"type": "string"}, "width": {"type": "integer"}, "height": {"type": "integer"}, "file_format": {"type": "string"}, "start": {"type": "integer"}, "end": {"type": "integer"}}, "required": ["output_path"]}},
    {"name": "blender_set_world", "description": "Set world background.", "inputSchema": {"type": "object", "properties": {"color": {"type": "array", "items": {"type": "number"}}, "strength": {"type": "number"}, "use_hdri": {"type": "boolean"}, "hdri_path": {"type": "string"}}}},
    {"name": "blender_smooth_shade", "description": "Smooth shading.", "inputSchema": {"type": "object", "properties": {"obj_name": {"type": "string"}}, "required": ["obj_name"]}},
    {"name": "blender_add_modifier", "description": "Add modifier.", "inputSchema": {"type": "object", "properties": {"obj_name": {"type": "string"}, "mod_type": {"type": "string"}, "params": {"type": "object"}}, "required": ["obj_name", "mod_type"]}}
]

TOOL_MAP = {t["name"]: t["name"].replace("blender_", "") for t in TOOLS}


def main():
    log("ready (ndjson mode)")
    while True:
        try:
            msg = read_msg()
        except Exception as e:
            log(f"err: {e}")
            break
        if msg is None:
            log("eof")
            break

        method = msg.get("method", "")
        mid = msg.get("id")
        params = msg.get("params", {})
        log(f"<- {method}")

        if method == "initialize":
            # Echo back whatever protocol version client sent
            client_version = params.get("protocolVersion", "2024-11-05")
            write_msg({"jsonrpc": "2.0", "id": mid, "result": {
                "protocolVersion": client_version,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "blender-mcp", "version": "1.0.0"}
            }})
            log(f"-> init ok (proto={client_version})")

        elif method == "notifications/initialized":
            log("client ready")

        elif method == "tools/list":
            write_msg({"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS}})
            log(f"-> {len(TOOLS)} tools")

        elif method == "tools/call":
            tool = params.get("name", "")
            args = params.get("arguments", {})
            action = TOOL_MAP.get(tool)
            if not action:
                res = {"status": "error", "error": f"Unknown: {tool}"}
            else:
                cmd = {"action": action}
                cmd.update(args)
                res = send_to_blender(cmd)
            write_msg({"jsonrpc": "2.0", "id": mid, "result": {
                "content": [{"type": "text", "text": json.dumps(res, ensure_ascii=False)}],
                "isError": res.get("status") == "error"
            }})
            log(f"-> {tool}")

        elif mid is not None:
            write_msg({"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"Unknown: {method}"}})


if __name__ == "__main__":
    main()
