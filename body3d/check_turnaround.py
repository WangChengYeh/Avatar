#!/usr/bin/env python3
"""
check_turnaround.py — 檢查一組人物旋轉圖（turnaround）是否適合做 3D 重建
版本 1.13.0（2026-11-24）

版本紀錄:
  1.13.0 新增頭部投影重疊區的烘焙前亮度差檢查（--head-overlap-work）。
  1.12.0 第 10c 項的寬度比差異改為 WARN，由人工比對輪廓、角度與姿勢；差達 5% 標示優先複核。
  1.11.0 依完美（正交渲染）照片校正、收緊門檻：第 10 項藍色 ≤ 1%（> 2% FAIL；主環側面 ≤ 3%）、
         第 10b 項 < 2%（≥ 4% FAIL）、第 10c 項 ±3%（≥ 5% FAIL）；紅色不設門檻（說明見五）
  1.10.0 第 10c 項：俯角 / 仰角環的手寬比、頭寬比要和同角度主環一致（差 ≥ 8% 判 FAIL，1.11.0 改為 5%）；九、重新生成俯角環的提示詞
  1.9.0  第 10 項：剪影一致性（主環重建形狀投影到每張身體圖，輸出紅藍對照圖 *_silhouette_check.png，
         藍色 = 照片有、形狀沒有，照片 ≥ 96% 要落在形狀內）；第 10b 項：透視強度（斜角兩手指尖中點偏移）
  1.8.0  第 1b 項：灰白雜點（AI 留在身體邊緣的無色色塊）；第 9 項：曝光 / 膚色亮度一致性
  1.7.0  第 8 項：俯視圖與主環一致性（主環重建形狀從正上方投影，身體中段覆蓋率 ≥ 97%），輸出 *_top_check.png 對照圖
  1.6.0  第 7c 項：腳踝一致性（相差 180° 的兩張，差 > 8% 判 FAIL）；第 7 項身材比例改判 FAIL
  1.5.0  33 張全部必要（四個環各 8 張 + 俯視）；九、AI 生成注意事項；俯角 / 仰角 / 頭部環檢查角度、翻轉、光線
  1.4.0  第 0 項完整性清單；第 7b 項腳間距；第 8 項額外圖片（俯視、俯角、頭部特寫、仰角）
  1.3.0  斜角鏡像比對只比手臂以下（排除透視造成的手臂長短差）
  1.2.0  第 6c 項：由光線方向偵測左右翻轉的圖
  1.1.0  第 6b 項：偵測同組內的左右翻轉複製
  1.0.0  主環 8 張：解析度 / 背景 / 構圖 / 姿勢 / 角度 / 真側面 / 鏡像 / 比例

用法:
    python3 check_turnaround.py <圖片資料夾> [--pose tpose|apose] [--out report.png]

所有圖放在同一個資料夾，檔名規則見下方「八、檔名」。
角度定義：0 = 正面，90 = 她的左側朝相機（臉朝畫面左），180 = 背面，270 = 右側。

單檔使用（Python 3）:
    python -m pip install numpy opencv-python
    python check_turnaround.py 照片資料夾

有重建中間檔時，可另外檢查頭部投影重疊區:
    python check_turnaround.py 照片資料夾 --head-overlap-work 工作資料夾
    工作資料夾需有 cams33.json、uvmesh.npz、face_lm33.npy 和頭部照片遮罩。


結束碼: 有 FAIL 回傳 1，否則 0。報告圖預設存成 turnaround_report.png（每張圖畫出去背輪廓）。

======================================================================
圖像規範（生成或拍攝旋轉圖時請照這份做）
======================================================================

一、需要哪些圖（一次補齊；全部用 AI 生成，所以全部都是必要）
  A. 主環 8 張【必要】相機水平、在肚臍高度，人轉 8 個角度
       000deg 正面      045deg 左前      090deg 左側（純側面）  135deg 左後
       180deg 背面      225deg 右後      270deg 右側（純側面）  315deg 右前
     → 決定身體、腿、頭的輪廓與大部分貼圖。

  B. 俯視 1 張【必要】相機在頭頂正上方、鏡頭垂直朝下（俯角 90°）
       同一個 T-pose；她的正面朝畫面下方、頭頂在畫面中央附近；
       雙手完整入鏡（左右留白）；同樣的光線與背景（可以是白色地面）。
       本腳本第 8 項會把主環重建的形狀從正上方投影，和這張比對（身體需 ≥ 97% 落在形狀內）；
       相機太近（透視太強、頭特別大）或身體 / 姿勢和主環不一致都會被判 FAIL。
     → 主環的相機全是水平的，看不到水平手臂的「上下厚度」，也看不到肩膀頂部、
       頭頂與髮髻的形狀。缺這張時手臂會被做成扁平的板子、肩膀頂部變成平台。

  C. 俯角環 8 張【必要】相機抬高、往下俯 30°，和主環同樣 8 個角度、同樣距離
     → 補肩膀與手臂上方、頭頂、髮髻、腳背的形狀與貼圖。

  D. 頭部特寫環 8 張【必要】000/045/090/135/180/225/270/315（同主環角度）
       相機與頭同高、水平；只拍頭到肩膀上緣；頭部高度 ≥ 畫面 60%（≥ 1200 像素）；
       同樣的髮型、表情、光線。
     → 全身圖裡臉只有約 200 像素高，特寫讓臉、眼睛、髮絲、髮髻清楚。

  E. 仰角環 8 張【必要】相機在膝蓋高度、往上仰 20°，和主環同樣 8 個角度、同樣距離
     → 補下巴下方、手臂下方（腋下）、髮髻下緣。

  共 8 + 1 + 8 + 8 + 8 = 33 張（四個環都是 8 張，加 1 張俯視），缺任何一張本腳本第 0 項都會判 FAIL。

  F. 腳的位置與形狀【必要條件，不是額外的圖】
       所有圖裡雙腳要站在完全相同的位置，腳間距、腳尖方向、腳踝粗細一致。
     → 不一致時，重建會把腳踝削細或少一隻腳。本腳本第 7b 項（腳間距）、
       第 7c 項（相差 180° 的兩張腳踝寬度差 < 8%）會檢查，不合格判 FAIL。

二、角度要求（本腳本第 4、5、6 項會檢查）
  - 角度必須「真的」是標示的角度，誤差 ±10° 內。
      45° 要看得到一半側面；只轉 15–20° 的圖等於又一張正面，沒有用。
  - 90° / 270° 必須是純側面：
      兩條腿完全重疊、只看得到一條腿；臉是純側臉，只看得到一隻眼睛。
      看得到兩條腿並排，代表角度不到 90°，無法當側面深度使用。
  - 相差 180° 的兩張（0/180、90/270、45/225、135/315）輪廓必須互為鏡像，
    代表是同一個身體、同一個姿勢從正反兩面看（斜角只比對手臂以下：
    透視會讓靠近相機的手臂看起來較長，屬正常）。

三、姿勢（所有圖都必須完全相同）
  - 預設 T-pose：雙臂水平伸直、掌心朝下，手指併攏伸直。
      從正面看，手尖高度約在身高由上往下 20–30% 處（肩膀高度），
      雙手展開寬度 > 身高的 85%。
      （T-pose 的手臂在 90° 側面時朝向鏡頭，不會擋住身體側面輪廓；
        A-pose 的手臂在側面會疊在身體上，身體側面的形狀就無法判斷。）
  - 若用 A-pose（--pose apose）：手臂約 45° 往下張開，所有角度張開程度一致。
  - 雙腳與肩同寬、平行站立，腳尖朝前，重心平均，站直。
  - 頭朝正前方，不轉頭、不歪頭、不低頭；表情自然固定。
  - 左右兩手高度對稱（差 < 身高 3%）。
  - 每一張都是同一個姿勢：只有「相機換了位置」，手、腳、頭的相對位置不能變。
  - 不要用左右翻轉來產生另一側（例如把 45° 翻成 315°）：臉、髮線、衣服的不對稱
    細節會被鏡像。本腳本第 6b 項偵測同組內的翻轉複製，
    第 6c 項由光線方向偵測翻轉（光源相對於相機固定，每張應該都是同一側較亮）。

四、人物一致性
  - 同一個人、同樣的身材比例（胸 / 腰 / 臀 / 大腿 / 小腿的寬度與厚度差 < 8%，
    本腳本第 7 項；腳踝見第 7c 項；不合格判 FAIL）。
  - 同一套衣服，衣服的邊界（褲腰、上衣下緣、肩帶）在每張圖的高度要一致。
  - 同樣的髮型；髮髻、馬尾等的位置在每張圖必須一致（例如背面看到的髮髻
    高度要和側面看到的一樣）。
  - 不要配件晃動（長耳環、飄動的頭髮、披巾）。

五、相機與構圖（本腳本第 2 項會檢查）
  - 主環：相機高度固定在肚臍附近，水平拍攝（俯角環、仰角、俯視依各自規定）。
  - 每張相機距離與焦距相同；要用長焦距（或正交投影），重建程式假設正交投影。
    本腳本第 10b 項量透視強度：斜角 4 張的兩手指尖中點要在身體中軸上（偏向近手 < 2% 半臂展，
    ≥ 4% 判 FAIL，約等於相機距離不到 14 m）；第 10 項把主環重建形狀投影到每張身體圖，
    輸出紅藍對照圖：藍色 = 照片有、形狀沒有，要 ≤ 1%（> 2% FAIL；主環 90° / 270° 側面 ≤ 3%）；
    紅色 = 形狀超出照片，不設門檻（形狀由剪影雕出，凹處雕不掉，一定比真實身體大，
    完美照片也有 3–75%）。第 10c 項比較俯角 / 仰角環和同角度主環的「手寬 / 臀寬」「頭寬 / 臀寬」。
    這些寬度用畫面高度區間估算，俯仰角或姿勢改變也可能影響讀值。差 ≥ 3% 判 WARN，
    ≥ 5% 標示優先複核。複核時比對照片的拍攝角度、姿勢與輪廓。
    以上門檻都用「完美照片」（模型正交渲染的 33 張）校正：完美照片藍色 0–0.6%、10b 0–0.2%、10c 0–2%。
  - 全身完整入鏡，頭頂與腳底上下都留白，手尖不要碰到畫面左右邊緣
    （頭部特寫只要求頭頂不被切到）。
  - 每張的人物高度差 < 2%；頭頂與腳底在畫面中的位置差 < 圖高 2%。
  - 人物置中；旋轉軸（身體中心）在每張圖大致同一個水平位置。

六、背景與光線（本腳本第 1 項會檢查）
  - 純白、均勻的背景（無漸層、無紋理、無地板線）。
  - 不要地面陰影或倒影：腳下的陰影會讓去背把兩腳連在一起。
  - 光線柔和平均（像攝影棚柔光），避免強烈明暗面與高光；
    光源相對於相機固定（每張都是同一側較亮），顏色與亮度一致。
  - 人物與背景顏色要有對比（白衣服配白背景會去背失敗）。
  - 不要有 AI 留下的灰白雜點（黏在身體邊緣的無色色塊，本腳本第 1b 項）。
  - 所有圖的曝光一致：膚色亮度和主環差 < 12%（本腳本第 9 項）。

七、畫質
  - 圖高至少 2000 像素（頭部特寫至少 1500），越高越好。
  - 對焦清楚、無動態模糊、無壓縮色塊；PNG 或高品質 JPG。
  - 不要加浮水印、文字、邊框。

八、檔名（全部放在同一個資料夾）
  A 主環     NN_AAAdeg_說明.jpg   例: 01_000deg_front.jpg … 08_315deg_front_right.jpg
  B 俯視     top.jpg              （檔名含 "top"）
  C 俯角環   el30_AAAdeg.jpg      例: el30_000deg.jpg、el30_045deg.jpg … el30_315deg.jpg
  D 頭部特寫 head_AAAdeg.jpg      例: head_000deg.jpg … head_315deg.jpg
  E 仰角環   low20_AAAdeg.jpg     例: low20_000deg.jpg、low20_045deg.jpg … low20_315deg.jpg
  - AAA 是三位數角度；角度方向：數字增加 = 相機往她的左側繞（從上往下看是逆時針）。

九、用 AI 生成時的注意事項
  - 33 張要是「同一個角色」：用同一張參考圖 / 角色設定 / 固定種子（seed），
    每張只改相機位置，不要每張重新描述人物（會造成臉、身材、髮髻位置不一致）。
  - 在提示詞寫明相機位置，例如
      "camera at navel height, horizontal, orbiting 45 degrees to her left"
      "camera directly overhead, looking straight down"
      "camera raised, tilted down 30 degrees"     "camera at knee height, tilted up 20 degrees"
    生成後一律用本腳本檢查：AI 常把 45° 畫成 15–20°、把 90° 畫成 60–75°（第 4、5 項）。
  - 不要用左右翻轉產生另一側（第 6b、6c 項會抓出來）。
  - 光線、背景、衣服、髮型、表情、手指姿勢、腳的位置在 33 張都要相同。
  - 透視越小越好：提示詞用長焦距（例如 200mm）或 orthographic / turnaround sheet 風格（第 10、10b 項會檢查；第 10c 項提供寬度比複核提示）。
    俯角 30° 環最容易出問題（AI 會把相機放得很近、從上往下拍，頭大腳小）。重新生成時每張都加上：
      orthographic projection, 200mm telephoto lens, camera very far away, no perspective distortion,
      head and feet drawn at the same scale, technical character turnaround sheet
    並寫明：camera elevated 30 degrees looking down, same distance and framing as the eye-level views,
    same T-pose, arms horizontal。
"""
import argparse, glob, json, os, re, sys
from pathlib import Path

__version__ = '1.13.0'
import numpy as np
import cv2

PASS, WARN, FAIL, INFO = 'PASS', 'WARN', 'FAIL', 'INFO'
results = []


def report(level, item, msg):
    results.append((level, item, msg))
    print(f'  [{level}] {item}: {msg}')


# ---------------------------------------------------------------- segmentation
def segment(im):
    """foreground mask against a light, near-uniform background (per-row border model)"""
    H, W = im.shape[:2]
    lab = cv2.cvtColor(im, cv2.COLOR_BGR2LAB).astype(np.float32)
    k = max(10, W // 25)
    border = np.concatenate([lab[:, :k], lab[:, -k:]], 1)
    bg = np.median(border, 1)[:, None, :]
    d = np.sqrt(((lab - bg) ** 2).sum(2))
    m = (d > 14).astype(np.uint8)
    # floor shadow: light, colourless pixels in the lowest part of the frame are not the person
    a_, b_ = lab[..., 1] - 128, lab[..., 2] - 128
    shadow = (np.sqrt(a_ * a_ + b_ * b_) < 6) & (lab[..., 0] > 140) & (np.arange(H)[:, None] > 0.8 * H)
    m[shadow] = 0
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    n, lb, st, _ = cv2.connectedComponentsWithStats(m)
    if n < 2:
        return None, lab, bg
    m = (lb == 1 + np.argmax(st[1:, 4])).astype(np.uint8)
    # fill only small holes (keep the gap between the legs / arms and body open)
    inv = (1 - m).astype(np.uint8)
    n2, lb2, st2, _ = cv2.connectedComponentsWithStats(inv)
    for i in range(1, n2):
        x, y, w, h, area = st2[i]
        if area < 0.0015 * H * W and x > 0 and y > 0 and x + w < W and y + h < H:
            m[lb2 == i] = 1
    return m > 0, lab, bg


def runs(row):
    xs = np.nonzero(row)[0]
    if len(xs) == 0:
        return []
    return [(r[0], r[-1]) for r in np.split(xs, np.nonzero(np.diff(xs) > 1)[0] + 1)]


def bbox(m):
    ys, xs = np.nonzero(m)
    return ys.min(), ys.max(), xs.min(), xs.max()


def normalise(m, h=600):
    """crop to the figure, scale to a common height, centre on the column centroid of the legs+torso"""
    t, b, l, r = bbox(m)
    crop = m[t:b + 1, l:r + 1].astype(np.uint8)
    s = h / crop.shape[0]
    crop = cv2.resize(crop, (max(1, int(crop.shape[1] * s)), h), interpolation=cv2.INTER_NEAREST)
    lower = crop[int(h * 0.45):]
    cx = np.nonzero(lower)[1].mean()
    W = 900
    out = np.zeros((h, W), np.uint8)
    off = int(W / 2 - cx)
    x0, x1 = max(0, off), min(W, off + crop.shape[1])
    out[:, x0:x1] = crop[:, x0 - off:x1 - off]
    return out > 0


def iou(a, b):
    return (a & b).sum() / max(1, (a | b).sum())


def best_iou_shift(a, b, max_shift=20):
    best = 0
    for dx in range(-max_shift, max_shift + 1, 2):
        best = max(best, iou(a, np.roll(b, dx, axis=1)))
    return best


def hand_span(m):
    """widest extent of the silhouette (hand tip to hand tip)"""
    t, b, l, r = bbox(m)
    return r - l, (b - t)


def leg_runs(m, fr0=0.78, fr1=0.92):
    t, b, _, _ = bbox(m)
    counts, widths = [], []
    for r in range(int(t + fr0 * (b - t)), int(t + fr1 * (b - t))):
        rr = runs(m[r])
        rr = [q for q in rr if q[1] - q[0] > 3]
        counts.append(len(rr))
        widths.append(sum(q[1] - q[0] for q in rr))
    return np.array(counts), np.array(widths) / (b - t)


def quick_hull(good, vs=0.01, height=1.65):
    """coarse orthographic visual hull from the main ring (7-of-8 vote); returns voxel centres (N, 3).
    Scale from the figure height, rotation axis from the calf-level centre, angles from the file names."""
    xs = np.arange(-0.95, 0.95, vs) + vs / 2; ys = np.arange(0.0, 1.72, vs) + vs / 2; zs = np.arange(-0.42, 0.42, vs) + vs / 2
    X, Y, Z = np.meshgrid(xs, ys, zs, indexing='ij')
    P = np.stack([X.ravel(), Y.ravel(), Z.ravel()], 1)
    votes = np.zeros(len(P), np.uint8); n = 0
    for a, v in good.items():
        m = cv2.dilate(v['m'].astype(np.uint8), np.ones((5, 5), np.uint8)); H_, W_ = m.shape
        t, b, _, _ = bbox(v['m']); s = (b - t) / height
        rr = int(t + 0.75 * (b - t)); xr = np.nonzero(v['m'][rr])[0]; cu = (xr.min() + xr.max()) / 2
        ph = np.radians(a)
        col = np.round(cu + s * (P[:, 0] * np.cos(ph) - P[:, 2] * np.sin(ph))).astype(int)
        row = np.round(b - s * P[:, 1]).astype(int)
        ok = (col >= 0) & (col < W_) & (row >= 0) & (row < H_)
        votes += ok & (m[np.clip(row, 0, H_ - 1), np.clip(col, 0, W_ - 1)] > 0); n += 1
    return P[votes >= max(1, n - 1)]


def top_consistency(hull, mt, core=0.22):
    """project the hull straight down (front toward image bottom) and fit scale / offset to the top silhouette.
    Returns (IoU of the body core |x|<core, IoU of everything, fitted scale ratio vs. arm span)."""
    H_, W_ = mt.shape
    ys_, xs_ = np.nonzero(mt)
    span_m = hull[:, 0].max() - hull[:, 0].min()
    s0 = (xs_.max() - xs_.min()) / span_m
    cu0 = (xs_.max() + xs_.min()) / 2 - s0 * (hull[:, 0].max() + hull[:, 0].min()) / 2
    corem = np.abs(hull[:, 0]) < core

    def render(s, cu, cv, sel):
        img = np.zeros((H_ // 4, W_ // 4), np.uint8)
        c = ((cu + s * hull[sel, 0]) / 4).astype(int); r = ((cv + s * hull[sel, 2]) / 4).astype(int)
        ok = (c >= 0) & (c < img.shape[1]) & (r >= 0) & (r < img.shape[0])
        img[r[ok], c[ok]] = 1
        k_ = 2 * int(np.ceil(s * 0.01 / 4)) + 1            # close gaps between projected 1 cm voxels
        img = cv2.morphologyEx(img, cv2.MORPH_CLOSE, np.ones((k_, k_), np.uint8))
        ff = img.copy() * 255; mk = np.zeros((img.shape[0] + 2, img.shape[1] + 2), np.uint8)
        cv2.floodFill(ff, mk, (0, 0), 128)
        return ff != 128
    ms = cv2.resize(mt.astype(np.uint8), (W_ // 4, H_ // 4), interpolation=cv2.INTER_AREA) > 0

    def score(s, cu, cv):
        img = render(s, cu, cv, corem)
        x0 = int((cu - s * core) / 4); x1 = int((cu + s * core) / 4) + 1
        a = img[:, max(0, x0):x1]; b = ms[:, max(0, x0):x1]
        return (a & b).sum() / max(1, (a | b).sum())
    # vertical offset: align the core centroid, then local search on scale / offsets
    zc = hull[corem, 2].mean()
    xc0 = int((cu0 - s0 * core)); xc1 = int((cu0 + s0 * core))
    ry = np.nonzero(mt[:, max(0, xc0):xc1].any(1))[0]
    cv0 = (ry.min() + ry.max()) / 2 - s0 * zc
    best = (score(s0, cu0, cv0), s0, cu0, cv0)
    for step in (16, 6, 2):
        improved = True
        while improved:
            improved = False
            sc, s, cu, cv = best
            # scale stays fixed at the arm-span value (a fat hull would otherwise pull it down to raise IoU)
            for ds, dc, dv in ((0, step, 0), (0, -step, 0), (0, 0, step), (0, 0, -step)):
                v2 = score(s + ds, cu + dc, cv + dv)
                if v2 > best[0] + 1e-4:
                    best = (v2, s + ds, cu + dc, cv + dv); improved = True
    sc, s, cu, cv = best
    full = render(s, cu, cv, np.ones(len(hull), bool))
    full_iou = (full & ms).sum() / max(1, (full | ms).sum())
    # coverage: share of the top view's body core that lies inside the hull's projection. The hull is an
    # outer bound of the true body, so a consistent top view is (almost) fully covered; perspective (head drawn
    # too big) or a different body / pose sticks out.
    img = render(s, cu, cv, corem)
    x0 = int((cu - s * core) / 4); x1 = int((cu + s * core) / 4) + 1
    a = cv2.dilate(img[:, max(0, x0):x1].astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    bm = ms[:, max(0, x0):x1]
    cover = (a & bm).sum() / max(1, bm.sum())
    # where does the top view stick out? head = near the core centroid (perspective makes it too big)
    out_ = bm & ~a
    yy, xx = np.nonzero(bm); cy, cx = yy.mean(), xx.mean()
    oy, ox = np.nonzero(out_)
    rad = 0.11 * s / 4
    head_share = float(((oy - cy) ** 2 + (ox - cx) ** 2 < rad ** 2).mean()) if len(oy) else 0.0
    # rough location of the excess (image bottom = her front): back of head / bun, feet / toes, sides
    where = {}
    if len(oy):
        mpx = s / 4                                          # px per metre at this resolution
        back = oy < cy - 0.06 * mpx; front = oy > cy + 0.06 * mpx; side = ~back & ~front
        for k_, sel_ in (('頭後 / 髮髻', back), ('腳尖 / 身體前方', front), ('肩膀 / 身體兩側', side)):
            if sel_.mean() > 0.15:
                where[k_] = float(sel_.mean())
    # diagnostic overlay (full resolution / 4): grey = both, red = only in the top photo, green = only in the hull
    ov = np.zeros(ms.shape + (3,), np.uint8)
    ov[full & ms] = (180, 180, 180); ov[ms & ~full] = (0, 0, 255); ov[full & ~ms] = (0, 200, 0)
    return sc, full_iou, s / s0, cover, head_share, ov, where


RING_EL = {'main': 0.0, 'el30': 30.0, 'low20': -20.0}
# section 10, blue = share of the photo outside the main-ring shape. Calibrated on perfect (orthographic, rendered)
# photos: 0–0.6 % blue, so > 1 % is a real inconsistency. Level-ring side views (90° / 270°) are tested against a
# hull built without them, which cannot reproduce a profile: perfect photos give 1.8–2.9 % there.
BLUE_PASS, BLUE_WARN = 0.01, 0.02
BLUE_SIDE_PASS, BLUE_SIDE_WARN = 0.03, 0.04
PERSP_PASS, PERSP_WARN = 0.02, 0.04      # near-hand shift of the fingertip midpoint (section 10b); perfect photos: 0–0.2 %


def near_hand_shift(m):
    """fingertip midpoint minus the vertical body axis (legs centroid column), in half arm spans.
    Orthographic + symmetric T-pose: 0 in every view (also elevated). Perspective: shifted toward the near hand."""
    ys, xs = np.nonzero(m); t, b = ys.min(), ys.max(); l, r = xs.min(), xs.max()
    band = m[int(t + 0.70 * (b - t)):int(t + 0.93 * (b - t))]
    if not band.any():
        return None
    return ((l + r) / 2 - np.nonzero(band)[1].mean()) / max(1, (r - l) / 2)


RATIO_WARN, RATIO_REVIEW = 0.03, 0.05     # section 10c: |ring ratio / level ratio - 1|; perfect photos: 0–2 %
PROMPT_ORTHO = ('orthographic projection, 200mm telephoto lens, camera very far away, no perspective distortion, '
                'head and feet drawn at the same scale, technical character turnaround sheet')


def width_ratios(m):
    """Estimate hand-span and head-width ratios relative to hip width in the image.

    Hips use the widest row at 42–62% of figure height. Head width uses the run around the body
    axis in the top 9%. These image bands can sample different contours as elevation changes.
    """
    ys, xs = np.nonzero(m); t, b = ys.min(), ys.max(); H = b - t; l, r = xs.min(), xs.max()
    band = m[int(t + 0.70 * H):int(t + 0.93 * H)]
    if not band.any():
        return None
    ax = int(round(np.nonzero(band)[1].mean()))
    hip = max(np.count_nonzero(m[y]) for y in range(int(t + 0.42 * H), int(t + 0.62 * H)))
    colhit = np.nonzero(m[:, max(0, ax - 3):ax + 4].any(1))[0]
    if not len(colhit) or hip == 0:
        return None
    top = colhit.min(); hw = 0
    for y in range(top, int(top + 0.09 * H)):
        xs_ = np.nonzero(m[y])[0]
        if not len(xs_):
            continue
        rr = np.split(xs_, np.nonzero(np.diff(xs_) > 1)[0] + 1)
        q = min(rr, key=lambda q: 0 if q[0] <= ax <= q[-1] else min(abs(q[0] - ax), abs(q[-1] - ax)))
        hw = max(hw, q[-1] - q[0] + 1)
    return (r - l) / hip, hw / hip


def ring_ratio_check(good, extra):
    """10c. el30 / low20 views vs the level view of the same angle (side views 90° / 270° skipped: the hand span
    is tiny there and the head outline seen from above differs). Returns {(ring, angle): (dev_hand, dev_head)}."""
    out = {}
    for cat in ('el30', 'low20'):
        for a, v in sorted(extra.get(cat, {}).items()):
            if a in (90, 270) or a not in good or v.get('m') is None:
                continue
            r0, r1 = width_ratios(good[a]['m']), width_ratios(v['m'])
            if r0 and r1:
                out[(cat, a)] = (r1[0] / r0[0] - 1, r1[1] / r0[1] - 1)
    return out


def perspective_check(good, extra):
    """10b. per ring: signed mean of the near-hand shift over the 4 diagonal views (near hand: image right at
    45° / 225°, image left at 135° / 315°). Leg-asymmetry bias cancels in the signed mean.
    Returns {ring: (p, est_distance_in_half_spans, {angle: shift})}."""
    sign = {45: 1, 135: -1, 225: 1, 315: -1}
    rings = {'main': good, 'el30': extra.get('el30', {}), 'low20': extra.get('low20', {})}
    out = {}
    for k, items in rings.items():
        vals = {a: near_hand_shift(items[a]['m']) for a in sign if a in items and items[a].get('m') is not None}
        vals = {a: x for a, x in vals.items() if x is not None}
        if len(vals) >= 3:
            p = float(np.mean([sign[a] * x for a, x in vals.items()]))
            out[k] = (p, (np.sin(np.radians(45)) / p) if p > 1e-3 else float('inf'), vals)
    return out


def project_hull(hull, phi, th, s, cu, cv, shape, D=None, Q=4, vs=0.01):
    """filled silhouette (1/Q resolution) of the voxel hull seen by an orthographic camera (D=None) or a
    perspective camera D metres from the body centre (same image scale s at the body centre)."""
    p, t = np.radians(phi), np.radians(th)
    r = np.array([np.cos(p), 0, -np.sin(p)])
    u = np.array([-np.sin(t) * np.sin(p), np.cos(t), -np.sin(t) * np.cos(p)])
    f = np.array([np.sin(p) * np.cos(t), np.sin(t), np.cos(p) * np.cos(t)])      # toward the camera
    a, b = hull @ r, hull @ u
    k_s = s
    if D is not None:
        c0 = np.array([0.0, 0.85, 0.0])
        k = D / np.maximum(0.3, D - (hull @ f - c0 @ f))
        a = c0 @ r + (a - c0 @ r) * k; b = c0 @ u + (b - c0 @ u) * k
        k_s = s * k.max()
    H_, W_ = shape[0] // Q, shape[1] // Q
    img = np.zeros((H_, W_), np.uint8)
    c = ((cu + s * a) / Q).astype(int); rr = ((cv - s * b) / Q).astype(int)
    ok = (c >= 0) & (c < W_) & (rr >= 0) & (rr < H_)
    img[rr[ok], c[ok]] = 1
    kk = 2 * int(np.ceil(k_s * vs / Q)) + 1                 # close the gaps between projected voxels
    img = cv2.morphologyEx(img, cv2.MORPH_CLOSE, np.ones((kk, kk), np.uint8))
    ff = img * 255; mk = np.zeros((H_ + 2, W_ + 2), np.uint8)
    cv2.floodFill(ff, mk, (0, 0), 128)
    return ff != 128


def fit_view(hull, m, phi, th, D=None, init=None, Q=4):
    """fit scale / offsets (and ±4° of angle) of the hull projection to the photo mask by IoU.
    Returns (iou, params)."""
    ms = cv2.resize(m.astype(np.uint8), (m.shape[1] // Q, m.shape[0] // Q), interpolation=cv2.INTER_AREA) > 0

    def score(x):
        img = project_hull(hull, x[3], x[4], x[0], x[1], x[2], m.shape, D, Q)
        return (img & ms).sum() / max(1, (img | ms).sum())
    if init is None:
        t, b, l, r_ = bbox(m)
        p, tt = np.radians(phi), np.radians(th)
        rr = np.array([np.cos(p), 0, -np.sin(p)]); uu = np.array([-np.sin(tt) * np.sin(p), np.cos(tt), -np.sin(tt) * np.cos(p)])
        a, bb = hull @ rr, hull @ uu
        s0 = (b - t) / (bb.max() - bb.min())
        x = [s0, (l + r_) / 2 - s0 * (a.max() + a.min()) / 2, (t + b) / 2 + s0 * (bb.max() + bb.min()) / 2, phi, th]
    else:
        x = list(init)
    best = (score(x), x)
    for frac in (0.04, 0.015, 0.005):
        steps = [(0, x[0] * frac), (1, 400 * frac), (2, 400 * frac), (3, 100 * frac), (4, 100 * frac)]
        improved = True
        while improved:
            improved = False
            for i, d in steps:
                for sg in (1, -1):
                    y = list(best[1]); y[i] += sg * d
                    if i == 3 and abs(y[3] - phi) > 4 or i == 4 and abs(y[4] - th) > 4:
                        continue
                    v = score(y)
                    if v > best[0] + 1e-4:
                        best = (v, y); improved = True
    return best


def ring_consistency(good, extra, out_png):
    """10. project the main-ring hull into every body view (main ring leave-one-out, el30, low20), paint
    red = hull beyond the photo, blue = photo beyond the hull, and test perspective. Returns result rows."""
    views = [('main', a, v) for a, v in sorted(good.items())] + \
            [(cat, a, v) for cat in ('el30', 'low20') for a, v in sorted(extra.get(cat, {}).items()) if v.get('m') is not None]
    full_hull = quick_hull(good)
    rows, tiles = [], []
    for cat, a, v in views:
        hull = quick_hull({k: w for k, w in good.items() if k != a}) if cat == 'main' else full_hull
        m = v['m']; th = RING_EL[cat]
        iou_o, x_o = fit_view(hull, m, a, th)
        Q = 4
        ms = cv2.resize(m.astype(np.uint8), (m.shape[1] // Q, m.shape[0] // Q), interpolation=cv2.INTER_AREA) > 0
        img = project_hull(hull, x_o[3], x_o[4], x_o[0], x_o[1], x_o[2], m.shape, None, Q)
        k3 = np.ones((3, 3), np.uint8)
        blue = ms & (cv2.dilate(img.astype(np.uint8), k3) == 0)          # photo has body, hull does not
        red = img & (cv2.dilate(ms.astype(np.uint8), k3) == 0)           # hull has body, photo does not
        cover = 1 - blue.sum() / max(1, ms.sum())
        red_fr = red.sum() / max(1, ms.sum())
        # where is the blue? hands = outer part of the span, head = top, feet = bottom, else body
        where = {}
        by, bx = np.nonzero(blue)
        if len(by):
            fy, fx = np.nonzero(ms); t_, b_, l_, r_ = fy.min(), fy.max(), fx.min(), fx.max()
            band = ms[int(t_ + 0.70 * (b_ - t_)):int(t_ + 0.93 * (b_ - t_))]
            axis = np.nonzero(band)[1].mean() if band.any() else (l_ + r_) / 2
            half = max(1, (r_ - l_) / 2)
            hand = np.abs(bx - axis) > 0.55 * half
            head = ~hand & (by < t_ + 0.14 * (b_ - t_))
            feet = ~hand & (by > t_ + 0.90 * (b_ - t_))
            for k_, sel_ in (('手', hand), ('頭', head), ('腳', feet), ('身體 / 腿', ~hand & ~head & ~feet)):
                if sel_.mean() >= 0.15:
                    where[k_] = float(sel_.mean())
        rows.append(dict(cat=cat, ang=a, name=v['name'], iou=iou_o, cover=cover, red=red_fr, where=where))
        # overlay tile: photo, red / blue painted, cropped to the figure
        sm = cv2.resize(v['im'], (ms.shape[1], ms.shape[0]), interpolation=cv2.INTER_AREA)
        sm[red] = (0, 0, 255); sm[blue] = (255, 0, 0)
        ys, xs = np.nonzero(ms | img)
        tile = sm[max(0, ys.min() - 8):ys.max() + 8, max(0, xs.min() - 8):xs.max() + 8]
        sc = 300 / tile.shape[0]; tile = cv2.resize(tile, (max(1, int(tile.shape[1] * sc)), 300))
        tile = cv2.copyMakeBorder(tile, 40, 0, 0, max(0, 260 - tile.shape[1]), cv2.BORDER_CONSTANT, value=(255, 255, 255))
        lab = f'{cat} {a}' if cat != 'main' else f'main {a} (LOO)'
        cv2.putText(tile, lab, (4, 16), 0, 0.5, (0, 0, 0), 1)
        cv2.putText(tile, f'cover {100 * cover:.1f}%  red {100 * red_fr:.0f}%', (4, 34), 0, 0.45,
                    (0, 0, 200) if cover < 0.95 else (0, 120, 0), 1)
        tiles.append(tile)
    hmax = max(t.shape[0] for t in tiles)
    tiles = [cv2.copyMakeBorder(t, 0, hmax - t.shape[0], 0, 0, cv2.BORDER_CONSTANT, value=(255, 255, 255)) for t in tiles]
    per = 8
    lines_ = []
    for i in range(0, len(tiles), per):
        row = tiles[i:i + per]
        lines_.append(np.hstack(row))
    wmax = max(l.shape[1] for l in lines_)
    lines_ = [cv2.copyMakeBorder(l, 0, 0, 0, wmax - l.shape[1], cv2.BORDER_CONSTANT, value=(255, 255, 255)) for l in lines_]
    sheet = np.vstack(lines_)
    sheet = cv2.copyMakeBorder(sheet, 0, 30, 0, 0, cv2.BORDER_CONSTANT, value=(255, 255, 255))
    cv2.putText(sheet, 'blue = photo has body, main-ring shape does not (must be ~0)   red = shape beyond photo (info)',
                (8, sheet.shape[0] - 10), 0, 0.55, (0, 0, 0), 1)
    cv2.imwrite(out_png, sheet)
    return rows


def grey_blob(im, m):
    """largest light, colourless blob stuck to the body outline (AI smudge). Blobs touching the image border are
    ignored (limbs cut by the frame). Returns its area as a fraction of the body area and its bbox."""
    lab = cv2.cvtColor(im, cv2.COLOR_BGR2LAB).astype(np.float32)
    ch = np.hypot(lab[..., 1] - 128, lab[..., 2] - 128)
    g = (m & (ch < 6) & (lab[..., 0] > 170)).astype(np.uint8)
    g = cv2.morphologyEx(g, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    outer = m & (cv2.distanceTransform(m.astype(np.uint8), cv2.DIST_L2, 5) < 6)
    H_, W_ = m.shape
    n, lb, st, _ = cv2.connectedComponentsWithStats(g)
    best, box = 0, None
    for i in range(1, n):
        x, y, w, h, area = st[i]
        if area < 400 or x <= 1 or y <= 1 or x + w >= W_ - 1 or y + h >= H_ - 1:
            continue
        if ((lb == i) & outer).sum() > 0.6 * area ** 0.5 and area > best:
            best, box = area, (int(x), int(y), int(w), int(h))
    return best / max(1, m.sum()), box


def skin_lightness(im, m):
    hsv = cv2.cvtColor(im, cv2.COLOR_BGR2HSV)
    skin = m & (hsv[..., 0] < 25) & (hsv[..., 1] > 40) & (hsv[..., 2] > 120)
    if skin.sum() < 500:
        return None
    return float(cv2.cvtColor(im, cv2.COLOR_BGR2LAB)[..., 0][skin].mean())


def report_blob(tag, im, m):
    fr, box = grey_blob(im, m)
    if fr >= 0.008:
        report(FAIL if fr >= 0.02 else WARN, tag + ' 灰白雜點',
               f'身體輪廓上有一塊偏白、沒有顏色的色塊，佔身體 {100 * fr:.1f}%（位置 x={box[0]}, y={box[1]}, '
               f'{box[2]}x{box[3]} 像素）；看起來是 AI 留下的雜點，重建時會被當成身體並貼到皮膚上，請清除後重新生成')


def hand_row_fraction(m):
    """vertical position of the outermost (left & right) points, as a fraction of height from the top"""
    t, b, l, r = bbox(m)
    yl = np.nonzero(m[:, l])[0].mean()
    yr = np.nonzero(m[:, r])[0].mean()
    return ((yl - t) / (b - t), (yr - t) / (b - t))


# ---------------------------------------------------------------- head overlap
C0 = np.array([0.0, 0.85, 0.0])


def camera_axes(phi, th):
    """image right r, image up u, toward-camera f (unit vectors)"""
    p, t = np.radians(phi), np.radians(th)
    r = np.array([np.cos(p), 0.0, -np.sin(p)])
    u = np.array([-np.sin(t) * np.sin(p), np.cos(t), -np.sin(t) * np.cos(p)])
    f = np.array([np.sin(p) * np.cos(t), np.sin(t), np.cos(p) * np.cos(t)])
    return r, u, f


def camera_project(P, c):
    """(col, row) arrays for points P (N, 3)"""
    r, u, f = camera_axes(c['phi'], c['th'])
    D = c.get('D')
    if not D:
        return c['cu'] + c['s'] * (P @ r), c['cv'] - c['s'] * (P @ u)
    Q = P - C0
    k = D / np.maximum(0.05 * D, D - Q @ f)
    return c['cu'] + c['s'] * (C0 @ r + k * (Q @ r)), c['cv'] - c['s'] * (C0 @ u + k * (Q @ u))


def camera_toward(P, c):
    """unit vectors from the points toward the camera (N, 3)"""
    _, _, f = camera_axes(c['phi'], c['th'])
    D = c.get('D')
    if not D:
        return np.broadcast_to(f, P.shape)
    v = C0 + D * f - P
    return v / np.linalg.norm(v, axis=1, keepdims=True)


def camera_depth(P, c):
    """larger = closer to the camera (for z-buffers)"""
    _, _, f = camera_axes(c['phi'], c['th'])
    D = c.get('D')
    if not D:
        return P @ f
    return -np.linalg.norm(C0 + D * f - P, axis=1)


FRONT = 'head_000deg'
CHEEKS = (('左臉頰', 'head_045deg', 1), ('右臉頰', 'head_315deg', -1))
MIN_SAMPLES = 60
# Provisional review threshold on the 0–255 luma scale.
LUMA_REVIEW = 40.0


def projected_samples(points, normals, cam, image, mask):
    """Sample luma on surface points visible in this source photo."""
    col, row = camera_project(points, cam)
    height, width = image.shape
    in_frame = (col >= 1) & (row >= 1) & (col < width - 2) & (row < height - 2)
    col = np.clip(col, 0, width - 1)
    row = np.clip(row, 0, height - 1)
    incidence = np.einsum('ij,ij->i', normals, camera_toward(points, cam))

    cell = 4
    grid_width, grid_height = width // cell + 1, height // cell + 1
    x, y = (col / cell).astype(int), (row / cell).astype(int)
    depth = camera_depth(points, cam)
    depth_grid = np.full((grid_height, grid_width), -1e9, dtype=np.float32)
    np.maximum.at(depth_grid, (y[in_frame], x[in_frame]), depth[in_frame])
    visible = depth >= cv2.dilate(depth_grid, np.ones((3, 3), np.uint8))[y, x] - 0.012
    col_index, row_index = np.rint(col).astype(int), np.rint(row).astype(int)
    valid = in_frame & visible & (incidence > 0.2) & (mask[row_index, col_index] > 0)
    return col_index, row_index, image[row_index, col_index].astype(float), valid


def read_view(folder, work, stem):
    image = cv2.imread(str(folder / f'{stem}.jpg'), cv2.IMREAD_GRAYSCALE)
    mask = cv2.imread(str(work / f'mask_{stem}.png'), cv2.IMREAD_GRAYSCALE)
    if image is None or mask is None or image.shape != mask.shape:
        raise ValueError(f'{stem} 缺少可配對的照片或遮罩')
    mask = cv2.erode(mask, np.ones((9, 9), np.uint8))
    return image, mask


def cheek_band(landmarks, shape, col, row):
    """Locate the transition around the eroded landmark outline used for the frontal bake."""
    face = np.zeros(shape, np.uint8)
    hull = cv2.convexHull(np.rint(landmarks).astype(np.int32))
    cv2.fillConvexPoly(face, hull, 1)
    face = cv2.erode(face, np.ones((61, 61), np.uint8))
    inside = cv2.distanceTransform(face, cv2.DIST_L2, 3)
    outside = cv2.distanceTransform(1 - face, cv2.DIST_L2, 3)

    top, bottom = landmarks[:, 1].min(), landmarks[:, 1].max()
    face_height = bottom - top
    cheek_rows = (row >= top + 0.45 * face_height) & (row <= top + 0.90 * face_height)
    return cheek_rows & (inside[row, col] <= 32) & (outside[row, col] <= 32)


def report_head_overlap(folder, work):
    folder, work = Path(folder), Path(work)
    try:
        cameras = json.loads((work / 'cams33.json').read_text(encoding='utf-8'))
        landmarks = np.load(work / 'face_lm33.npy')
        if (landmarks.ndim != 2 or landmarks.shape[0] < 3 or landmarks.shape[1] < 2
                or not np.isfinite(landmarks[:, :2]).all()):
            raise ValueError('正面臉部特徵點無效')
        landmarks = landmarks[:, :2]
        with np.load(work / 'uvmesh.npz') as mesh:
            vertices = mesh['pos']
            head = vertices[:, 1] >= 1.40
            points, normals = vertices[head], mesh['nrm'][head]
        frontal_image, frontal_mask = read_view(folder, work, FRONT)
        col, row, frontal_luma, frontal_valid = projected_samples(
            points, normals, cameras[FRONT], frontal_image, frontal_mask)
    except (OSError, KeyError, IndexError, ValueError) as error:
        print(f'[WARN] 頭部投影重疊：未完成檢查（{error}）')
        return

    band = cheek_band(landmarks, frontal_image.shape, col, row)
    face_midline = np.median(landmarks[:, 0])
    for cheek, side, direction in CHEEKS:
        label = f'{cheek} {FRONT} / {side}'
        try:
            image, mask = read_view(folder, work, side)
            _, _, side_luma, side_valid = projected_samples(points, normals, cameras[side], image, mask)
        except (ValueError, KeyError) as error:
            print(f'[WARN] {label}：未完成檢查（{error}）')
            continue

        common = band & frontal_valid & side_valid & (direction * (col - face_midline) > 0)
        count = np.count_nonzero(common)
        if count < MIN_SAMPLES:
            print(f'[WARN] {label}：共同可見取樣不足（{count} 點）')
            continue

        delta = np.abs(frontal_luma[common] - side_luma[common])
        median = float(np.median(delta))
        p90 = float(np.percentile(delta, 90))
        status = 'WARN' if p90 >= LUMA_REVIEW else 'PASS'
        guidance = '，接合處可能出現色帶，請複核照片的亮度及對位' if status == 'WARN' else ''
        print(f'[{status}] {label}：亮度絕對差中位數 {median:.1f}，第 90 百分位 {p90:.1f} / 255'
              f'（{count} 點）{guidance}')


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=f'check_turnaround {__version__}')
    ap.add_argument('--version', action='version', version=f'check_turnaround {__version__}')
    ap.add_argument('folder')
    ap.add_argument('--pose', choices=['tpose', 'apose'], default='tpose')
    ap.add_argument('--out', default='turnaround_report.png')
    ap.add_argument('--min-height', type=int, default=2000)
    ap.add_argument('--head-overlap-work', metavar='WORK_DIR',
                    help='用重建中間檔檢查頭部貼圖的重疊區亮度差')
    args = ap.parse_args()
    print(f'check_turnaround 版本 {__version__}')
    if args.head_overlap_work:
        report_head_overlap(args.folder, args.head_overlap_work)
        return

    files = sorted(f for f in glob.glob(os.path.join(args.folder, '*'))
                   if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')))
    views = {}                                   # A 主環
    extra = {'top': {}, 'el30': {}, 'head': {}, 'low20': {}}   # B–E
    for f in files:
        name = os.path.basename(f); low = name.lower()
        im = cv2.imread(f)
        if im is None:
            print(f'略過（讀不到圖）: {name}')
            continue
        mm = re.search(r'(\d{1,3})\s*deg', name, re.I) or re.search(r'_(\d{3})_', name)
        cat = 'top' if 'top' in low else 'el30' if low.startswith('el') else 'head' if low.startswith('head') \
            else 'low20' if low.startswith('low') else None
        if cat == 'top':
            extra['top'][0] = dict(name=name, im=im)
            continue
        if not mm:
            print(f'略過（檔名沒有角度）: {name}')
            continue
        ang = int(mm.group(1)) % 360
        if cat:
            extra[cat][ang] = dict(name=name, im=im)
        else:
            views[ang] = dict(name=name, im=im)
    if 0 not in views:
        sys.exit('需要一張主環 0° 正面圖（檔名含 000deg）')
    print(f'主環找到 {len(views)} 張: ' + ', '.join(f'{a}°' for a in sorted(views)))
    for k, lab_ in (('top', '俯視'), ('el30', '俯角環'), ('head', '頭部特寫'), ('low20', '仰角')):
        if extra[k]:
            print(f'{lab_} {len(extra[k])} 張: ' + ', '.join(v['name'] for _, v in sorted(extra[k].items())))

    # ---- 0. completeness
    print('\n0. 完整性（還缺哪些圖）')
    ring = [0, 45, 90, 135, 180, 225, 270, 315]
    miss_card = [a for a in (0, 90, 180, 270) if a not in views]
    miss_diag = [a for a in (45, 135, 225, 315) if a not in views]
    report(FAIL if miss_card else PASS, 'A 主環（正 / 側 / 背）',
           f'缺 {", ".join(f"{a:03d}deg" for a in miss_card)}' if miss_card else '0/90/180/270 都有')
    report(FAIL if miss_diag else PASS, 'A 主環（斜角）',
           f'缺 {", ".join(f"{a:03d}deg" for a in miss_diag)}' if miss_diag else '45/135/225/315 都有')
    if extra['top']:
        report(PASS, 'B 俯視', '有')
    else:
        report(FAIL, 'B 俯視', '缺 top.jpg：水平相機看不到手臂的上下厚度與肩膀頂部，手臂會變成扁板')
    miss = [a for a in ring if a not in extra['el30']]
    report(FAIL if miss else PASS, 'C 俯角環 30°',
           ('全部缺（el30_000deg … el30_315deg）' if len(miss) == 8 else f'缺 {", ".join(f"el30_{a:03d}deg" for a in miss)}')
           if miss else '8 張都有')
    miss = [a for a in ring if a not in extra['head']]
    report(FAIL if miss else PASS, 'D 頭部特寫環',
           ('全部缺（head_000deg … head_315deg）' if len(miss) == 8 else f'缺 {", ".join(f"head_{a:03d}deg" for a in miss)}')
           if miss else '8 張都有')
    miss = [a for a in ring if a not in extra['low20']]
    report(FAIL if miss else PASS, 'E 仰角環 20°',
           ('全部缺（low20_000deg … low20_315deg）' if len(miss) == 8 else f'缺 {", ".join(f"low20_{a:03d}deg" for a in miss)}')
           if miss else '8 張都有')

    # ---- 1. per image: resolution, background, shadow, segmentation
    print('\n1. 單張檢查（解析度 / 背景 / 地面陰影 / 去背）')
    for a, v in sorted(views.items()):
        im = v['im']; H, W = im.shape[:2]
        m, lab, bg = segment(im)
        v['m'] = m
        tag = f"{a:3d}° {v['name']}"
        if m is None or m.sum() < 0.02 * H * W:
            report(FAIL, tag, '去背失敗：找不到人物（背景要純白、均勻）')
            continue
        t, b, l, r = bbox(m)
        fig_h = b - t
        v['fig_h'], v['top'], v['bot'] = fig_h, t, b
        report_blob(tag, im, m)
        report(PASS if H >= args.min_height else WARN, tag,
               f'解析度 {W}x{H}，人物高 {fig_h}px' + ('' if H >= args.min_height else f'（建議圖高 ≥ {args.min_height}）'))
        if t < 0.02 * H or b > 0.98 * H or l < 2 or r > W - 3:
            report(FAIL, tag, '人物碰到畫面邊緣，需完整入鏡並留白')
        bgL = float(np.median(bg[..., 0]))
        if bgL < 215:
            report(WARN, tag, f'背景偏暗（L={bgL:.0f}），建議純白背景')
        # floor shadow: dark pixels outside the figure in the bottom band
        band = slice(int(b - 0.06 * fig_h), min(H, int(b + 0.04 * fig_h)))
        Lb = lab[band, :, 0]; mb = m[band]
        dark = (Lb < np.median(bg[band, :, 0]) - 12) & ~cv2.dilate(mb.astype(np.uint8), np.ones((9, 9), np.uint8)).astype(bool)
        frac = dark.sum() / max(1, dark.size)
        if frac > 0.01:
            report(WARN, tag, f'腳邊有地面陰影（{100 * frac:.1f}% 的底部區域），去背會受影響')

    good = {a: v for a, v in views.items() if v.get('m') is not None}
    if 0 not in good:
        sys.exit('正面圖去背失敗，無法繼續')

    # ---- 2. framing consistency
    print('\n2. 構圖一致性（每張人物高度、頭頂與腳底位置）')
    hs = np.array([v['fig_h'] for v in good.values()])
    spread = (hs.max() - hs.min()) / hs.mean()
    report(PASS if spread < 0.02 else WARN if spread < 0.04 else FAIL, '人物高度',
           f'差異 {100 * spread:.1f}%（應 < 2%：相機距離與焦距需相同）')
    tops = np.array([v['top'] / v['im'].shape[0] for v in good.values()])
    bots = np.array([v['bot'] / v['im'].shape[0] for v in good.values()])
    d = max(np.ptp(tops), np.ptp(bots))
    report(PASS if d < 0.02 else WARN, '頭頂 / 腳底位置', f'差異 {100 * d:.1f}% 圖高（應 < 2%：相機高度需固定）')

    # ---- 3. pose
    print(f'\n3. 姿勢（{args.pose}）')
    f0 = good[0]['m']
    span0, h0 = hand_span(f0)
    yl, yr = hand_row_fraction(f0)
    ratio = span0 / h0
    if args.pose == 'tpose':
        ok = yl < 0.30 and yr < 0.30 and ratio > 0.85
        report(PASS if ok else FAIL, 'T-pose（正面）',
               f'手尖高度在身高的 {100 * yl:.0f}% / {100 * yr:.0f}% 處（應 < 30%，手臂水平）；'
               f'雙手展開寬 / 身高 = {ratio:.2f}（應 > 0.85）')
    else:
        ok = 0.35 < yl < 0.60 and 0.35 < yr < 0.60
        report(PASS if ok else WARN, 'A-pose（正面）', f'手尖高度 {100 * yl:.0f}% / {100 * yr:.0f}%')
    sym = abs(yl - yr)
    report(PASS if sym < 0.03 else WARN, '左右手對稱', f'兩手高度差 {100 * sym:.1f}% 身高（應 < 3%）')

    # ---- 4. real angle of each view (from the hand span; arms lie in the body plane, span ∝ |cos θ|)
    print('\n4. 實際角度估計（由雙手展開寬度推算，±10° 內算正確）')
    for a, v in sorted(good.items()):
        if a in (0, 180):
            continue
        sp, hh = hand_span(v['m'])
        r_ = min(1.0, (sp / hh) / (span0 / h0))
        est = np.degrees(np.arccos(r_))                       # 0..90, distance from the front/back axis
        expect = min(a % 180, 180 - a % 180)                  # 45 -> 45, 90 -> 90, 135 -> 45
        if expect == 90:
            # at a true profile the T-pose arms point at the camera: span ~ shoulder depth only
            ok_ = r_ < 0.40
            report(PASS if ok_ else FAIL, f'{a:3d}°',
                   f'展開寬比例 {r_:.2f}（真側面時手臂朝鏡頭，應接近軀幹厚度；目前推算約 {est:.0f}° 而非 90°）'
                   if not ok_ else f'展開寬比例 {r_:.2f}，像真正側面')
        else:
            err = abs(est - expect)
            report(PASS if err <= 10 else FAIL, f'{a:3d}°', f'推算約 {est:.0f}°（應為 {expect}°，誤差 {err:.0f}°）')

    # ---- 5. true profiles: the legs must overlap
    print('\n5. 側面是否為真正 90°（兩腿應完全重疊）')
    for a in (90, 270):
        if a not in good:
            report(WARN, f'{a}°', '缺少這張（最重要的兩張之一）')
            continue
        cnt0, w0 = leg_runs(good[0]['m'])
        single = np.median(w0[cnt0 == 2] / 2) if (cnt0 == 2).any() else np.median(w0 / 2)
        cnt, w = leg_runs(good[a]['m'])
        rat = np.median(w) / single
        report(PASS if rat < 1.4 else FAIL, f'{a}° 腿部',
               f'側面小腿寬 = 正面單腿寬的 {rat:.2f} 倍（真側面兩腿重疊，應 < 1.4；'
               f'越大代表兩條腿並排、角度不到 90°）')

    # ---- 6. consistency between opposite / mirrored views
    print('\n6. 一致性（鏡像對應的兩張輪廓應幾乎相同，代表同一個身體、同一個姿勢）')
    # 相差 180° 的兩張從正反兩面拍同一個身體，輪廓必定互為鏡像（最嚴格的檢查）
    # 左右對稱的兩張（45/315、135/225）只在身體左右對稱時才相同，標準放寬
    pairs = [(0, 180, '0° vs 180°（正 / 背）', 0.90), (90, 270, '90° vs 270°（左 / 右側）', 0.90),
             (45, 225, '45° vs 225°', 0.90), (135, 315, '135° vs 315°', 0.90),
             (45, 315, '45° vs 315°（左右對稱）', 0.85), (135, 225, '135° vs 225°（左右對稱）', 0.85)]
    for a, b, label, thr in pairs:
        if a in good and b in good:
            na, nb = normalise(good[a]['m']), normalise(good[b]['m'])[:, ::-1]
            s = best_iou_shift(na, nb)
            if a % 90:
                # 斜角：透視讓靠近相機的手臂看起來較長，正反兩側長短相反，整體輪廓不會完全鏡像；
                # 所以只比對手臂以下的身體部分（若用正交 / 長焦相機，整體也會吻合）
                h_ = na.shape[0]; cut = int(0.30 * h_)
                na2, nb2 = na.copy(), nb.copy(); na2[:cut] = 0; nb2[:cut] = 0
                sb = best_iou_shift(na2, nb2)
                report(PASS if sb > thr else WARN if sb > thr - 0.05 else FAIL, label,
                       f'身體（手臂以下）鏡像重合度 {sb:.2f}（應 > {thr:.2f}）；含手臂 {s:.2f}'
                       + ('（手臂差異來自透視，正常）' if s < sb - 0.03 else ''))
            else:
                report(PASS if s > thr else WARN if s > thr - 0.05 else FAIL, label,
                       f'鏡像重合度 {s:.2f}（應 > {thr:.2f}）')

    # ---- 6b. mirrored duplicates: a view that is just a horizontal flip of another view
    print('\n6b. 翻轉複製檢查（某張是否只是另一張左右翻轉，而不是真的從另一側拍）')
    angs = sorted(good)
    found = False
    for i_, a in enumerate(angs):
        for b_ in angs[i_ + 1:]:
            A = cv2.resize(good[a]['im'], (256, 256), interpolation=cv2.INTER_AREA).astype(np.float32)
            B = cv2.resize(good[b_]['im'], (256, 256), interpolation=cv2.INTER_AREA).astype(np.float32)
            fgm = cv2.resize((good[a]['m'] | good[b_]['m'][:, ::-1]).astype(np.uint8), (256, 256)) > 0
            dflip = np.abs(A - B[:, ::-1]).max(2)[fgm].mean()
            if dflip < 4:
                found = True
                report(WARN, f'{a}° vs {b_}°',
                       f'{b_}° 是 {a}° 的左右翻轉複製（前景差異 {dflip:.1f}）。形狀可用（假設身體左右對稱），'
                       f'但臉、髮線、衣服的不對稱細節會被鏡像；最好真的從另一側生成。')
    if not found:
        report(PASS, '翻轉複製', '沒有發現左右翻轉複製的圖')

    # ---- 6c. lighting direction: studio lights are fixed relative to the camera, so in every genuine view the
    # same image side of the body is brighter. A horizontally flipped image has it reversed — this catches flips
    # even when the original they were made from is not in the set.
    print('\n6c. 光線方向一致性（偵測左右翻轉的圖，即使原圖不在這組裡）')

    def light_dir(im, m, r0=0.30, r1=0.95):
        L = cv2.cvtColor(im, cv2.COLOR_BGR2LAB)[..., 0].astype(float)
        t, b, _, _ = bbox(m)
        vals = []
        for r in range(int(t + r0 * (b - t)), int(t + r1 * (b - t)), 3):
            for a_, b2 in runs(m[r]):
                w_ = b2 - a_
                if w_ < 25:
                    continue
                q = max(3, w_ // 4)
                lft = L[r, a_ + 2:a_ + 2 + q].mean(); rgt = L[r, b2 - 1 - q:b2 - 1].mean()
                vals.append((lft - rgt) / (lft + rgt + 1e-6))
        v = np.array(vals)
        return (float(np.median(v)), float((v > 0).mean())) if len(v) else (0.0, 0.5)

    ld = {a: light_dir(v['im'], v['m']) for a, v in good.items()}
    strong = {a: d for a, d in ld.items() if abs(d[0]) > 0.06 and (d[1] > 0.65 or d[1] < 0.35)}
    if len(strong) < max(3, 0.6 * len(good)):
        report(PASS, '光線方向', '整組光線沒有明顯方向性（平光），此項不判斷')
    else:
        signs = np.array([np.sign(d[0]) for d in strong.values()])
        major = np.sign(signs.sum()) or 1.0
        side = '畫面左側' if major > 0 else '畫面右側'
        odd = [a for a, d in strong.items() if np.sign(d[0]) != major]
        if not odd:
            report(PASS, '光線方向', f'每張都是{side}較亮，光線一致（沒有左右翻轉的跡象）')
        for a in sorted(odd):
            d = ld[a]
            pct = 100 * (d[1] if major < 0 else 1 - d[1])
            report(WARN, f'{a}° 光線',
                   f'這張是{"畫面左側" if major < 0 else "畫面右側"}較亮（{pct:.0f}% 的列），'
                   f'其他張都是{side}較亮 → 很可能是把別張圖左右翻轉做出來的（臉、髮線、衣服細節會是鏡像）')

    # ---- 7. proportions: front width vs back width, side depth left vs right, per body height level
    print('\n7. 身材比例一致性（各高度的寬度 / 厚度）')

    def widths(m, fracs=(0.30, 0.38, 0.47, 0.55, 0.75)):   # ankles: section 7c (per leg, robust)
        t, b, _, _ = bbox(m)
        out = []
        cx = np.nonzero(m[int(t + 0.6 * (b - t))])[0].mean()
        for fr in fracs:
            rr = runs(m[int(t + fr * (b - t))])
            body = [q for q in rr if q[0] - 3 <= cx <= q[1] + 3] or rr
            q = max(body, key=lambda q: q[1] - q[0])
            out.append((q[1] - q[0]) / (b - t))
        return np.array(out)
    for a, b, label in ((0, 180, '正面 vs 背面 寬度'), (90, 270, '左側 vs 右側 厚度')):
        if a in good and b in good:
            wa, wb = widths(good[a]['m']), widths(good[b]['m'])
            devs = np.abs(wa / wb - 1); k_ = int(np.argmax(devs)); dev = devs[k_]
            lv = ['胸', '腰', '臀', '大腿', '小腿'][k_]
            report(PASS if dev < 0.08 else FAIL, label,
                   f'胸/腰/臀/大腿/小腿最大差異 {100 * dev:.0f}%，在「{lv}」（應 < 8%；腳踝見 7c）')

    # ---- 7b. feet: same stance in every view (front/back: gap between the feet; mirrored pairs agree)
    print('\n7b. 腳的位置一致性（每張雙腳要站在同一個位置）')

    def feet_gap(m):
        t, b, _, _ = bbox(m)
        gaps = []
        for fr in (0.90, 0.93, 0.96):
            rr = [q for q in runs(m[int(t + fr * (b - t))]) if q[1] - q[0] > 3]
            if len(rr) >= 2:
                rr = sorted(rr, key=lambda q: q[1] - q[0])[-2:]
                rr = sorted(rr)
                gaps.append(((rr[1][0] + rr[1][1]) - (rr[0][0] + rr[0][1])) / 2 / (b - t))
        return np.median(gaps) if gaps else None
    g0 = feet_gap(good[0]['m']) if 0 in good else None
    g180 = feet_gap(good[180]['m']) if 180 in good else None
    if g0 is not None and g180 is not None:
        dg = abs(g0 - g180)
        report(PASS if dg < 0.012 else WARN if dg < 0.025 else FAIL, '腳間距 正面 vs 背面',
               f'{100 * g0:.1f}% vs {100 * g180:.1f}% 身高（差 {100 * dg:.1f}%，應 < 1.2%）')
    elif g0 is None:
        report(WARN, '腳間距', '正面圖看不出兩隻腳（腳併攏或去背黏在一起），建議雙腳與肩同寬')
    for a in (45, 315):
        if a in good and (180 + a) % 360 in good:
            ga, gb = feet_gap(good[a]['m']), feet_gap(good[(180 + a) % 360]['m'])
            if ga is not None and gb is not None:
                dg = abs(ga - gb)
                report(PASS if dg < 0.015 else WARN, f'腳間距 {a}° vs {(180 + a) % 360}°',
                       f'{100 * ga:.1f}% vs {100 * gb:.1f}% 身高（差 {100 * dg:.1f}%，應 < 1.5%）')

    # ---- 7c. ankles / feet: same width in mirrored pairs (a mismatch makes the reconstruction shave an ankle off)
    print('\n7c. 腳踝一致性（相差 180° 的兩張，腳踝寬度要相同）')

    def ankles(m, r0=0.88, r1=0.94):
        t, b, _, _ = bbox(m)
        L_, R_, S_ = [], [], []
        for r in range(int(t + r0 * (b - t)), int(t + r1 * (b - t))):
            rr = [q for q in runs(m[r]) if q[1] - q[0] > 3]
            if len(rr) >= 2:
                rr = sorted(sorted(rr, key=lambda q: q[1] - q[0])[-2:])
                L_.append(rr[0][1] - rr[0][0]); R_.append(rr[1][1] - rr[1][0])
            S_.append(sum(q[1] - q[0] for q in rr))
        h_ = b - t
        md = lambda v_: float(np.median(v_)) / h_ if len(v_) else None
        return md(L_), md(R_), md(S_)
    an = {a: ankles(v['m']) for a, v in good.items()}
    TH = 0.08
    if 0 in an and 180 in an and None not in an[0][:2] and None not in an[180][:2]:
        # front image-left = her right leg = back image-right
        for leg, fa, fb in (('她的右腳', an[0][0], an[180][1]), ('她的左腳', an[0][1], an[180][0])):
            d_ = abs(fa / fb - 1)
            report(PASS if d_ < TH else FAIL, f'腳踝 0° vs 180°（{leg}）',
                   f'{100 * fa:.2f}% vs {100 * fb:.2f}% 身高（差 {100 * d_:.0f}%，應 < {100 * TH:.0f}%）')
    for a, b2 in ((90, 270), (45, 225), (135, 315)):
        if a in an and b2 in an and an[a][2] and an[b2][2]:
            d_ = abs(an[a][2] / an[b2][2] - 1)
            report(PASS if d_ < TH else FAIL, f'腳踝 {a}° vs {b2}°',
                   f'雙腳踝總寬 {100 * an[a][2]:.2f}% vs {100 * an[b2][2]:.2f}% 身高（差 {100 * d_:.0f}%，應 < {100 * TH:.0f}%）'
                   + ('；這兩張的腳形或站位不同，重新生成其中一張' if d_ >= TH else ''))

    # ---- 8. extra image sets (B–E)
    if any(extra.values()):
        print('\n8. 額外圖片檢查（俯視 / 俯角環 / 頭部特寫 / 仰角）')
    for cat, items in extra.items():
        hs_ = []
        for a, v in sorted(items.items()):
            im = v['im']; H_, W_ = im.shape[:2]
            m, lab, bg = segment(im)
            tag = f'{cat} {v["name"]}'
            if m is None or m.sum() < 0.01 * H_ * W_:
                report(FAIL, tag, '去背失敗：找不到人物（背景要純白、均勻）')
                continue
            v['m'] = m
            report_blob(tag, im, m)
            t, b, l, r = bbox(m)
            minh = 1500 if cat == 'head' else args.min_height
            if max(H_, W_) < minh:
                report(WARN, tag, f'解析度 {W_}x{H_}（建議 ≥ {minh}）')
            if cat == 'head':
                # close-ups are cut at the shoulders (sides / bottom); only the top of the head must be in frame
                if t < 2:
                    report(FAIL, tag, '頭頂被切到，上方需留白')
            elif l < 2 or r > W_ - 3 or t < 2 or b > H_ - 3:
                report(FAIL, tag, '人物碰到畫面邊緣，需完整入鏡並留白')
            if cat == 'top':
                ar = (r - l) / max(1, b - t)
                report(PASS if ar > 2.5 else FAIL, tag,
                       f'俯視輪廓寬 / 高 = {ar:.1f}（T-pose 從正上方看應是左右很長的十字形，> 2.5；'
                       f'若太小可能不是正上方、或手臂不在畫面橫向）')
                if len(good) >= 6:
                    hull_ = quick_hull(good)
                    cs, fs, sr, cov, hshare, ov_, where_ = top_consistency(hull_, m)
                    ovp = os.path.splitext(args.out)[0] + '_top_check.png'
                    cv2.imwrite(ovp, ov_)
                    lvl = PASS if cov >= 0.97 else WARN if cov >= 0.93 else FAIL
                    why = '' if lvl == PASS else (
                        '；超出的部分主要在頭部（%d%%）→ 俯視相機太近、透視太強（頭被拍得太大），請用長焦距 / 正交投影、相機拉遠重新生成' % (100 * hshare)
                        if hshare > 0.5 else
                        '；超出的部分在：' + '、'.join(f'{k}（{100 * v:.0f}%）' for k, v in where_.items()) +
                        ' → 這些部位在俯視圖和主環裡的位置 / 大小不一致（或相機不在正上方），請重新生成 top.jpg，'
                        '讓髮髻、腳的位置和主環相同（對照圖紅色 = 只有俯視圖有，綠色 = 只有主環有，手臂的綠色正常）')
                    report(lvl, tag + ' 與主環一致性',
                           f'俯視圖身體中段有 {100 * cov:.1f}% 落在主環重建形狀之內（應 ≥ 97%）；'
                           f'重合度 {cs:.2f}（含手臂 {fs:.2f}，主環看不到手臂上下厚度，只供參考）；對照圖 {ovp}' + why)
            if cat == 'head':
                hfrac = (b - t) / H_
                report(PASS if hfrac >= 0.6 else WARN, tag, f'頭到肩高度佔畫面 {100 * hfrac:.0f}%（應 ≥ 60%）')
            hs_.append(b - t)
        if len(hs_) >= 2 and cat in ('el30', 'head', 'low20'):
            sp = (max(hs_) - min(hs_)) / np.mean(hs_)
            report(PASS if sp < 0.03 else WARN, f'{cat} 大小一致', f'各張人物 / 頭部高度差 {100 * sp:.1f}%（應 < 3%）')
        if cat not in ('el30', 'head', 'low20'):
            continue
        okv = {a: v for a, v in items.items() if v.get('m') is not None}
        # (a) real angles for the body rings, from the hand span relative to that ring's own 000 view
        if cat in ('el30', 'low20') and 0 in okv:
            sp0, h0_ = hand_span(okv[0]['m'])
            for a, v in sorted(okv.items()):
                if a in (0, 180):
                    continue
                sp_, hh_ = hand_span(v['m'])
                r_ = min(1.0, (sp_ / hh_) / (sp0 / h0_))
                exp_ = min(a % 180, 180 - a % 180)
                if exp_ == 90:
                    report(PASS if r_ < 0.40 else FAIL, f'{cat} {a}° 角度',
                           f'展開寬比例 {r_:.2f}（真側面應 < 0.40）' + ('' if r_ < 0.40 else '，角度不到 90°'))
                else:
                    est_ = np.degrees(np.arccos(r_))
                    report(PASS if abs(est_ - exp_) <= 12 else FAIL, f'{cat} {a}° 角度',
                           f'推算約 {est_:.0f}°（應為 {exp_}°，±12° 內；俯 / 仰角會讓推算略有偏差）')
        # (b) flipped copies inside the ring
        angs_ = sorted(okv)
        flips = []
        for i_, a in enumerate(angs_):
            for b_ in angs_[i_ + 1:]:
                A = cv2.resize(okv[a]['im'], (256, 256), interpolation=cv2.INTER_AREA).astype(np.float32)
                B = cv2.resize(okv[b_]['im'], (256, 256), interpolation=cv2.INTER_AREA).astype(np.float32)
                fgm = cv2.resize((okv[a]['m'] | okv[b_]['m'][:, ::-1]).astype(np.uint8), (256, 256)) > 0
                if np.abs(A - B[:, ::-1]).max(2)[fgm].mean() < 4:
                    flips.append(f'{b_}° 是 {a}° 的左右翻轉')
        report(WARN if flips else PASS, f'{cat} 翻轉複製', '；'.join(flips) if flips else '沒有發現左右翻轉複製的圖')
        # (c) lighting direction consistent within the ring
        # head close-ups: use only neck / shoulders (face vs hair colour would fake a lighting direction)
        ldr = {a: (light_dir(v['im'], v['m'], 0.75, 0.98) if cat == 'head' else light_dir(v['im'], v['m']))
               for a, v in okv.items()}
        strong_ = {a: d for a, d in ldr.items() if abs(d[0]) > 0.06 and (d[1] > 0.65 or d[1] < 0.35)}
        if len(strong_) >= max(3, 0.6 * len(okv)):
            maj = np.sign(sum(np.sign(d[0]) for d in strong_.values())) or 1.0
            odd_ = sorted(a for a, d in strong_.items() if np.sign(d[0]) != maj)
            report(WARN if odd_ else PASS, f'{cat} 光線方向',
                   f'{", ".join(f"{a}°" for a in odd_)} 的亮側和其他張相反，可能是左右翻轉做出來的' if odd_
                   else f'每張都是{"畫面左側" if maj > 0 else "畫面右側"}較亮，一致')
        else:
            report(PASS, f'{cat} 光線方向', '光線沒有明顯方向性，此項不判斷')

    # ---- 9. exposure: skin lightness of every image vs. the main ring (big differences show as seams)
    print('\n9. 曝光一致性（每張圖的膚色亮度和主環比較）')
    allimgs = [(f'{a}°', v) for a, v in sorted(good.items())] + \
              [(f'{c} {a}', v) for c, items in extra.items() for a, v in sorted(items.items()) if v.get('m') is not None]
    lv = {k: skin_lightness(v['im'], v['m']) for k, v in allimgs}
    ref_ = [lv[f'{a}°'] for a in good if lv.get(f'{a}°')]
    if ref_:
        med = float(np.median(ref_))
        odd = [(k, x / med - 1) for k, x in lv.items() if x and abs(x / med - 1) > 0.12]
        for k, d_ in odd:
            report(WARN, f'{k} 曝光', f'膚色亮度比主環{"亮" if d_ > 0 else "暗"} {100 * abs(d_):.0f}%（應在 ±12% 內）；'
                                       f'光線 / 曝光要和主環相同，否則重建後會看到色差接縫')
        if not odd:
            report(PASS, '曝光一致', f'{len(lv)} 張的膚色亮度都在主環的 ±12% 內')

    # ---- 10. silhouette consistency with the main-ring shape (red / blue sheet)
    if len(good) >= 7:
        print('\n10. 剪影一致性（主環重建形狀投影到每張身體圖，輸出紅藍對照圖）')
        svp = os.path.splitext(args.out)[0] + '_silhouette_check.png'
        rows_ = ring_consistency(good, extra, svp)
        for r_ in rows_:
            lab = f"{'主環' if r_['cat'] == 'main' else r_['cat']} {r_['ang']}°"
            blue = 1 - r_['cover']
            side = r_['cat'] == 'main' and r_['ang'] in (90, 270)
            bp, bw = (BLUE_SIDE_PASS, BLUE_SIDE_WARN) if side else (BLUE_PASS, BLUE_WARN)
            lvl = PASS if blue <= bp else WARN if blue <= bw else FAIL
            msg = (f"藍色（照片有、主環形狀沒有）{100 * blue:.1f}%（應 ≤ {100 * bp:.0f}%，> {100 * bw:.0f}% 判 FAIL"
                   + ('；側面不參與建形狀，方法本身就有 2–3%' if side else '') + '）；'
                   f"紅色（形狀超出照片）{100 * r_['red']:.0f}%，只供參考：形狀由剪影雕出，一定比真實身體大，完美照片也有 3–75%")
            if lvl != PASS:
                w_ = r_['where']
                msg += '；藍色在：' + ('、'.join(f'{k}（{100 * x:.0f}%）' for k, x in w_.items()) or '各處')
                if w_.get('手', 0) + w_.get('頭', 0) >= 0.5 and w_.get('手', 0) >= 0.3:
                    msg += (' → 靠近相機的手被畫得比主環長 / 方向不同（頭也偏大）：典型的透視（見第 10b 項），'
                            '或這張的手臂姿勢和主環不同；請用 orthographic / 長焦距、相機拉遠重新生成這張')
                elif '頭' in w_ and w_['頭'] >= 0.5:
                    msg += ' → 頭被畫得比主環大：相機太近、透視太強（俯角環最常見），請相機拉遠 / 長焦距重新生成這張'
                else:
                    msg += ' → 這張的身體形狀 / 姿勢和主環不一致，請重新生成這張'
            report(lvl, lab + ' 剪影', msg)
        print(f'  對照圖: {svp}')
        print('\n10b. 透視強度（斜角 4 張：兩手指尖中點應在身體中軸上；透視會讓中點偏向靠近相機的手）')
        for k, (p_, dist_, vals_) in perspective_check(good, extra).items():
            lab = {'main': '主環', 'el30': '俯角環', 'low20': '仰角環'}[k]
            lvl = PASS if p_ < PERSP_PASS else WARN if p_ < PERSP_WARN else FAIL
            msg = (f"指尖中點偏向近手 {100 * p_:.1f}% 半臂展（應 < {100 * PERSP_PASS:.0f}%；"
                   + '、'.join(f'{a}° {100 * x:+.0f}%' for a, x in sorted(vals_.items())) + '）')
            if lvl != PASS:
                msg += f"；估計相機距離約 {dist_:.0f} 倍半臂展（約 {dist_ * 0.78:.1f} m，以身高 1.65 m 計）"
            if lvl != PASS:
                msg += (' → 照片是透視投影（相機太近），重建程式假設正交投影：手臂長度、方向在不同角度會不一致'
                        '（第 10 項藍色多在手上）。提示詞加 orthographic projection / 200mm telephoto / camera far away')
            report(lvl, lab + ' 透視', msg)
        print('\n10c. 俯角 / 仰角環和水平主環的寬度比（手寬 / 臀寬、頭寬 / 臀寬，供人工複核）')
        for (cat, a), (dh, dd) in ring_ratio_check(good, extra).items():
            worst = max(abs(dh), abs(dd))
            lvl = WARN if worst >= RATIO_WARN else PASS
            msg = (f'手寬比差 {100 * dh:+.0f}%、頭寬比差 {100 * dd:+.0f}%（和主環 {a}° 比，'
                   f'差 ≥ {100 * RATIO_WARN:.0f}% 判 WARN）')
            if lvl == WARN:
                review = '優先複核' if worst >= RATIO_REVIEW else '複核'
                msg += f' → {review}這張與同角度主環的輪廓、俯仰角與姿勢'
            report(lvl, f'{cat} {a}° 寬度比', msg)

    # ---- report image
    tiles = []
    allv = [(f'{a} deg', v) for a, v in sorted(views.items())] + \
           [(f'{c} {a}', v) for c, items in extra.items() for a, v in sorted(items.items())]
    for a, v in allv:
        im = v['im'].copy()
        if v.get('m') is not None:
            cnt, _ = cv2.findContours(v['m'].astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
            cv2.drawContours(im, cnt, -1, (0, 0, 255), max(2, im.shape[0] // 400))
        s = 600 / im.shape[0]
        im = cv2.resize(im, (int(im.shape[1] * s), 600))
        cv2.putText(im, str(a), (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 200), 2)
        tiles.append(im)
    wmax = max(t.shape[1] for t in tiles)
    tiles = [cv2.copyMakeBorder(t, 0, 0, 0, wmax - t.shape[1], cv2.BORDER_CONSTANT, value=(255, 255, 255)) for t in tiles]
    rows = [np.hstack(tiles[i:i + 4] + [np.full_like(tiles[0], 255)] * (4 - len(tiles[i:i + 4]))) for i in range(0, len(tiles), 4)]
    cv2.imwrite(args.out, np.vstack(rows))

    nF = sum(1 for r in results if r[0] == FAIL); nW = sum(1 for r in results if r[0] == WARN)
    nI = sum(1 for r in results if r[0] == INFO)
    print(f'\n總結: {nF} 個 FAIL, {nW} 個 WARN, {len(results) - nF - nW - nI} 個 PASS   報告圖: {args.out}')
    if nF:
        print('有 FAIL：這組圖不適合直接重建，請依上面的說明重新生成對應的圖。')
    elif nW:
        print('只有 WARN：可以用，但結果可能受影響。')
    else:
        print('全部通過：這組圖適合做 3D 重建。')
    sys.exit(1 if nF else 0)


if __name__ == '__main__':
    main()
