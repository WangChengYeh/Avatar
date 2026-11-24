"""T-pose arms: elliptical cross-section per x — vertical extent from the front view, front-back extent from the
top view (no other camera constrains horizontal arms well)."""
import numpy as np, cv2, json, sys
occ = np.load('occ33.npy'); g = json.load(open('grid33.json')); cams = json.load(open('cams33.json'))
vs = g['vs']; nx, ny, nz = occ.shape
xs = g['x0'] + np.arange(nx) * vs; ys = g['y0'] + np.arange(ny) * vs; zs = g['z0'] + np.arange(nz) * vs
front = [n for n, c in cams.items() if c['kind'] == 'main' and n.startswith('01_')][0]
cf, ct_ = cams[front], cams['top']
mf = cv2.imread(f'mask_{front}.png', 0) > 0
mt = cv2.imread('mask_top.png', 0) > 0


def runs(v):
    i = np.nonzero(v)[0]
    return [] if len(i) == 0 else [(r[0], r[-1]) for r in np.split(i, np.nonzero(np.diff(i) > 1)[0] + 1)]


p = np.radians(ct_['phi']); t = np.radians(ct_['th'])
r_t = np.array([np.cos(p), 0, -np.sin(p)]); u_t = np.array([-np.sin(t) * np.sin(p), np.cos(t), -np.sin(t) * np.cos(p)])
X0 = float(sys.argv[1]) if len(sys.argv) > 1 else 0.20
out = occ.copy(); n_done = 0
Y, Z = np.meshgrid(ys, zs, indexing='ij')
for i, x in enumerate(xs):
    if abs(x) < X0:
        continue
    # front view: vertical run of the arm at this x (topmost run)
    col = int(round(cf['cu'] + cf['s'] * x))
    if not (0 <= col < mf.shape[1]): continue
    rr = runs(mf[:, col])
    if not rr: continue
    a, b = rr[0]
    if (b - a) / cf['s'] > 0.20: continue                 # not an arm column (torso)
    y1 = (cf['cv'] - a) / cf['s']; y0 = (cf['cv'] - b) / cf['s']
    yc, ry = (y0 + y1) / 2, (y1 - y0) / 2
    # top view: the arm's run along the image rows at this x (at the arm's height)
    colt = ct_['cu'] + ct_['s'] * (x * r_t[0])
    colt = int(round(colt))
    if not (0 <= colt < mt.shape[1]): continue
    rt = runs(mt[:, colt])
    if not rt: continue
    # rows -> z : row = cv - s*(x*u_t[0] + y*u_t[1] + z*u_t[2])
    best = max(rt, key=lambda q: q[1] - q[0])
    zz = [(ct_['cv'] - rw) / ct_['s'] - x * u_t[0] - yc * u_t[1] for rw in best]
    zz = [q / u_t[2] for q in zz]
    z0, z1 = min(zz), max(zz)
    zc, rz = (z0 + z1) / 2, (z1 - z0) / 2
    if rz <= 0.005 or rz > 0.12: continue
    ell = ((Y - yc) / max(ry, 1e-3)) ** 2 + ((Z - zc) / rz) ** 2 <= 1.0
    blend = np.clip((abs(x) - X0) / 0.05, 0, 1)            # near the shoulder: union with the hull
    out[i] = ell if blend >= 1 else (ell | occ[i])
    n_done += 1
print('arm columns rebuilt:', n_done)
np.save('occ33b.npy', out)
