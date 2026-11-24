"""Add a 22-bone humanoid skeleton (Mixamo-style names, no prefix) to the textured GLB, skin it with automatic
weights and export a rigged GLB.   blender -b --python rig.py -- in.glb joints.json out.glb"""
import bpy, sys, json
from mathutils import Vector
from mathutils.kdtree import KDTree

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

# skin with automatic (bone heat) weights. Bone heat sometimes fails at human scale (metres) for numerical
# reasons ("failed to find solution"); try 10x / 100x scaled copies and keep the solution with the fewest holes.
def unweighted(ob):
    return [v.index for v in ob.data.vertices if not any(g.weight > 1e-4 for g in v.groups)]


def heat_weights(scale):
    if scale == 1:
        bpy.ops.object.select_all(action='DESELECT')
        body.select_set(True); arm.select_set(True); bpy.context.view_layer.objects.active = arm
        bpy.ops.object.parent_set(type='ARMATURE_AUTO')
        return
    b2 = body.copy(); b2.data = body.data.copy(); b2.vertex_groups.clear(); b2.parent = None
    for md in list(b2.modifiers):
        b2.modifiers.remove(md)
    a2 = arm.copy(); a2.data = arm.data.copy()
    for o in (b2, a2):
        bpy.context.scene.collection.objects.link(o); o.scale = (scale,) * 3
    bpy.ops.object.select_all(action='DESELECT')
    for o in (b2, a2):
        o.select_set(True)
    bpy.context.view_layer.objects.active = a2
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    bpy.ops.object.select_all(action='DESELECT')
    b2.select_set(True); a2.select_set(True); bpy.context.view_layer.objects.active = a2
    bpy.ops.object.parent_set(type='ARMATURE_AUTO')
    remaining = len(unweighted(b2))
    if remaining < len(unweighted(body)):
        for vg in list(body.vertex_groups):
            body.vertex_groups.remove(vg)
        groups = {g.index: body.vertex_groups.new(name=g.name) for g in b2.vertex_groups}
        for v in b2.data.vertices:
            for g in v.groups:
                if g.weight > 1e-6:
                    groups[g.group].add([v.index], g.weight, 'REPLACE')
    bpy.data.objects.remove(b2, do_unlink=True)
    bpy.data.objects.remove(a2, do_unlink=True)
    return remaining


def segment_distance_squared(p, start, end):
    axis = end - start
    fraction = (p - start).dot(axis) / axis.length_squared if axis.length_squared else 0.0
    return (p - (start + axis * max(0.0, min(1.0, fraction)))).length_squared


def repair_unweighted(indices):
    missing = set(indices)
    weighted = [v for v in body.data.vertices if v.index not in missing]
    neighbors = KDTree(len(weighted)) if weighted else None
    if neighbors is not None:
        for v in weighted:
            neighbors.insert(body.matrix_world @ v.co, v.index)
        neighbors.balance()
    segments = [(b.name, arm.matrix_world @ b.head_local, arm.matrix_world @ b.tail_local)
                for b in arm_data.bones]
    copied = 0
    for i in indices:
        p = body.matrix_world @ body.data.vertices[i].co
        if neighbors is not None:
            _, nearest, distance = neighbors.find(p)
            if distance <= 0.03:
                for assignment in body.data.vertices[nearest].groups:
                    body.vertex_groups[assignment.group].add([i], assignment.weight, 'REPLACE')
                copied += 1
                continue
        name, _, _ = min(segments, key=lambda s: segment_distance_squared(p, s[1], s[2]))
        group = body.vertex_groups.get(name) or body.vertex_groups.new(name=name)
        group.add([i], 1.0, 'REPLACE')
    print('RIG repaired', copied, 'from nearby weights and', len(indices) - copied, 'from bone segments')


for scale in (1, 10, 100):
    remaining = heat_weights(scale)
    unw = unweighted(body)
    print('RIG bone heat at scale', scale, 'candidate unweighted', len(unw) if remaining is None else remaining,
          'kept unweighted', len(unw))
    if not unw:
        break
if not any(modifier.type == 'ARMATURE' and modifier.object == arm for modifier in body.modifiers):
    bpy.ops.object.select_all(action='DESELECT')
    body.select_set(True); arm.select_set(True); bpy.context.view_layer.objects.active = arm
    bpy.ops.object.parent_set(type='ARMATURE_NAME')
print('RIG bones', len(arm_data.bones), 'vertex groups', len(body.vertex_groups), 'unweighted vertices', len(unw))
if unw:
    repair_unweighted(unw)
# glTF: a skinned mesh node should be a scene root (validator NODE_SKINNED_MESH_NON_ROOT). Unparent it but keep
# the Armature modifier, so the skin still binds to the skeleton.
bpy.ops.object.select_all(action='DESELECT'); body.select_set(True); bpy.context.view_layer.objects.active = body
bpy.ops.object.parent_clear(type='CLEAR_KEEP_TRANSFORM')
assert any(m.type == 'ARMATURE' and m.object == arm for m in body.modifiers), 'armature modifier lost'
bpy.ops.export_scene.gltf(filepath=OUT, export_format='GLB', export_yup=True, export_skins=True,
                          export_animations=False, export_image_format='AUTO', use_selection=False)
print('RIG exported', OUT)
