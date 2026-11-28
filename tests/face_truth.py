"""How far is the reconstructed face from the model the photos were rendered from?  A developer's measuring tool.

The perfect photo sets are renders of a known model (tests/data/luna-v1.glb; tests/data/body_rigged.glb for the
set rendered from an earlier result), so the face of a reconstruction can be compared with the truth instead of
with a number that only says the photos agree with each other. For each of the 468 face landmarks of the frontal
close-up, the depth along the frontal viewing ray is read on the truth and on the reconstruction.

    python tests/face_truth.py TRUTH.glb WORK [MESH ...]      # meshes in WORK; default: body33s_noface.ply body33s.ply

Measured on 2026-11-28 (body3d 2.29.0), mean / 90th percentile of the absolute depth error (mm):
    luna   trimmed hull 7.5 / 14.9   with the face relief 4.9 /  7.5
    synth  trimmed hull 4.9 /  8.0   with the face relief 5.9 / 12.7   (nose tip +20 mm, brow +12 mm)
The relief follows MediaPipe's idea of a face: nose tip 13-14 mm in front of the bridge on luna, synth and Gemini
avatar_001 v015 alike, where the true models have 11.5 mm (luna) and -0.3 mm (synth, a flat face).
Tried against these numbers and dropped: moving the whole face back to the 90 / 270 deg outlines (synth 10.3 mm),
trimming the face to the outlines after the relief (synth 7.1 mm; luna 5.0 mm and a nose tip 2.2 mm short).
Keeping only the inward part of the relief: luna 4.9, synth 3.9 mm, but on v015 the hull has no nose to keep."""
import json, os, sys
from pathlib import Path
import cv2
import numpy as np
import trimesh

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'body3d')); sys.path.insert(0, os.path.join(HERE, '..', 'body3d', 'steps'))
import check_turnaround as ct
import facemask

PARTS = {'nose tip': [1], 'nose base': [2], 'bridge': [6], 'brow': [9], 'eye, outer': [33, 263], 'eye, inner': [133, 362],
         'cheek': [205, 425], 'mouth corner': [61, 291], 'lip': [0], 'chin': [152, 199]}
ALIGN_VIEWS = ('head_000deg', 'head_045deg', 'head_090deg')
HEAD_Y = 1.45                       # the outline above this height (m) is used to align the truth


def silhouette(V, F, c, shape):
    col, row = ct.camera_project(V, c)
    P = np.round(np.stack([col, row], 1)[F]).astype(np.int32)
    im = np.zeros(shape, np.uint8)
    for t in P:
        cv2.fillConvexPoly(im, t, 1)
    return im


def load_truth(path):
    """candidate (vertices, faces) of the model in the file: its largest mesh as stored, and the whole scene with
    the node transforms applied. Files differ in which of the two is the upright figure in metres"""
    scene = trimesh.load(path, force='scene', process=False)
    g = max(scene.geometry.values(), key=lambda m: len(m.vertices))
    out = [(np.asarray(g.vertices, float), np.asarray(g.faces))]
    whole = scene.to_geometry() if hasattr(scene, 'to_geometry') else scene.dump(concatenate=True)
    out.append((np.asarray(whole.vertices, float), np.asarray(whole.faces)))
    return [(V, F) for V, F in out if 1.0 < np.ptp(V[:, 1]) < 2.5 and np.ptp(V[:, 1]) > np.ptp(V[:, 2])]


def align(V, F, work, cams, recon):
    """the truth in the reconstruction's frame: its height, then the offset at which its outline fits the head
    close-ups' masks best (the arms may be posed differently; only the head is compared). Returns vertices, misfit %"""
    V = V * (recon[:, 1].max() / V[:, 1].max())
    head = F[(V[F][:, :, 1] > HEAD_Y - 0.05).any(1)]
    masks = {n: facemask.trunk(cv2.imread(str(work / f'mask_{n}.png'), 0), cams[n]['s']) for n in ALIGN_VIEWS}

    def misfit(X):
        tot = 0
        for n, m in masks.items():
            c = cams[n]; r = silhouette(X, head, c, m.shape); cut = int(c['cv'] - c['s'] * HEAD_Y)
            a, b = m[:cut], r[:cut]
            tot += ((b & (1 - a)).sum() + (a & (1 - b)).sum()) / a.sum()
        return 100 * tot / len(masks)
    hr = recon[recon[:, 1] > HEAD_Y]; best = None
    for flip in (1, -1):                                   # the file may face the other way
        X = V * np.array([flip, 1, flip]); ht = X[X[:, 1] > HEAD_Y]
        X = X + np.array([hr[:, 0].mean() - ht[:, 0].mean(), 0, (hr[:, 2].min() + hr[:, 2].max() - ht[:, 2].min() - ht[:, 2].max()) / 2])
        s = misfit(X)
        if best is None or s < best[0]:
            best = (s, X)
    s, X = best
    for step in (0.004, 0.002, 0.001):
        moved = True
        while moved:
            moved = False
            for d in np.vstack([np.eye(3), -np.eye(3)]) * step:
                s2 = misfit(X + d)
                if s2 < s - 1e-4:
                    s, X, moved = s2, X + d, True
    return X, s


def landmark_depth(V, F, cam, lm):
    """depth (mm, along the frontal viewing direction) of the surface under each frontal landmark"""
    V = np.asarray(V, np.float32)
    tri = V[F[(V[F][:, :, 1] >= 1.36).any(1)]]
    f0 = ct.camera_axes(cam['phi'], cam['th'])[2]
    return ct.surface_landmarks(tri, cam, lm)[0] @ f0 * 1000


def compare(truth, work, meshes=('body33s_noface.ply', 'body33s.ply')):
    work = Path(work); cams = json.load(open(work / 'cams33.json')); fc = cams['head_000deg']
    lm = np.load(work / 'face_lm33.npy')[:468, :2]
    recon = np.asarray(trimesh.load(work / meshes[0], process=False).vertices)
    fits = [(align(V, F, work, cams, recon), F) for V, F in load_truth(truth)]
    if not fits:
        raise SystemExit(f'{truth}: no upright figure of 1-2.5 m found')
    (Vt, misfit), Ft = min(fits, key=lambda f: f[0][1])
    zt = landmark_depth(Vt, Ft, fc, lm)
    out = {'misfit': misfit, 'truth': {k: float(np.nanmean(zt[v]) - zt[6]) for k, v in PARTS.items()}, 'meshes': {}}
    for name in meshes:
        m = trimesh.load(work / name, process=False)
        e = landmark_depth(m.vertices, np.asarray(m.faces), fc, lm) - zt; ok = np.isfinite(e)
        out['meshes'][name] = {'mean': float(np.abs(e[ok]).mean()), 'p90': float(np.percentile(np.abs(e[ok]), 90)),
                               'median': float(np.median(e[ok])), 'parts': {k: float(np.nanmean(e[v])) for k, v in PARTS.items()}}
    return out


if __name__ == '__main__':
    res = compare(sys.argv[1], sys.argv[2], tuple(sys.argv[3:]) or ('body33s_noface.ply', 'body33s.ply'))
    print('truth aligned to the head close-ups: outlines differ by %.2f %% of the head' % res['misfit'])
    print('%-24s' % 'mm' + ''.join('%13s' % k for k in PARTS) + '   median  mean|e|   p90|e|')
    print('%-24s' % 'truth, from the bridge' + ''.join('%+13.1f' % v for v in res['truth'].values()))
    for name, r in res['meshes'].items():
        print('%-24s' % (name + ' - truth') + ''.join('%+13.1f' % v for v in r['parts'].values())
              + '   %+6.1f   %6.1f   %6.1f' % (r['median'], r['mean'], r['p90']))
