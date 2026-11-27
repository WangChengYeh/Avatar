#!/usr/bin/env python3
"""ai_request.py — 交給 AI 的工作單（docs/SOP.md：人只準備輸入與 token，修圖、改程式都由 AI 做）

AI 修圖單（照片的問題，交給 AI 生圖／修圖）：

    OUT/ai_fix_request/
        AI修圖單.md                 每一張要修的照片：問題、怎麼修、量到的數字
        photos/                     要修的原圖
        reference/                  參考圖（特寫：同角度全身圖的頭部，依規格裁切放大 4 倍，臉應該在的位置）

AI 改 code 單（程式的問題，交給 AI 寫程式）：
    OUT/ai_code_request/
        AI改code單.md               每一項：原因所在的階段、原因、路徑與數字、要改的檔、要補的檢查、驗收方式
        diagnosis.json / gates.json / run_all.log   重現與驗證用

一次只出一個階段的單（診斷 SOP：前面階段先修）：照片有問題時只出 AI 修圖單，程式的單等照片修好、重跑後再出。
run_all.py 在關卡未通過時自動產生，並放進該階段的結果包；也可以單獨執行：
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


def tilted_reference(photos, name, vs=0.01):
    """the tilted photo with the outline the level ring implies (green): the body the eight level photos carve,
    seen by the spec camera of this tilted view. Where the person reaches past the green line, the level ring and
    this photo disagree and the reconstruction cuts the body."""
    m_ = re.match(r'(el30|low20)_(\d{3})deg$', name)
    if not m_:
        return None
    ring, a = m_.group(1), int(m_.group(2))
    im = cv2.imread(os.path.join(photos, name + '.jpg'))
    if im is None:
        return None
    masks = {}
    for ang, f in FULL.items():
        full = cv2.imread(os.path.join(photos, f + '.jpg'))
        if full is None:
            return None
        masks[ang] = ct.segment(full)[0]
    hs = [np.ptp(np.flatnonzero(m.any(1))) for m in masks.values()]
    s = float(np.median(hs)) / ct.SPEC_HEIGHT
    xs = np.arange(-0.95, 0.95, vs) + vs / 2; ys = np.arange(0, 1.72, vs) + vs / 2; zs = np.arange(-0.42, 0.42, vs) + vs / 2
    X, Y, Z = np.meshgrid(xs, ys, zs, indexing='ij')
    Q = np.stack([X.ravel(), Y.ravel() - ct.SPEC_HEIGHT / 2, Z.ravel()], 1)
    votes = np.zeros(len(Q), np.uint8)
    for ang, m in masks.items():
        H, W = m.shape; r, u = ct._spec_axes(ang, 0.0)
        c = np.round(W / 2 + s * (Q @ r)).astype(int); w = np.round(H / 2 - s * (Q @ u)).astype(int)
        ok = (c >= 0) & (c < W) & (w >= 0) & (w < H)
        votes += ok & (m[np.clip(w, 0, H - 1), np.clip(c, 0, W - 1)] > 0)
    P = Q[votes >= len(masks) - 1]
    H, W = im.shape[:2]; r, u = ct._spec_axes(a, ct.RING_TILT[ring])
    c = np.round(W / 2 + s * (P @ r)).astype(int); w = np.round(H / 2 - s * (P @ u)).astype(int)
    ok = (c >= 0) & (c < W) & (w >= 0) & (w < H)
    sil = np.zeros((H, W), np.uint8); sil[w[ok], c[ok]] = 255
    k = 2 * int(np.ceil(s * vs)) + 1
    sil = cv2.morphologyEx(sil, cv2.MORPH_CLOSE, np.ones((k, k), np.uint8))
    cnt, _ = cv2.findContours(sil, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    out = im.copy()
    cv2.drawContours(out, cnt, -1, (0, 170, 0), max(3, W // 500))
    return out


def _full_body_view(name):
    """(azimuth, tilt) of a full-body photo by its name, or None"""
    m_ = re.match(r'(el30|low20)_(\d{3})deg$', name)
    if m_:
        return int(m_.group(2)), ct.RING_TILT[m_.group(1)]
    m_ = re.match(r'\d{2}_(\d{3})deg_', name)
    return (int(m_.group(1)), 0.0) if m_ else None


def _level_masks(photos):
    good = {}
    for ang, f in FULL.items():
        full = cv2.imread(os.path.join(photos, f + '.jpg'))
        if full is not None:
            good[ang] = dict(m=ct.segment(full)[0], name=f + '.jpg')
    return good


def feet_reference(photos, name, good=None):
    """the feet of this full-body photo, enlarged, with the reference feet (orange line: the feet the level front,
    back and side photos agree on, seen from this photo's angle) and what the photo draws outside them (red)"""
    view = _full_body_view(name)
    im = cv2.imread(os.path.join(photos, name + '.jpg'))
    if view is None or im is None:
        return None
    fr = ct.feet_reference(good or _level_masks(photos))
    if not fr:
        return None
    share, T, out = ct.feet_outside(ct.segment(im)[0], fr[0], fr[1], view[0], view[1])
    if not T.any():
        return None
    pic = im.copy()
    pic[out] = (0.35 * pic[out] + 0.65 * np.array((40, 40, 230))).astype(np.uint8)
    cnt, _ = cv2.findContours(T, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    cv2.drawContours(pic, cnt, -1, (0, 140, 255), max(3, im.shape[1] // 600))
    ys, xs = np.nonzero(T | out.astype(np.uint8))
    half = int(max(np.ptp(xs), np.ptp(ys)) * 0.75) + 60
    cy, cx = int(ys.mean()), int(xs.mean())
    y0, x0 = max(0, min(im.shape[0] - 2 * half, cy - half)), max(0, min(im.shape[1] - 2 * half, cx - half))
    crop = pic[y0:y0 + 2 * half, x0:x0 + 2 * half]
    return cv2.resize(crop, (1024, 1024), interpolation=cv2.INTER_CUBIC)


def coverage_overview(photos):
    """the eight level photos with what the all-view hull does not cover in red: where the body is carved away"""
    good = _level_masks(photos)
    extra = {}
    for ring in ct.RING_TILT:
        for a in range(0, 360, 45):
            im = cv2.imread(os.path.join(photos, f'{ring}_{a:03d}deg.jpg'))
            if im is not None:
                extra.setdefault(ring, {})[a] = dict(m=ct.segment(im)[0], name=f'{ring}_{a:03d}deg.jpg')
    if len(good) < 8 or not extra:
        return None
    lost = ct.all_view_hull(good, extra)[3]
    tiles = []
    for a in sorted(good):
        m = lost[a]['mask']; t = cv2.resize(cv2.imread(os.path.join(photos, FULL[a] + '.jpg')), (m.shape[1], m.shape[0]))
        t[m] = (40, 40, 230)
        cv2.putText(t, f'{a} deg', (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 2, cv2.LINE_AA)
        tiles.append(t)
    return np.vstack([np.hstack(tiles[:4]), np.hstack(tiles[4:])])


def arm_reference(photos, name):
    """the tilted photo with its arm_mask drawn in orange: where the arms should be"""
    im = cv2.imread(os.path.join(photos, name + '.jpg'))
    arm = arm_mask(photos, name)
    if im is None or arm is None:
        return None
    out = im.copy()
    out[arm] = (0.45 * out[arm] + 0.55 * np.array((0, 140, 255))).astype(np.uint8)
    cnt, _ = cv2.findContours(arm.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    cv2.drawContours(out, cnt, -1, (0, 100, 230), max(3, im.shape[1] // 600))
    return out


def arm_mask(photos, name, step=0.004):
    """where the arms of this tilted view should be: the arms the reconstruction builds (arms33: past 20 cm from the
    axis, height from the front view, depth from the top view), elliptical in cross-section, seen by the spec camera
    of this view, as a mask. R47: a +30° view whose near arm was drawn a few cm too high; the
    hull outline is fat around the arms, so the photo's arm sat inside it and looked right."""
    m_ = re.match(r'(el30|low20)_(\d{3})deg$', name)
    if not m_:
        return None
    ring, a = m_.group(1), int(m_.group(2))
    im = cv2.imread(os.path.join(photos, name + '.jpg'))
    front, top = (cv2.imread(os.path.join(photos, f + '.jpg')) for f in (FULL[0], 'top'))
    if im is None or front is None or top is None:
        return None
    mf, mt = ct.segment(front)[0].astype(bool), ct.segment(top)[0].astype(bool)
    H, W = mf.shape
    rows = np.flatnonzero(mf.any(1))
    s = (rows[-1] - rows[0]) / ct.SPEC_HEIGHT                       # px per m, front view
    tc, fc = np.flatnonzero(mt.any(0)), np.flatnonzero(mf.any(0))
    if not len(tc) or not len(fc):
        return None
    st = (tc[-1] - tc[0]) / ((fc[-1] - fc[0]) / s)                  # px per m, top view (same arm span)
    tcx = (tc[-1] + tc[0]) / 2
    band = mt[:, int(tcx - 0.10 * st):int(tcx + 0.10 * st)].any(1)
    tr = np.flatnonzero(band)
    trc = (tr[0] + tr[-1]) / 2                                     # the torso's depth centre (front toward the bottom)
    arm_x = 0.20 * ct.SPEC_HEIGHT / 1.65
    P = []
    for x in np.arange(-1.0, 1.0, step):
        if abs(x) < arm_x:
            continue
        c, ctp = int(round(W / 2 + s * x)), int(round(tcx + st * x))
        if not (0 <= c < W and 0 <= ctp < mt.shape[1]) or not mf[:, c].any() or not mt[:, ctp].any():
            continue
        r = np.flatnonzero(mf[:, c])
        y0, y1 = (H / 2 - r[-1]) / s, (H / 2 - r[0]) / s           # relative to the body centre
        if y1 - y0 > 0.25:                                         # a body column, not an arm
            continue
        zr = np.flatnonzero(mt[:, ctp])
        zc, zh = ((zr[0] + zr[-1]) / 2 - trc) / st, (zr[-1] - zr[0]) / 2 / st
        for t in np.linspace(0, 2 * np.pi, 48, endpoint=False):
            P.append((x, (y0 + y1) / 2 + (y1 - y0) / 2 * np.sin(t), zc + zh * np.cos(t)))
    if not P:
        return None
    P = np.array(P)
    r_, u_ = ct._spec_axes(a, ct.RING_TILT[ring])
    col = np.round(W / 2 + s * (P @ r_)).astype(int); row = np.round(H / 2 - s * (P @ u_)).astype(int)
    ok = (col >= 0) & (col < W) & (row >= 0) & (row < H)
    arm = np.zeros((H, W), np.uint8); arm[row[ok], col[ok]] = 1
    return cv2.morphologyEx(arm, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8)) > 0


def make(photos, out, leaves):
    """write OUT/ai_fix_request for the photo leaves; returns its path, or None when no photo has to be redrawn"""
    todo = sorted([d for d in leaves if d.get('owner') == '照片'],
                  key=lambda d: (d.get('stage', 1), {'高': 0, '中': 1, '低': 2}.get(d.get('confidence'), 3)))
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
    lines += ['順序：信心高的先修（照片都在階段 1；程式的問題不在這張單上，等照片修好重跑後再看）。', '']
    by_photo = {}
    for d in todo:
        for p in photos_of(d) or ['（未指定照片）']:
            by_photo.setdefault(p, []).append(d)
    if any('全視角外殼覆蓋' in d['item'] for d in todo):
        ov = coverage_overview(photos)
        if ov is not None:
            cv2.imwrite(os.path.join(dst, 'reference', '外殼覆蓋_少掉的部分.jpg'), ov, [cv2.IMWRITE_JPEG_QUALITY, 90])
            lines += ['**先看這張**：`reference/外殼覆蓋_少掉的部分.jpg`。8 張水平全身照上的紅色，是全部照片一起雕之後沒被蓋住的地方：',
                      '紅色在哪個部位，就是各張照片在那個部位對不上（下面每一項寫了要修哪幾張的哪裡）。', '']
    level_masks = None
    for k, (p, ds) in enumerate(by_photo.items(), 1):
        lines.append(f'## {k}. {p}.jpg')
        src = os.path.join(photos, p + '.jpg')
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(dst, 'photos', p + '.jpg'))
        for d in ds:
            lines += [f'- **問題**：{d["cause"]}（{d["item"]}，信心{d["confidence"]}）', f'- **怎麼修**：{d["action"]}']
            ev = d.get('evidence', {})
            nums = {k: v for k, v in ev.items() if k in ('dy_relative_mm', 'photo_11c_dy_mm', 'line', 'xor_percent', 'extra_px', 'missing_px')}
            if nums:
                lines.append('- **量到的數字**：' + '；'.join(f'{k} = {v}' for k, v in nums.items()))
        if any('腳的位置' in d['action'] for d in ds) and _full_body_view(p):
            level_masks = level_masks or _level_masks(photos)
            fref = feet_reference(photos, p, level_masks)
            if fref is not None:
                cv2.imwrite(os.path.join(dst, 'reference', p + '_腳的位置.jpg'), fref, [cv2.IMWRITE_JPEG_QUALITY, 90])
                lines.append(f'- **腳的參考圖**：`reference/{p}_腳的位置.jpg`（這張照片的腳，放大）：橘線是正面、背面、左右側面四張水平照決定的腳，'
                             '從這個角度看的範圍，是**上限**：腳要畫在橘線以內（斜角看橘線會比真的腳寬，不要填滿）。紅色是這張的腳超出橘線的'
                             '部分：把它收回橘線內，通常是腳尖的朝向、兩腳一前一後、或腳底畫得比其他張低。只改腳，小腿以上不要動。')
        if re.match(r'(el30|low20)_\d{3}deg$', p):
            ref = tilted_reference(photos, p)
            if ref is not None:
                cv2.imwrite(os.path.join(dst, 'reference', p + '_輪廓上限.jpg'), ref, [cv2.IMWRITE_JPEG_QUALITY, 90])
                if any('斜角照手臂' in d['item'] for d in ds):
                    aref = arm_reference(photos, p)
                    if aref is not None:
                        cv2.imwrite(os.path.join(dst, 'reference', p + '_手臂位置.jpg'), aref, [cv2.IMWRITE_JPEG_QUALITY, 90])
                        lines.append(f'- **手臂參考圖**：`reference/{p}_手臂位置.jpg`：橘色是手臂應該在的位置（重建時手臂只用正面與俯視照建，'
                                     '這是它從這個角度看的樣子）。把手臂畫在橘色裡：從斜上方（俯角）看，伸向鏡頭那隻水平的手臂在畫面上'
                                     '會往手的方向斜向下、而且比肩膀低；從斜下方（仰角）看則相反。不要把手臂畫得在畫面上看起來水平或抬高。')
                lines.append(f'- **參考圖**：`reference/{p}_輪廓上限.jpg`：綠線是 8 張水平全身圖用規格相機雕出的外殼、從這個角度看的'
                             '輪廓，是**上限**：人物的位置、大小、俯仰要和綠線一致，整個人要在綠線以內；超出綠線的部分重建時會被切掉。'
                             '真實的身體比綠線瘦（水平環看不到手臂上下、身體斜角的厚度，外殼在那裡是方塊或厚板），所以人物不會貼滿綠線。'
                             '**不要**把綠線填滿、不要用外殼或重建模型渲染／投影產生照片：那樣的照片過不了第 10i 項「斜角照是外殼形狀」。')
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


# which files hold a stage's check and its program (for the AI that changes the code)
STAGE_FILES = {
    1: ('body3d/check_turnaround.py（照片檢查）', 'AI 生圖規格（docs/Workflow-and-Validation.md#生圖規格）'),
    2: ('body3d/check_turnaround.py 的烘焙前檢查（--head-overlap-work：report_head_overlap 起）、body3d/diagnose.py',
        'body3d/steps/cams33.py、refine33.py、arms33.py、round33.py、legs33.py、mesh33s.py、headreg33.py、'
        'face_landmarks.py、face33.py、bl_uv33s.py、camera.py'),
    3: ('body3d/verify_glb.py', 'body3d/steps/bake33.py、bl_export.py、joints.py、rig.py、glb_unlit.py'),
    4: ('body3d/fit_report.py', '最早出錯的那一步（依 README 的 Loop engineering 第 2 步往前找）'),
}


def make_code(out, leaves, photos=None):
    """write OUT/ai_code_request for the program leaves of the earliest stage in the fix order; returns its path or
    None (no program leaf, or photos come first)"""
    todo = [d for d in leaves if d.get('owner') != '照片']
    if not todo or any(d.get('owner') == '照片' for d in leaves):
        return None
    first = min(d.get('stage', 2) for d in todo)
    todo = sorted([d for d in todo if d.get('stage', 2) == first], key=lambda d: d.get('order', 99))
    dst = os.path.join(out, 'ai_code_request')
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    os.makedirs(dst)
    for f in ('diagnosis.json', 'gates.json', 'run_all.log', 'autofix.json'):
        if os.path.exists(os.path.join(out, f)):
            shutil.copy2(os.path.join(out, f), os.path.join(dst, f))
    check_file, code_files = STAGE_FILES.get(first, STAGE_FILES[4])
    L = ['# AI 改 code 單', '',
         f'診斷樹判定下面 {len(todo)} 項是**程式**的問題，原因在**階段 {first}**。照診斷 SOP（docs/Diagnosis-Tree.md#診斷-sop）'
         '在這個階段裡修，完成後開 PR。', '',
         '## 重現', '',
         '```sh', f'python body3d/run_all.py {photos or "PHOTOS"} OUTPUT-新目錄 --name body', '```', '',
         '同一個資料夾裡有 `diagnosis.json`（診斷葉子與數字）、`gates.json`（各關卡數字）、`run_all.log`。', '',
         '## 要修的項目（照順序）', '']
    for k, d in enumerate(todo, 1):
        L += [f'### {k}. {d["item"]}（信心{d["confidence"]}）', '',
              f'- **原因**：{d["cause"]}', f'- **方向**：{d["action"]}',
              f'- **診斷路徑**：{" → ".join(d["path"])}',
              '- **數字**：`' + json.dumps(d.get('evidence', {}), ensure_ascii=False) + '`', '']
    L += ['## 怎麼做（照順序）', '',
          f'1. **補檢查**：在這個階段的檢查（{check_file}）加一項或改一項，讓它抓得到上面的問題：用這組照片會 FAIL，'
          '用兩組完美照片（`tests/data/luna-v1.glb` 與舊測試模型，用 `tests/render_synth.py` 渲染）仍是 0 FAIL／0 WARN。'
          '把新項目的門檻與兩組完美照片的數字寫在程式註解裡。',
          f'2. **修程式**：在這個階段的程式（{code_files}）裡修，不在後面的步驟補。',
          '3. **驗收**：',
          '   - 這組照片：第 1 步的檢查從 FAIL 變 PASS；如果照片本身也有問題，診斷會改出 AI 修圖單，那是下一輪。',
          '   - 兩組完美照片從頭跑 `run_all.py`：四道關卡全部 0 FAIL／0 WARN、可交付。',
          '   - `pytest -q` 相關測試通過；新檢查加一個測試（壞的情況 FAIL、完美照片 PASS）。',
          '4. **開 PR**：寫清楚診斷葉子、補的檢查（前後數字）、改了什麼、驗收結果；更新 CHANGELOG 與 docs/Diagnosis-Tree.md。',
          '5. 這一階段的單做完，用新的輸出資料夾從頭重跑，看新的診斷。', '',
          '不能用手動修正（例如改 cams33.json、改中間檔）代替改程式：那樣的結果無法重現，也不能交付。']
    open(os.path.join(dst, 'AI改code單.md'), 'w', encoding='utf-8').write('\n'.join(L))
    return dst


def main(argv=None):
    a = argv or sys.argv[1:]
    if len(a) != 2:
        print(__doc__); return 2
    leaves = json.load(open(os.path.join(a[1], 'diagnosis.json')))
    p = make(a[0], a[1], leaves)
    c = make_code(a[1], leaves, a[0])
    print(p or c or '沒有要交給 AI 的工作')
    return 0


if __name__ == '__main__':
    sys.exit(main())
