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
# template-detail regions follow the body but keep their own shape: hands (fingers), feet, face
base_w = np.where(reg == 1, 0.02, np.where(reg == 2, 0.15, 1.0))
# closest points: dense surface samples + KD-tree (no rtree here); inside = behind the sample's outward normal
S, fid = trimesh.sample.sample_surface_even(hull, 600000, seed=0)
SN = hull.face_normals[fid]; stree = cKDTree(S)


def closest(Q):
    dist, j = stree.query(Q)
    return S[j], dist, ((Q - S[j]) * SN[j]).sum(1) < 0
for it, lam in enumerate((40, 20, 10, 6, 4, 3, 2, 2)):
    cp, dist, inside = closest(X)
    # the hull is an upper bound of the body (carved from silhouettes): points outside are pulled in firmly,
    # points inside only gently (the hull cannot see concavities)
    w = base_w * np.where(inside, 0.8, 1.0)
    W = sp.diags(w)
    solve = factorized((W + lam * LtL).tocsc())
    rhs = w[:, None] * (cp - X0)
    D = np.stack([solve(rhs[:, c]) for c in range(3)], 1)
    X = X0 + D
    print('  iter', it, 'lam', lam, 'mean |d| mm', round(1000 * np.mean(dist), 1), 'outside', int((~inside).sum()))
cp, dist, _ = closest(X)
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
