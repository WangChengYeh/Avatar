"""Trim the head to the 8 head close-up outlines (run after headreg33, before face33; cwd = work dir).

Why: the visual hull is carved by the 24 full-body views, where the head is ~250 px tall, and the 8 head close-ups
(4x zoom) are only registered against it afterwards. Where the body views do not cut it (the face profile, under the
chin, the back of the neck) the head stays up to 1-2 cm too full. The bake then projects the front close-up onto
that extra volume, and the finished head shows a smeared face and jaw running into the neck at 90 / 270 deg
(Gemini avatar_001 v003, ChatGPT R52: head_090 16.7 % outside the photo's outline; perfect photos 3-5 %).

What: in every head close-up, a rim vertex (surface seen edge-on) that projects outside the photo's head mask moves
inward along its in-plane normal by that distance; the moves are spread smoothly over the surface (Laplacian solve)
and faded out below the chin. Only inward moves: the hull is an upper bound, and the masks include the hair.
The untrimmed mesh is kept as body33s_hull.ply, so a rerun starts from it.
usage: python headsil33.py"""
import json, os, shutil, sys
import cv2
import numpy as np
import scipy.sparse as sp
import trimesh
from scipy.sparse.linalg import factorized
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import camera

ITERS = 6
Y0, Y1 = 1.36, 1.42          # fade-in of the trimming (m, model frame: feet at 0, 1.65 m tall): head and neck,
                             # not the shoulders (only half in the close-ups' frame)
XMAX = 0.13                  # nor the arms (T-pose, at shoulder height)
TOL = 0.002                  # outlines closer than this (m) are left alone
REACH = 0.025                # misses farther than this are occlusions or a wrong match, not a too-full head
SMOOTH = 4.0

if not os.path.exists('body33s_hull.ply'):
    shutil.copy('body33s.ply', 'body33s_hull.ply')
if os.path.exists('body33s_noface.ply'):      # face33 must start again from the trimmed head
    os.remove('body33s_noface.ply')
mesh = trimesh.load('body33s_hull.ply', process=False)
cams = {n: c for n, c in json.load(open('cams33.json')).items() if c.get('kind') == 'head'}
if not cams:
    mesh.export('body33s.ply'); print('headsil33: no head cameras, mesh unchanged'); sys.exit(0)
X = np.asarray(mesh.vertices, float).copy(); F = np.asarray(mesh.faces)
zone = np.clip((X[:, 1] - Y0) / (Y1 - Y0), 0, 1) * np.clip((XMAX - np.abs(X[:, 0])) / 0.03, 0, 1)
free = zone > 0
E = mesh.edges_unique
A = sp.coo_matrix((np.ones(2 * len(E)), (np.r_[E[:, 0], E[:, 1]], np.r_[E[:, 1], E[:, 0]])), shape=(len(X),) * 2).tocsr()
L = sp.diags(np.asarray(A.sum(1)).ravel()) - A
LtL = (L.T @ L).tocsr()

sdf = {}
for n in cams:
    m = (cv2.imread(f'mask_{n}.png', 0) > 0).astype(np.uint8)
    sdf[n] = (cv2.distanceTransform(1 - m, cv2.DIST_L2, 5) - cv2.distanceTransform(m, cv2.DIST_L2, 5)).astype(np.float32)


def vnormals(P):
    return trimesh.Trimesh(P, F, process=False).vertex_normals


for it in range(ITERS):
    nrm = vnormals(X)
    acc = np.zeros_like(X); cnt = np.zeros(len(X))
    for n, c in cams.items():
        r_, u_, f_ = camera.axes(c['phi'], c['th'])
        nf = nrm @ f_
        rim = free & (np.abs(nf) < 0.3)
        col, row = camera.project(X[rim], c)
        sd = cv2.remap(sdf[n], col.astype(np.float32).reshape(1, -1), row.astype(np.float32).reshape(1, -1),
                       cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE).ravel() / c['s']     # metres, + = outside
        hit = np.abs(sd) < REACH
        ip = nrm[rim] - nf[rim, None] * f_
        ip /= np.linalg.norm(ip, axis=1, keepdims=True) + 1e-9
        ids = np.flatnonzero(rim)[hit]
        acc[ids] -= ip[hit] * sd[hit, None]          # signed: a view that sees the rim inside its outline holds it
        cnt[ids] += 1                                # (two close-ups that disagree meet halfway, R: Gemini 090/270)
    T = np.zeros_like(X); has = cnt > 0
    T[has] = acc[has] / cnt[has, None]
    out_ = has & ((T * nrm).sum(1) < -TOL)            # net move inward: the head is too full here
    T[out_] *= (1 - TOL / np.linalg.norm(T[out_], axis=1))[:, None]
    T[~out_] = 0
    has = out_
    if not has.any():
        break
    Wd = sp.diags(np.where(has, 1.0, 0.0) + 1e-4)
    solve = factorized((Wd + SMOOTH * LtL).tocsc())
    D = np.stack([solve(Wd @ T[:, k]) for k in range(3)], 1) * zone[:, None]
    X += D
    print('headsil33 %d: %d rim vertices outside the close-ups, mean miss %.1f mm, max move %.1f mm'
          % (it, has.sum(), 1000 * np.linalg.norm(T[has], axis=1).mean(), 1000 * np.linalg.norm(D, axis=1).max()))
moved = np.linalg.norm(X - mesh.vertices, axis=1)
print('headsil33: head trimmed, %d vertices moved > 1 mm, max %.1f mm' % ((moved > 0.001).sum(), 1000 * moved.max()))
trimesh.Trimesh(X, F, process=False).export('body33s.ply')
