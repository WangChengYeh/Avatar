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
    (r'全視角外殼覆蓋|外殼切割', '俯角／仰角的照片和水平環對不上，一起雕會把身體切瘦（成品會比照片小）',
     '重畫切最多的那幾張俯角／仰角照片：和水平環同一個相機距離與構圖、身體中心在畫面正中央、正交投影、俯角 30°／仰角 20°'),
    (r'臉部位置', '特寫的臉和同角度全身圖的位置不同', '重畫這張特寫：同角度全身圖頭部的 4 倍放大，五官位置一致（自動平移只修得了一部分，見文件）'),
    (r'頭部朝向|朝向', '臉的轉向和檔名角度不同', '重畫：頭朝正前方、只有相機繞著轉'),
    (r'^\s*\d+°|角度', '雙手展開寬度推算的角度不對', '重畫這個角度：相機角度要和檔名相同'),
    (r'耳朵', '特寫的耳朵和全身圖不同', '重畫這張特寫：耳朵高度與前後位置和全身圖一致'),
    (r'表面亮度|明暗|光線|曝光', '光線跟著相機轉或亮度不同', '重畫：光線固定在人身上，各角度同一曝光'),
    (r'距離|放大倍率|寬度', '相機距離／構圖和規格不同', '重畫這張：所有全身圖同一距離，特寫固定 4 倍'),
    (r'對準|置中|頭頂位置', '相機沒有對準規格的點', '重畫這張：身體中心（或特寫的頭部中心）在畫面正中央'),
    (r'俯仰角|透視', '俯仰角或透視不對', '重畫這張：正交投影、俯角 30°／仰角 20°'),
    (r'翻轉', '左右翻轉複製', '重畫這張：不要用另一側翻轉'),
    (r'臉部|五官|髮高', '臉的比例和正面不同', '重畫這張特寫：同一個髮型、臉的大小與五官比例'),
]


def diagnose_photo_fails(fail_lines):
    out, seen = [], {}
    for line in fail_lines:
        label = line.split(':', 1)[0].strip()
        for pat, cause, action in PHOTO_RULES:
            if re.search(pat, label):
                names = re.findall(r'(?:el30|low20)_\d{3}deg', line)          # photos the check names (10i culprits)
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


def diagnose_prebake(photos, work):
    photos, work = Path(photos), Path(work)
    res, cams = face_residuals(photos, work)
    out = []
    if 0 not in res or 45 not in res or 315 not in res:
        return [leaf('全身／頭部一致性', ['關卡 2 烘焙前檢查', '量不到 0° / 45° / 315° 的五官'], '五官偵測失敗', '程式',
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
    if not out:
        out.append(leaf('全身／頭部一致性', ['關卡 2', '1–3 都沒有超過門檻'], '五官位置在門檻附近或亮度造成', '程式',
                        '看亮度差（P90）與疊圖', '低', ev))
    return out


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
