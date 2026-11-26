"""MakeHuman template, step 3 (Blender): make the photo T-pose the rest pose, put the fitted body on the mesh, move
the bones to the joints the moved helpers define (rolls kept), remove the helper geometry, replace the head by the hull's (hull_head.npz, bridged at the neck, skin weights
transferred), drop the 'mixamorig:' prefix, split body / head bake groups and
unwrap them like bl_uv33s.py. Writes uvmesh.npz / uvmesh.blend (the bake33.py inputs) and body_mh.ply.
    blender -b --python mh_build.py -- WORK_DIR"""
import importlib, json, os, sys, bpy
import numpy as np
from mathutils import Vector
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mh_common
D = sys.argv[sys.argv.index('--') + 1]
pkg = mh_common.enable_mpfb()
RigService = importlib.import_module(pkg + '.services.rigservice').RigService
ExportService = importlib.import_module(pkg + '.services.exportservice').ExportService
bpy.ops.wm.open_mainfile(filepath=os.path.join(D, 'mh_prep.blend'))   # saved in the photo T-pose
h = next(o for o in bpy.data.objects if o.type == 'MESH' and o.name.startswith('Human'))
rig = next(o for o in bpy.data.objects if o.type == 'ARMATURE')
bpy.context.view_layer.objects.active = rig
RigService.apply_pose_as_rest_pose(rig)          # the T-pose becomes the rest pose (bone rolls stay MakeHuman's)
# the fitted T-pose body, helpers included (they define the joints), straight onto the mesh
posed = np.load(os.path.join(D, 'mh_fit.npz'))['posed']
assert len(posed) == len(h.data.vertices)
h.data.vertices.foreach_set('co', posed.ravel()); h.data.update()
# joints from the moved helpers, as MPFB defines them (CUBE: centre of a joint cube, MEAN: mean of vertices);
# each bone keeps its roll (z axis) so animation retargeting sees MakeHuman's bone frames
rigdef = json.load(open(os.path.join(os.path.dirname(importlib.import_module(pkg).__file__),
                                     'data', 'rigs', 'standard', 'rig.mixamo.json')))['bones']
gidx = {g.name: g.index for g in h.vertex_groups}
members = {}
for v in h.data.vertices:
    for g in v.groups:
        if g.weight > 0:
            members.setdefault(g.group, []).append(v.index)
co = np.array([v.co[:] for v in h.data.vertices])
M = np.array(h.matrix_world) @ np.linalg.inv(np.array(rig.matrix_world))


def joint(spec):
    ids = members[gidx[spec['cube_name']]] if spec['strategy'] == 'CUBE' else spec['vertex_indices']
    p = co[ids].mean(0)
    return Vector((M @ np.r_[p, 1.0])[:3])


bpy.ops.object.mode_set(mode='EDIT')
for name, spec in rigdef.items():
    eb = rig.data.edit_bones.get(name)
    if eb is None:
        continue
    z = eb.z_axis.copy()
    eb.head, eb.tail = joint(spec['head']), joint(spec['tail'])
    eb.align_roll(z)
bpy.ops.object.mode_set(mode='OBJECT')
ExportService.bake_modifiers_remove_helpers(h, bake_masks=True, remove_helpers=True)
# --- the head from the hull (mh_fit exported it): cut the template at the neck, put the hull's head on, bridge the
# two cut loops and give the new head the template head's skin weights (nearest surface)
import bmesh
HH = np.load(os.path.join(D, 'hull_head.npz'))
zcut = float(HH['cut'])                                     # pipeline y = Blender z
src = h.copy(); src.data = h.data.copy(); bpy.context.collection.objects.link(src)
bm = bmesh.new(); bm.from_mesh(h.data)
bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.co.z > zcut], context='VERTS')
nb = len(bm.verts)
newv = [bm.verts.new(Vector(p)) for p in HH['v']]
bm.verts.ensure_lookup_table()
for f in HH['f']:
    try:
        bm.faces.new([newv[i] for i in f])
    except ValueError:
        pass
bm.normal_update()
loop = [e for e in bm.edges if e.is_boundary and all(abs(v.co.z - zcut) < 0.03 for v in e.verts)]
r = bmesh.ops.bridge_loops(bm, edges=loop)
bm.to_mesh(h.data); bm.free(); h.data.update()
g = h.vertex_groups.new(name='hull_head'); g.add(list(range(nb, nb + len(HH['v']))), 1.0, 'REPLACE')
dt = h.modifiers.new('heads', 'DATA_TRANSFER'); dt.object = src
dt.use_vert_data = True; dt.data_types_verts = {'VGROUP_WEIGHTS'}; dt.vert_mapping = 'POLYINTERP_NEAREST'
dt.layers_vgroup_select_src = 'ALL'; dt.layers_vgroup_select_dst = 'NAME'; dt.vertex_group = 'hull_head'
bpy.context.view_layer.objects.active = h
bpy.ops.object.datalayout_transfer(modifier='heads')
bpy.ops.object.modifier_apply(modifier='heads')
h.vertex_groups.remove(h.vertex_groups['hull_head'])
bpy.data.objects.remove(src)
print('mh_build: head from the hull: %d vertices above %.3f m, %d bridge faces' % (len(HH['v']), zcut, len(r.get('faces', []))))
for b in rig.data.bones:
    b.name = b.name.replace('mixamorig:', '')
h.name, rig.name = 'Body', 'Armature'
bpy.context.view_layer.objects.active = h
for o in bpy.context.selected_objects:
    o.select_set(False)
h.select_set(True)
h.modifiers.new('tri', 'TRIANGULATE'); bpy.ops.object.modifier_apply(modifier='tri')
me = h.data
for p in me.polygons:
    p.use_smooth = True
co = np.array([v.co[:] for v in me.vertices])
yneck = co[:, 2].min() + 1.40 * (co[:, 2].max() - co[:, 2].min()) / 1.65    # head + upper neck: own texture
cen = np.zeros(len(me.polygons) * 3); me.polygons.foreach_get('center', cen); cen = cen.reshape(-1, 3)
grp = (cen[:, 2] > yneck).astype(np.int64)
me.materials.clear()
me.materials.append(bpy.data.materials.new('BodyMat')); me.materials.append(bpy.data.materials.new('HeadMat'))
me.polygons.foreach_set('material_index', grp.astype(np.int32)); me.update()
while me.uv_layers:                          # MakeHuman's own layout overlaps front and back: unwrap like bl_uv33s
    me.uv_layers.remove(me.uv_layers[0])
me.uv_layers.new(name='UVMap')
for g in (0, 1):
    bpy.ops.object.mode_set(mode='EDIT'); bpy.ops.mesh.select_all(action='DESELECT')
    h.active_material_index = g; bpy.ops.object.material_slot_select()
    bpy.ops.uv.smart_project(angle_limit=1.15, island_margin=0.004, area_weight=0.0)
    bpy.ops.object.mode_set(mode='OBJECT')
nv, nf = len(me.vertices), len(me.polygons)
vn = np.zeros(nv * 3); me.vertices.foreach_get('normal', vn); vn = vn.reshape(-1, 3)
lv = np.zeros(nf * 3, np.int64); me.loops.foreach_get('vertex_index', lv)
uv = np.zeros(nf * 3 * 2); me.uv_layers.active.data.foreach_get('uv', uv)
gl = lambda a: np.c_[a[:, 0], a[:, 2], -a[:, 1]]
np.savez(os.path.join(D, 'uvmesh.npz'), pos=gl(co), nrm=gl(vn), tri=lv.reshape(-1, 3), uv=uv.reshape(-1, 3, 2), grp=grp)
with open(os.path.join(D, 'body_mh.ply'), 'w') as f:      # ASCII PLY, pipeline frame (for fit_report.py)
    f.write(f'ply\nformat ascii 1.0\nelement vertex {nv}\nproperty float x\nproperty float y\nproperty float z\n'
            f'element face {nf}\nproperty list uchar int vertex_indices\nend_header\n')
    np.savetxt(f, gl(co), fmt='%.6f'); np.savetxt(f, np.c_[np.full(nf, 3), lv.reshape(-1, 3)], fmt='%d')
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(D, 'uvmesh.blend'))
print('mh_build: %d vertices, %d triangles, %d bones, height %.3f m' % (nv, nf, len(rig.data.bones), co[:, 2].max() - co[:, 2].min()))
