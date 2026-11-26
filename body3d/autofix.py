#!/usr/bin/env python3
"""autofix.py — 照片檢查未通過時，看能不能自動修（docs/SOP.md「未通過時自動修正」）

每一個未通過項目分成兩類：
    可以自動修  照片內容是對的，只是位置／大小差一點：量得出修正量、修完能用同一項檢查驗證
    要重新生成  內容錯了（角度、臉的朝向、光線、耳朵、五官比例、翻轉…），只能請 AI 重畫

只要有一項要重新生成，或可以修的項目信心不夠（修正量太大、會切到人、修完驗證沒通過），就不修，流程停下。
全部都能高信心修好時：在新的資料夾放修正後的照片（原檔不動），每一張改了什麼記在 autofix.json，
再跑一次照片檢查。

一個修正要「證明有用」才啟用（PROVEN）：在對照實驗（同一組照片，只差這幾張）裡，它要讓後面的關卡（不只是照片檢查
自己）變好。目前沒有經過證明的修正，所以未通過一律停下、交給 AI 重畫：
    第 11c 項 特寫臉部位置  平移特寫可以讓照片檢查通過，但 R14 對照實驗顯示烘焙前檢查的上下偏移只改善 5–6 px：
                            特寫環的上下對準是共用的，平移一張會被整個環吸收一部分（docs/Diagnosis-Tree.md）。
                            修正程式留著（kind='facepos'），沒有啟用。

用法:
    python autofix.py PHOTOS OUT_DIR       # 依照片檢查結果修正，寫 OUT_DIR/photos_fixed 與 autofix.json
"""
import json
import os
import re
import shutil
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import check_turnaround as ct          # noqa: E402

PROVEN = set()                         # fixes shown to improve the downstream gate in a controlled run; none yet
MAX_SHIFT_MM = 25.0                    # larger than this is not a framing slip: redraw the close-up
FULL = {0: '01_000deg_front', 45: '02_045deg_front_left', 315: '08_315deg_front_right'}


def classify(line):
    """(kind, angle) for a FAIL line the code can fix, else (None, label)"""
    label = line.split(':', 1)[0].strip()
    m = re.match(r'head (\d+)° 臉部位置$', label)
    if m and int(m.group(1)) in (45, 315) and 'facepos' in PROVEN:
        return 'facepos', int(m.group(1))
    return None, label


def _load(img, name):
    im = cv2.imread(os.path.join(img, name + '.jpg'))
    if im is None:
        raise FileNotFoundError(name)
    return im


def _scale(full):
    m = ct.segment(full)[0]
    rows = np.flatnonzero(m.any(1))
    return m, (rows[-1] - rows[0]) / ct.SPEC_HEIGHT


def _face_rel(img, a, close=None):
    """close-up face offset at angle a relative to 0° (mm), and the full-body px per metre"""
    off = {}
    for ang in (0, a):
        full = _load(img, FULL[ang])
        m, s = _scale(full)
        c = close if (ang == a and close is not None) else _load(img, f'head_{ang:03d}deg')
        o = ct.face_offset(full, m, c)
        if o is None or isinstance(o, str):
            return None, None
        off[ang] = o
        if ang == a:
            s_a = s
    return off[a] - off[0], s_a


def shift(im, dx, dy):
    """move the picture by (dx, dy) px, filling the uncovered edge with the background colour"""
    h, w = im.shape[:2]
    border = np.concatenate([im[:8].reshape(-1, 3), im[-8:].reshape(-1, 3), im[:, :8].reshape(-1, 3), im[:, -8:].reshape(-1, 3)])
    bg = tuple(int(v) for v in np.median(border, 0))
    return cv2.warpAffine(im, np.float32([[1, 0, dx], [0, 1, dy]]), (w, h), flags=cv2.INTER_LINEAR,
                          borderMode=cv2.BORDER_CONSTANT, borderValue=bg)


def plan(img, fail_lines):
    """dict(ok, items, reasons): ok only when every FAIL can be fixed with high confidence (fix verified)"""
    items, reasons = [], []
    for line in fail_lines:
        kind, arg = classify(line)
        if kind is None:
            reasons.append(f'要重新生成：{arg}')
            continue
        a = arg
        d, s = _face_rel(img, a)
        if d is None:
            reasons.append(f'head {a}° 臉部位置：找不到臉，無法量修正量')
            continue
        e = float(np.hypot(*d))
        if e > MAX_SHIFT_MM:
            reasons.append(f'head {a}° 臉部位置：差 {e:.1f} mm，超過 {MAX_SHIFT_MM:g} mm，不是構圖小偏差，要重畫特寫')
            continue
        k = s * ct.HEAD_ZOOM / 1000.0                                    # close-up px per mm
        dx, dy = float(-d[0] * k), float(-d[1] * k)
        close = _load(img, f'head_{a:03d}deg')
        cm = ct.segment(close)[0]
        # the picture moves by (dx, dy): what leaves the frame must be background, or the shift cuts the person.
        # An edge the person already runs off (the shoulders at the bottom of a close-up) may lose a little more;
        # an edge the person does not touch (above the head) must stay clear.
        H, W = cm.shape
        touches = dict(r=cm[:, -2:].any(), l=cm[:, :2].any(), b=cm[-2:].any(), t=cm[:2].any())
        cut = np.zeros_like(cm)
        if dx > 0 and not touches['r']: cut[:, W - int(np.ceil(dx)):] = True
        if dx < 0 and not touches['l']: cut[:, :int(np.ceil(-dx))] = True
        if dy > 0 and not touches['b']: cut[H - int(np.ceil(dy)):, :] = True
        if dy < 0 and not touches['t']: cut[:int(np.ceil(-dy)), :] = True
        lost = int((cm & cut).sum())
        if lost > 0.001 * cm.sum():
            reasons.append(f'head {a}° 臉部位置：平移 ({dx:+.0f}, {dy:+.0f}) px 會切到人（{lost} px），要重畫特寫')
            continue
        fixed = shift(close, dx, dy)
        d2, _ = _face_rel(img, a, fixed)                                 # verify with the same measurement
        e2 = float(np.hypot(*d2)) if d2 is not None else None
        if e2 is None or e2 > ct.FACEPOS_PASS:
            reasons.append(f'head {a}° 臉部位置：平移後仍差 {e2 if e2 is not None else "?"} mm，信心不夠')
            continue
        items.append(dict(photo=f'head_{a:03d}deg.jpg', kind='特寫臉部位置（第 11c 項）', dx_px=round(dx, 1),
                          dy_px=round(dy, 1), before_mm=round(e, 1), after_mm=round(e2, 1), image=fixed))
    ok = bool(items) and not reasons
    return dict(ok=ok, items=items, reasons=reasons)


def apply(img, dst, p, round_no):
    """copy the photos to dst with the planned fixes; returns the record (list of dicts, no images)"""
    os.makedirs(dst, exist_ok=True)
    fixed = {it['photo']: it for it in p['items']}
    for f in sorted(os.listdir(img)):
        if not f.lower().endswith('.jpg'):
            continue
        if f in fixed:
            cv2.imwrite(os.path.join(dst, f), fixed[f]['image'], [cv2.IMWRITE_JPEG_QUALITY, 95])
        else:
            shutil.copy2(os.path.join(img, f), os.path.join(dst, f))
    return [dict({k: v for k, v in it.items() if k != 'image'}, round=round_no) for it in p['items']]


def main(argv=None):
    import subprocess
    import argparse
    ap = argparse.ArgumentParser(description='照片檢查未通過時自動修正（只修量得出、驗證得了的項目）')
    ap.add_argument('img'); ap.add_argument('out')
    a = ap.parse_args(argv)
    os.makedirs(a.out, exist_ok=True)
    r = subprocess.run([sys.executable, os.path.join(HERE, 'check_turnaround.py'), a.img, '--out',
                        os.path.join(a.out, 'autofix_check.png')], capture_output=True, text=True)
    import deliver
    fails = deliver.fail_lines(r.stdout)
    if not fails:
        print('照片檢查沒有未通過項目，不用修'); return 0
    p = plan(a.img, fails)
    for it in p['items']:
        print(f"可以修：{it['photo']} 平移 ({it['dx_px']:+.0f}, {it['dy_px']:+.0f}) px，{it['before_mm']} → {it['after_mm']} mm")
    for why in p['reasons']:
        print('不能自動修：' + why)
    if not p['ok']:
        return 1
    rec = apply(a.img, os.path.join(a.out, 'photos_fixed'), p, 1)
    json.dump(rec, open(os.path.join(a.out, 'autofix.json'), 'w'), ensure_ascii=False, indent=1)
    print('修正後的照片：' + os.path.join(a.out, 'photos_fixed'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
