"""Add a 22-bone humanoid skeleton (Mixamo-style names, no prefix) to the textured GLB, skin it with automatic
weights and export a rigged GLB.   blender -b --python rig.py -- in.glb joints.json out.glb"""
import bpy, sys, json
from collections import defaultdict
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


def smoothstep(start, end, value):
    ratio = max(0.0, min(1.0, (value - start) / (end - start)))
    return ratio * ratio * (3 - 2 * ratio)


def blend_shoulder_weights():
    # The heat solution on the split UV mesh can change abruptly around the
    # deltoid. Give the shoulder cap one continuous torso-to-upper-arm blend.
    for side in ('Left', 'Right'):
        joint = gl2b(J[side + 'Arm'])
        direction = 1 if joint.x > 0 else -1
        upper_arm = body.vertex_groups.get(side + 'Arm') or body.vertex_groups.new(name=side + 'Arm')
        shoulder = body.vertex_groups.get(side + 'Shoulder') or body.vertex_groups.new(name=side + 'Shoulder')
        for vertex in body.data.vertices:
            lateral = (vertex.co.x - joint.x) * direction
            vertical = vertex.co.z - joint.z
            if not (-0.095 < lateral < 0.150 and -0.18 < vertical < 0.12):
                continue
            influence = (smoothstep(-0.095, -0.045, lateral) *
                         (1 - smoothstep(0.106, 0.150, lateral)) *
                         smoothstep(-0.18, -0.10, vertical) *
                         (1 - smoothstep(0.065, 0.12, vertical)))
            if influence <= 1e-6:
                continue
            arm_weight = smoothstep(-0.03, 0.073, lateral)
            indices = [vertex.index]
            old = {group.group: group.weight for group in vertex.groups if group.weight > 0}
            total = sum(old.values())
            weights = {index: (1 - influence) * weight / total for index, weight in old.items()}
            weights[upper_arm.index] = weights.get(upper_arm.index, 0.0) + influence * arm_weight
            weights[shoulder.index] = weights.get(shoulder.index, 0.0) + influence * (1 - arm_weight)
            for index in old:
                body.vertex_groups[index].remove(indices)
            ranked = sorted(weights, key=lambda index: (-weights[index], index))[:4]
            kept = sum(weights[index] for index in ranked)
            for index in ranked:
                if weights[index] > 0:
                    body.vertex_groups[index].add(indices, weights[index] / kept, 'REPLACE')


def synchronize_seam_weights():
    # glTF splits positions at UV seams. Skinning must move those copies together.
    coincident = defaultdict(list)
    for vertex in body.data.vertices:
        coincident[tuple(round(value, 5) for value in vertex.co)].append(vertex.index)

    seams = 0
    for indices in coincident.values():
        if len(indices) < 2:
            continue
        weights = defaultdict(float)
        for index in indices:
            for group in body.data.vertices[index].groups:
                weights[group.group] += group.weight
        ranked = sorted(weights, key=lambda group: (-weights[group], group))[:4]
        total = sum(weights[group] for group in ranked)
        if total <= 0:
            continue
        for group in weights:
            body.vertex_groups[group].remove(indices)
        for group in ranked:
            if weights[group] > 0:
                body.vertex_groups[group].add(indices, weights[group] / total, 'REPLACE')
        seams += 1
    print('RIG synchronized weights for', seams, 'coincident vertex groups')


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
blend_shoulder_weights()
synchronize_seam_weights()
# glTF: a skinned mesh node should be a scene root (validator NODE_SKINNED_MESH_NON_ROOT). Unparent it but keep
# the Armature modifier, so the skin still binds to the skeleton.
bpy.ops.object.select_all(action='DESELECT'); body.select_set(True); bpy.context.view_layer.objects.active = body
bpy.ops.object.parent_clear(type='CLEAR_KEEP_TRANSFORM')
assert any(m.type == 'ARMATURE' and m.object == arm for m in body.modifiers), 'armature modifier lost'
bpy.ops.export_scene.gltf(filepath=OUT, export_format='GLB', export_yup=True, export_skins=True,
                          export_animations=False, export_image_format='AUTO', use_selection=False)
print('RIG exported', OUT)
