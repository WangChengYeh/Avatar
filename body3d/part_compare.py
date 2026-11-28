"""Gate 4, part by part: does the finished model look like the photos, piece by piece?

Why: the final acceptance compared outlines of the whole figure in the full-body photos. The head is a few percent
of that outline and what lies inside an outline (where the hair ends and the face begins, a patch of the wrong
colour) is not in it. Gemini avatar_001 v018 passed all four gates and did not look like its photos: a jaw as wide
as the cheekbones, a bun turned into a cone, a face standing out of its profile.

What: the finished GLB is drawn with the registered camera of every level full-body photo and every head close-up
(its own texture, no lighting). The photos' colours are grouped into the few things the figure is made of, and every
photo and its drawing are split into these parts. A full-body photo: hair, skin, each garment (shades of one colour
are one thing). A head close-up: two parts only, the dark one and the light one, hair and skin; with more, the
light in the hair came out as a part of its own or joined a garment of a similar colour, and the numbers moved
with the grouping. For each part: the area that lies in one picture and not, within a few pixels, in the other, as
a share of the figure in that photo. A part that is the wrong shape, in the wrong place or the wrong colour shows
up as that part's number, in that view.

Not everything at once: the report marks the few parts that differ most (FIRST) as the ones to fix this round.

Calibrated on 2026-11-28 (body3d 2.29.0, both templates), largest part in any view:
    perfect photos (luna, synth)   full-body 0.5-1.1 %    head close-ups 2.5-3.0 %
    Gemini avatar_001 v015 / v018  full-body 6.0-6.3 %    head close-ups 9.5-9.7 % (45 and 315 deg; 4-8 % elsewhere)
usage: python part_compare.py WORK PHOTOS MODEL.glb [--out parts_compare.jpg]"""
import json
import os
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, 'steps'))
import camera

LEVEL_PASS, LEVEL_FAIL = 0.025, 0.04         # a part's share of the figure, full-body photo
HEAD_PASS, HEAD_FAIL = 0.05, 0.08            # head close-up (the head and neck are the figure)
COLOURS = 7                                  # colour clusters before shades are joined
SAME_HUE, SAME_LIGHT = 7.0, 60.0             # Lab a / b and L: closer than this in every pair = shades of one thing
MIN_PART = 0.02                              # smaller than this share of the figure in both pictures: not reported
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
    pal, lab, nm = {}, {}, {}
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
    rows = []
    for n, (Lp, Lr) in lab.items():
        head = kind(n) == 'head'
        tot = max(1, int((Lp > 0).sum())); row = {}
        for k, word in enumerate(nm[kind(n)]):
            a, b = Lp == k + 1, Lr == k + 1
            if a.sum() < MIN_PART * tot and b.sum() < MIN_PART * tot:
                continue
            row[word] = (100 * a.sum() / tot, 100 * b.sum() / tot, 100 * differs(a, b) / tot)
        worst = max(row.items(), key=lambda kv: kv[1][2]) if row else ('', (0, 0, 0))
        lo, hi = (HEAD_PASS, HEAD_FAIL) if head else (LEVEL_PASS, LEVEL_FAIL)
        level = 'FAIL' if worst[1][2] > 100 * hi else 'WARN' if worst[1][2] > 100 * lo else 'PASS'
        rows.append(dict(view=n, kind='head' if head else 'main', level=level, worst=worst[0],
                         parts={k: [round(float(x), 2) for x in v] for k, v in row.items()}))
    # what to fix this round: the few that differ most, measured against their own limit (a close-up's parts are
    # larger shares of a smaller figure)
    over = sorted(((r['parts'][r['worst']][2] / (100 * (HEAD_FAIL if r['kind'] == 'head' else LEVEL_FAIL)), r['view'])
                   for r in rows if r['level'] == 'FAIL'), reverse=True)
    first = [v for _, v in over[:FIRST]]
    for r in rows:
        r['first'] = r['view'] in first
    level = 'FAIL' if any(r['level'] == 'FAIL' for r in rows) else 'WARN' if any(r['level'] == 'WARN' for r in rows) else 'PASS'
    if picture:
        draw(picture, rows, shots, lab, pal, kind)
    return dict(parts=sorted({w for v in nm.values() for w in v}), views=rows, level=level, first=first)


def draw(path, rows, shots, lab, pals, kind, most=6):
    """the views to fix first, then the ones that differ most: photo, its parts, the model, its parts; what differs
    painted red on the parts"""
    swatch = {}
    for k, (cen, fam) in pals.items():
        fc = np.array([cen[fam == i].mean(0) for i in range(fam.max() + 1)])
        bgr = cv2.cvtColor(np.clip(np.stack([fc[:, 0] * 2, fc[:, 1], fc[:, 2]], -1), 0, 255).astype(np.uint8)[None], cv2.COLOR_LAB2BGR)[0]
        swatch[k] = np.vstack([[255, 255, 255], bgr]).astype(np.uint8)
    limit = lambda r: 100 * (HEAD_FAIL if r['kind'] == 'head' else LEVEL_FAIL)
    order = sorted(rows, key=lambda r: (not r.get('first'), -max([v[2] for v in r['parts'].values()] or [0]) / limit(r)))[:most]
    tiles = []
    for r in order:
        ph, pm, rim, rm = shots[r['view']]; Lp, Lr = lab[r['view']]
        pal = swatch[kind(r['view'])]; n = len(pal) - 1
        ys, xs = np.nonzero(pm | rm)
        y0, y1, x0, x1 = max(ys.min() - 20, 0), min(ys.max() + 20, SIZE), max(xs.min() - 20, 0), min(xs.max() + 20, SIZE)
        k = np.ones((TOLERANCE, TOLERANCE), np.uint8); bad = np.zeros(pm.shape, np.uint8)
        for q in range(1, n + 1):
            a, b = (Lp == q).astype(np.uint8), (Lr == q).astype(np.uint8)
            bad |= (a & (cv2.dilate(b, k) == 0)) | (b & (cv2.dilate(a, k) == 0))
        bad = cv2.morphologyEx(bad, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8)) > 0     # specks say nothing
        cells = []
        for pic, marked in ((ph, False), (pal[Lp], True), (rim, False), (pal[Lr], True)):
            c = pic.copy()
            if marked:
                c[bad & (c.sum(2) < 765)] = (40, 40, 230)          # where this picture has a part the other has not
            c = c[y0:y1, x0:x1]; s = 380 / max(c.shape[:2])
            c = cv2.resize(c, (max(1, int(c.shape[1] * s)), max(1, int(c.shape[0] * s))))
            pad = np.full((380, 380, 3), 255, np.uint8); pad[:c.shape[0], :c.shape[1]] = c
            cells.append(pad)
        tiles.append(np.hstack(cells))
    cv2.imwrite(path, np.vstack(tiles), [cv2.IMWRITE_JPEG_QUALITY, 88])


def lines(res):
    """the report lines of the acceptance: one per view"""
    out = []
    for r in res['views']:
        head = r['kind'] == 'head'
        lo, hi = (HEAD_PASS, HEAD_FAIL) if head else (LEVEL_PASS, LEVEL_FAIL)
        txt = '、'.join(f'{k} {v[2]:.1f}%' for k, v in sorted(r['parts'].items(), key=lambda kv: -kv[1][2])) or '沒有可比的部分'
        msg = (f'[{r["level"]}] {r["view"]} 分塊比對: {txt}（{"頭部特寫" if head else "全身圖"}每一塊應 ≤ {100 * lo:g}%，'
               f'> {100 * hi:g}% 判 FAIL；完美照片 ≤ {"3.1" if head else "1.1"}%）')
        if r['level'] != 'PASS':
            p, m_ = r['parts'][r['worst']][:2]
            how = '成品的這一塊比照片大' if m_ > p * 1.15 else '成品的這一塊比照片小' if m_ < p * 0.87 else '大小相近，形狀或位置不同'
            msg += (f' → 成品在這個角度的「{r["worst"]}」和照片對不上（照片佔人物的 {p:.0f}%、成品 {m_:.0f}%：{how}）。')
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
    ap = argparse.ArgumentParser(description='成品與原圖分塊比對')
    ap.add_argument('work'); ap.add_argument('photos'); ap.add_argument('glb'); ap.add_argument('--out')
    a = ap.parse_args()
    res = compare(a.work, a.photos, a.glb, a.out)
    print('分成：' + '、'.join(res['parts']))
    print('\n'.join(lines(res)))
    if res.get('first'):
        print('這一輪先修：' + '、'.join(res['first']))
    sys.exit(1 if res['level'] == 'FAIL' else 0)
