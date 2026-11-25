"""Blender: render the finished GLB with the spec cameras of the input photos, for the client report.
    blender -b --python bl_client_render.py -- MODEL.glb OUT_DIR [SIZE]
Writes OUT_DIR/main_{000..315}.png (full body, level ring) and head_{000..315}.png (head close-ups).
Spec cameras (docs/Workflow-and-Validation.md, check_turnaround.py section 10d / 10e): orthographic; full-body views
1.95 m wide (scaled by the model height / 1.65 m), aimed at the body centre (half the height); head close-ups 4x
zoom, aimed half a head below the head top (12.8 cm at 1.65 m). Phi: camera toward her left = +. Flat shading with the
texture colours (Standard view transform, white background), so the render compares with the photos directly."""
import math
import os
import sys

import bpy
from mathutils import Vector

args = sys.argv[sys.argv.index('--') + 1:]
glb, out = args[0], args[1]
size = int(args[2]) if len(args) > 2 else 1024
SPEC_HEIGHT, BODY_FRAME, HEAD_ZOOM, HEAD_DROP = 1.65, 1.95, 4.0, 0.128

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=glb)
# the importer adds an Icosphere as the bone display shape: not part of the model
shapes = {pb.custom_shape for o in bpy.context.scene.objects if o.type == 'ARMATURE' for pb in o.pose.bones if pb.custom_shape}
for o in shapes:
    o.hide_render = True
meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH' and o not in shapes]
dg = bpy.context.evaluated_depsgraph_get()          # deformed vertices: a skinned mesh's bound_box is not reliable
zs = [(ev.matrix_world @ v.co).z for o in meshes for ev in [o.evaluated_get(dg)] for v in ev.to_mesh().vertices]
z0, z1 = min(zs), max(zs)
k = (z1 - z0) / SPEC_HEIGHT

sc = bpy.context.scene
sc.render.engine = 'BLENDER_WORKBENCH'
sc.display.shading.light = 'FLAT'
sc.display.shading.color_type = 'TEXTURE'
sc.view_settings.view_transform = 'Standard'
sc.world = bpy.data.worlds.new('white')
sc.world.color = (1, 1, 1)
sc.render.resolution_x = sc.render.resolution_y = size
sc.render.image_settings.file_format = 'PNG'
cam = bpy.data.cameras.new('spec')
cam.type = 'ORTHO'
co = bpy.data.objects.new('spec', cam)
sc.collection.objects.link(co)
sc.camera = co
os.makedirs(out, exist_ok=True)
views = [('main', BODY_FRAME * k, (z0 + z1) / 2), ('head', BODY_FRAME / HEAD_ZOOM * k, z1 - HEAD_DROP * k)]
for kind, width, cz in views:
    cam.ortho_scale = width
    for phi in range(0, 360, 45):
        a = math.radians(phi)
        d = Vector((math.sin(a), -math.cos(a), 0))        # glTF +Z (her front) is Blender -Y; +phi toward her left (+X)
        co.location = Vector((0, 0, cz)) + d * 5
        co.rotation_euler = (math.pi / 2, 0, a)
        cam.clip_end = 20
        sc.render.filepath = os.path.join(out, f'{kind}_{phi:03d}.png')
        bpy.ops.render.render(write_still=True)
print('bl_client_render: model height %.3f m, %d views' % (z1 - z0, 16))
