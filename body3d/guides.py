#!/usr/bin/env python3
"""guides.py — 先給輪廓再畫：由已經畫好的照片，算出下一段每張照片的輪廓圖，並量畫好的照片有沒有照著線

    python body3d/guides.py PHOTOS OUT          # 看畫到第幾段、寫出這一段的輪廓圖與 OUT/guides.md
    python body3d/guides.py PHOTOS --check      # 只量，不寫圖

33 張照片分六段畫（docs/papers/11-guides-first.md）。前四段的輪廓是「準確的」：只靠規格（人不動、相機水平、沒有
近大遠小）就能從已有的照片算出來，照著畫就對。後兩段只有「上限」：外殼比人胖，照著填就錯。

    段  畫什麼                              輪廓圖                                        種類
    1   正面全身照                          沒有（照文字規格）                            —
    2   背面、左側、左前、左後（4 張）      背面：正面輪廓左右翻轉；其餘：高度橫線、指尖直線  準確
    3   右後、右側、右前（3 張）            對面那張的輪廓左右翻轉＋高度橫線              準確
    4   頭部特寫 8 張                       同角度全身照的頭放大 4 倍（當底圖，只補細節）   準確
    5   俯視                                水平圈外殼從上面看（綠線）＋手臂的左右範圍      上限
    6   俯角、仰角 16 張                    外殼投影（綠線）、手臂要在的位置（橘）          上限

每一段畫完就量那一段（check）：沒照著線的照片點名重畫。同一張連續 MAX_TRIES 次沒過就先放行（記在 stage_log.json），
最後仍由 run_all 的四道關卡判定：這裡的量只是提早說，不是另一道關卡。
"""
import argparse
import hashlib
import json
import os
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import check_turnaround as ct          # noqa: E402

__version__ = '1.0.2'

FULL = {0: '01_000deg_front', 45: '02_045deg_front_left', 90: '03_090deg_left', 135: '04_135deg_back_left',
        180: '05_180deg_back', 225: '06_225deg_back_right', 270: '07_270deg_right', 315: '08_315deg_front_right'}
ANGLES = tuple(range(0, 360, 45))
STAGES = (
    ('front', '正面全身照', [FULL[0]]),
    ('level_a', '背面、左側、左前、左後', [FULL[a] for a in (180, 45, 90, 135)]),
    ('level_b', '右後、右側、右前（對面那張的翻轉）', [FULL[a] for a in (225, 270, 315)]),
    ('heads', '頭部特寫', [f'head_{a:03d}deg' for a in ANGLES]),
    ('top', '俯視', ['top']),
    ('tilted', '俯角與仰角', [f'{r}_{a:03d}deg' for r in ('el30', 'low20') for a in ANGLES]),
)
ALL = [n for _, _, names in STAGES for n in names]
MAX_TRIES = 3                    # a photo that fails its stage this many times in a row is let through

# what "followed the line" means. Calibrated on the two perfect sets (renders of known models with the spec cameras:
# luna-v1, synth) and on what the AI drew without guides (Gemini avatar_001 v015, ChatGPT avatar_001 R83):
#                         perfect      Gemini v015             ChatGPT R83
#   head top / floor      <= 1 mm      <= 1 mm                 <= 4 mm
#   arm edges             <= 2 mm      <= 5 mm                 6-14 mm at the diagonals (its "arm band" loss, #130)
#   hand tip to hand tip  <= 4.1 %     2.5-4.7 %               0.2-8.5 %
#   flipped outline       0.2-0.3 %    7.1-11.0 %              3.5-14.1 %
#   close-up vs 4x head   0.8-2.5 %    1.3-2.8 and 7.7-12.8 %  16-31 % (all eight)
#   top view outside      <= 0.1 %     1.0 %                   1.6 %
# FAIL = clearly not the same outline.
ROW_FAIL = 12.0                  # mm: head top / floor of a level photo against the front photo
ARM_ROW_FAIL = 10.0              # mm: upper / lower edge of the arms of a level photo against the front photo
SPAN_FAIL = 8.0                  # %: hand tip to hand tip against the front photo's times |cos angle| (5 deg at 45 deg)
FLIP_FAIL = 3.0                  # %: outline against the opposite photo flipped (not shared / union)
HEAD_FAIL = 5.0                  # %: close-up outline above the shoulders against the full-body head enlarged 4x
HEAD_AIM_FAIL = 10.0             # mm: where the head sits in a close-up against the full-body head enlarged 4x
TOP_SPAN_FAIL = 3.0              # %: the top view's width against the front view's
TOP_OUT_FAIL = 3.0               # %: of the top view's figure outside the level ring's hull seen from above
FRONT_HEIGHT = (0.846, 0.03)     # the figure fills this share of the frame height, +- this much
FRONT_CENTRE_FAIL = 25.0         # mm: the figure's axis off the image centre
FRONT_ARM_FAIL = 25.0            # mm: an arm's height at 30 cm from the axis against 55 cm (arms level)

GREEN, ORANGE, BLUE, GREY = (0, 170, 0), (0, 140, 255), (200, 110, 30), (150, 150, 150)


# ---------------------------------------------------------------------------------------------------------------
# reading

class Photos:
    """the photos of a folder and their outlines, read once"""

    def __init__(self, folder):
        self.folder = folder
        self._im, self._m = {}, {}

    def path(self, name):
        return os.path.join(self.folder, name + '.jpg')

    def has(self, name):
        return os.path.isfile(self.path(name))

    def image(self, name):
        if name not in self._im:
            self._im[name] = cv2.imread(self.path(name)) if self.has(name) else None
        return self._im[name]

    def mask(self, name):
        if name not in self._m:
            im = self.image(name)
            self._m[name] = None if im is None else (ct.segment(im)[0] > 0)
        return self._m[name]

    def digest(self, name):
        return hashlib.sha1(open(self.path(name), 'rb').read()).hexdigest()[:12]


def front_lines(m):
    """what the front photo fixes for every level photo: px per m, the rows of the head top, the floor and the arms'
    upper and lower edge, the columns of the axis and the two hand tips; None when it is not a T-pose figure"""
    rows = np.flatnonzero(m.any(1)); cols = np.flatnonzero(m.any(0))
    if len(rows) < 50 or len(cols) < 50:
        return None
    H, W = m.shape
    top, floor = int(rows[0]), int(rows[-1])
    s = (floor - top) / ct.SPEC_HEIGHT
    k = ct.SPEC_HEIGHT / 1.65
    L = dict(s=s, top=top, floor=floor, cx=W / 2, tip_l=int(cols[0]), tip_r=int(cols[-1]), shape=(H, W))
    band = arm_band(m, L, 1.0)
    if band is None:
        return None
    L['arm_top'], L['arm_bot'] = band
    # the legs' gap on the axis: the crotch (front and back views only)
    strip = m[:, int(W / 2) - 2:int(W / 2) + 3].any(1)
    below = np.flatnonzero(~strip[int(L['arm_bot'] + 0.25 * k * s):floor])
    L['crotch'] = int(L['arm_bot'] + 0.25 * k * s + below[0]) if len(below) else None
    return L


def first_run(column):
    """(first, last) row of the first run of figure from the top of a column of an outline, or None"""
    r = np.flatnonzero(column)
    if not len(r):
        return None
    gap = np.flatnonzero(np.diff(r) > 1)
    return int(r[0]), int(r[gap[0]] if len(gap) else r[-1])


def arm_band(m, L, c, near=0.30, far=0.55):
    """(upper row, lower row) of the arms of a level photo: the median over the columns between `near` and `far`
    metres from the axis (times c = |cos angle|: how much the arms are foreshortened), both sides; None when the
    figure has no arms there. In a column the arm is the first run of figure from the top: in a diagonal view a hip
    or a thigh can reach under the arm, and "down to the last figure row" would then be the leg"""
    k = ct.SPEC_HEIGHT / 1.65; s = L['s']; cx = L['cx']; H, W = m.shape
    tops, bots = [], []
    for side in (-1, 1):
        a, b = sorted((int(round(cx + side * near * k * s * c)), int(round(cx + side * far * k * s * c))))
        for col in range(max(0, a), min(W, b + 1)):
            r = first_run(m[:, col])
            if r:
                tops.append(r[0]); bots.append(r[1])
    if len(tops) < 20:
        return None
    return float(np.median(tops)), float(np.median(bots))


def level_hull(P):
    """the body the level photos present carve together (one may disagree): (points (N, 3) relative to the body
    centre, px per m), or None with fewer than four. An upper bound: the person is inside it and thinner"""
    masks = {a: P.mask(FULL[a]) for a in ANGLES if P.has(FULL[a])}
    if len(masks) < 4:
        return None
    vs = 0.01; k = ct.SPEC_HEIGHT / 1.65
    hs = [np.ptp(np.flatnonzero(m.any(1))) for m in masks.values()]
    s = float(np.median(hs)) / ct.SPEC_HEIGHT
    xs = np.arange(-0.95 * k, 0.95 * k, vs) + vs / 2; ys = np.arange(0, 1.72 * k, vs) + vs / 2
    zs = np.arange(-0.42 * k, 0.42 * k, vs) + vs / 2
    X, Y, Z = np.meshgrid(xs, ys, zs, indexing='ij')
    Q = np.stack([X.ravel(), Y.ravel() - ct.SPEC_HEIGHT / 2, Z.ravel()], 1)
    votes = np.zeros(len(Q), np.uint8)
    for a, m in masks.items():
        H, W = m.shape; r, u = ct._spec_axes(a, 0.0)
        md = cv2.dilate(m.astype(np.uint8), np.ones((5, 5), np.uint8))
        c = np.round(W / 2 + s * (Q @ r)).astype(int); w = np.round(H / 2 - s * (Q @ u)).astype(int)
        ok = (c >= 0) & (c < W) & (w >= 0) & (w < H)
        votes += ok & (md[np.clip(w, 0, H - 1), np.clip(c, 0, W - 1)] > 0)
    return Q[votes >= len(masks) - (1 if len(masks) >= 8 else 0)], s


def seen(pts, s, a, th, shape, vs=0.01):
    """the outline of the points from the spec camera (azimuth a, tilt th; the top view is tilt 90), as a mask"""
    return ct._splat(pts, a, th, s, shape, vs) > 0


def differ(a, b):
    """how far two outlines are apart: the area only one of them has, in % of the area either has"""
    u = (a | b).sum()
    return 100.0 * (a ^ b).sum() / max(1, u)


def head_reference(P, angle):
    """(the full-body photo's head enlarged 4x as the close-up should frame it, its outline) or (None, None)"""
    full, m = P.image(FULL[angle]), P.mask(FULL[angle])
    if full is None:
        return None, None
    rows = np.flatnonzero(m.any(1))
    s = (rows[-1] - rows[0]) / ct.SPEC_HEIGHT
    H, W = full.shape[:2]
    cx, cy = W / 2, rows[0] + 0.128 * ct.SPEC_HEIGHT / 1.65 * s
    half = W / ct.HEAD_ZOOM / 2
    M = np.float32([[ct.HEAD_ZOOM, 0, -ct.HEAD_ZOOM * (cx - half)], [0, ct.HEAD_ZOOM, -ct.HEAD_ZOOM * (cy - half)]])
    im = cv2.warpAffine(full, M, (W, H), flags=cv2.INTER_CUBIC, borderValue=(255, 255, 255))
    mm = cv2.warpAffine(m.astype(np.uint8), M, (W, H), flags=cv2.INTER_LINEAR) > 0
    return im, mm


def head_rows(mm):
    """the rows of a close-up outline that are the head: from its top down to 25 cm below it (above the shoulders)"""
    rows = np.flatnonzero(mm.any(1))
    if not len(rows):
        return slice(0, 0)
    px = ct.HEAD_ZOOM * mm.shape[1] / ct.BODY_FRAME          # px per m in a close-up
    return slice(int(rows[0]), int(min(mm.shape[0], rows[0] + 0.25 * px)))


# ---------------------------------------------------------------------------------------------------------------
# measuring: did the photo follow its lines

def _r(photo, item, value, limit, unit, msg):
    return dict(photo=photo, item=item, value=round(float(value), 2), limit=limit, unit=unit,
                level='FAIL' if abs(value) > limit else 'PASS', msg=msg)


def check_front(P):
    name = FULL[0]; m = P.mask(name); out = []
    L = front_lines(m)
    if L is None:
        return [dict(photo=name, item='T 字姿勢', value=0, limit=0, unit='', level='FAIL',
                     msg='找不到向兩側平伸的手臂：正面照要是 T 字姿勢、白色背景、全身入鏡')]
    H, W = m.shape; s = L['s']
    share = (L['floor'] - L['top']) / H
    out.append(dict(photo=name, item='人物高度', value=round(100 * share, 1), limit=100 * FRONT_HEIGHT[1], unit='%',
                    level='FAIL' if abs(share - FRONT_HEIGHT[0]) > FRONT_HEIGHT[1] else 'PASS',
                    msg=f'人物高佔畫面 {100 * share:.1f}%（規格 {100 * FRONT_HEIGHT[0]:.1f}%）'))
    mid = (L['top'] + L['floor']) / 2
    out.append(_r(name, '上下置中', 1000 * (mid - H / 2) / s, FRONT_CENTRE_FAIL, 'mm',
                  f'身體中心比畫面中心低 {1000 * (mid - H / 2) / s:+.0f} mm（頭頂和腳底到上下邊緣要一樣遠）'))
    torso = np.flatnonzero(m[int(L['arm_bot'] + 0.05 * s):int(L['arm_bot'] + 0.25 * s)].any(0))
    if len(torso):
        off = 1000 * ((torso[0] + torso[-1]) / 2 - W / 2) / s
        out.append(_r(name, '左右置中', off, FRONT_CENTRE_FAIL, 'mm', f'軀幹的中線偏畫面中線 {off:+.0f} mm'))
    for side, word in ((-1, '畫面左邊'), (1, '畫面右邊')):
        k = ct.SPEC_HEIGHT / 1.65
        mid_rows = []
        for d in (0.30, 0.55):
            col = int(round(L['cx'] + side * d * k * s)); r = first_run(m[:, min(W - 1, max(0, col))])
            mid_rows.append((r[0] + r[1]) / 2 if r else np.nan)
        if not np.isnan(mid_rows).any():
            d = 1000 * (mid_rows[1] - mid_rows[0]) / s
            out.append(_r(name, f'手臂水平（{word}）', d, FRONT_ARM_FAIL, 'mm',
                          f'{word}的手臂往外{"下垂" if d > 0 else "上揚"} {abs(d):.0f} mm（要水平）'))
    return out


def check_level(P, angle, L):
    """a level photo against the front photo's lines and, when the opposite photo is there, its flipped outline"""
    name = FULL[angle]; m = P.mask(name); out = []
    rows = np.flatnonzero(m.any(1)); cols = np.flatnonzero(m.any(0)); s = L['s']
    if len(rows) < 50:
        return [dict(photo=name, item='人物', value=0, limit=0, unit='', level='FAIL', msg='照片裡找不到人物（背景要白）')]
    out.append(_r(name, '頭頂的高度', 1000 * (rows[0] - L['top']) / s, ROW_FAIL, 'mm',
                  f'頭頂比正面照{"低" if rows[0] > L["top"] else "高"} {abs(1000 * (rows[0] - L["top"]) / s):.0f} mm'))
    out.append(_r(name, '腳底的高度', 1000 * (rows[-1] - L['floor']) / s, ROW_FAIL, 'mm',
                  f'腳底比正面照{"低" if rows[-1] > L["floor"] else "高"} {abs(1000 * (rows[-1] - L["floor"]) / s):.0f} mm'))
    c = abs(np.cos(np.radians(angle)))
    opp = FULL[(angle + 180) % 360]
    flipped = P.has(opp) and angle >= 180
    if c > 0.6 and (angle == 180 or not flipped):
        band = arm_band(m, L, c)
        if band is None:
            out.append(dict(photo=name, item='手臂', value=0, limit=0, unit='', level='FAIL',
                            msg='在兩條指尖直線之間找不到平伸的手臂'))
        else:
            for got, ref, word in ((band[0], L['arm_top'], '上緣'), (band[1], L['arm_bot'], '下緣')):
                d = 1000 * (got - ref) / s
                out.append(_r(name, f'手臂{word}的高度', d, ARM_ROW_FAIL, 'mm',
                              f'手臂{word}比正面照{"低" if d > 0 else "高"} {abs(d):.0f} mm'))
        want = (L['tip_r'] - L['tip_l']) * c
        d = 100 * ((cols[-1] - cols[0]) - want) / want
        out.append(_r(name, '指尖到指尖', d, SPAN_FAIL, '%',
                      f'雙手指尖的距離比兩條直線{"寬" if d > 0 else "窄"} {abs(d):.1f}%'))
    if flipped:
        d = differ(m, P.mask(opp)[:, ::-1])
        out.append(_r(name, '翻轉的輪廓', d, FLIP_FAIL, '%',
                      f'輪廓和 {opp} 左右翻轉後不重疊的部分佔 {d:.1f}%（完美照片 0.2–0.3%）'))
    return out


def check_head(P, angle):
    name = f'head_{angle:03d}deg'
    ref = head_reference(P, angle)[1]
    m = P.mask(name)
    if ref is None or m is None:
        return []
    if m.shape != ref.shape:
        m = cv2.resize(m.astype(np.uint8), ref.shape[::-1], interpolation=cv2.INTER_NEAREST) > 0
    r, rm = head_rows(ref), head_rows(m)
    if r.stop <= r.start or rm.stop <= rm.start:
        return [dict(photo=name, item='人物', value=0, limit=0, unit='', level='FAIL', msg='照片裡找不到頭（背景要白）')]
    # where the head sits in the frame, then its shape with the framing taken out: the two are different mistakes
    px = ct.HEAD_ZOOM * ref.shape[1] / ct.BODY_FRAME
    dy = rm.start - r.start
    dx = float(np.nonzero(m[rm])[1].mean() - np.nonzero(ref[r])[1].mean())
    out = [_r(name, '頭在畫面裡的高度', 1000 * dy / px, HEAD_AIM_FAIL, 'mm',
              f'頭頂比全身照放大後的位置{"低" if dy > 0 else "高"} {abs(1000 * dy / px):.0f} mm（頭頂離上緣要約 24%）'),
           _r(name, '頭在畫面裡的左右', 1000 * dx / px, HEAD_AIM_FAIL, 'mm',
              f'頭比全身照放大後的位置偏{"右" if dx > 0 else "左"} {abs(1000 * dx / px):.0f} mm')]
    M = np.float32([[1, 0, -dx], [0, 1, -dy]])
    ms = cv2.warpAffine(m.astype(np.uint8), M, m.shape[::-1], flags=cv2.INTER_NEAREST) > 0
    d = differ(ms[r], ref[r])
    out.append(_r(name, '和全身照的頭同一個輪廓', d, HEAD_FAIL, '%',
                  f'對齊位置之後，肩膀以上的輪廓和 {FULL[angle]} 的頭放大 4 倍不重疊的部分佔 {d:.1f}%'))
    return out


def check_top(P, L, hull):
    m = P.mask('top'); out = []
    cols = np.flatnonzero(m.any(0))
    if len(cols) < 50:
        return [dict(photo='top', item='人物', value=0, limit=0, unit='', level='FAIL', msg='照片裡找不到人物（背景要白）')]
    want = L['tip_r'] - L['tip_l']
    d = 100 * ((cols[-1] - cols[0]) - want) / want
    out.append(_r('top', '指尖到指尖', d, TOP_SPAN_FAIL, '%', f'俯視圖的寬度比正面照{"寬" if d > 0 else "窄"} {abs(d):.1f}%（要一樣寬）'))
    if hull is not None:
        bound = cv2.dilate(seen(hull[0], hull[1], 0, 90.0, m.shape).astype(np.uint8), np.ones((9, 9), np.uint8)) > 0
        o = 100 * (m & ~bound).sum() / max(1, m.sum())
        out.append(_r('top', '在綠線裡面', o, TOP_OUT_FAIL, '%', f'人物有 {o:.1f}% 畫到綠線外面'))
    return out


def check_stage(P, key):
    """[{photo, item, value, limit, unit, level, msg}] for the photos of a stage that are there"""
    unread = [n for n in STAGES_BY_KEY[key] if P.has(n) and P.image(n) is None]
    if unread:
        return [dict(photo=n, item='檔案', value=0, limit=0, unit='', level='FAIL', msg='這個檔案讀不出來（要是 JPEG 圖片）')
                for n in unread]
    if P.has(FULL[0]) and P.image(FULL[0]) is None:
        return []
    if P.has(FULL[0]):
        H0, W0 = P.image(FULL[0]).shape[:2]
        if key == 'front' and H0 != W0:
            return [dict(photo=FULL[0], item='大小', value=0, limit=0, unit='', level='FAIL',
                         msg=f'正面照是 {W0} × {H0}：要是正方形（規格 2048 × 2048）')]
        odd = [n for n in STAGES_BY_KEY[key] if P.has(n) and P.image(n).shape[:2] != (H0, W0)]
        if odd:                       # the lines and outlines are in the front photo's pixels: nothing else to measure
            return [dict(photo=n, item='大小', value=0, limit=0, unit='', level='FAIL',
                         msg=f'這張是 {P.image(n).shape[1]} × {P.image(n).shape[0]}，正面照是 {W0} × {H0}：每一張都要和正面照一樣大')
                    for n in odd]
    L = front_lines(P.mask(FULL[0])) if P.has(FULL[0]) else None
    if key == 'front':
        return check_front(P) if P.has(FULL[0]) else []
    if L is None:
        return []
    if key in ('level_a', 'level_b'):
        names = dict(STAGES_BY_KEY[key])
        return [r for a in ANGLES if FULL[a] in names and P.has(FULL[a]) for r in check_level(P, a, L)]
    if key == 'heads':
        return [r for a in ANGLES if P.has(f'head_{a:03d}deg') for r in check_head(P, a)]
    if key == 'top' and P.has('top'):
        return check_top(P, L, level_hull(P))
    return []          # the tilted rings have only upper bounds: the photo check (run_all, gate 1) measures them


STAGES_BY_KEY = {key: {n: 1 for n in names} for key, _, names in STAGES}


# ---------------------------------------------------------------------------------------------------------------
# drawing the guides

def _canvas(shape):
    return np.full((shape[0], shape[1], 3), 255, np.uint8)


def _hline(im, row, label, colour=GREY):
    W = im.shape[1]; row = int(round(row))
    for x in range(0, W, 36):
        cv2.line(im, (x, row), (min(W - 1, x + 20), row), colour, 2)
    cv2.putText(im, label, (12, row - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.8, colour, 2, cv2.LINE_AA)


def _vline(im, col, label, colour=GREY):
    H = im.shape[0]; col = int(round(col))
    for y in range(0, H, 36):
        cv2.line(im, (col, y), (col, min(H - 1, y + 20)), colour, 2)
    cv2.putText(im, label, (col + 8, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, colour, 2, cv2.LINE_AA)


def _outline(im, mask, colour, fill=None, thick=None):
    if fill is not None:
        im[mask] = (0.25 * im[mask] + 0.75 * np.array(fill)).astype(np.uint8)
    cnt, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    cv2.drawContours(im, cnt, -1, colour, thick or max(3, im.shape[1] // 500))


def guide_level(P, angle, L):
    """(image, what it is: 'exact' with the opposite photo's flipped outline, else 'lines', the lines to say)"""
    im = _canvas(L['shape'])
    opp = FULL[(angle + 180) % 360]
    # only the back view and the three views of stage 3 are drawn on a flipped outline; 45 / 90 / 135 are the
    # ones the others are flipped from
    kind = 'exact' if P.has(opp) and angle >= 180 else 'lines'
    c = np.cos(np.radians(angle))
    _hline(im, L['top'], 'head top'); _hline(im, L['floor'], 'floor'); _vline(im, L['cx'], 'axis')
    if kind == 'exact' and angle != 180:
        # the flipped outline says where the arms are: no second set of lines beside it
        _outline(im, P.mask(opp)[:, ::-1], BLUE, fill=(245, 225, 200))
        return im, kind
    if abs(c) > 0.6:
        _hline(im, L['arm_top'], 'arm upper edge'); _hline(im, L['arm_bot'], 'arm lower edge')
        for tip in (L['tip_l'], L['tip_r']):
            _vline(im, L['cx'] + c * (tip - L['cx']), 'hand tip')
    else:
        # seen along the arms: only the end of the hand shows, in front of the shoulder
        h = L['arm_bot'] - L['arm_top']
        cv2.rectangle(im, (int(L['cx'] - h), int(L['arm_top'])), (int(L['cx'] + h), int(L['arm_bot'])), ORANGE, 3)
        cv2.putText(im, 'arm seen end-on: only the hand end, inside this box', (int(L['cx'] + h + 12), int(L['arm_top']) + 24),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, ORANGE, 2, cv2.LINE_AA)
    if L.get('crotch') and angle in (0, 180):
        _hline(im, L['crotch'], 'crotch')
    if kind == 'exact':                 # the outline last, on top of the lines
        _outline(im, P.mask(opp)[:, ::-1], BLUE, fill=(245, 225, 200))
    return im, kind


def guide_top(P, L, hull):
    im = _canvas(L['shape'])
    if hull is not None:
        _outline(im, seen(hull[0], hull[1], 0, 90.0, L['shape']), GREEN)
    for tip in (L['tip_l'], L['tip_r']):
        _vline(im, tip, 'hand tip')
    _vline(im, L['cx'], 'axis')
    return im, 'bound'


def guide_tilted(P, name, L, hull):
    ring, a = name.split('_')[0], int(name.split('_')[1][:3]); th = ct.RING_TILT[ring]
    im = _canvas(L['shape'])
    if hull is not None:
        _outline(im, seen(hull[0], hull[1], a, th, L['shape']), GREEN)
    if P.has('top'):
        arms = ct.rebuilt_arms(P.mask(FULL[0]), P.mask('top'))
        if arms:
            am = ct.arms_seen(arms[0], arms[1], a, th, L['shape']) > 0
            _outline(im, am, ORANGE, fill=(170, 215, 255))
    return im, 'bound'


SAY = {
    'exact': '**準確的輪廓：照著畫。** 藍線是對面那張照片左右翻轉的輪廓，人物的外形要和藍線重合（填滿淺色區域，不要超出）。'
             '虛線是正面照量到的高度：頭頂、手臂的上下緣、腳底都要落在線上。',
    'lines': '**準確的線：照著畫。** 橫的虛線是正面照量到的高度（頭頂 head top、手臂上緣／下緣、腳底 floor），每一條都要對上；'
             '直的虛線是旋轉軸（axis）與雙手指尖該到的位置（hand tip）：兩條指尖線之間的距離是準確的，左右位置假設手臂在身體正中間的平面上，整體差 1–2 cm 沒關係。橘色方框（側面照才有）：手臂正對鏡頭，'
             '只看得到手掌的端面，落在框裡，不要畫出往前或往後伸的前臂。線只定高度與指尖，身體的寬度照這個人物畫。',
    'head': '**底圖：只補細節。** 這張是同一個角度的全身照，頭的部分放大 4 倍（所以模糊）。用它當底圖／參考圖（image-to-image），'
            '畫成清楚的頭部特寫：頭的外形、髮型的輪廓、眼睛鼻子嘴巴耳朵的位置都不要動，只把細節畫清楚。背景白色。',
    'bound': '**輪廓的上限：不要照著填。** 綠線是水平那一圈照片雕出來的外殼，從這個角度看到的樣子：人物要在綠線裡面，'
             '而且比綠線瘦（外殼比真的人胖，手臂尤其是；照著綠線填滿，手臂會變成扁平的厚板）。'
             '橘色（俯角、仰角才有）：手臂要在的位置，由正面照定高度、俯視圖定前後。',
}


# ---------------------------------------------------------------------------------------------------------------
# which stage, and its guides

def misnamed(folder, names):
    """{name: the file in the folder that was meant to be name.jpg}: the same name with another extension or in
    capitals (01_000deg_front.png, HEAD_000DEG.JPG). The photo was drawn; asking to draw it again goes on forever"""
    have = {}
    for f in (os.listdir(folder) if os.path.isdir(folder) else []):
        stem, ext = os.path.splitext(f)
        if ext.lower() in ('.jpg', '.jpeg', '.png', '.webp'):
            have.setdefault(stem.lower(), f)
    return {n: have[n.lower()] for n in names if n.lower() in have and have[n.lower()] != n + '.jpg'}


def status(photos, log=None):
    """{'stage': 1..6 or None when all 33 are drawn and measured, 'key', 'title', 'draw': the photos to draw now,
    'results': this stage's measurements, 'waived': photos let through after MAX_TRIES}. log: {photo: [digests of
    the versions that failed]} from earlier calls, updated here"""
    P = Photos(photos); log = log if log is not None else {}
    waived = []
    for i, (key, title, names) in enumerate(STAGES):
        missing = [n for n in names if not P.has(n)]
        res = check_stage(P, key)
        bad = sorted({r['photo'] for r in res if r['level'] == 'FAIL'})
        redo = []
        for n in bad:
            tries = log.setdefault(n, [])
            d = P.digest(n)
            if d not in tries:
                tries.append(d)
            if len(tries) >= MAX_TRIES:
                waived.append(n)
            else:
                redo.append(n)
        if missing or redo:
            return dict(stage=i + 1, key=key, title=title, draw=missing + redo, redo=redo, results=res, waived=waived, P=P,
                        misnamed=misnamed(photos, missing))
    return dict(stage=None, key=None, title='33 張都畫好了', draw=[], redo=[], results=[], waived=waived, P=P, misnamed={})


def make(photos, out, log_path=None):
    """write the guides of the stage to draw now into `out` (one PNG per photo, guides.md, stage.json); returns the
    status without the photo cache. log_path: where the failed tries of every photo are kept (default: in `out`).
    next_step keeps one for the whole avatar: a photo let through after MAX_TRIES stays let through in the next
    version, which copies the photos (a retouch round used to start its three tries again)"""
    os.makedirs(out, exist_ok=True)
    log_path = log_path or os.path.join(out, 'stage_log.json')
    log = json.load(open(log_path, encoding='utf-8')) if os.path.exists(log_path) else {}
    st = status(photos, log)
    json.dump(log, open(log_path, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
    P = st.pop('P')
    for f in os.listdir(out):                      # the guides of earlier stages were made from photos since redrawn
        if f.endswith('_guide.png'):
            os.remove(os.path.join(out, f))
    lines = [f'# 輪廓圖：第 {st["stage"]} 段（共 {len(STAGES)} 段）　{st["title"]}' if st['stage'] else '# 33 張都畫好了：跑 run_all', '']
    files = {}
    if st['stage']:
        L = front_lines(P.mask(FULL[0])) if P.has(FULL[0]) else None
        hull = level_hull(P) if st['key'] in ('top', 'tilted') else None
        fails = {}
        for r in st['results']:
            if r['level'] == 'FAIL' and r['photo'] in st['redo']:
                fails.setdefault(r['photo'], []).append(r['msg'])
        if st['key'] == 'front':
            lines += ['這一段沒有輪廓圖：照 `docs/Workflow-and-Validation.md#生圖規格` 畫**正面全身照 1 張**，'
                      f'存成 `{FULL[0]}.jpg`。之後的 32 張都從這一張長出來，所以這一張要最仔細：T 字姿勢（雙臂水平）、'
                      '人物高佔畫面 84.6%、上下左右置中、白色背景、沒有方向性的光。', '']
        for n in st['draw']:
            if st['key'] in ('level_a', 'level_b') and L:
                a = next(a for a in ANGLES if FULL[a] == n); im, kind = guide_level(P, a, L)
            elif st['key'] == 'heads':
                a = int(n[5:8]); im, kind = head_reference(P, a)[0], 'head'
            elif st['key'] == 'top' and L:
                im, kind = guide_top(P, L, hull)
            elif st['key'] == 'tilted' and L:
                im, kind = guide_tilted(P, n, L, hull)
            else:
                im, kind = None, None
            if im is not None:
                f = f'{n}_guide.png'; cv2.imwrite(os.path.join(out, f), im); files[n] = f
                lines += [f'## `{n}.jpg`　輪廓圖 `{f}`', '', SAY[kind], '']
            elif n in fails:
                lines += [f'## `{n}.jpg`', '']
            if n in fails:
                lines += ['上一次畫的沒有照著線（重畫時以上一次畫的這張為底，只改沒對上的地方，其餘不要動）：'] \
                    + [f'- {m}' for m in fails[n]] + ['']
        lines += ['畫的時候把輪廓圖和正面照一起給生圖模型當參考；**交出去的照片上不能留下任何線、框或文字**（那是給你看的）。'
                  '同一個人物、同樣的衣服與光線；規格其餘的部分照 `docs/Workflow-and-Validation.md#生圖規格`。',
                  f'畫好的照片放進 `{os.path.abspath(photos)}`，檔名如上，再跑一次 next_step。', '']
    if st['misnamed']:
        lines += ['**檔名不對的照片（已經畫了，改檔名就好，不用重畫）：**'] + [f'- `{f}` 要改成 `{n}.jpg`（JPEG 格式、小寫 .jpg）'
                                                                    for n, f in sorted(st['misnamed'].items())] + ['']
    if st['waived']:
        lines += ['連續 {} 次沒照著線、先放行的照片（最後由四道關卡判定）：{}'.format(MAX_TRIES, '、'.join(st['waived'])), '']
    open(os.path.join(out, 'guides.md'), 'w', encoding='utf-8').write('\n'.join(lines))
    st['files'] = files; st['guides'] = os.path.join(out, 'guides.md')
    json.dump({k: v for k, v in st.items()}, open(os.path.join(out, 'stage.json'), 'w', encoding='utf-8'),
              ensure_ascii=False, indent=1)
    return st


def main(argv=None):
    ap = argparse.ArgumentParser(description=f'guides {__version__}：先給輪廓再畫')
    ap.add_argument('photos'); ap.add_argument('out', nargs='?')
    ap.add_argument('--check', action='store_true', help='每一段都量，只印結果，不寫圖')
    ap.add_argument('--version', action='version', version=f'guides {__version__}')
    a = ap.parse_args(argv)
    if a.check or not a.out:
        P = Photos(a.photos)
        for i, (key, title, names) in enumerate(STAGES):
            print(f'第 {i + 1} 段 {title}：{sum(P.has(n) for n in names)}/{len(names)} 張')
            for r in check_stage(P, key):
                print(f'  [{r["level"]}] {r["photo"]} {r["item"]}: {r["value"]:+g}{r["unit"]}（門檻 {r["limit"]:g}）{r["msg"]}')
        return 0
    st = make(a.photos, a.out)
    print(f'第 {st["stage"]} 段 {st["title"]}：要畫 {"、".join(st["draw"])}；說明在 {st["guides"]}' if st['stage']
          else '33 張都畫好了：跑 run_all')
    return 0


if __name__ == '__main__':
    sys.exit(main())
