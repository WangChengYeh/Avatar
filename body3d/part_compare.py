"""Gate 4: where does the finished model differ from the photos, by region of the body?

Why: the final acceptance compared outlines of the whole figure in the full-body photos. The head is a few percent
of that outline and what lies inside an outline (where the hair ends and the face begins, a patch of the wrong
colour) is not in it. Gemini avatar_001 v018 passed all four gates and did not look like its photos: a jaw as wide
as the cheekbones, a bun turned into a cone, a face standing out of its profile.

What (the user's order: the difference over the whole body first, then split by joint):
1. The finished GLB is drawn with the registered camera of every level full-body photo and every head close-up
   (its own texture, no lighting).
2. The difference over the whole figure. Photo and drawing are each split into the few things the figure is made of
   (a full-body photo: hair, skin, each garment, shades of one colour being one thing; a close-up: hair and skin);
   a pixel differs where one of these lies in one picture and not, within a few pixels, in the other. So a wrong
   outline, a boundary in the wrong place and a patch of the wrong colour all count.
3. The split by joint. Every piece of the model's surface belongs to the bone of its own skeleton it lies nearest
   to: head (with the neck), torso, upper arms, forearms, hands, thighs, shins, feet. Drawn with the same camera
   this gives every pixel of the figure a region; the difference is counted per region.
Not everything at once: the report marks the few views that differ most (FIRST) as the ones to fix this round.

Calibrated on 2026-11-28 (body3d 2.34.0, both templates), the largest region in any view:
    perfect photos (luna, synth)   full-body 0.4-0.9 % of the figure   head close-ups 3-4 % of the head
    Gemini avatar_001 v015         full-body 4.0-4.7 %                 head close-ups 7-14 %
usage: python part_compare.py WORK PHOTOS MODEL.glb [--out parts_compare.jpg]"""
import json
import os
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'steps'))
import camera

# What differs inside one region of the body. Full-body photo: as a share of the whole figure, so a hand (1 % of
# the figure) that is half wrong does not outweigh a torso that is a tenth wrong. Head close-up: the head region
# alone, as a share of the head (the sliver of shoulders in the frame is not judged).
LEVEL_PASS, LEVEL_FAIL = 0.015, 0.025
HEAD_PASS, HEAD_FAIL = 0.06, 0.09
PERFECT = {'main': 0.9, 'head': 4.0}         # the largest value on perfect photos, both templates (%), for the report
COLOURS = 7                                  # colour clusters before shades are joined
SAME_HUE, SAME_LIGHT = 7.0, 60.0             # Lab a / b and L: closer than this in every pair = shades of one thing
MIN_PART = 0.02                              # smaller than this share of the figure in both pictures: not reported
MIN_REGION = 0.008                           # a region of the body smaller than this share of the figure: not judged
TOLERANCE = 9                                # px at 1024: a part's edge may sit 4 px off
FIRST = 3                                    # the parts that differ most are the ones to fix this round
HEAD_FLOOR = 1.40                            # m: a close-up is compared above the shoulders (1.65 m figure)
SIZE = 1024


def load_glb(path):
    """(vertices, faces, one BGR colour per face) of the model in the file, node transforms applied"""
    import trimesh
    scene = trimesh.load(path, force='scene', process=False)
    Vs, Fs, Cs, off = [], [], [], 0
    for m in scene.dump(concatenate=False):
        V, F = np.asarray(m.vertices, float), np.asarray(m.faces)
        mat = getattr(m.visual, 'material', None)
        img = getattr(mat, 'baseColorTexture', None) or getattr(mat, 'emissiveTexture', None) or getattr(mat, 'image', None)
        uv = getattr(m.visual, 'uv', None)
        if img is None or uv is None or len(F) < 100:
            continue                                   # helper geometry without a texture
        tex = cv2.cvtColor(np.asarray(img.convert('RGB')), cv2.COLOR_RGB2BGR); h, w = tex.shape[:2]
        c = np.asarray(uv, float)[F].mean(1)
        Cs.append(tex[np.clip(((1 - c[:, 1]) * h).astype(int), 0, h - 1), np.clip((c[:, 0] * w).astype(int), 0, w - 1)])
        Vs.append(V); Fs.append(F + off); off += len(V)
    if not Vs:
        raise ValueError(f'{path}: no textured mesh')
    return np.vstack(Vs), np.vstack(Fs), np.vstack(Cs)


# the regions of the body, from the model's own skeleton: every piece of the surface belongs to the bone it lies
# nearest to (distance over the limb's usual radius, so the side of the chest is the torso, not the upper arm)
REGIONS = (
    ('頭', 0.13, (('Neck', 'Head'), ('Head', 'HeadTop_End'))),      # with the neck: the head joint sits above the jaw
    ('軀幹', 0.16, (('Hips', 'Spine'), ('Spine', 'Spine1'), ('Spine1', 'Spine2'), ('Spine2', 'Neck'),
                  ('LeftShoulder', 'LeftArm'), ('RightShoulder', 'RightArm'), ('Hips', 'LeftUpLeg'), ('Hips', 'RightUpLeg'))),
    ('左上臂', 0.055, (('LeftArm', 'LeftForeArm'),)), ('左前臂', 0.045, (('LeftForeArm', 'LeftHand'),)),
    ('左手', 0.05, (('LeftHand', 'LeftHandEnd'), ('LeftHand', 'LeftHandMiddle4'), ('LeftHand', 'LeftHandMiddle3'))),
    ('右上臂', 0.055, (('RightArm', 'RightForeArm'),)), ('右前臂', 0.045, (('RightForeArm', 'RightHand'),)),
    ('右手', 0.05, (('RightHand', 'RightHandEnd'), ('RightHand', 'RightHandMiddle4'), ('RightHand', 'RightHandMiddle3'))),
    ('左大腿', 0.09, (('LeftUpLeg', 'LeftLeg'),)), ('左小腿', 0.06, (('LeftLeg', 'LeftFoot'),)),
    ('左腳', 0.06, (('LeftFoot', 'LeftToeBase'), ('LeftToeBase', 'LeftToeEnd'), ('LeftToeBase', 'LeftToe_End'))),
    ('右大腿', 0.09, (('RightUpLeg', 'RightLeg'),)), ('右小腿', 0.06, (('RightLeg', 'RightFoot'),)),
    ('右腳', 0.06, (('RightFoot', 'RightToeBase'), ('RightToeBase', 'RightToeEnd'), ('RightToeBase', 'RightToe_End'))),
)


def glb_joints(path):
    """{bone name: position} of the skeleton in the file, in the model's frame (rest pose)"""
    import struct
    with open(path, 'rb') as f:
        magic, _, _ = struct.unpack('<4sII', f.read(12))
        if magic != b'glTF':
            raise ValueError(f'{path}: not a GLB')
        n, kind = struct.unpack('<I4s', f.read(8))
        doc = json.loads(f.read(n))
    nodes = doc.get('nodes', [])

    def local(nd):
        if 'matrix' in nd:
            return np.array(nd['matrix'], float).reshape(4, 4).T
        M = np.eye(4)
        x, y, z, w = nd.get('rotation', (0, 0, 0, 1))
        R = np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                      [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                      [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]])
        M[:3, :3] = R * np.array(nd.get('scale', (1, 1, 1)), float)[None]
        M[:3, 3] = nd.get('translation', (0, 0, 0))
        return M
    world = {}

    def walk(i, parent):
        world[i] = parent @ local(nodes[i])
        for c in nodes[i].get('children', []):
            walk(c, world[i])
    kids = {c for nd in nodes for c in nd.get('children', [])}
    for i in range(len(nodes)):
        if i not in kids:
            walk(i, np.eye(4))
    joints = {j for sk in doc.get('skins', []) for j in sk.get('joints', [])}
    return {nodes[i].get('name', str(i)).split(':')[-1]: world[i][:3, 3] for i in joints}


def face_regions(V, F, joints):
    """the region (index into REGIONS) of every face: the bone it lies nearest to; None without a skeleton"""
    segs, owner, rad = [], [], []
    for r, (_, radius, pairs) in enumerate(REGIONS):
        for a, b in pairs:
            if a in joints and b in joints:
                segs.append((joints[a], joints[b])); owner.append(r); rad.append(radius)
    if 'Head' in joints and 'HeadTop_End' not in joints:      # no head-top bone: the head reaches up from its joint
        segs.append((joints['Head'], joints['Head'] + np.array([0, 0.18, 0.0]))); owner.append(0); rad.append(REGIONS[0][1])
    if len({*owner}) < 6:
        return None
    P = V[F].mean(1); best = np.full(len(P), np.inf); out = np.zeros(len(P), int)
    for (a, b), o, r in zip(segs, owner, rad):
        ab = b - a; t = np.clip(((P - a) @ ab) / max(ab @ ab, 1e-12), 0, 1)
        d = np.linalg.norm(P - (a + t[:, None] * ab), axis=1) / r
        m = d < best
        best[m] = d[m]; out[m] = o
    return out


def render(V, F, C, cam, size=SIZE, full=2048):
    """the model seen by a registered camera: flat face colours, far faces first. (BGR image, mask) at `size`"""
    _, _, f = camera.axes(cam['phi'], cam['th'])
    col, row = camera.project(V, cam)
    tri = V[F]
    front = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]) @ f > 0
    order = np.argsort(camera.depth(tri.mean(1), cam)); order = order[front[order]]
    P = np.round(np.stack([col, row], 1)[F] * (size / full) * 4).astype(np.int32)
    im = np.full((size, size, 3), 255, np.uint8); mk = np.zeros((size, size), np.uint8)
    for i in order:
        cv2.fillConvexPoly(im, P[i], C[i].tolist(), shift=2); cv2.fillConvexPoly(mk, P[i], 1, shift=2)
    return im, mk > 0


def _feature(im):
    lab = cv2.cvtColor(cv2.GaussianBlur(im, (0, 0), 1.5), cv2.COLOR_BGR2LAB).astype(np.float32)
    return np.stack([0.5 * lab[..., 0], lab[..., 1], lab[..., 2]], -1)        # lightness counts half: light varies


def families(centres):
    """colour clusters -> family index each. Two groups are joined only while every pair in the joined group
    differs in lightness alone and by less than SAME_LIGHT: light and shade of one thing. Dark hair and fair skin
    of about the same hue are not chained together through a middle shade"""
    k = len(centres); L = centres[:, 0] * 2
    close = lambda i, j: (abs(centres[i, 1] - centres[j, 1]) < SAME_HUE and abs(centres[i, 2] - centres[j, 2]) < SAME_HUE
                          and abs(L[i] - L[j]) < SAME_LIGHT)
    groups = [[i] for i in range(k)]
    while True:
        best = None
        for x in range(len(groups)):
            for y in range(x + 1, len(groups)):
                if all(close(i, j) for i in groups[x] for j in groups[y]):
                    d = max(abs(L[i] - L[j]) for i in groups[x] for j in groups[y])
                    if best is None or d < best[0]:
                        best = (d, x, y)
        if best is None:
            break
        _, x, y = best
        groups[x] += groups[y]; del groups[y]
    fam = np.zeros(k, int)
    for n, g in enumerate(sorted(groups, key=min)):
        fam[g] = n
    return fam


def palette(pictures, seed=3, colours=COLOURS):
    """the figure's colours: (cluster centres, family per cluster). pictures: [(BGR image, mask)].
    colours = 2: a head, its dark and its light part (hair, skin), darker first, no joining"""
    rng = np.random.default_rng(seed); X = []
    for im, m in pictures:
        m = cv2.erode(m.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
        f = _feature(im)[m]
        if len(f):
            X.append(f[rng.choice(len(f), min(len(f), 15000), replace=False)])
    X = np.vstack(X).astype(np.float32)
    cv2.setRNGSeed(seed)
    _, _, cen = cv2.kmeans(X, min(colours, len(X)), None, (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 60, 0.2),
                           5, cv2.KMEANS_PP_CENTERS)
    if colours == 2:
        cen = cen[np.argsort(cen[:, 0])]
        return cen, np.arange(len(cen))
    return cen, families(cen)


def parts(im, mask, cen, fam):
    """label picture: 0 = background, 1.. = family + 1"""
    f = _feature(im)
    L = fam[((f[:, :, None, :] - cen[None, None]) ** 2).sum(-1).argmin(-1)]
    L = cv2.medianBlur(L.astype(np.uint8) + 1, 7)
    L[~mask] = 0
    return L


def unmatched(a, b, tol=TOLERANCE):
    """mask: pixels of a part that lie farther than tol / 2 px from the same part in the other picture, both ways"""
    k = np.ones((tol, tol), np.uint8)
    return (a & (cv2.dilate(b.astype(np.uint8), k) == 0)) | (b & (cv2.dilate(a.astype(np.uint8), k) == 0))


def region_map(V, F, region, cam, photo, model, full):
    """every pixel of the figure (photo or model) -> the region of the body it belongs to, 1.. (0 = background).
    The model's regions are drawn with the camera; a pixel only the photo has takes the nearest region"""
    fig = photo | model
    if region is None:
        return fig.astype(np.uint8)
    lut = np.stack([np.arange(1, len(REGIONS) + 1)] * 3, 1).astype(np.uint8)
    im, mk = render(V, F, lut[region], cam, photo.shape[0], full)
    R = np.where(mk, im[..., 0], 0).astype(np.uint8)
    _, lb = cv2.distanceTransformWithLabels((R == 0).astype(np.uint8), cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL)
    ys, xs = np.nonzero(R); src = np.zeros(lb.max() + 1, np.uint8); src[lb[ys, xs]] = R[ys, xs]
    return np.where(fig, np.where(R > 0, R, src[lb]), 0).astype(np.uint8)


def differs(a, b, tol=TOLERANCE):
    """pixels of a part that lie farther than tol / 2 px from the same part in the other picture, both ways"""
    k = np.ones((tol, tol), np.uint8)
    return int((a & (cv2.dilate(b.astype(np.uint8), k) == 0)).sum() + (b & (cv2.dilate(a.astype(np.uint8), k) == 0)).sum())


def names(cen, fam, front_head, back_head, front_body):
    """a word for every family: the skin (middle of the face in the frontal close-up), the hair (upper back of the
    head in the back close-up), garments by where they sit in the frontal full-body photo. label pictures in"""
    n = fam.max() + 1; out = {}

    def most(L, rows, cols, skip=()):
        ys, xs = np.nonzero(L)
        if not len(ys):
            return None
        y0, y1, x0, x1 = ys.min(), ys.max(), xs.min(), xs.max()
        box = L[int(y0 + rows[0] * (y1 - y0)):int(y0 + rows[1] * (y1 - y0)), int(x0 + cols[0] * (x1 - x0)):int(x0 + cols[1] * (x1 - x0))]
        cnt = np.bincount(box[box > 0], minlength=n + 1)
        for s in skip:
            cnt[s + 1] = 0
        return int(cnt.argmax()) - 1 if cnt.sum() else None
    skin = most(front_head, (0.45, 0.75), (0.35, 0.65)) if front_head is not None else None
    hair = most(back_head, (0.05, 0.45), (0.25, 0.75), skip=() if skin is None else (skin,)) if back_head is not None else None
    if skin is not None:
        out[skin] = '皮膚'
    if hair is not None:
        out[hair] = '頭髮'
    ys = np.nonzero(front_body.any(1))[0] if front_body is not None else []
    used = {}
    for k in range(n):
        if k in out:
            continue
        # a shade between the hair's and the skin's colour (the shadow under the chin, a highlight in the hair)
        near = [j for j in (skin, hair) if j is not None and
                np.abs(cen[fam == k][:, 1:].mean(0) - cen[fam == j][:, 1:].mean(0)).max() < 1.5 * SAME_HUE]
        where = None
        if len(ys):
            r = np.nonzero((front_body == k + 1).any(1))[0]
            where = (r.mean() - ys[0]) / max(1, ys[-1] - ys[0]) if len(r) else None
        if near and (where is None or (front_body == k + 1).sum() < 0.03 * (front_body > 0).sum()):
            base = '膚色與髮色之間的顏色'
        elif where is None:
            base = '其他顏色'
        else:
            base = '上身的衣物' if where < 0.40 else '下身的衣物'          # the waist is about 0.4 of the height down
        used[base] = used.get(base, 0) + 1
        out[k] = base if used[base] == 1 else f'{base} {used[base]}'
    return [out[k] for k in range(n)]


def compare(work, photos, glb, picture=None):
    """{'parts': [names], 'views': [{view, kind, level, worst, parts: {name: (photo %, model %, differs %)}}], 'level'}"""
    cams = json.load(open(os.path.join(work, 'cams33.json')))
    views = [n for n, c in sorted(cams.items()) if c.get('kind') in ('main', 'head')]
    V, F, C = load_glb(glb)
    shots = {}
    for n in views:
        im = cv2.imread(os.path.join(photos, n + '.jpg')); m = cv2.imread(os.path.join(work, f'mask_{n}.png'), 0)
        if im is None or m is None:
            continue
        full = m.shape[0]
        ph = cv2.resize(im, (SIZE, SIZE), interpolation=cv2.INTER_AREA)
        pm = cv2.resize(m, (SIZE, SIZE), interpolation=cv2.INTER_NEAREST) > 0
        rim, rm = render(V, F, C, cams[n], SIZE, full)
        if cams[n].get('kind') == 'head':              # the head and neck: above the shoulders
            cut = int((cams[n]['cv'] - cams[n]['s'] * HEAD_FLOOR) * SIZE / full)
            pm[max(cut, 0):] = False; rm[max(cut, 0):] = False
        shots[n] = (ph, pm, rim, rm)
    if not shots:
        return dict(parts=[], views=[], level='PASS')
    kind = lambda n: 'head' if cams[n].get('kind') == 'head' else 'main'
    pal, lab, nm, diffmaps = {}, {}, {}, {}
    for k in ('main', 'head'):
        mine = [n for n in shots if kind(n) == k]
        if not mine:
            continue
        pal[k] = palette([(shots[n][0], shots[n][1]) for n in mine], colours=2 if k == 'head' else COLOURS)
        for n in mine:
            lab[n] = (parts(shots[n][0], shots[n][1], *pal[k]), parts(shots[n][2], shots[n][3], *pal[k]))
    pick = lambda tag: next((lab[n][0] for n in shots if kind(n) == 'main' and tag in n), None)
    if 'main' in pal:                                  # the skin and the hair of the full-body photos: where the
        front = pick('_000deg'); back = pick('_180deg')    # head is (the top 13 % of the figure)
        top = lambda L: None if L is None else np.where(np.arange(L.shape[0])[:, None] < np.nonzero(L.any(1))[0][0] + 0.13 * np.ptp(np.nonzero(L.any(1))[0]), L, 0)
        nm['main'] = names(pal['main'][0], pal['main'][1], top(front), top(back), front)
    if 'head' in pal:
        nm['head'] = ['頭髮', '皮膚'][:len(pal['head'][0])]
    try:
        region = face_regions(V, F, glb_joints(glb))
    except Exception:                                  # a model without a readable skeleton: one region, the figure
        region = None
    rows = []
    for n, (Lp, Lr) in lab.items():
        head = kind(n) == 'head'
        tot = max(1, int((Lp > 0).sum()))
        # 1. the difference over the whole figure: where a part lies in one picture and not in the other
        bad = np.zeros(Lp.shape, bool); by_part = {}
        for k, word in enumerate(nm[kind(n)]):
            a, b = Lp == k + 1, Lr == k + 1
            if a.sum() < MIN_PART * tot and b.sum() < MIN_PART * tot:
                continue
            d = unmatched(a, b)
            bad |= d; by_part[word] = d
        bad = cv2.morphologyEx(bad.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8)) > 0
        # 2. split by the regions of the body the model's joints give
        full = cv2.imread(os.path.join(work, f'mask_{n}.png'), 0).shape[0]
        R = region_map(V, F, region, cams[n], Lp > 0, shots[n][3], full)
        row = {}
        for r in range(1, int(R.max()) + 1):
            area = int((R == r).sum())
            if area < MIN_REGION * tot:
                continue
            d = bad & (R == r)
            main = max(by_part, key=lambda w: int((by_part[w] & d).sum())) if by_part and d.any() else ''
            # (the region's share of the figure, the share of the region that differs, the part that differs most,
            #  that difference as a share of the figure)
            row[REGIONS[r - 1][0] if region is not None else '全身'] = (100 * area / tot, 100 * d.sum() / area, main,
                                                                    100 * d.sum() / tot)
        judged = {k: (v[1] if head else v[3]) for k, v in row.items() if not head or k in ('頭', '全身')}
        worst = max(judged.items(), key=lambda kv: kv[1]) if judged else ('', 0.0)
        lo, hi = (HEAD_PASS, HEAD_FAIL) if head else (LEVEL_PASS, LEVEL_FAIL)
        level = 'FAIL' if worst[1] > 100 * hi else 'WARN' if worst[1] > 100 * lo else 'PASS'
        rows.append(dict(view=n, kind='head' if head else 'main', level=level, worst=worst[0], value=round(float(worst[1]), 2),
                         differs=round(100 * bad.sum() / tot, 2),
                         regions={k: [round(float(v[0]), 1), round(float(v[1]), 1), v[2], round(float(v[3]), 2)]
                                  for k, v in row.items()}))
        diffmaps[n] = (bad, R)
    # what to fix this round: the few that differ most, measured against their own limit (a close-up's parts are
    # larger shares of a smaller figure)
    over = sorted(((r['value'] / (100 * (HEAD_FAIL if r['kind'] == 'head' else LEVEL_FAIL)), r['view'])
                   for r in rows if r['level'] == 'FAIL'), reverse=True)
    first = [v for _, v in over[:FIRST]]
    for r in rows:
        r['first'] = r['view'] in first
    level = 'FAIL' if any(r['level'] == 'FAIL' for r in rows) else 'WARN' if any(r['level'] == 'WARN' for r in rows) else 'PASS'
    if picture:
        draw(picture, rows, shots, lab, pal, kind, diffmaps)
    return dict(parts=sorted({w for v in nm.values() for w in v}), views=rows, level=level, first=first)


def draw(path, rows, shots, lab, pals, kind, diffmaps, most=6):
    """the views to fix first, then the ones that differ most: photo, the model, and where they differ (red) over
    the regions of the body (their borders in grey)"""
    limit = lambda r: 100 * (HEAD_FAIL if r['kind'] == 'head' else LEVEL_FAIL)
    order = sorted(rows, key=lambda r: (not r.get('first'), -r['value'] / limit(r)))[:most]
    tiles = []
    for r in order:
        ph, pm, rim, rm = shots[r['view']]; bad, R = diffmaps[r['view']]
        ys, xs = np.nonzero(pm | rm)
        y0, y1, x0, x1 = max(ys.min() - 20, 0), min(ys.max() + 20, SIZE), max(xs.min() - 20, 0), min(xs.max() + 20, SIZE)
        edge = cv2.morphologyEx(R, cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8)) > 0
        cells = []
        for pic in (ph, rim):
            cells.append(pic); marked = (0.45 * pic + 140).clip(0, 255).astype(np.uint8)
            marked[~(pm | rm)] = 255; marked[edge] = (150, 150, 150); marked[bad] = (40, 40, 230)
            cells.append(marked)
        out = []
        for c in (cells[0], cells[2], cells[1]):          # photo, model, the difference by region
            c = c[y0:y1, x0:x1]; f = 420 / max(c.shape[:2])
            c = cv2.resize(c, (max(1, int(c.shape[1] * f)), max(1, int(c.shape[0] * f))))
            pad = np.full((420, 420, 3), 255, np.uint8); pad[:c.shape[0], :c.shape[1]] = c
            out.append(pad)
        tiles.append(np.hstack(out))
    cv2.imwrite(path, np.vstack(tiles), [cv2.IMWRITE_JPEG_QUALITY, 88])


def lines(res):
    """the report lines of the acceptance: one per view; the regions of the body, most different first"""
    out = []
    for r in res['views']:
        head = r['kind'] == 'head'
        lo, hi = (HEAD_PASS, HEAD_FAIL) if head else (LEVEL_PASS, LEVEL_FAIL)
        if head:
            reg = [(k, v) for k, v in r['regions'].items() if k in ('頭', '全身')]
            txt = '、'.join(f'{k} {v[1]:.0f}%' for k, v in reg) or '沒有可比的區域'
            rule = f'頭部特寫：頭這一區對不上的比例應 ≤ {100 * lo:g}%，> {100 * hi:g}% 判 FAIL；完美照片 ≤ {PERFECT["head"]:g}%'
        else:
            reg = sorted(r['regions'].items(), key=lambda kv: -kv[1][3])
            txt = '、'.join(f'{k} {v[3]:.1f}%（該區的 {v[1]:.0f}%）' for k, v in reg[:4] if v[3] >= 0.1) or '各區都對得上'
            rule = (f'全身圖：每一區對不上的面積佔整個人物的比例應 ≤ {100 * lo:g}%，> {100 * hi:g}% 判 FAIL；'
                    f'完美照片 ≤ {PERFECT["main"]:g}%')
        msg = f'[{r["level"]}] {r["view"]} 分區差異: {txt}（整個人物有 {r["differs"]:.1f}% 對不上；{rule}）'
        if r['level'] != 'PASS':
            main = r['regions'][r['worst']][2]
            msg += f' → 成品在這個角度的「{r["worst"]}」和照片對不上' + (f'，主要是{main}' if main else '') + '。'
            if r.get('first'):
                msg += '【這一輪先修】差最多的幾個之一：看 parts_compare.jpg 最上面幾列紅色的地方'
            elif r['level'] == 'FAIL':
                msg += '這一輪先修標了【這一輪先修】的那幾個，重跑後再看這一張'
            else:
                msg += '看 parts_compare.jpg 紅色的地方'
        out.append(msg)
    return out


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(description='成品與原圖的差異，依關節分區')
    ap.add_argument('work'); ap.add_argument('photos'); ap.add_argument('glb'); ap.add_argument('--out')
    a = ap.parse_args()
    res = compare(a.work, a.photos, a.glb, a.out)
    print('分成：' + '、'.join(res['parts']))
    print('\n'.join(lines(res)))
    if res.get('first'):
        print('這一輪先修：' + '、'.join(res['first']))
    sys.exit(1 if res['level'] == 'FAIL' else 0)
