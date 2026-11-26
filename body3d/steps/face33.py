"""Face step: align the 3/4 head close-ups by facial landmarks and give the mesh a real face relief.

Why: the head close-ups were registered by their silhouettes, which include the hair; AI draws the hair volume a
little differently in every close-up, so scale and position drift (measured: 4–9 mm offset, one face 9.5 % too
long). And the head geometry comes from body-scale silhouettes: no nose (19–27 mm too flat), no eye sockets
(8–16 mm too full). Both make the frontal and 3/4 textures land in different places -> a doubled face.

What it does (cwd = work dir; needs face_lm33.npy from face_landmarks.py and mediapipe):
  1. 468 MediaPipe landmarks in head_000 (given) and in head_045 / head_315 (detected here).
  2. head_000 is the anchor. Each landmark is a point on the head_000 viewing ray: X_i = P_i + t_i f0, where P_i is
     where the ray meets the mesh and t_i an unknown depth correction.
  3. Least squares: per 3/4 view (phi ±5°, fixed when the photos passed the check; with the ring lock only phi, otherwise also s, cu, cv) and per landmark
     t_i so that X_i reprojects onto the
     landmarks detected in the 3/4 views (robust loss; landmarks on the far, hidden side are skipped).
  4. The 3/4 head cameras are replaced by the landmark fit; t is spread over the face (thin-plate RBF in the
     head_000 image plane, faded out over 15 mm outside the landmark outline) and the face vertices are moved
     along the head_000 viewing direction. body33s.ply is rewritten (original kept as body33s_noface.ply).
usage: python face33.py IMG_DIR"""
import json, os, shutil, sys
import cv2
import numpy as np
import trimesh
from scipy.interpolate import RBFInterpolator
from scipy.optimize import least_squares
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import camera

IMG = sys.argv[1]
SIDE = ('head_045deg', 'head_315deg')
MAX_T = 0.025                       # largest depth correction (m)
FADE = 0.015                        # fade-in width inside the landmark outline: no movement on the outline (m)
if not os.path.exists('face_lm33.npy'):
    print('face33: no face_lm33.npy (no face in head_000deg; run the face step)', file=sys.stderr); sys.exit(2)
try:
    import mediapipe as mp
except ImportError:
    sys.exit('face33: mediapipe is required (pip install "mediapipe==0.10.14")')

cams = json.load(open('cams33.json'))
# always start from the head cameras as headreg33 left them (kept in 'pre_face'; headreg33 writes fresh dicts),
# so running this step again gives exactly the same result
for n in SIDE:
    if n in cams and 'pre_face' in cams[n]:
        cams[n] = dict(cams[n]['pre_face'])
# always start from the uncorrected mesh, so running the step again does not apply the correction twice
# always start from the uncorrected mesh (the mesh step deletes the backup), so a rerun does not apply it twice
if not os.path.exists('body33s_noface.ply'):
    shutil.copy('body33s.ply', 'body33s_noface.ply')
mesh = trimesh.load('body33s_noface.ply', process=False)
V = np.asarray(mesh.vertices, float); F = np.asarray(mesh.faces)
L0 = np.load('face_lm33.npy')[:, :2]
c0 = cams['head_000deg']; r0, u0, f0 = camera.axes(c0['phi'], c0['th'])

fm = mp.solutions.face_mesh.FaceMesh(static_image_mode=True, refine_landmarks=False, min_detection_confidence=0.3)


def detect(n):
    im = cv2.imread(os.path.join(IMG, n + '.jpg'))
    if im is None:
        return None
    h, w = im.shape[:2]
    r = fm.process(cv2.cvtColor(im, cv2.COLOR_BGR2RGB))
    return None if not r.multi_face_landmarks else np.array([[l.x * w, l.y * h] for l in r.multi_face_landmarks[0].landmark])


def raycast(px, c):
    """first mesh hit (nearest to the camera) of the viewing rays through pixels px (head region only)"""
    sel = (V[F][:, :, 1] > 1.30).all(1)
    FF = F[sel]
    uv = np.c_[camera.project(V, c)]; dep = camera.depth(V, c)
    T = uv[FF]; Z = dep[FF]
    out = np.full((len(px), 3), np.nan); nrm = np.full((len(px), 3), np.nan)
    fn = mesh.face_normals[sel]
    a, b, cc = T[:, 0], T[:, 1], T[:, 2]
    v0, v1 = b - a, cc - a
    den = v0[:, 0] * v1[:, 1] - v1[:, 0] * v0[:, 1]
    ok = np.abs(den) > 1e-9
    for i, q in enumerate(px):
        v2 = q - a
        with np.errstate(divide='ignore', invalid='ignore'):
            l1 = (v2[:, 0] * v1[:, 1] - v1[:, 0] * v2[:, 1]) / den
            l2 = (v0[:, 0] * v2[:, 1] - v2[:, 0] * v0[:, 1]) / den
        hit = ok & (l1 >= 0) & (l2 >= 0) & (l1 + l2 <= 1)
        if hit.any():
            z = (1 - l1 - l2) * Z[:, 0] + l1 * Z[:, 1] + l2 * Z[:, 2]
            k = np.nonzero(hit)[0][np.argmax(z[hit])]
            out[i] = (1 - l1[k] - l2[k]) * V[FF[k, 0]] + l1[k] * V[FF[k, 1]] + l2[k] * V[FF[k, 2]]
            nrm[i] = fn[k]
    return out, nrm


P, N = raycast(L0, c0)
good = ~np.isnan(P[:, 0])
obs = {}
for n in SIDE:
    if n in cams:
        L = detect(n)
        if L is not None:
            _, _, fs = camera.axes(cams[n]['phi'], cams[n]['th'])
            vis = good & (N @ fs > 0.15)                 # landmark faces this camera (far-side contour is hidden)
            obs[n] = (L, vis)
if not obs:
    print('face33: no face found in the 3/4 close-ups', file=sys.stderr); sys.exit(2)
idx = np.nonzero(good)[0]; nL = len(idx)
names = list(obs)
# fixed distance and centre within the close-up ring (headreg33): with the ring lock on, the landmarks may only
# turn a close-up (its angle); scale and position stay those of the ring, so a face drawn bigger is not absorbed
HEAD_RING = None
if camera.ring_lock_enabled() and os.path.exists('ring_consistency.json'):
    HEAD_RING = json.load(open('ring_consistency.json')).get('rings', {}).get('head')
    if HEAD_RING and not json.load(open('ring_consistency.json')).get('head_locked'):
        HEAD_RING = None


def unpack(x):
    cs = {}
    for j, n in enumerate(names):
        dphi, s, cu, cv = x[4 * j:4 * j + 4]
        if HEAD_RING:
            cs[n] = camera.ring_apply(dict(cams[n], phi=cams[n]['phi'] + dphi), HEAD_RING)
        else:
            cs[n] = dict(cams[n], phi=cams[n]['phi'] + dphi, s=s, cu=cu, cv=cv)
    return cs, x[4 * len(names):]


def residuals(x):
    cs, t = unpack(x)
    X = P[idx] + t[:, None] * f0
    res = []
    for n in names:
        L, vis = obs[n]
        m = vis[idx]
        col, row = camera.project(X[m], cs[n])
        res.append((col - L[idx[m], 0]) / cs[n]['s'] * 1000)      # mm
        res.append((row - L[idx[m], 1]) / cs[n]['s'] * 1000)
    res.append(0.05 * t * 1000)                                   # weak prior: stay near the mesh
    res.append([5.0 * x[4 * j] for j in range(len(names))])       # weak prior: angle near the old one
    return np.concatenate(res)


x0 = np.concatenate([[0.0, cams[n]['s'], cams[n]['cu'], cams[n]['cv']] for n in names] + [np.zeros(nL)])
SW = 1e-6 if HEAD_RING else 0.2                     # ring lock: scale / position are not free (unused in unpack)
CW = 1e-3 if HEAD_RING else 1e5
# angle: ±5°, or the spec angle when the photos passed the check (camera.MAX_DPHI = 0): on perfect photos MediaPipe
# reads 3/4 faces with a bias that turned the close-ups 2.5–2.8° and put the face 7 mm off the full-body view (#28)
DP = min(5.0, camera.MAX_DPHI) or 1e-6
lo = np.concatenate([[-DP, cams[n]['s'] * (1 - SW), cams[n]['cu'] - CW, cams[n]['cv'] - CW] for n in names] + [np.full(nL, -MAX_T)])
hi = np.concatenate([[DP, cams[n]['s'] * (1 + SW), cams[n]['cu'] + CW, cams[n]['cv'] + CW] for n in names] + [np.full(nL, MAX_T)])
print('face33: ring lock ' + ('on: only the close-up angles move' if HEAD_RING else 'off: angle, scale and position per close-up'))
r_before = np.abs(residuals(x0)[:-nL - len(names)])
sol = least_squares(residuals, x0, bounds=(lo, hi), loss='soft_l1', f_scale=3.0, x_scale='jac', max_nfev=200)
r_after = np.abs(sol.fun[:-nL - len(names)])
cs, t = unpack(sol.x)
print(f'face33: landmark misalignment median {np.median(r_before):.1f} mm -> {np.median(r_after):.1f} mm '
      f'(p90 {np.percentile(r_before, 90):.1f} -> {np.percentile(r_after, 90):.1f} mm)')
for n in names:
    o, c = cams[n], cs[n]
    print(f'  {n}: phi {o["phi"]:.1f}->{c["phi"]:.1f}  s {o["s"]:.0f}->{c["s"]:.0f}  cu {o["cu"]:.0f}->{c["cu"]:.0f}  cv {o["cv"]:.0f}->{c["cv"]:.0f}')
    cams[n] = dict(c, pre_face={k: v for k, v in o.items() if k != 'pre_face'})
print(f'  depth corrections: median {1000 * np.median(t):+.1f} mm, range {1000 * t.min():+.1f} .. {1000 * t.max():+.1f} mm '
      f'(nose tip {1000 * t[np.nonzero(idx == 1)[0][0]]:+.1f} mm)' if (idx == 1).any() else '')

# ---- spread the depth corrections over the face and move the vertices along f0. Only interior landmarks
# (eyes, brows, nose, mouth, cheeks) that fit well: the face-outline points sit on the silhouette in the 3/4 views
# and triangulate badly; the outline itself is pinned (t = 0) so the face blends into the head without a step.
oval = sorted({i for e in mp.solutions.face_mesh.FACEMESH_FACE_OVAL for i in e})
fit_err = np.zeros(nL)
for n in names:
    L, vis = obs[n]; m = vis[idx]
    col, row = camera.project((P[idx] + t[:, None] * f0)[m], cs[n])
    e = np.full(nL, 0.0); e[m] = np.hypot(col - L[idx[m], 0], row - L[idx[m], 1]) / cs[n]['s']
    fit_err = np.maximum(fit_err, e)
inner = ~np.isin(idx, oval) & (fit_err < 0.003) & (np.abs(t) < MAX_T - 1e-4)
uv_all = np.c_[camera.project(P[idx], c0)] / c0['s']                 # landmark positions in metres (image plane)
outline = np.isin(idx, oval)
pts = np.r_[uv_all[inner], uv_all[outline]]; val = np.r_[t[inner], np.zeros(outline.sum())]
print(f'  depth field from {inner.sum()} interior landmarks, outline ({outline.sum()}) pinned to 0')
rbf = RBFInterpolator(pts, val, kernel='thin_plate_spline', smoothing=1e-3)
uvL = uv_all[outline]
uvV = np.c_[camera.project(V, c0)] / c0['s']
front = (V[:, 1] > 1.30) & (np.asarray(mesh.vertex_normals) @ f0 > 0.2) & ((V - P[idx].mean(0)) @ f0 > -0.06)
hull = cv2.convexHull((uvL * 2000).astype(np.int32))
dist = np.array([cv2.pointPolygonTest(hull, (float(p[0] * 2000), float(p[1] * 2000)), True) / 2000 for p in uvV[front]])
w = np.clip(dist / FADE, 0, 1)                                          # 0 on / outside the outline, 1 from FADE inside
d = np.clip(rbf(uvV[front]), -MAX_T, MAX_T) * w
V2 = V.copy(); V2[front] += d[:, None] * f0
print(f'  moved {int((np.abs(d) > 1e-4).sum())} vertices, max {1000 * np.abs(d).max():.1f} mm')
trimesh.Trimesh(V2, F, process=False).export('body33s.ply')
json.dump(cams, open('cams33.json', 'w'), indent=1)
