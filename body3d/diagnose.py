#!/usr/bin/env python3
"""diagnose.py — 未通過時的診斷樹（docs/Diagnosis-Tree.md）

每一個未通過項目沿著樹往下問，直到找到原因（葉）：誰要修（照片／程式）、怎麼修、信心多高、根據哪些數字。

    python diagnose.py photos PHOTOS_DIR OUT_DIR       # 關卡 1：照片檢查的未通過項目
    python diagnose.py prebake PHOTOS_DIR WORK_DIR     # 關卡 2：烘焙前檢查的臉部未通過項目（需要重建中間檔）

關卡 2「全身／頭部一致性」的樹用量測分支（完美照片校準，見文件）：
    1. 0° 也偏？                     是 → 全部角度一起偏：相機或偵測（程式）
    2. 左右偏移（45° 與 315° 反向）？  是 → 2a 頭部特寫環的對準點偏離旋轉軸，且大小對得上 → 程式（headreg）
                                          2b 對不上 → 臉部網格深度（程式）
    3. 上下偏移（扣掉偵測偏差）？      是 → 3a 照片第 11c 項量到同方向的上下差 → 照片（重畫特寫）
                                          3b 照片沒量到 → 程式
"""
import json
import os
import re
import sys
from pathlib import Path

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import check_turnaround as ct          # noqa: E402

# perfect photos (luna-v1 and the old test model, cameras known): dx -1.6..+1.3 px, dy -3.6..-5.9 px (detector bias
# between the 4x full-body crop and the close-up), head-ring aim z within 1 mm
BASE_DX, BASE_DY = 0.0, -5.0
TOL_PX = 4.0                           # residual beyond the baseline that counts as a real offset (body px)
AIM_Z_MM = 5.0                         # head-ring aim off the axis by more than this is a misfit
FULL = {0: '01_000deg_front', 45: '02_045deg_front_left', 315: '08_315deg_front_right'}


STAGE_NAME = {1: '階段 1 照片', 2: '階段 2 重建', 3: '階段 3 模型', 4: '階段 4 成品驗收'}
CONF_RANK = {'高': 0, '中': 1, '低': 2}


def leaf(item, path, cause, owner, action, confidence, evidence, stage=None):
    """stage: where the cause is (not the gate that caught it): photos are stage 1; the program leaves here are the
    reconstruction (stage 2)"""
    stage = stage or (1 if owner == '照片' else 2)
    return dict(item=item, path=path, cause=cause, owner=owner, action=action, confidence=confidence,
                evidence=evidence, stage=stage, stage_name=STAGE_NAME[stage])


def fix_order(leaves):
    """several FAILs: fix the earlier stage first, and within a stage the higher confidence first. A later stage
    is built on the earlier ones, so fixing the photos can change (or clear) what the reconstruction does; a
    high-confidence leaf is the one the measurements explain."""
    out = sorted(leaves, key=lambda d: (d['stage'], CONF_RANK.get(d['confidence'], 3)))
    return [dict(d, order=i + 1) for i, d in enumerate(out)]


# ---- gate 1: rule-based leaves (what each photo-check item measures says who fixes it)
PHOTO_RULES = [
    (r'^照片資料夾|^[A-E] (主環|俯視|俯角環|頭部特寫環|仰角環)|缺少|檔名', '缺照片，或檔名、格式不對', '照檔名規格補齊 33 張（2048 × 2048 小寫 .jpg，見 docs/Workflow-and-Validation.md#輸入照片）'),
    (r'斜角照是外殼形狀', '俯角／仰角照片是照水平環外殼填滿或渲染出來的，不是畫出來的人（手臂成扁平厚板，成品對不上照片）',
     'AI 重新生成這張（不能用渲染或投影）：同一個人、同一姿勢、真實的俯角 30°／仰角 20° 視角，人物在輪廓上限綠線以內、比綠線瘦'),
    (r'斜角照手臂', '這張斜角照的手臂和水平環的手臂不一樣（抬的高度、前後角度或長短）',
     '重畫這張，只改手臂：T-pose 手臂完全水平、和水平環同一高度、同樣筆直向兩側伸，手腕與手指方向相同'),
    (r'全視角外殼覆蓋|外殼切割', '俯角／仰角的照片和水平環對不上，一起雕會把身體切瘦（成品會比照片小）',
     '重畫切最多的那幾張俯角／仰角照片：和水平環同一個相機距離與構圖、身體中心在畫面正中央、正交投影、俯角 30°／仰角 20°'),
    (r'剪影$', '這張的人物輪廓超出其他照片推出的身體（藍色）：手臂姿勢、身形或透視和水平環不同',
     '重畫這張：和水平環同一姿勢（手臂水平、手腕與手指方向相同）、同一身形，正交投影；藍色落在哪個部位就修那裡（報告第 10 項、剪影對照圖）'),
    (r'\d+° vs \d+°|厚度|腳踝', '不同角度看到的身體形狀不一致（鏡像的兩張、左右厚度或腳踝對不上）',
     '重畫差最多的那一張：同一身形、同一姿勢，雙腳位置相同（照報告這一項指出的部位）'),
    (r'大小一致|人物高度|頭頂 / 腳底位置|構圖佔比', '各張人物的大小或上下位置不同：相機距離、構圖不一致',
     '重畫差最多的那幾張：所有全身圖同一個相機距離與構圖（畫面寬 1.95 m、身體中心在畫面正中央）'),
    (r'輪廓清晰度', '人物邊緣模糊（對焦、動態模糊或放大重取樣），去背邊界不準', '重新生成或用原解析度輸出這幾張，不要放大'),
    (r'灰白雜點', '照片上有 AI 留下的灰白色塊，重建時會被當成身體', '重畫或修掉這個色塊（報告寫了位置）'),
    (r'與主環一致性', '俯視圖和水平環對不上（髮髻、腳的位置或身形不同）', '重畫俯視圖：髮髻、腳的位置與身形和水平環相同'),
    (r'腳間距|頭部疑似重複', '姿勢或照片內容不對（雙腳距離不同、頭部特寫重複）', '照報告這一項的「→」重畫這張'),
    (r'頭部特寫鏡像', '相對的兩張頭部特寫（相差 180°）畫的不是同一顆頭（大小、後腦勺、髮髻、鼻子或下巴的位置不同），貼圖會貼歪',
     '兩張一起重畫：先畫好一張，另一張以它的左右鏡像為準（頭的大小、髮髻的位置與大小、鼻尖與下巴的高度相同）'),
    (r'臉部位置', '特寫的臉和同角度全身圖的位置不同', '重畫這張特寫：同角度全身圖頭部的 4 倍放大，五官位置一致（自動平移只修得了一部分，見文件）'),
    (r'頭部朝向|朝向', '臉的轉向和檔名角度不同', '重畫：頭朝正前方、只有相機繞著轉'),
    (r'^\s*\d+°$|角度', '雙手展開寬度推算的角度不對', '重畫這個角度：相機角度要和檔名相同'),
    (r'耳朵', '特寫的耳朵和全身圖不同', '重畫這張特寫：耳朵高度與前後位置和全身圖一致'),
    (r'亮度|明暗|光線|曝光', '光線跟著相機轉或亮度不同', '重畫：光線固定在人身上，各角度同一曝光'),
    (r'距離|放大倍率|寬度', '相機距離／構圖和規格不同', '重畫這張：所有全身圖同一距離，特寫固定 4 倍'),
    (r'對準|置中|頭頂位置', '相機沒有對準規格的點', '重畫這張：身體中心（或特寫的頭部中心）在畫面正中央'),
    (r'俯仰角|透視', '俯仰角或透視不對', '重畫這張：正交投影、俯角 30°／仰角 20°'),
    (r'翻轉', '左右翻轉複製', '重畫這張：不要用另一側翻轉'),
    (r'臉部|五官|髮高', '臉的比例和正面不同', '重畫這張特寫：同一個髮型、臉的大小與五官比例'),
]


FULL_NAMES = {0: '01_000deg_front', 45: '02_045deg_front_left', 90: '03_090deg_left', 135: '04_135deg_back_left',
              180: '05_180deg_back', 225: '06_225deg_back_right', 270: '07_270deg_right', 315: '08_315deg_front_right'}


def photos_in_label(label):
    """the one photo an item is about when its label says so: 'el30 45° 剪影' -> el30_045deg, '主環 90° 剪影' ->
    03_090deg_left. Labels that compare two photos ('low20 90° / 主環 90°', '45° vs 225°') name none: which one to
    redraw is in the line, not the label."""
    if '/' in label or ' vs ' in label:
        return []
    m = re.match(r'(\d+)°$', label)                    # the level ring's angle estimate: '45°'
    if m:
        return [FULL_NAMES[int(m.group(1))]] if int(m.group(1)) in FULL_NAMES else []
    m = re.match(r'(el30|low20|head|主環) (\d+)°', label)
    if not m:
        return []
    ring, a = m.group(1), int(m.group(2))
    return [FULL_NAMES[a]] if ring == '主環' and a in FULL_NAMES else [] if ring == '主環' else [f'{ring}_{a:03d}deg']


# a rule whose cause is in what the line measured, not in its label: (label, in the line, cause, action). First match wins,
# before PHOTO_RULES. R63-R72: '全視角外殼覆蓋' sent the AI to the tilted views' framing for ten rounds; the feet were off
LINE_RULES = [
    (r'全視角外殼覆蓋', '少掉的主要是腳', '各張全身照的腳畫得不一樣（腳尖的朝向、兩腳的前後或腳底的高度），一起雕會把前腳掌削掉，覆蓋率不足',
     '只修這幾張的腳，照「腳的位置」參考圖：藍色（別張有腳、這張沒畫到）補上，紅色（超出橘線）收掉，腳尖的朝向和水平照一致、腳底踩在同一條地面線上；'
     '身體其他部位、相機距離與構圖都不要動'),
    (r'全視角外殼覆蓋', '少掉的主要在手臂的上下緣', '各張水平照的手臂高度或粗細差了 1–2 cm，一起雕會把手臂的上下緣削掉，覆蓋率不足',
     '只修手臂：水平環斜角的那幾張（45°、135°、225°、315°），手臂完全水平、高度與粗細和正面照一致；相機距離與構圖不要動'),
]


def diagnose_photo_fails(fail_lines):
    out, seen = [], {}
    for line in fail_lines:
        label = re.split(r'[:：]', line, 1)[0].strip()
        rules = [(lp, c, a) for lp, inline, c, a in LINE_RULES if re.search(lp, label) and inline in line] + PHOTO_RULES
        for pat, cause, action in rules:
            if re.search(pat, label):
                names = re.findall(r'(?:el30|low20|head)_\d{3}deg|\d{2}_\d{3}deg_[a-z_]+|\btop\b(?=\.jpg)', line)  # photos named
                names += photos_in_label(label)
                if names:
                    action += '：' + '、'.join(dict.fromkeys(names))
                if (cause, action) in seen:                                   # the same finding at several angles
                    d = seen[(cause, action)]
                    d['item'] = re.sub(r'（\d+ 個角度）$', '', d['item']) + f'（{d["evidence"]["count"] + 1} 個角度）'
                    d['evidence']['count'] += 1
                    break
                d = leaf(label, ['關卡 1 照片檢查', f'項目：{label}'], cause, '照片', action, '高',
                         {'line': line, 'count': 1})
                seen[(cause, action)] = d
                out.append(d)
                break
        else:
            out.append(leaf(label, ['關卡 1 照片檢查', f'項目：{label}', '沒有對應的規則'], '未分類', '照片',
                            'AI 修圖：依報告「→」後面的建議重畫；診斷規則要補（AI 改程式）', '低', {'line': line}))
    return out


# ---- gate 2: measured branches for the full-body / close-up face consistency
def face_residuals(photos, work):
    """{angle: (dx, dy)} median landmark offset (body px, close-up ray through the mesh into the full-body view)"""
    cams = json.load(open(work / 'cams33.json'))
    with np.load(work / 'uvmesh.npz') as m:
        V, F = m['pos'], m['tri']
    tri = V[F[(V[F, 1] >= 1.36).any(axis=1)]]
    out = {}
    for a, body in FULL.items():
        head = f'head_{a:03d}deg'
        full = cv2.imread(str(photos / (body + '.jpg')))
        lm = work / ('face_lm33.npy' if a == 0 else f'face_lm33_{a:03d}.npy')
        if full is None or not lm.exists() or head not in cams or body not in cams:
            continue
        close = np.load(lm)
        pts = tri.reshape(-1, 3); pts = pts[pts[:, 1] >= ct.BODY_HEAD_MIN_HEIGHT]
        pr = np.column_stack(ct.camera_project(pts, cams[body])); lo, hi = pr.min(0), pr.max(0); mg = (hi - lo) * 0.16
        x0, y0 = np.maximum(np.floor(lo - mg), 0).astype(int)
        x1, y1 = np.minimum(np.ceil(hi + mg), list(full.shape[:2][::-1])).astype(int)
        roi = full[y0:y1, x0:x1]; sc = max(1.0, 512 / max(roi.shape[:2]))
        en = cv2.resize(roi, None, fx=sc, fy=sc, interpolation=cv2.INTER_CUBIC)
        L = ct.detect_face_landmarks(en)
        if L is None or isinstance(L, str):
            continue
        L = L * np.array([roi.shape[1] / en.shape[1], roi.shape[0] / en.shape[0]]) + [x0, y0]
        samples = ct.landmark_correspondences(tri, cams[head], cams[body], close[:, :2], L)
        d = [np.median(e - o, 0) for e, o in ct.group_landmark_samples(samples).values() if len(e) >= 3]
        if d:
            out[a] = tuple(float(v) for v in np.median(d, 0))
    return out, cams


def head_ring_aim_z(cams):
    """z (m) of the point the head close-up ring is aimed at, from the 45° / 315° cameras (orthographic)"""
    c45, c315 = cams['head_045deg'], cams['head_315deg']
    return (c45['cu'] - c315['cu']) / (2 * np.sin(np.radians(45)) * c45['s'])


def photo_face_offsets(photos):
    """11c in the photo plane: {angle: (dx mm, dy mm)} relative to 0°"""
    off = {}
    for a, body in FULL.items():
        full = cv2.imread(str(photos / (body + '.jpg'))); close = cv2.imread(str(photos / f'head_{a:03d}deg.jpg'))
        if full is None or close is None:
            return {}
        o = ct.face_offset(full, ct.segment(full)[0], close)
        if o is None or isinstance(o, str):
            return {}
        off[a] = o
    return {a: tuple(float(v) for v in off[a] - off[0]) for a in (45, 315)}


def head_pair_leaves(fail_lines):
    """'頭部特寫相鄰一致 head_045deg / head_090deg' FAILs: two neighbouring close-ups disagree on the cheek / jaw. The
    close-up in two disagreeing pairs is the one to redraw (both of a pair when no close-up is in two)."""
    pairs = [re.findall(r'head_(\d{3})deg', l)[:2] for l in fail_lines if '頭部特寫相鄰一致' in l]
    pairs = [p for p in pairs if len(p) == 2]
    if not pairs:
        return []
    count = {}
    for a, b in pairs:
        count[a] = count.get(a, 0) + 1; count[b] = count.get(b, 0) + 1
    redo = [a for a in sorted(count) if count[a] >= 2] or sorted(count)
    if len(pairs) >= ct.HEAD_PAIR_RING:               # most of the ring disagrees: all eight, whoever is in two pairs
        redo = [f'{a:03d}' for a in range(0, 360, 45)]
    names = [f'head_{a}deg' for a in redo]
    return [leaf('頭部特寫相鄰一致', ['關卡 2 烘焙前檢查', '相鄰兩張頭部特寫在同一塊皮膚上不一致',
                 f'不一致的組：{"、".join(f"{a}°/{b}°" for a, b in pairs)}'],
                 '相鄰角度的頭部特寫把臉頰、下巴畫得不一樣（位置、形狀或明暗），烘焙後側面糊成一塊', '照片',
                 '重畫：' + '、'.join(names) + '。' + ct.head_pair_advice(len(names)),
                 '高', {'pairs': ['/'.join(p) for p in pairs]})]


def front_oblique_leaves(fail_lines):
    """'正面／斜面一致性 head_045deg' FAILs: after the face relief the frontal close-up's features still do not land on
    this 3/4 close-up's. The 3/4 close-up is the one to redraw."""
    names = list(dict.fromkeys(n for l in fail_lines if '正面／斜面一致性' in l for n in re.findall(r'head_\d{3}deg', l)[:1]))
    if not names:
        return []
    mm = [float(v) for l in fail_lines if '正面／斜面一致性' in l for v in re.findall(r'→ ([\d.]+) mm', l)[:1]]
    return [leaf('正面／斜面一致性', ['關卡 2 烘焙前檢查', '正面特寫的五官搬到斜面特寫上對不到',
                 '臉的起伏已經照特徵點補過，剩下的差是照片之間的差'],
                 '斜面特寫把臉畫得和正面特寫不一樣（大小、長度或五官高度），湊不成同一張臉', '照片',
                 '重畫：' + '、'.join(names) + '。' + ct.front_oblique_advice(), '中',
                 {'photos': names, 'median_mm': mm})]


def diagnose_prebake(photos, work, fail_lines=None):
    """fail_lines: the pre-bake check's [FAIL] lines; None = the head / body consistency tree only (older callers)"""
    photos, work = Path(photos), Path(work)
    pair = head_pair_leaves(fail_lines or []) + front_oblique_leaves(fail_lines or [])
    if fail_lines is not None and all('頭部特寫相鄰一致' in l or '正面／斜面一致性' in l for l in fail_lines):
        return pair                                   # nothing else failed: no face-residual tree
    res, cams = face_residuals(photos, work)
    out = list(pair)
    if 0 not in res or 45 not in res or 315 not in res:
        return pair + [leaf('全身／頭部一致性', ['關卡 2 烘焙前檢查', '量不到 0° / 45° / 315° 的五官'], '五官偵測失敗', '程式',
                     'AI 改程式：檢查臉部特徵點步驟（face_landmarks / face33）', '低', {'measured': list(res)})]
    s = cams[FULL[45]]['s']
    r0 = (res[0][0] - BASE_DX, res[0][1] - BASE_DY)
    ev = dict(residual_px={a: [round(v, 1) for v in res[a]] for a in res}, baseline_px=[BASE_DX, BASE_DY])
    if abs(r0[0]) > TOL_PX or abs(r0[1]) > TOL_PX:
        out.append(leaf('全身／頭部一致性 0°', ['關卡 2', '1. 0° 也偏 → 是'], '全部角度一起偏：相機或五官偵測',
                        '程式', 'AI 改程式：檢查相機（全身與特寫環的對準點、比例）與特徵點步驟', '中', ev))
    # 2. horizontal: depth errors show up opposite at 45° and 315° (orthographic, level: dx = -sin(phi) * depth error)
    anti = (res[45][0] - res[315][0]) / 2
    if abs(anti) > TOL_PX:
        qz = head_ring_aim_z(cams)
        predicted = -qz * np.sin(np.radians(45)) * s          # dx at 45° caused by the ring aim being off the axis
        e2 = dict(ev, antisymmetric_dx_px=round(anti, 1), head_ring_aim_z_mm=round(1000 * qz, 1),
                  predicted_dx_px=round(predicted, 1))
        if abs(1000 * qz) > AIM_Z_MM and abs(anti - predicted) < 0.35 * abs(anti):
            out.append(leaf('全身／頭部一致性 45° / 315° 左右', ['關卡 2', '2. 左右偏移、45° 與 315° 反向 → 是',
                            f'2a. 頭部特寫環對準點 z = {1000 * qz:+.1f} mm（完美照片 ±1 mm），預測 {predicted:+.1f} px、實測 {anti:+.1f} px → 對得上'],
                            '頭部特寫相機環的對準點被擬合到旋轉軸前後（headreg 用剪影擬合，頭髮／髮髻造成）', '程式',
                            'AI 改程式：照片檢查通過時，把頭部特寫環的對準點固定在旋轉軸上（和全身環一樣；headreg 1.40 已修，再出現表示退步）', '高', e2))
        else:
            out.append(leaf('全身／頭部一致性 45° / 315° 左右', ['關卡 2', '2. 左右偏移、45° 與 315° 反向 → 是',
                            f'2b. 對準點 z = {1000 * qz:+.1f} mm 解釋不了（預測 {predicted:+.1f} px、實測 {anti:+.1f} px）'],
                            '臉部網格的前後深度不對', '程式', 'AI 改程式：檢查臉部深度（face33 / 網格）', '中', e2))
    # 3. vertical: depth does not move a level orthographic view up or down
    p11 = photo_face_offsets(photos)
    for a in (45, 315):
        dy = res[a][1] - BASE_DY - r0[1]                          # relative to 0°, like 11c
        if abs(dy) <= TOL_PX:
            continue
        dy_mm = 1000 * dy / s
        e3 = dict(ev, dy_relative_px=round(dy, 1), dy_relative_mm=round(dy_mm, 1),
                  photo_11c_dy_mm=round(p11[a][1], 1) if a in p11 else None)
        if a in p11 and np.sign(p11[a][1]) == np.sign(dy_mm) and abs(p11[a][1]) >= 0.4 * abs(dy_mm):
            out.append(leaf(f'全身／頭部一致性 {a}° 上下', ['關卡 2', '3. 上下偏移（扣掉偵測偏差、以 0° 為準）→ 是',
                            f'3a. 照片第 11c 項上下差 {p11[a][1]:+.1f} mm，同方向 → 照片'],
                            f'{a}° 特寫的臉和全身圖的臉上下位置不同', '照片',
                            f'重畫 head_{a:03d}deg：同角度全身圖頭部的 4 倍放大，眼鼻嘴高度一致', '高', e3))
        else:
            out.append(leaf(f'全身／頭部一致性 {a}° 上下', ['關卡 2', '3. 上下偏移 → 是', '3b. 照片沒量到同方向的差 → 程式'],
                            '特寫相機的上下對準或比例不對', '程式', 'AI 改程式：檢查頭部特寫環的上下對準（headreg）', '中', e3))
    if len(out) == len(pair):
        out.append(leaf('全身／頭部一致性', ['關卡 2', '1–3 都沒有超過門檻'], '五官位置在門檻附近或亮度造成', '程式',
                        '看亮度差（P90）與疊圖', '低', ev))
    return out


# ---- gate 4: the finished body against the full-body photos (fit_report.json)
FIT_LIST = 6                           # the worst views go on the retouch request; the rest are counted


def fit_direction(row):
    """what the extra / missing pixels say about one view (extra: the model outside the photo's outline; missing:
    the person in the photo where the model is not)"""
    ex, mi = row.get('extra', 0), row.get('missing', 0)
    if ex > 1.5 * mi:
        return ('模型超出這張照片的輪廓：照片上的人比其他角度畫得瘦、小，或位置偏了',
                '人物的大小、位置照規格（畫面寬 1.95 m、對準身體中心），身體和手臂的粗細和其他角度一致')
    if mi > 1.5 * ex:
        return ('這張照片上的人有一部分模型沒有：照片畫得比其他角度胖、大，或手臂／腳伸到別的位置，重建時被其他照片切掉',
                '把人物畫在其他角度看得到的範圍裡：大小、手臂和腳的位置與水平環一致，不要畫得比其他角度寬')
    return ('多出與缺少差不多：人物的位置、姿勢或比例和其他角度對不上（不是單純大小）',
            '照規格相機重畫：人物置中、T-pose 手臂水平、腳的位置與水平環一致')


def diagnose_fit(out):
    """gate 4 FAIL: the finished body misses the full-body photos. The worst views are the photos to redraw (the hull
    is carved by all of them, so one inconsistent photo cuts the body that the others see)."""
    try:
        rep = json.load(open(os.path.join(out, 'fit_report.json'), encoding='utf-8'))
    except (OSError, ValueError):
        return []
    if rep.get('level') != 'FAIL':
        return []
    import fit_report
    rows = sorted(rep.get('rows', []), key=lambda r: -r['xor'])
    over = [r for r in rows if r['xor'] > fit_report.VIEW_WARN]
    pick = over[:FIT_LIST] or rows[:3]
    diag = [r for r in rows if re.search(r'_(045|135|225|315)deg', r['view'])]
    rest = [r for r in rows if r not in diag]
    note = ''
    if diag and rest and np.mean([r['xor'] for r in diag]) > 1.3 * np.mean([r['xor'] for r in rest]):
        level = '、'.join('%s %.0f%%' % (r['view'], 100 * r['xor']) for r in diag if r.get('kind') == 'main')
        note = ('。斜 45° 的角度（045 / 135 / 225 / 315）在每一環都最差' + (f'，水平環的斜角圖也偏（{level}）' if level else '')
                + '：斜角環和水平環對不上，外殼在斜角被切掉。斜角照要照水平環畫（參考圖的綠線）')
    more = len(over) - len(pick)
    if more > 0:
        note += f'。另外 {more} 張也超過 {100 * fit_report.VIEW_WARN:.0f}%：先修這 {len(pick)} 張，重跑後再看'
    out_ = []
    for r in pick:
        cause, how = fit_direction(r)
        out_.append(leaf(f'最終剪影 {r["view"]}', ['關卡 4 最終驗收', f'平均不一致 {100 * rep["mean"]:.1f}% > 10%',
                         f'{r["view"]} 不一致 {100 * r["xor"]:.1f}%（單張應 ≤ {100 * fit_report.VIEW_WARN:.0f}%）'],
                         cause + (note if r is pick[0] else ''), '照片', f'重畫 {r["view"]}：{how}', '中',
                         dict(xor_percent=round(100 * r['xor'], 1), extra_px=r['extra'], missing_px=r['missing'],
                              mean_percent=round(100 * rep['mean'], 1),
                              other_views_over=more if more > 0 else 0)))
    return out_


def main(argv=None):
    import argparse
    import subprocess
    ap = argparse.ArgumentParser(description='未通過項目的診斷樹')
    ap.add_argument('gate', choices=['photos', 'prebake'])
    ap.add_argument('photos'); ap.add_argument('dir')
    a = ap.parse_args(argv)
    if a.gate == 'prebake':
        res = diagnose_prebake(a.photos, a.dir)
    else:
        import deliver
        r = subprocess.run([sys.executable, os.path.join(HERE, 'check_turnaround.py'), a.photos, '--out',
                            os.path.join(a.dir, 'diagnose_check.png')], capture_output=True, text=True)
        res = diagnose_photo_fails(deliver.fail_lines(r.stdout))
    for d in fix_order(res):
        print(f"{d['order']}. [{d['stage_name']}｜{d['owner']}｜信心{d['confidence']}] {d['item']}：{d['cause']}\n"
              f"    路徑：{' → '.join(d['path'])}\n    怎麼修：{d['action']}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
