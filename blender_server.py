import bpy
import socket
import threading
import json
import os

HOST = '127.0.0.1'
PORT = 65432

def handle_client(conn):
    try:
        data = b''
        while True:
            chunk = conn.recv(4096)
            if not chunk:
                break
            data += chunk
            # Thử parse JSON, nếu được thì xử lý
            try:
                msg = json.loads(data.decode())
                result = process_command(msg)
                response = json.dumps({"status": "ok", "result": result})
                conn.sendall(response.encode())
                data = b''
            except json.JSONDecodeError:
                continue
    except Exception as e:
        try:
            conn.sendall(json.dumps({"status": "error", "error": str(e)}).encode())
        except:
            pass
    finally:
        conn.close()

def process_command(msg):
    action = msg.get("action", "")

    if action == "move":
        obj = bpy.data.objects.get(msg["object"])
        if obj:
            obj.location = msg["location"]
            bpy.context.view_layer.update()
            return f"Moved {msg['object']}"
        return f"Object {msg['object']} not found"

    elif action == "create":
        obj_type = msg.get("type", "cube")
        loc = msg.get("location", [0, 0, 0])
        params = msg.get("params", {})

        if obj_type == "cube":
            bpy.ops.mesh.primitive_cube_add(size=params.get("size", 2), location=loc)
        elif obj_type == "sphere":
            bpy.ops.mesh.primitive_uv_sphere_add(
                radius=params.get("radius", 1),
                segments=params.get("segments", 32),
                ring_count=params.get("rings", 16),
                location=loc
            )
        elif obj_type == "plane":
            bpy.ops.mesh.primitive_plane_add(size=params.get("size", 2), location=loc)
        elif obj_type == "torus":
            bpy.ops.mesh.primitive_torus_add(
                major_radius=params.get("major_radius", 1),
                minor_radius=params.get("minor_radius", 0.25),
                location=loc
            )
        elif obj_type == "light":
            light_type = params.get("light_type", "AREA")
            bpy.ops.object.light_add(type=light_type, location=loc)
            light = bpy.context.active_object
            light.data.energy = params.get("energy", 100)
            if hasattr(light.data, "size"):
                light.data.size = params.get("size", 2)
            if "color" in params:
                light.data.color = params["color"]
        elif obj_type == "camera":
            bpy.ops.object.camera_add(location=loc)

        obj = bpy.context.active_object
        if "name" in msg:
            obj.name = msg["name"]
        if "rotation" in msg:
            obj.rotation_euler = msg["rotation"]

        return f"Created {obj_type}: {obj.name}"

    elif action == "material":
        obj = bpy.data.objects.get(msg["object"])
        if not obj:
            return f"Object {msg['object']} not found"
        mat = bpy.data.materials.new(name=msg.get("name", "Material"))
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes['Principled BSDF']
        props = msg.get("props", {})
        if "color" in props:
            bsdf.inputs['Base Color'].default_value = props["color"]
        if "metallic" in props:
            bsdf.inputs['Metallic'].default_value = props["metallic"]
        if "roughness" in props:
            bsdf.inputs['Roughness'].default_value = props["roughness"]
        obj.data.materials.append(mat)
        return f"Material applied to {obj.name}"

    elif action == "smooth":
        obj = bpy.data.objects.get(msg["object"])
        if obj:
            bpy.context.view_layer.objects.active = obj
            obj.select_set(True)
            bpy.ops.object.shade_smooth()
            return f"Smooth shading on {obj.name}"
        return "Object not found"

    elif action == "delete_all":
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete(use_global=False)
        return "All objects deleted"

    elif action == "set_camera":
        cam = bpy.data.objects.get(msg.get("object", "RenderCam"))
        if cam and cam.type == 'CAMERA':
            bpy.context.scene.camera = cam
            return f"Active camera: {cam.name}"
        return "Camera not found"

    elif action == "world":
        world = bpy.data.worlds.new(name="World")
        world.use_nodes = True
        bg = world.node_tree.nodes['Background']
        bg.inputs['Color'].default_value = msg.get("color", [0.02, 0.02, 0.05, 1])
        bg.inputs['Strength'].default_value = msg.get("strength", 0.5)
        bpy.context.scene.world = world
        return "World set"

    elif action == "render":
        scene = bpy.context.scene
        engine = msg.get("engine", "BLENDER_EEVEE_NEXT")
        scene.render.engine = engine
        scene.render.resolution_x = msg.get("width", 1920)
        scene.render.resolution_y = msg.get("height", 1080)
        scene.render.resolution_percentage = 100
        output = msg.get("output", "/tmp/blender_render.png")
        os.makedirs(os.path.dirname(output), exist_ok=True)
        scene.render.filepath = output
        scene.render.image_settings.file_format = msg.get("format", "PNG")
        bpy.ops.render.render(write_still=True)
        return f"Rendered to {output}"

    return f"Unknown action: {action}"

def server():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((HOST, PORT))
        s.listen()
        print(f"Blender MCP Server started on {HOST}:{PORT}")
        while True:
            conn, addr = s.accept()
            threading.Thread(target=handle_client, args=(conn,), daemon=True).start()

threading.Thread(target=server, daemon=True).start()
