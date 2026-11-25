"""Render a clean synthetic 33-view turnaround set (2048x2048 JPG, white background, orthographic) from a GLB.
Used by the tests as known-good input for check_turnaround.py.
    blender -b --factory-startup --python render_synth.py -- model.glb OUT_DIR [PERSP_DISTANCE_M]
With a distance, a perspective camera that far from the target is used instead (same framing), to produce a
set that violates the "orthographic / long lens" rule."""
import bpy, sys, math, os
from mathutils import Vector

args = sys.argv[sys.argv.index('--') + 1:]
GLB, OUT = args[0], args[1]
PERSP = float(args[2]) if len(args) > 2 else None
os.makedirs(OUT, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=GLB)
s = bpy.context.scene; s.render.engine = 'BLENDER_WORKBENCH'
s.display.shading.light = 'FLAT'; s.display.shading.color_type = 'TEXTURE'
s.world = bpy.data.worlds.new('w'); s.world.color = (1, 1, 1); s.view_settings.view_transform = 'Standard'
s.render.image_settings.file_format = 'JPEG'; s.render.image_settings.quality = 95
s.render.resolution_x = s.render.resolution_y = 2048
cam = bpy.data.objects.new('c', bpy.data.cameras.new('c')); s.collection.objects.link(cam); s.camera = cam
cam.data.type = 'ORTHO'
NAMES = {0: 'front', 45: 'front_left', 90: 'left', 135: 'back_left', 180: 'back', 225: 'back_right',
         270: 'right', 315: 'front_right'}


def shot(name, target, direction, scale):
    d = direction.normalized()
    if PERSP:
        cam.data.type = 'PERSP'; cam.data.sensor_fit = 'HORIZONTAL'
        cam.data.angle = 2 * math.atan(scale / 2 / PERSP)
        cam.location = target + d * PERSP
    else:
        cam.data.ortho_scale = scale
        cam.location = target + d * 6
    if abs(d.z) > 0.99:
        cam.rotation_euler = (0, 0, 0)       # straight down: image up = her back, front toward the image bottom
    else:
        cam.rotation_euler = (target - cam.location).to_track_quat('-Z', 'Y').to_euler()
    s.render.filepath = os.path.join(OUT, name + '.jpg'); bpy.ops.render.render(write_still=True)


def ring(phi, el):
    a, e = math.radians(phi), math.radians(el)        # phi>0: camera toward her left (+X); Blender front = -Y
    return Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e)))


# fixed camera distance (input spec): every full-body view (level, +30°, -20°, top) is framed the same, BODY_FRAME
# wide, aimed at the body centre; the head close-ups are one fixed zoom, HEAD_FRAME wide, aimed at the head centre
BODY_FRAME, HEAD_ZOOM = 1.95, 4.0
HEAD_FRAME = BODY_FRAME / HEAD_ZOOM
# body centre (input spec): on the vertical axis, half the figure height above the feet, measured from the model
# (meshes standing on the floor); the head close-ups aim at the head centre
dg = bpy.context.evaluated_depsgraph_get(); zs = []
for o in s.objects:                 # meshes standing on the floor (the test GLB also holds a unit helper sphere)
    if o.type == 'MESH':
        z = [(o.matrix_world @ v.co).z for v in o.evaluated_get(dg).to_mesh().vertices]
        if z and min(z) > -0.05:
            zs += z
body = Vector((0, 0, (min(zs) + max(zs)) / 2)); head = Vector((0, 0, 1.52))
print('SYNTH body centre', round(body.z, 4), 'height', round(max(zs) - min(zs), 4))
for i, phi in enumerate(range(0, 360, 45)):
    shot(f'{i + 1:02d}_{phi:03d}deg_{NAMES[phi]}', body, ring(phi, 0), BODY_FRAME)
    shot(f'el30_{phi:03d}deg', body, ring(phi, 30), BODY_FRAME)
    shot(f'low20_{phi:03d}deg', body, ring(phi, -20), BODY_FRAME)
    shot(f'head_{phi:03d}deg', head, ring(phi, 0), HEAD_FRAME)
shot('top', body, Vector((0, 0, 1)), BODY_FRAME)
print('SYNTH done', OUT)
