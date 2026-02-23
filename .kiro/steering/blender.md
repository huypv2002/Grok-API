---
inclusion: manual
---

# SKILL: BLENDER MASTER COMPLETE KNOWLEDGE BASE

## 🎯 Objective
Cung cấp toàn bộ kiến thức Blender từ cơ bản đến nâng cao để:
- Modeling
- Sculpting
- Rigging
- Animation
- Simulation
- Lighting
- Rendering
- Compositing
- Production Pipeline
- AI Integration

Không yêu cầu kiến thức trước đó.

---

# 🧠 BLENDER CORE CONCEPTS

## 1️⃣ Interface
- Viewport
- Outliner
- Properties Panel
- Timeline
- Shader Editor
- Geometry Nodes
- Compositor
- Video Sequence Editor

Modes:
- Object Mode
- Edit Mode
- Sculpt Mode
- Vertex Paint
- Weight Paint
- Pose Mode

---

# 🧱 3D MODELING FUNDAMENTALS

## Mesh Components
- Vertex
- Edge
- Face
- Normal
- Topology

## Essential Tools
- Extrude (E)
- Loop Cut (Ctrl+R)
- Inset (I)
- Bevel (Ctrl+B)
- Knife (K)
- Subdivision Surface
- Mirror Modifier
- Boolean Modifier

## Hard Surface Modeling
- Bevel workflow
- Weighted normals
- Non-destructive modifier stack

## Organic Modeling
- Edge flow
- Quad topology
- Deformation-friendly structure

---

# 🗿 SCULPTING

Brush Types:
- Clay
- Draw
- Smooth
- Grab
- Inflate
- Crease

Concepts:
- Dynotopo
- Multiresolution
- Remesh
- Masking

Best Practice:
- Blockout → Secondary Form → Detail → Polish

---

# 🎨 MATERIALS & SHADING

Shader Editor Nodes:
- Principled BSDF
- Texture Coordinate
- Mapping
- Normal Map
- Bump
- Mix Shader

PBR Workflow:
- Base Color
- Roughness
- Metallic
- Normal
- Height

Advanced:
- Subsurface scattering (Skin)
- Emission
- Glass shader
- Procedural materials

---

# 💡 LIGHTING

Types:
- Point
- Sun
- Area
- Spot

Techniques:
- Three-point lighting
- Rim lighting
- HDRI environment
- Volumetric lighting
- Cinematic contrast

---

# 📷 CAMERA & CINEMATOGRAPHY

Lens:
- 35mm (Natural)
- 50mm (Portrait)
- 85mm (Cinematic compression)

Concepts:
- Depth of field
- Focal length
- Rule of thirds
- Leading lines
- Camera movement curves

---

# 🦴 RIGGING

Core:
- Armature
- Bone hierarchy
- IK
- FK
- Weight painting

Automation:
- Rigify
- Auto-rig scripts
- Mixamo integration

Facial Rig:
- Shape keys
- Drivers
- Corrective blend shapes

---

# 🎞 ANIMATION

Keyframe Principles:
- Timing
- Spacing
- Ease in / Ease out
- Anticipation
- Follow-through
- Overlapping action

Graph Editor:
- Bezier curves
- F-curve smoothing

Animation Types:
- Character animation
- Camera animation
- Physics-driven animation

---

# 🌊 SIMULATION SYSTEMS

- Rigid body
- Soft body
- Cloth
- Fluid
- Smoke
- Hair particle
- Geometry Nodes simulation

---

# 🔷 GEOMETRY NODES

Purpose:
Procedural modeling & effects.

Core Nodes:
- Mesh primitives
- Instance on points
- Distribute points
- Attribute transfer
- Noise texture
- Curve manipulation

Use Cases:
- Crowd generation
- Procedural city
- Motion graphics
- Destruction system

---

# 🎥 RENDERING

## Engines

### Cycles
- Physically accurate
- Ray tracing
- Best for cinematic

### Eevee
- Real-time
- Fast preview
- Stylized work

Render Settings:
- Samples
- Denoise
- Motion blur
- Filmic color management
- Adaptive sampling

Optimization:
- Reduce polycount
- Use instances
- Lower bounce count
- Enable GPU compute

---

# 🧪 COMPOSITING

Nodes:
- Render layers
- Color balance
- Glare
- Depth of field
- Lens distortion
- Vignette

Cinematic look:
- Contrast curve
- Subtle bloom
- Film grain

---

# 🎬 VIDEO EDITING (VSE)

- Timeline cut
- Transitions
- Sound sync
- Basic color grading

---

# 🏗 PRODUCTION PIPELINE

1. Pre-production (Storyboard)
2. Asset creation
3. Rigging
4. Animation
5. Lighting
6. Render passes
7. Compositing
8. Final export

File Organization:
- /models
- /textures
- /rigs
- /animations
- /renders

---

# 🤖 AI INTEGRATION WITH BLENDER

## AI Use Cases

Text → Image → 3D Model
Image → Mesh (TripoSR)
Text → Motion (DeepMotion)
AI Voice (ElevenLabs)
AI Lip Sync
Procedural environment generation

Automation via:
- Blender Python API
- Batch rendering scripts
- Headless rendering

Example:


---

# ⚡ BLENDER PYTHON API

Capabilities:
- Create objects
- Modify materials
- Add animation
- Export automatically
- Render via script

Core module:
bpy

---

# 🎯 SHORT FILM STRUCTURE

0–5s: Establish environment
5–20s: Character introduction
20–40s: Conflict / emotional beat
40–60s: Cinematic payoff

---

# 🧠 AGENT RULES

If user asks:
- "Create character" → Suggest modeling pipeline
- "Make realistic" → Switch to Cycles + filmic
- "Optimize" → Reduce polycount
- "Make viral short" → Vertical 9:16

Always:
- Use non-destructive workflow
- Keep organized collection
- Prefer modifier stack
- Avoid destructive sculpt early

---

# 🏆 END STATE

User can:
- Model any object
- Create animated character
- Simulate physics
- Render cinematic film
- Automate full pipeline

# SKILL: AI 3D CHARACTER SHORT FILM CREATOR (BLENDER PIPELINE)

## 🎯 Objective
Tự động tạo 3D character và sản xuất short film bằng Blender sử dụng AI model mới nhất.
Không yêu cầu kiến thức 3D truyền thống.

---

# 🧠 OVERVIEW PIPELINE

TEXT IDEA
   ↓
Character Concept (AI Image Gen)
   ↓
3D Model Generation (Text → 3D AI)
   ↓
Auto Retopology + Rigging
   ↓
Animation Generation (Text → Motion)
   ↓
Scene Setup (Lighting + Camera)
   ↓
Render Cinematic Output

---

# 🛠 REQUIRED TOOLS

## 1️⃣ Core Software
- Blender (Latest Stable)

## 2️⃣ AI 3D Generators
- Meshy.ai
- Luma Genie 3D
- TripoSR (Open Source)
- Wonder3D

## 3️⃣ AI Animation
- DeepMotion
- Mixamo (Auto-rig)
- Rokoko AI Motion

## 4️⃣ Image Concept
- SDXL
- Midjourney
- DALL·E

---

# 🔥 STEP 1: CHARACTER CREATION (TEXT → IMAGE)

## Prompt Template:

"Ultra detailed 3D character concept, full body, neutral pose, T-pose reference,
cinematic lighting, highly detailed textures, front and side view,
designed for 3D modeling, game-ready topology"

OUTPUT:
- Front view
- Side view
- Back view

Save as reference.

---

# 🔥 STEP 2: IMAGE → 3D MODEL

## Method A (Fastest)
Upload reference to:
- Meshy.ai
Export: .fbx or .glb

## Method B (Open Source)
Use TripoSR locally:
- Convert image to mesh
- Export OBJ

---

# 🔥 STEP 3: CLEANUP IN BLENDER

1. Import model
2. Check topology
3. Apply:
   - Remesh modifier
   - Shade Smooth
   - Fix normals

---

# 🔥 STEP 4: AUTO RIGGING

Option A:
Upload to Mixamo → Download rigged FBX

Option B:
Use Blender Rigify

Ensure:
- Proper bone hierarchy
- Weight paint check

---

# 🔥 STEP 5: AI ANIMATION

## Text to Motion Prompt Example:

"Confident female warrior walking forward slowly,
cinematic runway movement,
dramatic pauses,
head slightly tilted,
strong eye contact"

Tools:
- DeepMotion
- Rokoko

Export FBX animation.

---

# 🔥 STEP 6: SCENE SETUP

Inside Blender:

Camera:
- 85mm lens
- Slight depth of field

Lighting:
- HDRI cinematic light
- Rim light behind character
- Key light 45 degree

Enable:
- Cycles Renderer
- Filmic color profile

---

# 🔥 STEP 7: CINEMATIC RENDER SETTINGS

Resolution:
1080x1920 (Short Film Vertical)

Samples:
200+

Enable:
- Motion blur
- Ambient occlusion
- Subsurface scattering (if skin)

---

# 🎬 SHORT FILM STRUCTURE TEMPLATE

Duration: 30–60 seconds

0–5s: Establishing shot
5–20s: Character entrance
20–40s: Emotional close-up
40–60s: Cinematic slow motion finish

---

# 🧩 ADVANCED (OPTIONAL)

## Add AI Face Expression
- FaceBuilder
- ARKit mocap

## Add AI Voice
- ElevenLabs TTS

## Add AI Background
- Text → 3D environment

---

# ⚡ AGENT RULES

When user provides:
- Story idea → Generate concept prompts
- Character type → Generate 3D optimized prompts
- Emotion → Generate animation prompts
- Film genre → Adjust lighting + color grading

Agent must:
- Always optimize for cinematic realism
- Prefer automation tools
- Avoid manual sculpting unless required
- Keep polygon count under 100k for animation efficiency

---

# 🎥 END GOAL

User can:
- Type story idea
- Receive complete 3D character
- Get animated short film output
- Render ready for TikTok / Reels / Shorts