"""
Blender Addon - Socket Server
Chạy trong Blender Scripting tab. Nhận commands từ MCP server và execute bpy code.
"""
import bpy
import socket
import threading
import json
import traceback
import os
import math

HOST = '127.0.0.1'
PORT = 65432

# Queue để chạy code trên main thread (bpy yêu cầu)
_command_queue = []
_result_store = {}
_lock = threading.Lock()


def execute_on_main_thread(cmd_id, func, *args, **kwargs):
    """Queue function để chạy trên Blender main thread."""
    event = threading.Event()
    with _lock:
        _command_queue.append((cmd_id, func, args, kwargs, event))
    event.wait(timeout=300)  # max 5 phút cho render
    with _lock:
        return _result_store.pop(cmd_id, {"status": "error", "error": "timeout"})


def process_queue():
    """Timer callback - chạy trên main thread."""
    with _lock:
        queue = list(_command_queue)
        _command_queue.clear()

    for cmd_id, func, args, kwargs, event in queue:
        try:
            result = func(*args, **kwargs)
            with _lock:
                _result_store[cmd_id] = {"status": "ok", "result": result}
        except Exception as e:
            with _lock:
                _result_store[cmd_id] = {"status": "error", "error": str(e), "traceback": traceback.format_exc()}
        finally:
            event.set()

    return 0.05  # 50ms interval


# ============ Command Handlers ============

def cmd_execute_code(code):
    """Chạy arbitrary Python code trong Blender."""
    local_vars = {}
    exec(code, {"bpy": bpy, "math": math, "os": os, "json": json}, local_vars)
    return local_vars.get("result", "Code executed")


def cmd_get_scene_info():
    """Lấy thông tin scene hiện tại."""
    objects = []
    for obj in bpy.context.scene.objects:
        info = {
            "name": obj.name,
            "type": obj.type,
            "location": list(obj.location),
            "rotation": list(obj.rotation_euler),
            "scale": list(obj.scale),
            "visible": obj.visible_get()
        }
        if obj.type == 'MESH':
            info["vertices"] = len(obj.data.vertices)
            info["faces"] = len(obj.data.polygons)
        objects.append(info)

    return {
        "object_count": len(objects),
        "objects": objects,
        "active_camera": bpy.context.scene.camera.name if bpy.context.scene.camera else None,
        "render_engine": bpy.context.scene.render.engine,
        "frame_current": bpy.context.scene.frame_current,
        "frame_start": bpy.context.scene.frame_start,
        "frame_end": bpy.context.scene.frame_end,
        "fps": bpy.context.scene.render.fps
    }


def cmd_create_object(obj_type, name=None, location=None, rotation=None, scale=None, params=None):
    """Tạo object mới."""
    loc = tuple(location or [0, 0, 0])
    rot = tuple(rotation or [0, 0, 0])
    p = params or {}

    if obj_type == "cube":
        bpy.ops.mesh.primitive_cube_add(size=p.get("size", 2), location=loc)
    elif obj_type == "sphere":
        bpy.ops.mesh.primitive_uv_sphere_add(
            radius=p.get("radius", 1), segments=p.get("segments", 32),
            ring_count=p.get("rings", 16), location=loc)
    elif obj_type == "plane":
        bpy.ops.mesh.primitive_plane_add(size=p.get("size", 2), location=loc)
    elif obj_type == "cylinder":
        bpy.ops.mesh.primitive_cylinder_add(
            radius=p.get("radius", 1), depth=p.get("depth", 2),
            vertices=p.get("vertices", 32), location=loc)
    elif obj_type == "cone":
        bpy.ops.mesh.primitive_cone_add(
            radius1=p.get("radius1", 1), radius2=p.get("radius2", 0),
            depth=p.get("depth", 2), location=loc)
    elif obj_type == "torus":
        bpy.ops.mesh.primitive_torus_add(
            major_radius=p.get("major_radius", 1),
            minor_radius=p.get("minor_radius", 0.25), location=loc)
    elif obj_type == "monkey":
        bpy.ops.mesh.primitive_monkey_add(size=p.get("size", 2), location=loc)
    elif obj_type == "empty":
        bpy.ops.object.empty_add(type=p.get("display_type", "PLAIN_AXES"), location=loc)
    elif obj_type == "text":
        bpy.ops.object.text_add(location=loc)
        if "body" in p:
            bpy.context.active_object.data.body = p["body"]
    elif obj_type == "light":
        light_type = p.get("light_type", "POINT")
        bpy.ops.object.light_add(type=light_type, location=loc)
        light = bpy.context.active_object
        light.data.energy = p.get("energy", 100)
        if hasattr(light.data, "size"):
            light.data.size = p.get("size", 1)
        if "color" in p:
            light.data.color = tuple(p["color"][:3])
        if light_type == "SPOT" and "spot_size" in p:
            light.data.spot_size = p["spot_size"]
    elif obj_type == "camera":
        bpy.ops.object.camera_add(location=loc)
        cam = bpy.context.active_object
        if "lens" in p:
            cam.data.lens = p["lens"]
        if "set_active" in p and p["set_active"]:
            bpy.context.scene.camera = cam
    else:
        return f"Unknown type: {obj_type}"

    obj = bpy.context.active_object
    if name:
        obj.name = name
    obj.rotation_euler = rot
    if scale:
        obj.scale = tuple(scale)

    return f"Created {obj_type}: {obj.name} at {list(obj.location)}"


def cmd_modify_object(name, location=None, rotation=None, scale=None, visible=None):
    """Di chuyển/xoay/scale object."""
    obj = bpy.data.objects.get(name)
    if not obj:
        return f"Object '{name}' not found"
    if location is not None:
        obj.location = tuple(location)
    if rotation is not None:
        obj.rotation_euler = tuple(rotation)
    if scale is not None:
        obj.scale = tuple(scale)
    if visible is not None:
        obj.hide_viewport = not visible
        obj.hide_render = not visible
    return f"Modified {name}"


def cmd_set_material(obj_name, color=None, metallic=None, roughness=None,
                     emission_color=None, emission_strength=None, mat_name=None):
    """Set material cho object."""
    obj = bpy.data.objects.get(obj_name)
    if not obj:
        return f"Object '{obj_name}' not found"

    mat = bpy.data.materials.new(name=mat_name or f"{obj_name}_Mat")
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes['Principled BSDF']

    if color:
        bsdf.inputs['Base Color'].default_value = tuple(color)
    if metallic is not None:
        bsdf.inputs['Metallic'].default_value = metallic
    if roughness is not None:
        bsdf.inputs['Roughness'].default_value = roughness
    if emission_color:
        bsdf.inputs['Emission Color'].default_value = tuple(emission_color)
    if emission_strength is not None:
        bsdf.inputs['Emission Strength'].default_value = emission_strength

    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)

    return f"Material applied to {obj_name}"


def cmd_delete_objects(names=None, all_objects=False):
    """Xóa objects."""
    if all_objects:
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete(use_global=False)
        return "All objects deleted"

    if names:
        deleted = []
        for name in names:
            obj = bpy.data.objects.get(name)
            if obj:
                bpy.data.objects.remove(obj, do_unlink=True)
                deleted.append(name)
        return f"Deleted: {deleted}"

    return "Nothing to delete"


def cmd_set_keyframe(obj_name, frame, location=None, rotation=None, scale=None):
    """Set keyframe cho animation."""
    obj = bpy.data.objects.get(obj_name)
    if not obj:
        return f"Object '{obj_name}' not found"

    bpy.context.scene.frame_set(frame)
    if location is not None:
        obj.location = tuple(location)
        obj.keyframe_insert(data_path="location", frame=frame)
    if rotation is not None:
        obj.rotation_euler = tuple(rotation)
        obj.keyframe_insert(data_path="rotation_euler", frame=frame)
    if scale is not None:
        obj.scale = tuple(scale)
        obj.keyframe_insert(data_path="scale", frame=frame)

    return f"Keyframe set for {obj_name} at frame {frame}"


def cmd_set_animation_range(start, end, fps=None):
    """Set animation frame range."""
    bpy.context.scene.frame_start = start
    bpy.context.scene.frame_end = end
    if fps:
        bpy.context.scene.render.fps = fps
    return f"Animation range: {start}-{end}" + (f" @ {fps}fps" if fps else "")


def cmd_render_image(output_path, engine=None, width=None, height=None, samples=None):
    """Render image."""
    scene = bpy.context.scene
    if engine:
        scene.render.engine = engine
    if width:
        scene.render.resolution_x = width
    if height:
        scene.render.resolution_y = height
    if samples and scene.render.engine == 'CYCLES':
        scene.cycles.samples = samples

    scene.render.resolution_percentage = 100
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    scene.render.filepath = output_path
    scene.render.image_settings.file_format = 'PNG'
    bpy.ops.render.render(write_still=True)
    return f"Image rendered: {output_path}"


def cmd_render_animation(output_path, engine=None, width=None, height=None,
                         file_format=None, start=None, end=None):
    """Render animation to video."""
    scene = bpy.context.scene
    if engine:
        scene.render.engine = engine
    if width:
        scene.render.resolution_x = width
    if height:
        scene.render.resolution_y = height
    if start is not None:
        scene.frame_start = start
    if end is not None:
        scene.frame_end = end

    scene.render.resolution_percentage = 100
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
    scene.render.filepath = output_path

    fmt = (file_format or "FFMPEG").upper()
    if fmt == "FFMPEG":
        scene.render.image_settings.file_format = 'FFMPEG'
        scene.render.ffmpeg.format = 'MPEG4'
        scene.render.ffmpeg.codec = 'H264'
        scene.render.ffmpeg.constant_rate_factor = 'MEDIUM'
    else:
        scene.render.image_settings.file_format = fmt

    bpy.ops.render.render(animation=True)
    return f"Animation rendered: {output_path}"


def cmd_set_world(color=None, strength=None, use_hdri=None, hdri_path=None):
    """Setup world/environment."""
    world = bpy.context.scene.world
    if not world:
        world = bpy.data.worlds.new("World")
        bpy.context.scene.world = world
    world.use_nodes = True

    if use_hdri and hdri_path:
        tree = world.node_tree
        tree.nodes.clear()
        bg = tree.nodes.new('ShaderNodeBackground')
        env = tree.nodes.new('ShaderNodeTexEnvironment')
        output = tree.nodes.new('ShaderNodeOutputWorld')
        env.image = bpy.data.images.load(hdri_path)
        tree.links.new(env.outputs['Color'], bg.inputs['Color'])
        tree.links.new(bg.outputs['Background'], output.inputs['Surface'])
        if strength is not None:
            bg.inputs['Strength'].default_value = strength
        return f"HDRI loaded: {hdri_path}"
    else:
        bg = world.node_tree.nodes.get('Background')
        if bg:
            if color:
                bg.inputs['Color'].default_value = tuple(color)
            if strength is not None:
                bg.inputs['Strength'].default_value = strength
        return "World updated"


def cmd_smooth_shade(obj_name):
    """Apply smooth shading."""
    obj = bpy.data.objects.get(obj_name)
    if not obj:
        return f"Object '{obj_name}' not found"
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.shade_smooth()
    obj.select_set(False)
    return f"Smooth shading on {obj_name}"


def cmd_add_modifier(obj_name, mod_type, params=None):
    """Thêm modifier cho object."""
    obj = bpy.data.objects.get(obj_name)
    if not obj:
        return f"Object '{obj_name}' not found"
    p = params or {}
    mod = obj.modifiers.new(name=p.get("name", mod_type), type=mod_type)
    # Set common modifier properties
    for key, val in p.items():
        if key != "name" and hasattr(mod, key):
            setattr(mod, key, val)
    return f"Modifier {mod_type} added to {obj_name}"


# ============ Command Router ============

COMMANDS = {
    "execute_code": lambda msg: cmd_execute_code(msg["code"]),
    "get_scene_info": lambda msg: cmd_get_scene_info(),
    "create_object": lambda msg: cmd_create_object(**{k: v for k, v in msg.items() if k != "action"}),
    "modify_object": lambda msg: cmd_modify_object(**{k: v for k, v in msg.items() if k != "action"}),
    "set_material": lambda msg: cmd_set_material(**{k: v for k, v in msg.items() if k != "action"}),
    "delete_objects": lambda msg: cmd_delete_objects(**{k: v for k, v in msg.items() if k != "action"}),
    "set_keyframe": lambda msg: cmd_set_keyframe(**{k: v for k, v in msg.items() if k != "action"}),
    "set_animation_range": lambda msg: cmd_set_animation_range(**{k: v for k, v in msg.items() if k != "action"}),
    "render_image": lambda msg: cmd_render_image(**{k: v for k, v in msg.items() if k != "action"}),
    "render_animation": lambda msg: cmd_render_animation(**{k: v for k, v in msg.items() if k != "action"}),
    "set_world": lambda msg: cmd_set_world(**{k: v for k, v in msg.items() if k != "action"}),
    "smooth_shade": lambda msg: cmd_smooth_shade(msg["obj_name"]),
    "add_modifier": lambda msg: cmd_add_modifier(**{k: v for k, v in msg.items() if k != "action"}),
}


def handle_command(msg):
    action = msg.get("action", "")
    handler = COMMANDS.get(action)
    if not handler:
        return {"status": "error", "error": f"Unknown action: {action}"}
    return handler(msg)


# ============ Socket Server ============

_cmd_counter = 0

def handle_client(conn):
    global _cmd_counter
    try:
        data = b''
        while True:
            chunk = conn.recv(8192)
            if not chunk:
                break
            data += chunk
        if not data:
            return

        msg = json.loads(data.decode())
        _cmd_counter += 1
        cmd_id = _cmd_counter

        result = execute_on_main_thread(cmd_id, handle_command, msg)
        conn.sendall(json.dumps(result).encode())
    except Exception as e:
        try:
            conn.sendall(json.dumps({"status": "error", "error": str(e)}).encode())
        except:
            pass
    finally:
        conn.close()


_server_running = False

def start_server():
    global _server_running
    if _server_running:
        print("Server already running")
        return

    def server_loop():
        global _server_running
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((HOST, PORT))
            s.listen(5)
            _server_running = True
            print(f"✓ Blender MCP Server started on {HOST}:{PORT}")
            while _server_running:
                try:
                    s.settimeout(1.0)
                    conn, addr = s.accept()
                    threading.Thread(target=handle_client, args=(conn,), daemon=True).start()
                except socket.timeout:
                    continue
                except Exception as e:
                    if _server_running:
                        print(f"Server error: {e}")

    threading.Thread(target=server_loop, daemon=True).start()
    bpy.app.timers.register(process_queue, persistent=True)
    print("✓ Command queue processor registered")


# Auto-start
start_server()
