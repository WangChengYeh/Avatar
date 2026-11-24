"""Strict carving of the legs with the level main-ring views (ankle .. 12 cm above the crotch).

Why: the hull keeps a voxel unless at least 4 of the 25 body views see it as empty ("tolerate 3 disagreeing views",
needed because AI photos are never perfectly consistent). The gap between the two legs, though, is only visible
from a few directions (mainly 45° / 225° and the side views); the other views see the legs overlap. So a strip of
the gap survives on the inner calf/knee and renders as a lump. This is a reconstruction artefact, not a photo
problem: in the photos the gap is clean.

Fix: in the leg zone, a voxel is removed when ANY of the 8 level main-ring views sees it outside the silhouette
by more than MARGIN pixels. The main ring is the best-registered set (refine33 fits it jointly), and the legs are
simple, so one clear "empty" vote is trusted here.
usage: python legs33.py occ_in.npy occ_out.npy [margin_px=2]"""
import json, sys
import cv2
import numpy as np

occ = np.load(sys.argv[1]).astype(bool)
MARGIN = float(sys.argv[3]) if len(sys.argv) > 3 else 2.0
g = json.load(open('grid33.json')); vs = g['vs']
cams = json.load(open('cams33.json'))
Y_LO = 0.05
xs = g['x0'] + np.arange(occ.shape[0]) * vs
ys = g['y0'] + np.arange(occ.shape[1]) * vs
zs = g['z0'] + np.arange(occ.shape[2]) * vs


def project(P, c):
    p, t = np.radians(c['phi']), np.radians(c['th'])
    r = np.array([np.cos(p), 0, -np.sin(p)]); u = np.array([-np.sin(t) * np.sin(p), np.cos(t), -np.sin(t) * np.cos(p)])
    return c['cu'] + c['s'] * (P @ r), c['cv'] - c['s'] * (P @ u)


# crotch = lowest slice above 0.3 m where the legs have merged into one part
crotch = None
for j in range(int(np.searchsorted(ys, 0.3)), occ.shape[1]):
    n, _, st, _ = cv2.connectedComponentsWithStats(occ[:, j, :].astype(np.uint8))
    if sum(st[1:, 4] > 30) == 1:
        crotch = j; break
if crotch is None:
    sys.exit('legs33: 找不到胯下高度')
j0, j1 = int(np.searchsorted(ys, Y_LO)), int(np.searchsorted(ys, ys[crotch] + 0.12))   # legs + upper thighs / hips
sub = occ[:, j0:j1, :]
I, J, K = np.nonzero(sub)
P = np.c_[xs[I], ys[J + j0], zs[K]]
remove = np.zeros(len(P), bool)
per_view = {}
for n, c in cams.items():
    if c.get('kind') != 'main':
        continue
    m = (cv2.imread(f'mask_{n}.png', 0) > 0).astype(np.uint8)
    dist = cv2.distanceTransform(1 - m, cv2.DIST_L2, 5)          # pixels outside the silhouette
    u, v = project(P, c)
    ui = np.clip(np.round(u).astype(int), 0, m.shape[1] - 1); vi = np.clip(np.round(v).astype(int), 0, m.shape[0] - 1)
    out = dist[vi, ui] > MARGIN
    per_view[n] = int(out.sum())
    remove |= out
res = occ.copy()
res[I[remove], J[remove] + j0, K[remove]] = False
# drop tiny islands left in the leg slices
for j in range(j0, j1):
    sl = res[:, j, :].astype(np.uint8)
    n, lb, st, _ = cv2.connectedComponentsWithStats(sl)
    for i in range(1, n):
        if st[i, 4] < 15:
            res[:, j, :][lb == i] = False
print(f'legs33: crotch y={ys[crotch]:.3f} m, legs {Y_LO:.2f}..{ys[j1]:.3f} m, removed {int(remove.sum())} voxels '
      f'({100 * remove.sum() / max(1, len(P)):.1f}% of leg volume)')
print('  per view: ' + ', '.join(f'{k[:6]} {v}' for k, v in sorted(per_view.items())))
np.save(sys.argv[2], res)
