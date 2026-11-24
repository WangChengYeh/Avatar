"""Import the reconstructed mesh, decimate, UV-unwrap, save .blend + arrays for baking."""
import bpy, sys
import numpy as np

D = sys.argv[-1]
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.wm.ply_import(filepath=D + '/body33s.ply', forward_axis='NEGATIVE_Z', up_axis='Y')
ob = bpy.context.selected_objects[0]
ob.name = 'Body'
bpy.context.view_layer.objects.active = ob
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
mod = ob.modifiers.new('tri', 'TRIANGULATE')
bpy.ops.object.modifier_apply(modifier='tri')
me = ob.data
for p in me.polygons:
    p.use_smooth = True

import json
yneck = 1.40                                         # head + upper neck get their own texture (metres)
cen = np.zeros(len(me.polygons) * 3); me.polygons.foreach_get('center', cen); cen = cen.reshape(-1, 3)
grp = (cen[:, 2] > yneck).astype(np.int64)            # Blender Z is up here
me.materials.append(bpy.data.materials.new('BodyMat'))
me.materials.append(bpy.data.materials.new('HeadMat'))
me.polygons.foreach_set('material_index', grp.astype(np.int32))
me.update()
for g in (0, 1):
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='DESELECT')
    ob.active_material_index = g
    bpy.ops.object.material_slot_select()
    bpy.ops.uv.smart_project(angle_limit=1.15, island_margin=0.004, area_weight=0.0)
    if g == 0:
        uvs = None
    bpy.ops.object.mode_set(mode='OBJECT')
nv, nf = len(me.vertices), len(me.polygons)
co = np.zeros(nv * 3); me.vertices.foreach_get('co', co); co = co.reshape(-1, 3)
vn = np.zeros(nv * 3); me.vertices.foreach_get('normal', vn); vn = vn.reshape(-1, 3)
lv = np.zeros(nf * 3, np.int64); me.loops.foreach_get('vertex_index', lv)
uv = np.zeros(nf * 3 * 2); me.uv_layers.active.data.foreach_get('uv', uv)
ls = np.zeros(nf, np.int64); me.polygons.foreach_get('loop_start', ls)
lt = np.zeros(nf, np.int64); me.polygons.foreach_get('loop_total', lt)
assert (lt == 3).all() and (ls == np.arange(nf) * 3).all()
# convert Blender Z-up to glTF/photo frame (X right, Y up, Z toward front camera)
gl = lambda a: np.c_[a[:, 0], a[:, 2], -a[:, 1]]
np.savez(D + '/uvmesh.npz', pos=gl(co), nrm=gl(vn), tri=lv.reshape(-1, 3), uv=uv.reshape(-1, 3, 2), grp=grp)
bpy.ops.wm.save_as_mainfile(filepath=D + '/uvmesh.blend')
print('UVDONE', nv, nf)
