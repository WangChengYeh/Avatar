"""MakeHuman template, step 2: fit the T-posed template to the photo hull body33s.ply (Laplacian-regularised
non-rigid ICP), carry the displacement to the helper vertices (they define the joints) and back to the rest pose
(inverse linear blend skinning). Hands (fingers) and feet keep the template's shape and follow the body.
    python mh_fit.py WORK_DIR        (reads mh_prep.npz, body33s.ply; writes mh_fit.npz)
Pipeline frame: X her left, Y up, Z toward the front camera. Blender: (x, y, z)_bl -> (x, z, -y)."""
import os, sys
import numpy as np, trimesh, scipy.sparse as sp
from scipy.sparse.linalg import factorized
from scipy.spatial import cKDTree
D = sys.argv[1]
PREP, HULL, OUT = (os.path.join(D, f) for f in ('mh_prep.npz', 'body33s.ply', 'mh_fit.npz'))
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
            if k.startswith('foot'):
                # the feet stand on the floor: the leg field alone let a thin hull pull them 5 cm under it (R17;
                # pre-bake check 'mesh on the floor')
                Dp[:, 1] += FLOOR - (X0[m, 1] + Dp[m, 1]).min()
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
INSIDE_W = 0.03
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
print('mh_fit: mean distance to the hull %.1f mm' % (1000 * dist.mean()))
