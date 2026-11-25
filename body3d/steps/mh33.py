"""MakeHuman template (run_all.py --template makehuman): replaces the hull mesh after the camera / head steps with a
fitted MakeHuman body (clean quad topology, Mixamo rig with fingers, MakeHuman skin weights; CC0 assets).
    python mh33.py WORK_DIR BLENDER
Measures the photo T-pose on body33s.ply (wrist, knee and ankle centres), then runs
mh_prep.py (Blender) -> mh_fit.py -> mh_build.py (Blender). Needs the MPFB extension installed in Blender."""
import json, os, subprocess, sys
import numpy as np, trimesh
D, BLENDER = sys.argv[1], sys.argv[2]
HERE = os.path.dirname(os.path.abspath(__file__))
H = trimesh.load(os.path.join(D, 'body33s.ply')).vertices      # pipeline frame, feet at y = 0
height = float(H[:, 1].max() - H[:, 1].min())


def centre(sel):
    return [float(v) for v in (H[sel].min(0) + H[sel].max(0)) / 2]


T = {'height': height}
for side, sx in (('Left', 1), ('Right', -1)):
    x = sx * H[:, 0]
    wrist = (x > 0.56 * height / 1.65) & (x < 0.62 * height / 1.65)          # arm cross-section near the wrist
    knee = (x > 0) & (x < 0.25) & (np.abs(H[:, 1] - 0.29 * height) < 0.015)
    ankle = (x > 0) & (x < 0.25) & (np.abs(H[:, 1] - 0.06 * height) < 0.010)
    T[side] = {'wrist': centre(wrist), 'knee': centre(knee), 'ankle': centre(ankle)}
json.dump(T, open(os.path.join(D, 'mh_targets.json'), 'w'), indent=1)
print('mh33: hull height %.3f m; wrist L %s R %s' % (height, np.round(T['Left']['wrist'], 3), np.round(T['Right']['wrist'], 3)),
      flush=True)
bl = [BLENDER, '-b', '--python-exit-code', '1', '--python']
subprocess.run(bl + [os.path.join(HERE, 'mh_prep.py'), '--', D], check=True)
subprocess.run([sys.executable, os.path.join(HERE, 'mh_fit.py'), D], check=True)
subprocess.run(bl + [os.path.join(HERE, 'mh_build.py'), '--', D], check=True)
