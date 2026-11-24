"""Add a 22-bone humanoid skeleton (Mixamo-style names, no prefix) to the textured GLB, skin it with automatic
weights and export a rigged GLB.   blender -b --python rig.py -- in.glb joints.json out.glb"""
import bpy, sys, json
from mathutils import Vector

IN, JS, OUT = sys.argv[-3], sys.argv[-2], sys.argv[-1]
J = json.load(open(JS))
gl2b = lambda p: Vector((p[0], -p[2], p[1]))          # glTF (x, y up, z fwd) -> Blender (x, y back, z up)

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=IN)
meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
assert len(meshes) == 1, [o.name for o in meshes]
body = meshes[0]; body.name = 'Body'
# apply any import transform so the mesh is in world space
bpy.ops.object.select_all(action='DESELECT'); body.select_set(True); bpy.context.view_layer.objects.active = body
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

# bone: (name, head joint, tail joint, parent)
BONES = [
    ('Hips', 'Hips', 'Spine', None),
    ('Spine', 'Spine', 'Spine1', 'Hips'),
    ('Spine1', 'Spine1', 'Spine2', 'Spine'),
    ('Spine2', 'Spine2', 'Neck', 'Spine1'),
    ('Neck', 'Neck', 'Head', 'Spine2'),
    ('Head', 'Head', 'HeadTop_End', 'Neck'),
]
for S in ('Left', 'Right'):
    BONES += [
        (S + 'Shoulder', S + 'Shoulder', S + 'Arm', 'Spine2'),
        (S + 'Arm', S + 'Arm', S + 'ForeArm', S + 'Shoulder'),
        (S + 'ForeArm', S + 'ForeArm', S + 'Hand', S + 'Arm'),
        (S + 'Hand', S + 'Hand', S + 'HandEnd', S + 'ForeArm'),
        (S + 'UpLeg', S + 'UpLeg', S + 'Leg', 'Hips'),
        (S + 'Leg', S + 'Leg', S + 'Foot', S + 'UpLeg'),
        (S + 'Foot', S + 'Foot', S + 'ToeBase', S + 'Leg'),
        (S + 'ToeBase', S + 'ToeBase', S + 'ToeEnd', S + 'Foot'),
    ]

arm_data = bpy.data.armatures.new('Armature')
arm = bpy.data.objects.new('Armature', arm_data)
bpy.context.scene.collection.objects.link(arm)
bpy.ops.object.select_all(action='DESELECT'); arm.select_set(True); bpy.context.view_layer.objects.active = arm
bpy.ops.object.mode_set(mode='EDIT')
eb = arm_data.edit_bones
for name, h, t, parent in BONES:
    b = eb.new(name)
    b.head = gl2b(J[h]); b.tail = gl2b(J[t])
    if parent:
        b.parent = eb[parent]
        # connect when the child starts where the parent ends (spine, limbs)
        if (b.head - eb[parent].tail).length < 1e-4:
            b.use_connect = True
# consistent rolls: limbs roll so the bone's Z axis points up / forward (helps retargeting)
for b in eb:
    if 'Arm' in b.name or 'Hand' in b.name or 'Shoulder' in b.name:
        b.align_roll(Vector((0, 0, 1)))
    else:
        b.align_roll(Vector((0, -1, 0)))
bpy.ops.object.mode_set(mode='OBJECT')

# skin with automatic (bone heat) weights
bpy.ops.object.select_all(action='DESELECT')
body.select_set(True); arm.select_set(True); bpy.context.view_layer.objects.active = arm
bpy.ops.object.parent_set(type='ARMATURE_AUTO')
# every vertex must be weighted; report the unweighted ones
unw = [v.index for v in body.data.vertices if not any(g.weight > 1e-4 for g in v.groups)]
print('RIG bones', len(arm_data.bones), 'vertex groups', len(body.vertex_groups), 'unweighted vertices', len(unw))
if unw:
    # fall back: give unweighted vertices to the nearest bone segment
    import mathutils
    segs = [(b.name, arm.matrix_world @ b.head_local, arm.matrix_world @ b.tail_local) for b in arm_data.bones]
    for i in unw:
        p = body.matrix_world @ body.data.vertices[i].co
        best = min(segs, key=lambda s: (mathutils.geometry.intersect_point_line(p, s[1], s[2])[0] - p).length)
        vg = body.vertex_groups.get(best[0]) or body.vertex_groups.new(name=best[0])
        vg.add([i], 1.0, 'REPLACE')
    print('RIG fixed unweighted vertices', len(unw))
# glTF: a skinned mesh node should be a scene root (validator NODE_SKINNED_MESH_NON_ROOT). Unparent it but keep
# the Armature modifier, so the skin still binds to the skeleton.
bpy.ops.object.select_all(action='DESELECT'); body.select_set(True); bpy.context.view_layer.objects.active = body
bpy.ops.object.parent_clear(type='CLEAR_KEEP_TRANSFORM')
assert any(m.type == 'ARMATURE' and m.object == arm for m in body.modifiers), 'armature modifier lost'
bpy.ops.export_scene.gltf(filepath=OUT, export_format='GLB', export_yup=True, export_skins=True,
                          export_animations=False, export_image_format='AUTO', use_selection=False)
print('RIG exported', OUT)
