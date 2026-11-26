#!/usr/bin/env python3
"""ai_request.py — AI 修圖單：診斷樹判定是照片的問題時，交給 AI 生圖／修圖的清單

    OUT/ai_fix_request/
        AI修圖單.md                 每一張要修的照片：問題、怎麼修、量到的數字
        photos/                     要修的原圖
        reference/                  參考圖（特寫：同角度全身圖的頭部，依規格裁切放大 4 倍，臉應該在的位置）

run_all.py 在診斷有「照片」葉子時自動產生，並放進該階段的結果包；也可以單獨執行：
    python ai_request.py PHOTOS OUT_DIR          # 讀 OUT_DIR/diagnosis.json
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

FULL = {0: '01_000deg_front', 45: '02_045deg_front_left', 90: '03_090deg_left', 135: '04_135deg_back_left',
        180: '05_180deg_back', 225: '06_225deg_back_right', 270: '07_270deg_right', 315: '08_315deg_front_right'}


def photos_of(leaf):
    """the photo files a leaf asks to redraw"""
    text = leaf['item'] + ' ' + leaf['action']
    names = set(re.findall(r'head_\d{3}deg|el30_\d{3}deg|low20_\d{3}deg|\d{2}_\d{3}deg_[a-z_]+|top', text))
    m = re.search(r'head (\d+)°', leaf['item'])
    if m:
        names.add(f'head_{int(m.group(1)):03d}deg')
    m = re.search(r'全身／頭部一致性 (\d+)°', leaf['item'])
    if m:
        names.add(f'head_{int(m.group(1)):03d}deg')
    return sorted(names)


def closeup_reference(photos, angle):
    """what the close-up at this angle should look like by the spec: the full-body view's head region (aimed at the
    head centre on the axis, frame BODY_FRAME / HEAD_ZOOM wide), enlarged HEAD_ZOOM times"""
    full = cv2.imread(os.path.join(photos, FULL[angle] + '.jpg'))
    if full is None:
        return None
    m = ct.segment(full)[0]
    rows = np.flatnonzero(m.any(1))
    t, b = rows[0], rows[-1]
    s = (b - t) / ct.SPEC_HEIGHT
    H, W = full.shape[:2]
    cx, cy = W / 2, t + 0.128 * ct.SPEC_HEIGHT / 1.65 * s
    half = W / ct.HEAD_ZOOM / 2
    M = np.float32([[ct.HEAD_ZOOM, 0, -ct.HEAD_ZOOM * (cx - half)], [0, ct.HEAD_ZOOM, -ct.HEAD_ZOOM * (cy - half)]])
    return cv2.warpAffine(full, M, (W, H), flags=cv2.INTER_CUBIC, borderValue=(255, 255, 255))


def make(photos, out, leaves):
    """write OUT/ai_fix_request for the photo leaves; returns its path, or None when no photo has to be redrawn"""
    todo = [d for d in leaves if d.get('owner') == '照片']
    if not todo:
        return None
    dst = os.path.join(out, 'ai_fix_request')
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    os.makedirs(os.path.join(dst, 'photos')); os.makedirs(os.path.join(dst, 'reference'))
    lines = ['# AI 修圖單', '',
             '這些照片沒有通過檢查，原因在照片本身。請照下面每一項重畫或修圖，其他照片不要動；',
             '修好後整組 33 張重新跑 `run_all.py`（新的輸出資料夾）。', '',
             '共同規格：同一個人物、同一套衣服與髮型、T-pose；光線固定在人身上；正交投影；',
             '全身圖畫面寬 1.95 m、對準身體中心（離地半個身高）；頭部特寫是同角度全身圖頭部的 4 倍放大，',
             '對準頭部中心（頭頂下 12.8 cm）。', '']
    by_photo = {}
    for d in todo:
        for p in photos_of(d) or ['（未指定照片）']:
            by_photo.setdefault(p, []).append(d)
    for p, ds in sorted(by_photo.items()):
        lines.append(f'## {p}.jpg')
        src = os.path.join(photos, p + '.jpg')
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(dst, 'photos', p + '.jpg'))
        for d in ds:
            lines += [f'- **問題**：{d["cause"]}（{d["item"]}，信心{d["confidence"]}）', f'- **怎麼修**：{d["action"]}']
            ev = d.get('evidence', {})
            nums = {k: v for k, v in ev.items() if k in ('dy_relative_mm', 'photo_11c_dy_mm', 'line')}
            if nums:
                lines.append('- **量到的數字**：' + '；'.join(f'{k} = {v}' for k, v in nums.items()))
        m = re.match(r'head_(\d{3})deg$', p)
        if m and int(m.group(1)) in FULL:
            ref = closeup_reference(photos, int(m.group(1)))
            if ref is not None:
                cv2.imwrite(os.path.join(dst, 'reference', p + '_應該的樣子.jpg'), ref, [cv2.IMWRITE_JPEG_QUALITY, 90])
                lines.append(f'- **參考圖**：`reference/{p}_應該的樣子.jpg` 是同角度全身圖的頭部依規格放大 4 倍：'
                             '五官的高度、左右位置、頭的大小要和它一樣（細節畫清楚即可）。')
        lines.append('')
    open(os.path.join(dst, 'AI修圖單.md'), 'w', encoding='utf-8').write('\n'.join(lines))
    return dst


def main(argv=None):
    a = argv or sys.argv[1:]
    if len(a) != 2:
        print(__doc__); return 2
    leaves = json.load(open(os.path.join(a[1], 'diagnosis.json')))
    p = make(a[0], a[1], leaves)
    print(p or '沒有要 AI 修的照片')
    return 0


if __name__ == '__main__':
    sys.exit(main())
