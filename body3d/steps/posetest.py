"""Re-import the rigged GLB, pose it (arms down, elbow bent, leg forward, head turned) and render."""
import bpy, sys, math
from mathutils import Vector, Euler
GLB, OUT = sys.argv[-2], sys.argv[-1]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=GLB)
arm = [o for o in bpy.context.scene.objects if o.type == 'ARMATURE'][0]
bpy.context.view_layer.objects.active = arm
bpy.ops.object.mode_set(mode='POSE')
pb = arm.pose.bones
print('POSE bones:', len(pb))


def rot(name, axis, deg):
    b = pb[name]; b.rotation_mode = 'XYZ'
    e = list(b.rotation_euler); e['XYZ'.index(axis)] += math.radians(deg); b.rotation_euler = e


# world-space intent via bone-local rotations: test a few joints and read where the hand / foot ends up
def wpos(name, tail=True):
    b = pb[name]; return arm.matrix_world @ (b.tail if tail else b.head)


h0 = wpos('LeftHand'); f0 = wpos('RightFoot'); n0 = wpos('Head')
for ax in 'XYZ':
    pass
# arms down: rotate LeftArm / RightArm about their local Z (roll aligned to world up) until the hand drops
rot('LeftArm', 'Z', -60); rot('RightArm', 'Z', 60)
rot('LeftForeArm', 'X', 45); rot('RightForeArm', 'X', 45)
rot('LeftUpLeg', 'X', 30); rot('LeftLeg', 'X', -40)
rot('Head', 'Y', 25); rot('Spine1', 'X', 10)
bpy.context.view_layer.update()
h1 = wpos('LeftHand'); f1 = wpos('LeftFoot')
print('POSE left hand moved from', [round(v, 3) for v in h0], 'to', [round(v, 3) for v in h1])
bpy.ops.object.mode_set(mode='OBJECT')
s = bpy.context.scene; s.render.engine = 'BLENDER_WORKBENCH'
s.display.shading.light = 'STUDIO'; s.display.shading.color_type = 'TEXTURE'
s.render.resolution_x, s.render.resolution_y = 700, 900
s.world = bpy.data.worlds.new('w'); s.world.color = (1, 1, 1)
cam = bpy.data.objects.new('c', bpy.data.cameras.new('c')); s.collection.objects.link(cam); s.camera = cam
cam.data.type = 'ORTHO'; cam.data.ortho_scale = 2.0
for nm, az in (('front', 0), ('side', 90), ('q', 35)):
    a = math.radians(az); t = Vector((0, 0, 0.85))
    cam.location = t + Vector((math.sin(a), -math.cos(a), 0)) * 6
    cam.rotation_euler = (t - cam.location).to_track_quat('-Z', 'Y').to_euler()
    s.render.filepath = f'{OUT}_{nm}.png'; bpy.ops.render.render(write_still=True)
