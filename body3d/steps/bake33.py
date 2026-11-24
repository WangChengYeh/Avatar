"""Bake body + head textures from all 33 views (orthographic cameras in cams33.json).
weight = (n . view)^P  x  visibility (z-buffer per view)  x  distance from the photo silhouette edge  x  view weight
Head close-ups dominate on the head (highest resolution). Unseen texels are filled by diffusion over the surface."""
import json, os, sys
import cv2, numpy as np
from scipy.ndimage import distance_transform_edt

D = sys.argv[1]
SRC = sys.argv[2]
S_BODY, S_HEAD = 4096, 4096
cams = json.load(open(os.path.join(D, 'cams33.json')))
M = np.load(os.path.join(D, 'uvmesh.npz'))
pos, nrm, tri, uv, grp = M['pos'], M['nrm'], M['tri'], M['uv'], M['grp']

# ---------- rasterise triangle ids into UV space
SIZES = {0: S_BODY, 1: S_HEAD}
JJ, II, T, G = [], [], [], []
for g, Sg in SIZES.items():
    ids = np.full((Sg, Sg), -1, np.int32)
    pts = np.round(np.stack([uv[..., 0] * Sg, (1 - uv[..., 1]) * Sg], -1) * 16 - 8).astype(np.int32)
    for i in np.nonzero(grp == g)[0]:
        cv2.fillConvexPoly(ids, pts[i], int(i), lineType=cv2.LINE_8, shift=4)
    j_, i_ = np.nonzero(ids >= 0)
    JJ.append(j_); II.append(i_); T.append(ids[j_, i_]); G.append(np.full(len(j_), g))
jj, ii, t, tg = map(np.concatenate, (JJ, II, T, G))
Spx = np.where(tg == 0, SIZES[0], SIZES[1])
p = np.c_[(ii + 0.5) / Spx, 1 - (jj + 0.5) / Spx]
a, b, c = uv[t, 0], uv[t, 1], uv[t, 2]
v0, v1, v2 = b - a, c - a, p - a
d00 = (v0 * v0).sum(1); d01 = (v0 * v1).sum(1); d11 = (v1 * v1).sum(1); d20 = (v2 * v0).sum(1); d21 = (v2 * v1).sum(1)
den = d00 * d11 - d01 ** 2; den[np.abs(den) < 1e-20] = 1e-20
w1 = (d11 * d20 - d01 * d21) / den; w2 = (d00 * d21 - d01 * d20) / den
bc = np.clip(np.c_[1 - w1 - w2, w1, w2], 0, 1); bc /= bc.sum(1, keepdims=True)
X = (pos[tri[t]] * bc[..., None]).sum(1)
N = (nrm[tri[t]] * bc[..., None]).sum(1); N /= np.linalg.norm(N, axis=1, keepdims=True) + 1e-9
print('texels', len(X), flush=True)


def voxel_smooth(X, vals, vs):
    o = X.min(0) - vs
    g_ = np.floor((X - o) / vs).astype(np.int64); dims = g_.max(0) + 2
    key = (g_[:, 0] * dims[1] + g_[:, 1]) * dims[2] + g_[:, 2]
    uk, inv = np.unique(key, return_inverse=True)
    cnt = np.bincount(inv, minlength=len(uk))
    mean = np.stack([np.bincount(inv, vals[:, k], len(uk)) for k in range(vals.shape[1])], -1) / cnt[:, None]
    f = (X - o) / vs - 0.5; f0 = np.floor(f).astype(np.int64); fr = f - f0
    out = np.zeros_like(vals); wt = np.zeros(len(X))
    for dx in (0, 1):
        for dy in (0, 1):
            for dz in (0, 1):
                q = f0 + [dx, dy, dz]
                k2 = (q[:, 0] * dims[1] + q[:, 1]) * dims[2] + q[:, 2]
                j = np.clip(np.searchsorted(uk, k2), 0, len(uk) - 1); hit = uk[j] == k2
                w_ = np.abs((1 - dx) - fr[:, 0]) * np.abs((1 - dy) - fr[:, 1]) * np.abs((1 - dz) - fr[:, 2]) * hit
                out += w_[:, None] * mean[j]; wt += w_
    return out / np.maximum(wt, 1e-9)[:, None]


Ns = voxel_smooth(X, N, 0.012); Ns /= np.linalg.norm(Ns, axis=1, keepdims=True) + 1e-9


sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import camera      # orthographic or perspective (c['D']) projection shared by all steps


def remap(img, col, row):
    n = len(col); w_ = 4096; h_ = (n + w_ - 1) // w_
    mx = np.zeros(h_ * w_, np.float32); my = np.zeros(h_ * w_, np.float32)
    mx[:n] = col; my[:n] = row
    out = cv2.remap(img, mx.reshape(h_, w_), my.reshape(h_, w_), cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    return out.reshape(h_ * w_, -1)[:n].squeeze()


def load_view(n):
    im = cv2.imread(os.path.join(SRC, n + '.jpg'))
    m = (cv2.imread(os.path.join(D, f'mask_{n}.png'), 0) > 0).astype(np.uint8)
    H_, W_ = m.shape
    if n == 'top':
        # AI smudges in the top view: light, colourless pixels attached to the body are not skin / hair / clothes
        lab_ = cv2.cvtColor(im, cv2.COLOR_BGR2LAB).astype(np.float32)
        chroma = np.hypot(lab_[..., 1] - 128, lab_[..., 2] - 128)
        smudge = ((chroma < 9) & (lab_[..., 0] > 165)).astype(np.uint8)
        smudge = cv2.morphologyEx(smudge, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
        print('top view smudge pixels removed:', int((smudge & m).sum()))
        m = m & (1 - smudge)
    m2 = cv2.erode(m, np.ones((5, 5), np.uint8))
    _, lb = cv2.distanceTransformWithLabels(1 - m2, cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL)
    zy, zx = np.nonzero(m2 == 1); lut = np.zeros(lb.max() + 1, np.int64); lut[lb[zy, zx]] = zy * W_ + zx
    bled = im.reshape(-1, 3)[lut[lb]].reshape(im.shape).astype(np.float32)
    mb = m.copy(); mb[0, :] = mb[-1, :] = mb[:, 0] = mb[:, -1] = 0      # image border counts as an edge too
    ed = distance_transform_edt(mb).astype(np.float32)
    return bled, ed, m


VW = {'main': 6.0, 'el30': 1.0, 'low20': 1.0, 'top': 0.5, 'head': 1.0}   # main ring is the best-aligned: it wins where it sees
HEAD_PRI = {'head_000deg': 6.0, 'head_180deg': 3.0}                       # frontal close-up owns the face features
PW = 12.0                    # sharp: the most frontal view dominates (blending misaligned AI views ghosts)
# ---------- colour match: every non-main view is scaled per channel to agree with the main ring where both
# see the surface well (the top / elevated / low shots are lit a little differently)
rng = np.random.default_rng(0)
sub = rng.choice(len(X), min(400000, len(X)), replace=False)
Xs, Ns_s = X[sub], Ns[sub]


def view_samples(n, c):
    col, row = camera.project(Xs, c)
    img, ed, m = load_view(n)
    H_, W_ = m.shape
    inb = (col >= 1) & (col < W_ - 2) & (row >= 1) & (row < H_ - 2)
    w = np.clip(np.einsum('ij,ij->i', Ns_s, camera.toward(Xs, c)), 0, 1) ** 2 * inb * (remap(ed, col, row) > 8)
    return w, remap(img, col, row)


ref_acc = np.zeros((len(sub), 3)); ref_w = np.zeros(len(sub))
for n, c in cams.items():
    if c['kind'] == 'main':
        w, colv = view_samples(n, c)
        ref_acc += w[:, None] * colv; ref_w += w
ref = ref_acc / np.maximum(ref_w, 1e-9)[:, None]
GAIN = {}
for n, c in cams.items():
    if c['kind'] in ('main', 'head'):
        continue
    w, colv = view_samples(n, c)
    ov = (w > 0.5) & (ref_w > 0.5) & (colv.min(1) > 30) & (ref.min(1) > 30)
    if ov.sum() > 2000:
        GAIN[n] = np.clip(np.median(ref[ov] / colv[ov], axis=0), 0.8, 1.25)
        print(f'gain {n:14s} BGR {np.round(GAIN[n], 3)}  overlap {ov.sum()}')

acc = np.zeros((len(X), 3)); wsum = np.zeros(len(X)); wconf = np.zeros(len(X))
y = X[:, 1]
for n, c in sorted(cams.items()):
    kind = c['kind']
    col, row = camera.project(X, c)
    depth = camera.depth(X, c)                       # larger = closer to the camera
    ndot = np.einsum('ij,ij->i', Ns, camera.toward(X, c))
    img, ed, m = load_view(n)
    H_, W_ = m.shape
    inb = (col >= 1) & (col < W_ - 2) & (row >= 1) & (row < H_ - 2)
    # z-buffer in image space (cell ~ 4 px on the body views; head close-ups are ~3.5x bigger)
    cell = 4                                         # fine grid: a coarse one marks mouth corners / under the lips as hidden
    gw, gh = W_ // cell + 1, H_ // cell + 1
    k = np.clip((row / cell).astype(int), 0, gh - 1) * gw + np.clip((col / cell).astype(int), 0, gw - 1)
    zb = np.full(gw * gh, -1e9); np.maximum.at(zb, k[inb], depth[inb])
    zb = cv2.dilate(zb.reshape(gh, gw).astype(np.float32), np.ones((3, 3), np.uint8)).ravel()
    vis = depth >= zb[k] - 0.012
    edge_px = 6 if kind != 'head' else 18
    pw = 12.0 if kind == 'head' else PW
    w = np.clip(ndot, 0, 1) ** pw * vis * inb * np.clip((remap(ed, col, row) - 2) / edge_px, 0, 1) * VW[kind] * HEAD_PRI.get(n, 1.0)
    headw = np.clip((y - 1.36) / 0.05, 0, 1)
    if kind == 'head':
        w *= headw                                    # close-ups only on the head / upper neck
        if n == 'head_000deg' and os.path.exists(os.path.join(D, 'face_lm33.npy')):
            # inside the face outline (landmark hull) the frontal close-up owns the texture regardless of the
            # (noisy) surface normals, so no side close-up can paste a second eye / mouth
            lmk = np.load(os.path.join(D, 'face_lm33.npy'))[:, :2].astype(np.int32)
            fm = np.zeros(m.shape, np.uint8); cv2.fillConvexPoly(fm, cv2.convexHull(lmk), 1)
            fm = cv2.erode(fm, np.ones((61, 61), np.uint8))          # stay inside the face oval (earrings hang just outside)
            fm = cv2.GaussianBlur(fm.astype(np.float32), (0, 0), 8)
            inface = remap(fm, col, row) * (ndot > 0.2) * vis * inb
            w = w + inface * 1e3
    else:
        w *= 1 - headw                                # full-body views never paint the head (they would win on
                                                      # down-facing spots like under the lip and paste their own lips)
    # confidence uses a gentle power (is this texel seen at all?); blending uses the sharp one (who wins)
    wc = np.clip(ndot, 0, 1) ** 2 * vis * inb * np.clip((remap(ed, col, row) - 2) / edge_px, 0, 1)
    if kind == 'head':
        wc *= headw
    wconf += wc
    sel = w > 1e-12
    acc[sel] += w[sel, None] * remap(img, col[sel], row[sel]) * GAIN.get(n, np.ones(3))[None, :]
    wsum += w
    print(f'{n:28s} kind {kind:5s} texels used {sel.sum():9d}', flush=True)

colr = acc / np.maximum(wsum, 1e-30)[:, None]
conf = np.clip(wconf / 0.15, 0, 1) * (wsum > 1e-30)
print('low-confidence texels: %.1f%%' % (100 * (conf < 0.5).mean()), flush=True)

# ---------- fill weak texels by diffusion on a 6 mm voxel grid
vs = 0.006
g_ = np.floor((X - X.min(0)) / vs).astype(np.int64); dims = g_.max(0) + 1
key = (g_[:, 0] * dims[1] + g_[:, 1]) * dims[2] + g_[:, 2]
uk, inv = np.unique(key, return_inverse=True)
cw = np.bincount(inv, conf, len(uk)); cnt = np.bincount(inv, minlength=len(uk))
cc = np.stack([np.bincount(inv, conf * colr[:, k], len(uk)) for k in range(3)], -1)
known = cw / cnt > 0.6
vc = np.where(known[:, None], cc / np.maximum(cw, 1e-9)[:, None], 0)
gx, gy, gz = uk // (dims[1] * dims[2]), (uk // dims[2]) % dims[1], uk % dims[2]
nb = []
for dx in (-1, 0, 1):
    for dy in (-1, 0, 1):
        for dz in (-1, 0, 1):
            if dx == dy == dz == 0: continue
            k2 = ((gx + dx) * dims[1] + gy + dy) * dims[2] + gz + dz
            j = np.clip(np.searchsorted(uk, k2), 0, len(uk) - 1)
            nb.append(np.where(uk[j] == k2, j, -1))
nb = np.stack(nb, 1); have = known.copy()
for it in range(300):
    valid = (nb >= 0) & have[np.maximum(nb, 0)]
    s_ = (vc[np.maximum(nb, 0)] * valid[..., None]).sum(1); n_ = valid.sum(1)
    upd = (~known) & (n_ > 0)
    vc[upd] = s_[upd] / n_[upd, None]
    newly = upd & ~have; have |= upd
    if it > 60 and not newly.any():
        break
fill = vc[inv]
final = conf[:, None] * colr + (1 - conf[:, None]) * fill

for g, Sg in SIZES.items():
    k_ = tg == g
    tex = np.zeros((Sg, Sg, 3), np.float32); tex[jj[k_], ii[k_]] = final[k_]
    occ = np.zeros((Sg, Sg), np.uint8); occ[jj[k_], ii[k_]] = 1
    _, labels = cv2.distanceTransformWithLabels(1 - occ, cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL)
    lut = np.zeros(labels.max() + 1, np.int64); lut[labels[jj[k_], ii[k_]]] = jj[k_] * Sg + ii[k_]
    tex = tex.reshape(-1, 3)[lut[labels]].reshape(Sg, Sg, 3)
    cv2.imwrite(os.path.join(D, f'texture_{g}.jpg'), np.clip(tex, 0, 255).astype(np.uint8), [cv2.IMWRITE_JPEG_QUALITY, 92])
print('done')
