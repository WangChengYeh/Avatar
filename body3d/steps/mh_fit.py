"""MakeHuman template, step 2: fit the T-posed template to the photos: inflate it to the hull body33s.ply, fit it
to the hull (Laplacian-regularised non-rigid ICP; hands and feet rigid, placed on the hull's), then refine it on
the 24 full-body silhouettes; carry the displacement to the helper vertices (they define the joints) and back to the
rest pose (inverse linear blend skinning). Also exports the hull's head (hull_head.npz) for mh_build.
    python mh_fit.py WORK_DIR        (reads mh_prep.npz, body33s.ply, cams33.json, mask_*.png; writes mh_fit.npz,
                                      hull_head.npz)
Pipeline frame: X her left, Y up, Z toward the front camera. Blender: (x, y, z)_bl -> (x, z, -y)."""
import os, sys
import numpy as np, trimesh, scipy.sparse as sp
from scipy.sparse.linalg import factorized
from scipy.spatial import cKDTree
D = WORK = sys.argv[1]
PREP, HULL, OUT, RELIEF = (os.path.join(D, f) for f in ('mh_prep.npz', 'body33s.ply', 'mh_fit.npz', 'face_relief.npz'))
d = np.load(PREP, allow_pickle=True)
bl2gl = lambda a: np.c_[a[:, 0], a[:, 2], -a[:, 1]]
gl2bl = lambda a: np.c_[a[:, 0], -a[:, 2], a[:, 1]]
P0 = bl2gl(d['posed']); body = d['body']; region = d['region']
faces = [f[:n] for f, n in zip(d['faces'], d['nfv'])]
hull = trimesh.load(HULL)
H = hull.vertices
# --- global: uniform scale to the hull height, feet on the floor, centre on the hull's rotation axis
B = P0[body]
k = (H[:, 1].max() - H[:, 1].min()) / (B[:, 1].max() - B[:, 1].min())
P = (P0 - [0, B[:, 1].min(), 0]) * k + [0, H[:, 1].min(), 0]
# torso band (waist to chest, arms excluded): bounding-box centres in x / z (feet would pull a centroid forward)
def band_centre(V):
    t = V[(V[:, 1] > 0.55 * V[:, 1].max()) & (V[:, 1] < 0.72 * V[:, 1].max()) & (np.abs(V[:, 0]) < 0.2)]
    return (t[:, [0, 2]].min(0) + t[:, [0, 2]].max(0)) / 2
P[:, [0, 2]] += band_centre(H) - band_centre(P[body])
print('scale', round(k, 4))
# --- body graph Laplacian (uniform)
idx = np.flatnonzero(body); loc = -np.ones(len(P), int); loc[idx] = np.arange(len(idx))
E = set()
for f in faces:
    for a, b in zip(f, list(f[1:]) + [f[0]]):
        a, b = loc[a], loc[b]
        if a >= 0 and b >= 0 and a != b:
            E.add((min(a, b), max(a, b)))
E = np.array(sorted(E)); n = len(idx)
A = sp.coo_matrix((np.ones(2 * len(E)), (np.r_[E[:, 0], E[:, 1]], np.r_[E[:, 1], E[:, 0]])), shape=(n, n)).tocsr()
deg = np.asarray(A.sum(1)).ravel()
L = sp.diags(deg) - A
LtL = (L.T @ L).tocsr()
X0 = P[idx].copy(); X = X0.copy()
reg = region[idx]
# Template-detail parts keep their own shape and move as one piece: the face, each hand (fingers) and each foot (toes).
# A smooth non-rigid field squeezes thin features a few mm wide (eyelids, nostrils, lips, fingers, toes) until they
# pass through each other: on the polished photos 5000 faces (19 %) intersected the mesh itself, 2000 of them on the
# head, and the two layers z-fight as dark / light specks in the app. The hull is carved from silhouettes and has
# no nose, lips or eye sockets, so the face only takes its position and size from the cheeks and temples
# (least-squares translation and uniform scale within ±5 %); hands and feet follow their arm / leg. Each part is blended into the fitted field over BLEND metres.
top = X0[:, 1].max()
hb = X0[(X0[:, 1] > top - 0.24)]
face = (X0[:, 1] > top - 0.25) & (X0[:, 1] < top - 0.06) & (X0[:, 2] > (hb[:, 2].min() + hb[:, 2].max()) / 2) \
    & (np.abs(X0[:, 0]) < 0.08)
PARTS = {'face': face, 'hand_l': (reg == 1) & (X0[:, 0] > 0), 'hand_r': (reg == 1) & (X0[:, 0] < 0),
         'foot_l': (reg == 2) & (X0[:, 0] > 0), 'foot_r': (reg == 2) & (X0[:, 0] < 0)}
BLEND = 0.04
FLOOR = float(H[:, 1].min())                       # the hull's floor (the photos' feet)
FACE_SCALE = (0.95, 1.05)
# the hull's 3D opening (round33) shaves off the nose and lips, so only the cheeks / temples place the face
FACE_DATA = face & (np.abs(X0[:, 0]) > 0.035)
base_w = np.where(reg > 0, 0.0, np.where(face, 0.0, 1.0))
part_w = {}
for k, m in PARTS.items():
    t = np.clip(1 - cKDTree(X0[m]).query(X0)[0] / BLEND, 0, 1)
    part_w[k] = t * t * (3 - 2 * t)
print('rigid parts (vertices):', {k: int(m.sum()) for k, m in PARTS.items()})


def rigid_parts(D, cp, w_data):
    """replace the fitted field on every part by one translation (face: translation + uniform scale to the hull)"""
    out = D.copy()
    for k, m in PARTS.items():
        if k == 'face':
            ww = w_data[m]
            if ww.sum() > 1:
                c = X0[m].mean(0); A = X0[m] - c; B = cp[m] - c
                t = (ww[:, None] * (B - A)).sum(0) / ww.sum()
                sc = float(np.clip((ww * (A * (B - t)).sum(1)).sum() / (ww * (A * A).sum(1)).sum(), *FACE_SCALE))
                Dp = (sc - 1) * (X0 - c) + t
            else:
                Dp = np.broadcast_to(D[m].mean(0), D.shape)
        else:
            Dp = np.broadcast_to(D[m].mean(0), D.shape).copy()
            if k.startswith('hand'):
                # the fingertips reach where the photos' do (the hull's tip along the arm): the arm field alone
                # left the template hand a few cm short or long (luna-v1: wrist missing, fingertips extra)
                sx = np.sign(X0[m, 0].mean())
                tip_t = (sx * (X0[m, 0] + Dp[m, 0])).max()
                tip_h = (sx * H[:, 0]).max()
                Dp[:, 0] += sx * (tip_h - tip_t)
                # then turn the hand as one piece about its centre to lie in the hull's hand (palm direction,
                # finger spread plane): weighted Kabsch to the hull's closest points
                A_ = X0[m] + Dp[m]
                cpa, dd, ins, _ = closest(A_)
                ww = np.where(ins, 0.3, 1.0) * (dd < 0.04)
                if ww.sum() > 10:
                    ca = (ww[:, None] * A_).sum(0) / ww.sum(); cb = (ww[:, None] * cpa).sum(0) / ww.sum()
                    Hm = ((A_ - ca) * ww[:, None]).T @ (cpa - cb)
                    U_, _, Vt = np.linalg.svd(Hm)
                    R_ = Vt.T @ U_.T
                    if np.linalg.det(R_) < 0:
                        Vt[-1] *= -1; R_ = Vt.T @ U_.T
                    ang = np.degrees(np.arccos(np.clip((np.trace(R_) - 1) / 2, -1, 1)))
                    if ang < 35:
                        Dp = Dp + ((X0 + Dp - ca) @ R_.T + cb - (X0 + Dp))
            if k.startswith('foot'):
                # the feet stand on the floor: the leg field alone let a thin hull pull them 5 cm under it (R17;
                # pre-bake check 'mesh on the floor')
                Dp[:, 1] += FLOOR - (X0[m, 1] + Dp[m, 1]).min()
                # and on the photos' footprint: the leg field carried the template foot a few cm forward of it
                # (luna-v1: heel missing, toes extra in every side view). Centre the sole on the hull's sole.
                sole_t = X0[m] + Dp[m]; sole_t = sole_t[sole_t[:, 1] < FLOOR + 0.03]
                sx = np.sign(X0[m, 0].mean())
                sole_h = H[(H[:, 1] < FLOOR + 0.03) & (np.sign(H[:, 0]) == sx)]
                if len(sole_t) > 10 and len(sole_h) > 10:
                    ct = (sole_t[:, [0, 2]].min(0) + sole_t[:, [0, 2]].max(0)) / 2
                    chh = (sole_h[:, [0, 2]].min(0) + sole_h[:, [0, 2]].max(0)) / 2
                    Dp[:, [0, 2]] += chh - ct
        b = part_w[k][:, None]
        out = (1 - b) * out + b * Dp
    return out


# vertex normals of the body (for rejecting closest points on the wrong side: cavities, folds)
tri_ = np.array([[loc[f[0]], loc[f[i]], loc[f[i + 1]]] for f in faces for i in range(1, len(f) - 1)])
tri_ = tri_[(tri_ >= 0).all(1)]


def vnormals(V):
    fn = np.cross(V[tri_[:, 1]] - V[tri_[:, 0]], V[tri_[:, 2]] - V[tri_[:, 0]])
    vn = np.zeros_like(V)
    for k in range(3):
        np.add.at(vn, tri_[:, k], fn)
    return vn / (np.linalg.norm(vn, axis=1, keepdims=True) + 1e-12)
# closest points: dense surface samples + KD-tree (no rtree here); inside = behind the sample's outward normal
S, fid = trimesh.sample.sample_surface_even(hull, 600000, seed=0)
SN = hull.face_normals[fid]; stree = cKDTree(S)


def closest(Q):
    dist, j = stree.query(Q)
    return S[j], dist, ((Q - S[j]) * SN[j]).sum(1) < 0, j
INSIDE_W = 0.1
# The template body (MakeHuman default build, weight 0.45) is a size thinner than most hulls: 7-10 mm inside it
# everywhere on luna-v1, so with the gentle inside pull every silhouette came out too small (final acceptance
# 14.4 %). Inflate the template first: each vertex moves out along its normal by the smoothed depth at which it
# sits inside the hull (body only; face, hands and feet keep their shape), then the fit below starts at the
# hull's size. Concavities the hull bridges (armpits, between the thighs) are deeper than INFLATE_MAX and only
# take the cap, the smoothing keeps neighbouring vertices together.
INFLATE_MAX = 0.02
if INFLATE_MAX > 0:
    _, dist0, inside0, j0 = closest(X0)
    n0 = vnormals(X0)
    ok0 = inside0 & ((n0 * SN[j0]).sum(1) > 0.5)
    off = np.where(ok0, np.minimum(dist0, INFLATE_MAX), 0.0)
    nbr = sp.diags(1 / np.maximum(deg, 1)) @ A
    for _ in range(20):
        off = 0.5 * off + 0.5 * (nbr @ off)
    off *= base_w > 0                                      # not the face, hands or feet
    X0 = X0 + off[:, None] * n0
    X = X0.copy()
    print('inflate: template moved out by median %.1f mm (p90 %.1f) to the hull before the fit'
          % (1000 * np.median(off[off > 0]), 1000 * np.percentile(off[off > 0], 90)))
for it, lam in enumerate((40, 20, 12, 8, 6, 6)):
    cp, dist, inside, j = closest(X)
    # only closest points facing the same way count (standard ICP normal test): a cavity or a fold would match the
    # far wall of the hull and turn inside out
    agree = (vnormals(X) * SN[j]).sum(1) > 0.3
    # the hull is an upper bound of the body (carved from silhouettes): points outside are pulled in firmly,
    # points inside only gently (the hull cannot see concavities)
    # inside: the hull bridges concavities (under the jaw, behind the ears, armpits); pulling both walls of one out
    # to the same hull surface makes them intersect, so inside points are pulled only very gently
    side = np.where(inside, INSIDE_W, 1.0) * agree
    w = base_w * side + 1e-4
    W = sp.diags(w)
    solve = factorized((W + lam * LtL).tocsc())
    rhs = w[:, None] * (cp - X0)
    D = np.stack([solve(rhs[:, c]) for c in range(3)], 1)
    D = rigid_parts(D, cp, side * FACE_DATA)
    X = X0 + D
    print('  iter', it, 'lam', lam, 'mean |d| mm', round(1000 * np.mean(dist), 1), 'outside', int((~inside).sum()),
          'normal-rejected', int((~agree).sum()))
# --- silhouette refinement: the hull is an upper bound (fat between the eight level views) and the template a
# generic body, so the fit above still misses the photos' outline by 1-2 cm here and there (luna-v1: 8.5 % after
# the fit). Fit the outline itself: in every full-body view, a vertex on the model's rim that lands off the photo's
# outline moves along its normal (in the image plane) by that distance; the moves of all views are combined by
# the same smooth solve as above (the level ring counting for more: silfit.py). Face, hands and feet keep their shape; only near-outline misses count (an
# occluded rim lands deep inside the photo silhouette and is ignored).
SIL_ITERS = 4
if SIL_ITERS and os.path.exists(os.path.join(WORK, 'cams33.json')):
    import json as _json, cv2
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import silfit
    cams_ = {n: c for n, c in _json.load(open(os.path.join(WORK, 'cams33.json'))).items()
             if c.get('kind') in ('main', 'el30', 'low20')}
    sdfs = {n: silfit.signed(cv2.imread(os.path.join(WORK, f'mask_{n}.png'), 0)) for n in cams_}
    tri_ = np.array([(f[0], f[k], f[k + 1]) for f in ([int(v) for v in f] for f in faces) for k in range(1, len(f) - 1)])
    tri_ = loc[tri_[body[tri_].all(1)]]                         # the body's own surface, in X's numbering
    free = base_w > 0
    for it in range(SIL_ITERS):
        # the level ring has the larger say and every vertex is measured against the model's own outline: silfit.py
        T_, has = silfit.moves(X, vnormals(X), tri_, cams_, sdfs, free)
        Wd = sp.diags(np.where(has, 1.0, 0.0) + 1e-4)
        solve_ = factorized((Wd + 4.0 * LtL).tocsc())
        Dd = np.stack([solve_(Wd @ T_[:, k]) for k in range(3)], 1)
        X = X + Dd * free[:, None]
        print('  silhouette refinement %d: %d rim vertices, mean move %.1f mm' % (it, has.sum(), 1000 * np.abs(T_[has]).sum(1).mean()))
cp, dist, _, _ = closest(X)
fold = (vnormals(X) * vnormals(X0)).sum(1) < 0
print('vertices turned over (normal > 90° from the template):', int(fold.sum()))
print('final mean / p90 distance to hull mm', round(1000 * dist.mean(), 1), round(1000 * np.percentile(dist, 90), 1))
# --- helpers follow the nearest body vertices
Pn = P.copy(); Pn[idx] = X
other = np.flatnonzero(~body)
tree = cKDTree(P[idx]); dd, nn = tree.query(P[other], k=8)
wgt = 1 / (dd + 1e-4); wgt /= wgt.sum(1, keepdims=True)
Pn[other] = P[other] + (wgt[..., None] * (X - X0)[nn]).sum(1)
# --- back to the Blender frame and to the rest pose (the global scale / shift is kept in the rest shape too)
Pb = gl2bl(Pn)
Minv = np.linalg.inv(d['Mv'])
R = np.einsum('nij,nj->ni', Minv, np.c_[Pb, np.ones(len(Pb))])[:, :3]
np.savez(OUT, rest=R, posed=Pb)
# --- the head comes from the hull (mh_build): the template face is a generic face, and fitting it to the person
# (depth relief, mouth cavity, hair bun) left seams, holes and patchwork on the perfect photos, while the hull's head
# (with face33's relief) bakes cleanly on both. Export the hull above HEAD_CUT of the height, Blender frame.
HEAD_CUT = 1.40 / 1.65
hv, hf = np.asarray(hull.vertices), np.asarray(hull.faces)
ycut = float(H[:, 1].min() + HEAD_CUT * (H[:, 1].max() - H[:, 1].min()))
keepf = (hv[hf][:, :, 1] > ycut).all(1)
used = np.unique(hf[keepf]); remap_ = -np.ones(len(hv), int); remap_[used] = np.arange(len(used))
np.savez(os.path.join(WORK, 'hull_head.npz'), v=gl2bl(hv[used]), f=remap_[hf[keepf]], cut=ycut)
print('hull head: %d vertices above %.3f m for mh_build' % (len(used), ycut))
print('mh_fit: mean distance to the hull %.1f mm' % (1000 * dist.mean()))
