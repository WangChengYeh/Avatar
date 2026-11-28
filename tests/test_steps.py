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


def _head_with_an_earring(scale=4199.0):
    """a close-up's head mask (2048 px): an ellipse, an ear joined along its long side, and an earring on a thread"""
    m = np.zeros((2048, 2048), np.uint8)
    cv2.ellipse(m, (1024, 1000), (330, 420), 0, 0, 360, 1, -1)
    ear = np.zeros_like(m); cv2.ellipse(ear, (1024 + 335, 1000), (38, 110), 0, 0, 360, 1, -1)       # 9 mm out, 52 mm tall
    ring = np.zeros_like(m)
    cv2.line(ring, (1024 + 340, 1100), (1024 + 350, 1290), 1, int(round(0.002 * scale)))            # thread, 2 mm
    cv2.ellipse(ring, (1024 + 352, 1330), (int(0.004 * scale), int(0.011 * scale)), 0, 0, 360, 1, -1)   # drop, 8 mm wide
    return m, ear, ring


def test_head_outline_drops_what_hangs_by_a_thin_neck():
    """headsil33 carves the head to the close-ups' outlines. An earring in the outline is carved into the jaw: Gemini
    avatar_001 v015's frontal close-up was 157 mm wide at the jaw with its earrings, 131 mm without"""
    import facemask
    head, ear, ring = _head_with_an_earring()
    full = head | ear | ring
    out = facemask.trunk(full, 4199.0)
    assert out.dtype == np.uint8 and set(np.unique(out)) <= {0, 1}
    assert not (out & ~full.astype(bool)).any(), 'the outline only loses pixels'
    hang = (ring > 0) & (head == 0) & (ear == 0)
    below_ear = hang & (np.arange(2048)[:, None] > 1125)                         # clear of where the thread leaves the ear
    assert out[below_ear].mean() < 0.02, f'{out[below_ear].mean():.0%} of the earring is still part of the head'
    assert out[head > 0].mean() > 0.999, 'the head itself was cut'
    assert out[(ear > 0) & (head == 0) & (ring == 0)].mean() > 0.97, 'the ear was cut: it joins the head along its long side'
    row = 1330                                                                   # the drop's row: the jaw is the head's width again
    assert np.flatnonzero(out[row]).max() == np.flatnonzero(head[row]).max()


def test_head_outline_keeps_a_nose_tip():
    """a profile: the tip of the nose is rounder than a strand of hair and stays within 1 mm"""
    import facemask
    m = np.zeros((2048, 2048), np.uint8)
    cv2.ellipse(m, (1100, 1000), (380, 430), 0, 0, 360, 1, -1)
    tip = (1100 - 380 - 95, 1060)                                                # a nose 23 mm out, tip radius 6 mm
    cv2.fillConvexPoly(m, np.array([(1100 - 360, 930), (1100 - 360, 1130), (tip[0] + 20, tip[1] + 22), (tip[0] + 20, tip[1] - 22)]), 1)
    cv2.circle(m, (tip[0] + 25, tip[1]), 25, 1, -1)
    out = facemask.trunk(m, 4199.0)
    lost = (np.flatnonzero(out[tip[1]]).min() - np.flatnonzero(m[tip[1]]).min()) / 4.199
    assert lost < 1.0, f'the nose tip lost {lost:.1f} mm'


def _ball_head(bump=0.0):
    import trimesh
    ball = trimesh.creation.icosphere(subdivisions=5, radius=0.09)      # edges of 3 mm, as on the head
    V = np.asarray(ball.vertices, float); n = V / 0.09
    V = V + np.array([0, 0, 1.0]) * (bump * np.clip((n[:, 2] - 0.6) / 0.4, 0, 1) ** 2)[:, None]    # a bulge on the face
    return V + np.array([0, 1.55, 0.0]), np.asarray(ball.faces)


def _ball_cams(size=512, s=1000.0):
    cams, sdf = {}, {}
    for a in range(0, 360, 45):
        r, u, _ = camera.axes(float(a), 0.0); c0 = np.array([0, 1.55, 0.0])
        cams[f'head_{a:03d}deg'] = dict(phi=float(a), th=0.0, s=s, cu=size / 2 - s * (c0 @ r), cv=size / 2 + s * (c0 @ u), kind='head')
        m = np.zeros((size, size), np.uint8); cv2.circle(m, (size // 2, size // 2), int(0.09 * s), 1, -1)
        sdf[f'head_{a:03d}deg'] = (cv2.distanceTransform(1 - m, cv2.DIST_L2, 5) - cv2.distanceTransform(m, cv2.DIST_L2, 5)).astype(np.float32)
    return cams, sdf


def test_trim_brings_a_head_that_stands_out_of_the_side_outlines_back():
    """headsil33: where the hull is fuller than the close-ups' outlines it is moved inside them. A ball with a 15 mm
    bulge on its front, outlines of the ball alone"""
    import headsil33
    V, F = _ball_head(bump=0.015)
    cams, sdf = _ball_cams()
    front = lambda X: (X[:, 2].max() - 0.09) * 1000                             # mm in front of the ball, seen from the side
    assert 14 < front(V) < 16
    X = headsil33.trim(V, F, cams, sdf, tag='test')
    assert front(X) < 4.0, f'the bulge still stands {front(X):.1f} mm in front of the side outlines'
    back = V[:, 2] < 0
    assert np.linalg.norm(X - V, axis=1)[back].max() < 0.004, 'the back of the head moved with the face'
    assert (np.linalg.norm(X - np.array([0, 1.55, 0]), axis=1) > 0.080).all(), 'trimmed far inside the outlines'


def test_trim_leaves_a_head_inside_its_outlines_alone():
    import headsil33
    V, F = _ball_head()
    cams, sdf = _ball_cams()
    X = headsil33.trim(V, F, cams, sdf, tag='test')
    assert np.linalg.norm(X - V, axis=1).max() < 0.001


def test_close_up_gives_no_colour_where_an_earring_hangs():
    """bake33: a pale, colourless patch at the outline (an earring, the matte's white fringe) is not the head's
    colour. Baked, the frontal close-up's earrings landed on the jaw as white patches (Gemini avatar_001 v018).
    Teeth and the whites of the eyes are pale too, but not next to the background, and stay"""
    import facemask
    head, ear, ring = _head_with_an_earring()
    drop = np.zeros_like(head); cv2.ellipse(drop, (1024 + 345, 1250), (30, 90), 0, 0, 360, 1, -1)     # a tassel, 14 mm wide
    m = head | ear | drop
    im = np.full((2048, 2048, 3), 255, np.uint8)
    im[m > 0] = (140, 170, 215)                                                # skin (BGR)
    im[(drop > 0) & (head == 0)] = (236, 238, 240)                             # the tassel: nearly white
    teeth = np.zeros_like(head); cv2.ellipse(teeth, (1024, 1180), (60, 14), 0, 0, 360, 1, -1)
    im[teeth > 0] = (232, 236, 240)
    out = facemask.solid(m, im, 4199.0)
    tassel = (drop > 0) & (head == 0) & (ear == 0)
    assert out[tassel].mean() < 0.05, f'{out[tassel].mean():.0%} of the earring still gives colour'
    assert out[teeth > 0].all(), 'the teeth were taken for an earring'
    inner = cv2.erode(head, np.ones((61, 61), np.uint8)) > 0
    assert out[inner].all(), 'skin inside the head was dropped'


def test_head_grows_out_to_a_bun_the_hull_lost():
    """headsil33, 2.33.0: where the close-ups' outlines lie outside the mesh, the mesh grows out to them. Gemini
    avatar_001 v015: the full-body photos carved the bun into a cone and the head could only be trimmed further.
    A ball whose close-ups all show a bun behind it"""
    import headsil33
    V, F = _ball_head()
    cams, _ = _ball_cams()
    bun = np.array([0, 1.55, -0.095]); size, sdf = 512, {}
    for n, c in cams.items():
        m = np.zeros((size, size), np.uint8)
        cv2.circle(m, (size // 2, size // 2), int(0.09 * c['s']), 1, -1)
        col, row = camera.project(bun[None], c)
        cv2.circle(m, (int(round(col[0])), int(round(row[0]))), int(0.045 * c['s']), 1, -1)
        sdf[n] = (cv2.distanceTransform(1 - m, cv2.DIST_L2, 5) - cv2.distanceTransform(m, cv2.DIST_L2, 5)).astype(np.float32)
    back = lambda X: (-X[:, 2].min() - 0.09) * 1000                             # mm behind the ball
    assert back(V) < 0.5
    same = headsil33.trim(V, F, cams, sdf, tag='test')                          # trimming alone cannot bring it back
    assert back(same) < 0.5
    X = headsil33.trim(V, F, cams, sdf, tag='test', iters=headsil33.GROW_ITERS, grow=True)
    assert back(X) > 25, f'the bun reaches {back(X):.0f} mm behind the head; the close-ups show 50'
    front = V[:, 2] > 0.03
    assert np.linalg.norm(X - V, axis=1)[front].max() < 0.006, 'the face moved with the bun (more than a tenth of it)'
    for n, c in cams.items():                                                   # and nothing grew past an outline
        col, row = camera.project(X, c)
        sd = sdf[n][np.clip(np.round(row).astype(int), 0, size - 1), np.clip(np.round(col).astype(int), 0, size - 1)] / c['s']
        assert sd.max() < 0.006, f'{n}: {1000 * sd.max():.1f} mm outside the outline'


def _post(radius, n=96, levels=41):
    """an upright round post (vertices, outward normals, triangles), 0.4 m to 1.4 m"""
    a = np.linspace(0, 2 * np.pi, n, endpoint=False); y = np.linspace(0.4, 1.4, levels)
    N = np.stack([np.sin(a), np.zeros(n), np.cos(a)], 1)
    V = np.concatenate([np.c_[radius * N[:, 0], np.full(n, h), radius * N[:, 2]] for h in y])
    T = []
    for j in range(levels - 1):
        for i in range(n):
            p, q = j * n + i, j * n + (i + 1) % n
            T += [(p, q, p + n), (q, q + n, p + n)]
    return V, np.tile(N, (levels, 1)), np.array(T)


def _post_photos(level_radius, tilted_radius, size=1024, s=800.0):
    """cameras and outlines of a post seen by a level ring and a ring 30° up; the two rings may disagree on its width"""
    import silfit
    cams, sdf = {}, {}
    for kind, th, radius in (('main', 0.0, level_radius), ('el30', 30.0, tilted_radius)):
        V, _, T = _post(radius)
        for phi in range(0, 360, 45):
            n = f'{kind}_{phi:03d}deg'
            cams[n] = dict(phi=float(phi), th=th, s=s, cu=size / 2, cv=size / 2 + s * 0.9 * np.cos(np.radians(th)), kind=kind)
            col, row = camera.project(V, cams[n])
            m = np.zeros((size, size), np.uint8)
            cv2.fillPoly(m, list(np.round(np.stack([col, row], 1)[T]).astype(np.int32)), 1)
            sdf[n] = silfit.signed(m)
    return cams, sdf


def _outward(V, N, T, cams, sdf):
    """mean move of the vertices in the middle of the post, along their normals, mm"""
    import silfit
    move, has = silfit.moves(V, N, T, cams, sdf)
    mid = has & (V[:, 1] > 0.7) & (V[:, 1] < 1.1)
    assert mid.sum() > 500
    return 1000 * float((move[mid] * N[mid]).sum(1).mean())


def test_outline_fit_leaves_a_body_that_matches_its_photos_alone():
    """vertices near the rim lie a little inside the model's outline; taking them to be on it pushed a body that
    already matched out by 2-3 mm per side (luna-v1: 7 mm wider than the photos, now 3)"""
    cams, sdf = _post_photos(0.10, 0.10)
    V, N, T = _post(0.10)
    assert abs(_outward(V, N, T, cams, sdf)) < 0.6


def test_outline_fit_follows_the_level_photos_when_the_tilted_ones_are_wider():
    """Gemini avatar_001: the ring 30° up drew the torso 1 cm wider per side than the level ring, and an even average
    left the body wider than every level photo. The level ring has six times the say"""
    cams, sdf = _post_photos(0.10, 0.11)
    V, N, T = _post(0.105)                                     # halfway: an even average would not move it
    move = _outward(V, N, T, cams, sdf)
    assert -5.0 < move < -2.5, move                            # toward the level photos' 0.10 (6 : 1 -> -3.6 mm)
    assert abs(_outward(*_post(0.1014), cams, sdf)) < 0.8      # and it settles near (6 x 0.10 + 0.11) / 7


def test_tilted_views_only_fill_in_what_no_level_photo_sees():
    """Gemini avatar_001: the ring 30° up painted the top of the chest half and half with the level photos and left
    a second neckline and a second strap. Their share is set by how well the best level photo faces the surface"""
    import whopaints
    share = whopaints.level_share(np.array([0.0, 0.45, 0.60, 0.75, 1.0]))
    assert share[0] == 0 and share[1] == 0          # no level photo sees it (or only at a glance): the tilted views
    assert 0.3 < share[2] < 0.7                     # the hand-over, a share of the colour and not a weight
    assert share[3] == 1 and share[4] == 1          # a level photo faces it: the tilted views have no say
    assert np.all(np.diff(whopaints.level_share(np.linspace(0, 1, 101))) >= 0)
    # on the head the close-ups paint, whatever the level full-body photos see (2.18.0: a full-body view under the lip)
    assert whopaints.level_share(np.array([0.0, 0.4]), on_head=np.array([1.0, 1.0])).tolist() == [1.0, 1.0]
    assert 0.4 < whopaints.level_share(np.array([0.0]), on_head=np.array([0.5]))[0] < 0.6


def test_a_side_view_does_not_paint_around_the_arm():
    """seen along the arm, a T-pose arm is a small disc; an AI draws the forearm and hand across the chest or the
    hip, and what lies beyond the model's own arm was painted on the torso (finger marks on the hips)"""
    import whopaints
    marks = np.zeros((200, 200), bool); marks[95:105, 95:105] = True        # the model's arm, end-on (4 px cells)
    radius = whopaints.ARM_SHADOW * 1050 / 4                                 # 10 cm at a full-body view's scale
    shadow = whopaints.arm_shadow(marks, radius)
    assert shadow[100, 100] and shadow[100, 100 + int(radius)] and shadow[100 - int(radius), 100]
    assert not shadow[100, 100 + int(radius) + 8] and not shadow[40, 40]    # the rest of the torso keeps the photo
    assert 20 < radius < 35
    assert not whopaints.arm_shadow(np.zeros((50, 50), bool), radius).any() # no arm in the picture: nothing excluded
