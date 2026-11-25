"""MakeHuman template, step 1 (Blender): a female MakeHuman body with the Mixamo rig (52 bones, fingers included),
posed into the photo T-pose. Writes mh_prep.npz (rest / posed vertices of the whole base mesh, helpers included,
per-vertex skin matrices, body mask, faces, regions) and mh_prep.blend.
    blender -b --python mh_prep.py -- WORK_DIR        (reads mh_targets.json written by mh33.py)"""
import json, os, sys, bpy
import numpy as np
from mathutils import Vector
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mh_common
args = sys.argv[sys.argv.index('--') + 1:]
D = args[0]
T = json.load(open(os.path.join(D, 'mh_targets.json')))       # pipeline frame (x her left, y up, z front)
pkg = mh_common.enable_mpfb()
import importlib
HumanService = importlib.import_module(pkg + '.services.humanservice').HumanService
TargetService = importlib.import_module(pkg + '.services.targetservice').TargetService
for o in list(bpy.data.objects):
    bpy.data.objects.remove(o)
macro = TargetService.get_default_macro_info_dict()
macro.update(gender=0.0, age=0.5, muscle=0.5, weight=0.45, proportions=0.6, height=0.5, cupsize=0.5, firmness=0.5)
h = HumanService.create_human(scale=0.1, feet_on_ground=True, macro_detail_dict=macro)
TargetService.bake_targets(h)
rig = HumanService.add_builtin_rig(h, 'mixamo')
bpy.context.view_layer.update()
rest = np.array([v.co[:] for v in h.data.vertices])
# hull points -> Blender frame at the template's scale (the fit rescales the template to the hull height later)
k = (rest[:, 2].max() - rest[:, 2].min()) / T['height']
bl = lambda p: [p[0] * k, -p[2] * k, p[1] * k]
targets = {side: {key: bl(T[side][key]) for key in ('wrist', 'knee', 'ankle')} for side in ('Left', 'Right')}
mh_common.pose_photo(rig, targets)
for m in h.modifiers:
    if m.type == 'MASK':
        m.show_viewport = False
ev = h.evaluated_get(bpy.context.evaluated_depsgraph_get()).to_mesh()
posed = np.array([v.co[:] for v in ev.vertices])
assert len(posed) == len(rest)
# per-vertex skin matrix (rest -> posed): linear blend of the bone matrices, for undoing the pose after fitting
Mb = {b.name: np.array(rig.pose.bones[b.name].matrix @ b.matrix_local.inverted()) for b in rig.data.bones}
gname = {g.index: g.name for g in h.vertex_groups}
n = len(rest)
Mv = np.zeros((n, 4, 4)); wsum = np.zeros(n); region = np.zeros(n, np.int8); body = np.zeros(n, bool)
domw = np.zeros(n); dom = [''] * n
for v in h.data.vertices:
    for g in v.groups:
        name = gname[g.group]
        if name == 'body' and g.weight > 0:
            body[v.index] = True
        if name in Mb and g.weight > 0:
            Mv[v.index] += g.weight * Mb[name]; wsum[v.index] += g.weight
            if g.weight > domw[v.index]:
                domw[v.index], dom[v.index] = g.weight, name
nz = wsum > 0
Mv[nz] /= wsum[nz][:, None, None]; Mv[~nz] = np.eye(4)
for i, name in enumerate(dom):          # 1 hands (fingers kept from the template), 2 feet
    name = name.replace('mixamorig:', '')
    region[i] = 1 if 'Hand' in name else 2 if ('Foot' in name or 'Toe' in name) else 0
faces = [list(p.vertices) for p in h.data.polygons if all(body[i] for i in p.vertices)]
np.savez(os.path.join(D, 'mh_prep.npz'), rest=rest, posed=posed, Mv=Mv, body=body, region=region,
         faces=np.array([f + [f[-1]] * (4 - len(f)) for f in faces]), nfv=np.array([len(f) for f in faces]),
         targets=json.dumps(targets),
         # after mh_fit the body is at the hull's scale: mh_build re-poses the refitted rig with these
         targets_hull=json.dumps({side: {key: [T[side][key][0], -T[side][key][2], T[side][key][1]]
                                         for key in ('wrist', 'knee', 'ankle')} for side in ('Left', 'Right')}))
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(D, 'mh_prep.blend'))
print('mh_prep: %d vertices (%d body), template / hull scale %.3f' % (n, body.sum(), k))
