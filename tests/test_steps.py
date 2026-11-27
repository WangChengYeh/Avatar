"""reconstruction steps on small made-up shapes (no photos, no Blender): round33 keeps a thin forefoot, legs33 carves
the torso's depth with the two level side views"""
import json
import os
import sys

import cv2
import numpy as np

from conftest import PKG, run_py

sys.path.insert(0, os.path.join(PKG, 'steps'))
import camera

VS = 0.004
GRID = dict(vs=VS, x0=-0.898, y0=0.002, z0=-0.378)
SHAPE = (450, 430, 190)


def axes():
    return (GRID['x0'] + np.arange(SHAPE[0]) * VS, GRID['y0'] + np.arange(SHAPE[1]) * VS,
            GRID['z0'] + np.arange(SHAPE[2]) * VS)


def box(occ, x, y, z):
    xs, ys, zs = axes()
    occ[np.ix_((xs >= x[0]) & (xs < x[1]), (ys >= y[0]) & (ys < y[1]), (zs >= z[0]) & (zs < z[1]))] = True


def person():
    occ = np.zeros(SHAPE, bool)
    for sx in (-1, 1):
        box(occ, sorted((sx * 0.04, sx * 0.16)), (0.0, 0.80), (-0.06, 0.06))       # legs
    box(occ, (-0.16, 0.16), (0.80, 1.40), (-0.10, 0.10))                            # hips and torso, 20 cm deep
    box(occ, (-0.07, 0.07), (1.40, 1.64), (-0.09, 0.09))                            # head
    return occ


def test_round_keeps_a_thin_forefoot(tmp_path):
    """Gemini avatar_001 v010: the photos left the forefoot about 2 cm thick; the 28 mm opening ball removed it and
    the model stood on ankle stubs (21.6 -> 12.8 cm). Under 10 cm the ball is 1 voxel"""
    occ = person()
    for sx in (-1, 1):
        box(occ, sorted((sx * 0.05, sx * 0.15)), (0.0, 0.020), (0.06, 0.17))        # forefoot: 2 cm thick, 11 cm long
    json.dump(GRID, open(tmp_path / 'grid33.json', 'w'))
    np.save(tmp_path / 'in.npy', occ)
    rc, out = run_py('steps/round33.py', 'in.npy', 'out.npy', 3, cwd=tmp_path)
    assert rc == 0, out
    res = np.load(tmp_path / 'out.npy')
    _, ys, zs = axes()
    z = zs[np.flatnonzero(res[:, ys < 0.08, :].any((0, 1)))]
    assert z.max() > 0.16, f'forefoot cut back to {z.max():.3f} m'
    assert res[:, ys > 0.5, :].sum() <= occ[:, ys > 0.5, :].sum()                   # the rest is still only opened


def test_legs_carves_the_torso_depth_with_the_level_side_views(tmp_path):
    """Gemini avatar_001 v010: level side photos 23.5 / 23.8 cm at the bust, hull 26.4 cm (the tilted side views are
    drawn thicker and outvote them). What both level side views see outside goes; what one of them shows stays"""
    true = person()
    cams = {}
    for i, a in enumerate(range(0, 360, 45)):
        n = f'{i + 1:02d}_{a:03d}deg'
        cams[n] = dict(phi=float(a), th=0.0, s=1049.7, cu=1024.0, cv=1890.0, kind='main')
    xs, ys, zs = axes()
    I, J, K = np.nonzero(true)
    P = np.c_[xs[I], ys[J], zs[K]]
    k = np.ones((2 * int(np.ceil(VS * 1049.7)) + 1,) * 2, np.uint8)
    for n, c in cams.items():
        m = np.zeros((2048, 2048), np.uint8)
        u, v = camera.project(P, c)
        m[np.round(v).astype(int), np.round(u).astype(int)] = 255
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, k)
        if n.endswith('270deg'):                           # this side photo shows the back 1 cm fuller
            fat = true.copy(); box(fat, (-0.16, 0.16), (1.00, 1.30), (-0.11, -0.10))
            a_, b_, c_ = np.nonzero(fat); u, v = camera.project(np.c_[xs[a_], ys[b_], zs[c_]], c)
            m[:] = 0; m[np.round(v).astype(int), np.round(u).astype(int)] = 255
            m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, k)
        cv2.imwrite(str(tmp_path / f'mask_{n}.png'), m)
    hull = true.copy()
    box(hull, (-0.16, 0.16), (1.00, 1.30), (0.10, 0.13))   # 3 cm too deep in front: no level side view shows it
    box(hull, (-0.16, 0.16), (1.00, 1.30), (-0.11, -0.10))  # 1 cm at the back: the 270° photo shows it
    json.dump(GRID, open(tmp_path / 'grid33.json', 'w')); json.dump(cams, open(tmp_path / 'cams33.json', 'w'))
    np.save(tmp_path / 'in.npy', hull)
    rc, out = run_py('steps/legs33.py', 'in.npy', 'out.npy', cwd=tmp_path)
    assert rc == 0 and 'torso' in out, out
    res = np.load(tmp_path / 'out.npy')
    band = (ys > 1.05) & (ys < 1.25)
    front = res[:, band, :][:, :, zs > 0.112].sum(); back = res[:, band, :][:, :, zs < -0.102].sum()
    assert front == 0, f'{front} voxels of the extra front left'
    assert back > 0, 'the back that one level side photo shows was carved'


def _face_landmarks():
    """468 made-up landmarks in a 2048 px close-up: the outline on an ellipse (143 x 165 mm at 4199 px/m), the
    features (brows, eyes, nose, lips) inside the part of the face they occupy on a person"""
    import facemask
    rng = np.random.default_rng(1)
    cx, cy, a, b = 1024.0, 1000.0, 300.0, 346.0
    ang = rng.uniform(0, 2 * np.pi, 468)
    lm = np.c_[cx + a * np.cos(ang), cy + b * np.sin(ang)]
    f = np.array(facemask.FEATURE_IDX)
    lm[f] = np.c_[cx + rng.uniform(-200, 200, len(f)), cy + rng.uniform(-150, 190, len(f))]
    lm[[70, 300, 291, 61, 17]] = [[cx - 245, cy - 150], [cx + 245, cy - 150], [cx + 105, cy + 150], [cx - 105, cy + 150],
                                  [cx, cy + 190]]                              # brow tails, mouth corners, lower lip
    return lm, (cx, cy, a, b)


def test_face_owner_mask_is_whole_on_the_features_and_fades_to_the_outline():
    """bake33: the frontal close-up alone paints the features; its share falls smoothly to nothing at the face
    outline. Before 2.28.0 the hand-over took 2-4 mm (12 px): a line down each cheek (Gemini avatar_001 v015)"""
    import facemask
    lm, (cx, cy, a, b) = _face_landmarks()
    m = facemask.owner_mask(lm, (2048, 2048), facemask.PAD * 4199)
    assert m.dtype == np.float32 and 0 <= m.min() and m.max() <= 1
    for i in facemask.FEATURE_IDX:                                             # every feature is the frontal view's
        assert m[int(lm[i, 1]), int(lm[i, 0])] > 0.999, i
    assert m[int(cy), int(cx + a + 5)] == 0 and m[int(cy - b - 5), int(cx)] == 0     # nothing outside the outline
    assert m[int(cy), int(cx + a - 3)] < 0.01                                  # and next to nothing just inside it
    row = m[int(cy + 150), int(cx + 105):int(cx + a)]                          # from a mouth corner out over the cheek
    assert row[0] > 0.999 and row[-1] < 0.05
    assert (np.diff(row.astype(float)) <= 1e-6).all(), 'the share only falls on the way out'
    step = np.abs(np.diff(row.astype(float))).max()
    assert step < 0.03, f'largest change between neighbouring pixels {step:.3f}: the hand-over is a line again'
    band = ((row > 0.1) & (row < 0.9)).sum() / 4.199                           # mm
    assert band > 10, f'hand-over band on the cheek {band:.1f} mm'


def test_face_owner_mask_without_the_468_point_mesh():
    """fewer landmarks (another detector): the middle of the outline stands in for the features"""
    import facemask
    ang = np.linspace(0, 2 * np.pi, 40, endpoint=False)
    lm = np.c_[1024 + 300 * np.cos(ang), 1000 + 346 * np.sin(ang)]
    m = facemask.owner_mask(lm, (2048, 2048), 17)
    assert m[1000, 1024] > 0.999 and m[1000, 1024 + 305] == 0 and 0.05 < m[1000, 1024 + 200] < 0.95
