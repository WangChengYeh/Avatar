#!/usr/bin/env python3
"""
check_turnaround.py — 檢查一組人物旋轉圖（turnaround）是否適合做 3D 重建
版本 1.21.0（2026-11-24）

版本紀錄:
  1.21.0 --mode ai（預設）/ photo：AI 生成的圖可以重來，門檻改成「完美照片 + 小餘裕」，翻轉複製、光線翻轉、
         解析度、背景 / 陰影等 WARN 在 ai 模式判 FAIL；俯角 / 仰角環大小一致改比相差 180° 的兩張；
         第 11 項：臉部一致性（頭部特寫 0° / 45° / 315° 都要找得到臉；五官比例、頭髮高度 / 臉高要和正面一致，
         扣掉偵測偏差後 ±2%，> 4% 判 FAIL）
  1.20.0 疊圖及 CSV 加入亮度一致率、五官對位誤差與獨立的覆蓋率判定。
  1.19.0 新增各視角照片回投到正面及背面的疊圖、差異圖與覆蓋率。
  1.18.0 收緊曝光、臉頰亮度與五官門檻，關鍵尺寸或位置嚴重偏差會擋下烘焙。
  1.17.0 五官投影檢查加入眼距、鼻寬、口寬、臉型等尺寸及縮放後比例差。
  1.16.0 烘焙前比對正面與左右斜面的五官投影，列出整體縮放和平移試算前後的偏移。
  1.15.0 收緊生圖曝光規格，新增照片臉頰亮度粗篩及烘焙前亮度門檻。
  1.14.0 新增重建輸入格式、角度檔名與重複照片檢查，並輸出頭部局部複核圖。
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
    五官對位另讀取 face_lm33_045.npy 與 face_lm33_315.npy。
    加 --view-overlay-dir 報告資料夾 可輸出正背面疊圖。


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
  - 33 張圖鎖定同一組曝光、白平衡、光源方向與強度，各視角不使用自動曝光。
  - 臉部用均勻柔光，正面和左右斜面的臉頰要保持同一膚色亮度。避免深色帶、局部高光及分區補光。
  - 第 9 項曝光粗篩：全圖平均膚色亮度相對主環偏差應 ≤ 3%；頭部臉頰取樣亮度差應 ≤ 5 / 255。
  - 烘焙前投影重疊檢查：共同可見臉頰亮度絕對差的第 90 百分位應 ≤ 12 / 255；
    > 12 至 20 判 WARN，> 20 判 FAIL。

七、畫質
  - 重建輸入全部使用 2048 × 2048 的 JPEG，副檔名為小寫 .jpg。
  - 對焦清楚、無動態模糊、無明顯壓縮色塊。
  - 不要加浮水印、文字、邊框。

八、檔名（全部放在同一個資料夾）
  A 主環     NN_AAAdeg_說明.jpg   例: 01_000deg_front.jpg … 08_315deg_front_right.jpg
  B 俯視     top.jpg
  C 俯角環   el30_AAAdeg.jpg      例: el30_000deg.jpg、el30_045deg.jpg … el30_315deg.jpg
  D 頭部特寫 head_AAAdeg.jpg      例: head_000deg.jpg … head_315deg.jpg
  E 仰角環   low20_AAAdeg.jpg     例: low20_000deg.jpg、low20_045deg.jpg … low20_315deg.jpg
  - 每組每個角度只放一張，主環正面以 01_000deg 開頭。
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
  - 每張沿用同一段亮度提示詞：
      fixed exposure and white balance across all views, even diffuse facial lighting,
      consistent cheek brightness, no hard shadows or local highlights on the cheeks
  - 透視越小越好：提示詞用長焦距（例如 200mm）或 orthographic / turnaround sheet 風格（第 10、10b 項會檢查；第 10c 項提供寬度比複核提示）。
    俯角 30° 環最容易出問題（AI 會把相機放得很近、從上往下拍，頭大腳小）。重新生成時每張都加上：
      orthographic projection, 200mm telephoto lens, camera very far away, no perspective distortion,
      head and feet drawn at the same scale, technical character turnaround sheet
    並寫明：camera elevated 30 degrees looking down, same distance and framing as the eye-level views,
    same T-pose, arms horizontal。
"""
import argparse, csv, hashlib, json, os, re, sys
from itertools import combinations
from pathlib import Path

__version__ = '1.21.0'
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
# --mode ai (default): AI images can be regenerated at no cost, so thresholds are "perfect photos + a small margin"
# and policy items (flipped copies, lighting flips, resolution) FAIL. --mode photo: the looser 1.11 thresholds.
MODE = {'ai': True}


def T(ai, photo):
    """threshold for the current mode"""
    return ai if MODE['ai'] else photo


def strict(level):
    """WARN becomes FAIL in AI mode (for items that are simply wrong, e.g. a flipped copy)"""
    return FAIL if (MODE['ai'] and level == WARN) else level
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


# section 11, face consistency of the head close-ups (needs mediapipe). Ratios of vertical distances only, so with
# level orthographic cameras they are the same in every view; MediaPipe itself reads 3/4 faces a little
# differently, so the 3/4 views are compared with the bias measured on perfect (rendered) photos.
FACE_VIEWS = (0, 45, 315)
FACE_BIAS = {'prop': 1.024, 'hair': 1.055}      # 3/4 view / frontal view on perfect photos
FACE_PASS, FACE_FAIL = 0.02, 0.04               # |ratio / bias - 1|; perfect photos: 0–0.6 %


def face_measures(im, m):
    """(eye->mouth / brow->chin, head top->brow / brow->chin, face height px) or None if no face"""
    try:
        import mediapipe as mp
    except ImportError:
        return 'nomp'
    h, w = im.shape[:2]
    with mp.solutions.face_mesh.FaceMesh(static_image_mode=True, min_detection_confidence=0.3) as fm:
        r = fm.process(cv2.cvtColor(im, cv2.COLOR_BGR2RGB))
    if not r.multi_face_landmarks:
        return None
    L = np.array([[l.x * w, l.y * h] for l in r.multi_face_landmarks[0].landmark])
    foreground_rows = np.flatnonzero(m.any(1))
    if not foreground_rows.size:
        return None
    top = foreground_rows[0]
    brow = L[[105, 334], 1].mean(); eye = L[[33, 133, 362, 263], 1].mean()
    mouth = L[[61, 291, 13, 14], 1].mean(); chin = L[152, 1]
    face = chin - brow
    if not np.isfinite(L).all() or face <= 0 or mouth <= eye or brow <= top:
        return None
    return (mouth - eye) / face, (brow - top) / face, face


def face_check(extra):
    """11. returns list of (level, label, message)"""
    heads = extra.get('head', {})
    out = []
    M = {}
    for a in FACE_VIEWS:
        v = heads.get(a)
        if v is None or v.get('m') is None:
            out.append((FAIL, f'head {a}° 臉部', '缺少可用的頭部特寫'))
            continue
        r = face_measures(v['im'], v['m'])
        if r == 'nomp':
            return [(WARN, '臉部一致性', '沒有安裝 mediapipe，第 11 項無法檢查（pip install "mediapipe==0.10.14"）')]
        if r is None:
            out.append((FAIL, f'head {a}° 臉部', '找不到臉（MediaPipe）：正面 / 3/4 頭部特寫要清楚看到五官，'
                                                   '不要被頭髮遮住，也不要轉超過 45°'))
        else:
            M[a] = r
            out.append((PASS, f'head {a}° 臉部', f'找到臉，臉高 {r[2]:.0f} px'))
    if 0 not in M:
        return out
    pass_limit, fail_limit = T(FACE_PASS, 0.04), T(FACE_FAIL, 0.08)
    for a in (45, 315):
        if a not in M:
            continue
        for k, i, what in (('prop', 0, '五官比例（眼到嘴 / 眉到下巴）'), ('hair', 1, '頭髮高度 / 臉高（頭頂到眉 / 眉到下巴）')):
            dev = (M[a][i] / M[0][i]) / FACE_BIAS[k] - 1
            lvl = PASS if abs(dev) <= pass_limit else WARN if abs(dev) <= fail_limit else FAIL
            msg = (f'{what}：{M[a][i]:.3f}，正面 {M[0][i]:.3f}，扣掉 3/4 偵測偏差後差 {100 * dev:+.1f}%'
                   f'（應在 ±{100 * pass_limit:.0f}% 內，> {100 * fail_limit:.0f}% 判 FAIL）')
            if lvl != PASS:
                if k == 'hair':
                    msg += (' → 這張 3/4 特寫的' + ('臉畫得比正面大（或頭髮比較扁）' if dev < 0 else '臉畫得比正面小（或頭髮比較蓬）') +
                            '：重建用頭髮輪廓對齊相機，臉會和正面錯開，貼圖出現兩層臉。重新生成，要求和 head_000 '
                            '同一個髮型、同樣的頭髮蓬度、同樣的臉部大小')
                else:
                    msg += ' → 五官位置和正面不同（不是同一張臉 / 表情不同），重新生成這張'
            out.append((lvl, f'head {a}° vs 0° {"五官比例" if k == "prop" else "髮高比"}', msg))
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
# Brightness thresholds use the 0–255 grayscale scale unless noted.
EXPOSURE_MAX_DIFF = 0.03
PHOTO_CHEEK_MAX_DIFF = 5.0
PROJECTED_LUMA_PASS = 12.0
PROJECTED_LUMA_FAIL = 20.0


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


# MediaPipe landmark indices. Keep the mouth out of the scale/translation fit.
FEATURE_POINTS = (
    ('眼部', (33, 133, 159, 145, 263, 362, 386, 374)),
    ('鼻部', (1, 2, 4, 98, 327)),
    ('嘴部', (61, 291, 13, 14, 17, 0)),
)
ALIGNMENT_REVIEW_FRACTION = 0.01
ALIGNMENT_FAIL_FRACTION = 0.015
ALIGNMENT_FAIL_MIN_POINTS = 3

# Tuple endpoints use the mean image position of the specified landmarks.
RIGHT_EYE_CENTER, LEFT_EYE_CENTER = (33, 133), (362, 263)
EYE_MIDLINE = RIGHT_EYE_CENTER + LEFT_EYE_CENTER
MOUTH_CENTER = (13, 14)
FACE_DIMENSIONS = (
    ('眼距（眼角中點）', RIGHT_EYE_CENTER, LEFT_EYE_CENTER),
    ('內眼角距', (133,), (362,)),
    ('外眼角距', (33,), (263,)),
    ('右眼寬', (33,), (133,)),
    ('左眼寬', (362,), (263,)),
    ('右眼開合', (159,), (145,)),
    ('左眼開合', (386,), (374,)),
    ('鼻翼寬', (98,), (327,)),
    ('鼻樑至鼻尖', (168,), (1,)),
    ('眼線中心至鼻尖', EYE_MIDLINE, (1,)),
    ('鼻底至上唇', (2,), (0,)),
    ('嘴寬', (61,), (291,)),
    ('唇部開合', (13,), (14,)),
    ('嘴部中心至下巴', MOUTH_CENTER, (152,)),
    ('顴部寬', (234,), (454,)),
    ('下顎寬', (172,), (397,)),
    ('前額至下巴', (10,), (152,)),
)
FEATURE_ANCHORS = tuple(dict.fromkeys(
    [(index,) for _, indices in FEATURE_POINTS for index in indices] +
    [anchor for _, first, second in FACE_DIMENSIONS for anchor in (first, second)]))
DIMENSION_REVIEW_FRACTION = 0.04
DIMENSION_REVIEW_MIN_PX = 2.0
DIMENSION_FAIL_FRACTION = 0.08
DIMENSION_FAIL_MIN_PX = 5.0
# Gate stable dimensions with reliable paired landmarks. Openings/face outlines stay advisory.
CRITICAL_DIMENSIONS = {
    '眼距（眼角中點）', '內眼角距', '外眼角距', '右眼寬', '左眼寬',
    '鼻翼寬', '鼻樑至鼻尖', '嘴寬',
}


def mesh_point_at(pixel, triangles, projected, depths):
    """Find the foremost surface point under a pixel in an orthographic view."""
    x, y = pixel
    cols, rows = projected[:, :, 0], projected[:, :, 1]
    candidates = np.flatnonzero(
        (cols.min(1) <= x) & (cols.max(1) >= x) &
        (rows.min(1) <= y) & (rows.max(1) >= y))
    if not len(candidates):
        return None, None

    a, b, c = projected[candidates].transpose(1, 0, 2)
    edge1, edge2 = b - a, c - a
    delta = pixel - a
    denominator = edge1[:, 0] * edge2[:, 1] - edge1[:, 1] * edge2[:, 0]
    nondegenerate = np.abs(denominator) > 1e-9
    safe = np.where(nondegenerate, denominator, 1)
    w1 = (delta[:, 0] * edge2[:, 1] - delta[:, 1] * edge2[:, 0]) / safe
    w2 = (edge1[:, 0] * delta[:, 1] - edge1[:, 1] * delta[:, 0]) / safe
    weights = np.column_stack((1 - w1 - w2, w1, w2))
    inside = nondegenerate & (weights.min(1) >= -1e-7)
    if not inside.any():
        return None, None

    hit_indices = candidates[inside]
    hit_weights = weights[inside]
    front = np.argmax((depths[hit_indices] * hit_weights).sum(1))
    triangle = triangles[hit_indices[front]]
    point = hit_weights[front] @ triangle
    normal = np.cross(triangle[1] - triangle[0], triangle[2] - triangle[0])
    return point, normal / max(np.linalg.norm(normal), 1e-12)


def estimate_scale_translation(projected, observed):
    """Fit a single positive isotropic scale and a translation in pixel space."""
    x_center, y_center = projected.mean(0), observed.mean(0)
    x, y = projected - x_center, observed - y_center
    variance = np.sum(x * x)
    if variance <= 1e-9:
        return None
    scale = np.sum(x * y) / variance
    if scale <= 0:
        return None
    return scale, y_center - scale * x_center


def projected_triangles(triangles, cam):
    flat = triangles.reshape(-1, 3)
    xy = np.column_stack(camera_project(flat, cam)).reshape(-1, 3, 2)
    return xy, camera_depth(flat, cam).reshape(-1, 3)


def landmark_correspondences(triangles, front_cam, side_cam, frontal, oblique):
    front_xy, front_depth = projected_triangles(triangles, front_cam)
    side_xy, side_depth = projected_triangles(triangles, side_cam)
    _, _, direction = camera_axes(side_cam['phi'], side_cam['th'])
    samples = {}
    for anchor in FEATURE_ANCHORS:
        point, normal = mesh_point_at(frontal[list(anchor)].mean(0), triangles, front_xy, front_depth)
        if point is None or normal @ direction < 0.25:
            continue
        pixel = np.array(camera_project(point, side_cam))
        visible, _ = mesh_point_at(pixel, triangles, side_xy, side_depth)
        if visible is None or np.linalg.norm(visible - point) > 0.008:
            continue
        samples[anchor] = (pixel, oblique[list(anchor)].mean(0))
    return samples


def group_landmark_samples(samples):
    pairs = {}
    for label, indices in FEATURE_POINTS:
        visible = [samples[(i,)] for i in indices if (i,) in samples]
        if visible:
            pairs[label] = tuple(np.asarray(visible).transpose(1, 0, 2))
        else:
            pairs[label] = (np.empty((0, 2)), np.empty((0, 2)))
    return pairs


def dimension_status(label, difference, fraction, calibrated):
    if (calibrated and label in CRITICAL_DIMENSIONS
            and abs(difference) > DIMENSION_FAIL_MIN_PX
            and abs(fraction) > DIMENSION_FAIL_FRACTION):
        return FAIL
    if abs(difference) > DIMENSION_REVIEW_MIN_PX and abs(fraction) > DIMENSION_REVIEW_FRACTION:
        return WARN
    return PASS


def report_face_dimensions(side, samples, scale):
    """Compare distances in the same view, before and after correcting global scale."""
    failed = False
    for label, first, second in FACE_DIMENSIONS:
        if first not in samples or second not in samples:
            print(f'[INFO] 五官尺寸 {side} {label}：共同可見點不足')
            continue
        projected_a, observed_a = samples[first]
        projected_b, observed_b = samples[second]
        expected = float(np.linalg.norm(projected_a - projected_b))
        observed = float(np.linalg.norm(observed_a - observed_b))
        if expected < 1.0:
            print(f'[INFO] 五官尺寸 {side} {label}：投影距離小於 1 px')
            continue

        reference = expected * scale if scale is not None else expected
        difference = observed - reference
        fraction = difference / reference
        level = dimension_status(label, difference, fraction, scale is not None)
        failed |= level == FAIL
        resized = f'，縮放後投影 {reference:.1f} px' if scale is not None else ''
        suffix = '縮放後差' if scale is not None else '原始差'
        print(f'[{level}] 五官尺寸 {side} {label}：原始投影 {expected:.1f} px，照片 {observed:.1f} px'
              f'{resized}；{suffix} {difference:+.1f} px（{100 * fraction:+.1f}%）')
    return failed


# Each endpoint comes from the side where it faces the camera.
BILATERAL_DIMENSIONS = (
    ('眼距（眼角中點）', RIGHT_EYE_CENTER, LEFT_EYE_CENTER),
    ('外眼角距', (33,), (263,)),
    ('嘴寬', (61,), (291,)),
    ('顴部寬', (234,), (454,)),
    ('下顎寬', (172,), (397,)),
)


def oblique_endpoints_to_front(side, samples, fit, triangles, front_cam, side_cam):
    """Back-project the visible, nearer half of an oblique photo to frontal pixels."""
    scale, shift = fit
    near_index = 0 if side == 'head_315deg' else 1
    anchors = {(first, second)[near_index] for _, first, second in BILATERAL_DIMENSIONS}
    side_xy, side_depth = projected_triangles(triangles, side_cam)
    front_xy, front_depth = projected_triangles(triangles, front_cam)
    _, _, side_direction = camera_axes(side_cam['phi'], side_cam['th'])
    projected = {}
    for anchor in anchors.intersection(samples):
        normalized_pixel = (samples[anchor][1] - shift) / scale
        point, normal = mesh_point_at(normalized_pixel, triangles, side_xy, side_depth)
        if point is None or normal @ side_direction < 0.25:
            continue
        pixel = np.array(camera_project(point, front_cam))
        visible, _ = mesh_point_at(pixel, triangles, front_xy, front_depth)
        if visible is not None and np.linalg.norm(visible - point) <= 0.008:
            projected[anchor] = pixel
    return projected


def report_bilateral_dimensions(frontal, back_projected, overlay_kpis=None):
    """Compare frontal spans using one visible endpoint from each oblique view."""
    right = back_projected.get('head_315deg', {})
    left = back_projected.get('head_045deg', {})
    failed = False
    for label, first, second in BILATERAL_DIMENSIONS:
        if first not in right or second not in left:
            print(f'[INFO] 五官尺寸 斜面回投正面 {label}：左右可見端點不足')
            continue
        reference = float(np.linalg.norm(frontal[list(first)].mean(0) - frontal[list(second)].mean(0)))
        if reference < 1.0:
            print(f'[INFO] 五官尺寸 斜面回投正面 {label}：正面距離小於 1 px')
            continue
        estimated = float(np.linalg.norm(right[first] - left[second]))
        difference = estimated - reference
        fraction = difference / reference
        level = dimension_status(label, difference, fraction, calibrated=True)
        failed |= level == FAIL
        if overlay_kpis is not None and first == RIGHT_EYE_CENTER and second == LEFT_EYE_CENTER:
            overlay_kpis['bilateral_eye_span'] = (100 * fraction, level)
        print(f'[{level}] 五官尺寸 斜面回投正面 {label}：正面照片 {reference:.1f} px，'
              f'左右斜面回投 {estimated:.1f} px；差 {difference:+.1f} px（{100 * fraction:+.1f}%）')
    return failed


def report_landmark_alignment(work, cameras, frontal, vertices, photo_height, overlay_kpis=None):
    min_count = max(index for anchor in FEATURE_ANCHORS for index in anchor) + 1
    sides = [(f'head_{angle}deg', work / f'face_lm33_{angle}.npy') for angle in ('045', '315')]
    if len(frontal) < min_count or not any(path.is_file() for _, path in sides):
        print('[WARN] 五官投影：取樣資料不足，需要正面與斜面特徵點')
        return False
    try:
        with np.load(work / 'uvmesh.npz') as mesh:
            triangles = vertices[mesh['tri']]
        triangles = triangles[(triangles[:, :, 1] >= 1.36).any(1)]
    except (OSError, KeyError, IndexError, ValueError) as error:
        print(f'[WARN] 五官投影：無法讀取三角網格（{error}）')
        return False

    limit = photo_height * ALIGNMENT_REVIEW_FRACTION
    fail_limit = photo_height * ALIGNMENT_FAIL_FRACTION
    back_projected = {}
    failed = False
    for side, path in sides:
        if not path.is_file() or side not in cameras:
            print(f'[WARN] 五官投影 {side}：缺少斜面特徵點或相機')
            continue
        if cameras[FRONT].get('D') or cameras[side].get('D'):
            print(f'[WARN] 五官投影 {side}：需要正交頭部相機')
            continue
        try:
            oblique = np.load(path)
            if (oblique.ndim != 2 or oblique.shape[0] < min_count or oblique.shape[1] < 2
                    or not np.isfinite(oblique[:, :2]).all()):
                raise ValueError('斜面特徵點無效')
        except (OSError, ValueError) as error:
            print(f'[WARN] 五官投影 {side}：{error}')
            continue

        samples = landmark_correspondences(triangles, cameras[FRONT], cameras[side], frontal, oblique[:, :2])
        pairs = group_landmark_samples(samples)
        eyes, nose = pairs['眼部'], pairs['鼻部']
        fit = None
        if len(eyes[0]) >= 2 and len(nose[0]) >= 2:
            fit = estimate_scale_translation(np.vstack((eyes[0], nose[0])), np.vstack((eyes[1], nose[1])))
        if fit is not None:
            scale, shift = fit
            print(f'[INFO] 五官投影 {side}：用眼鼻試算整體縮放 {scale:.3f}× 與平移'
                  f'（x {shift[0]:+.1f}，y {shift[1]:+.1f} px）；嘴部用於驗證')
        else:
            print(f'[WARN] 五官投影 {side}：共同可見眼鼻點不足，無法試算整體縮放')

        for label, (points, targets) in pairs.items():
            if len(points) < 2:
                print(f'[WARN] 五官投影 {side} {label}：共同可見點不足（{len(points)} 點）')
                continue
            offsets = targets - points
            before = float(np.median(np.linalg.norm(offsets, axis=1)))
            dx, dy = np.median(offsets, axis=0)
            fitted = scale * points + shift if fit is not None else points
            after = float(np.median(np.linalg.norm(targets - fitted, axis=1)))
            if fit is not None and len(points) >= ALIGNMENT_FAIL_MIN_POINTS and after > fail_limit:
                level = FAIL
                failed = True
            else:
                level = WARN if before > limit or after > limit else PASS
            if overlay_kpis is not None and fit is not None:
                overlay_kpis.setdefault(side, {})[label] = (after, level)
            correction = f'{before:.1f} → {after:.1f} px' if fit is not None else f'{before:.1f} px'
            guidance = '；整體校正後仍需複核局部對位' if fit is not None and after > limit else ''
            if level == FAIL:
                guidance += f'（校正後失敗門檻 > {fail_limit:.1f} px）'
            print(f'[{level}] 五官投影 {side} {label}：中位偏移 {correction}'
                  f'（{len(points)} 點，目標 ≤ {limit:.1f} px）；'
                  f'原始偏移 x {dx:+.1f}、y {dy:+.1f} px（右、下為正）{guidance}')
        failed |= report_face_dimensions(side, samples, fit[0] if fit is not None else None)
        if fit is not None:
            back_projected[side] = oblique_endpoints_to_front(
                side, samples, fit, triangles, cameras[FRONT], cameras[side])
    if len(back_projected) == len(sides):
        failed |= report_bilateral_dimensions(frontal, back_projected, overlay_kpis)
    return failed


def report_head_overlap(folder, work, overlay_kpis=None):
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
        return 0

    band = cheek_band(landmarks, frontal_image.shape, col, row)
    face_midline = np.median(landmarks[:, 0])
    failed = False
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
        status = PASS if p90 <= PROJECTED_LUMA_PASS else WARN if p90 <= PROJECTED_LUMA_FAIL else FAIL
        failed |= status == FAIL
        guidance = '，請複核重疊區亮度和對位' if status != PASS else ''
        print(f'[{status}] {label}：亮度絕對差中位數 {median:.1f}，第 90 百分位 {p90:.1f} / 255'
              f'（{count} 點，目標 ≤ {PROJECTED_LUMA_PASS:g}，失敗 > {PROJECTED_LUMA_FAIL:g}）{guidance}')
    failed |= report_landmark_alignment(work, cameras, landmarks, vertices, frontal_image.shape[0], overlay_kpis)
    if failed:
        print('烘焙前驗證有 FAIL：請修正列出的亮度或五官偏差。')
    return int(failed)


# ---------------------------------------------------------------- front/back reprojection report
OVERLAY_SIZE = 384
OVERLAY_TILE_SIZE = 256
OVERLAY_MIN_COVERAGE = 0.05
OVERLAY_LUMA_TOLERANCE = 20
OVERLAY_DEPTH_TOLERANCE = 0.012


def rasterize_surface(vertices, faces, cam, size=OVERLAY_SIZE, photo_size=2048, with_points=False):
    """Rasterize nearest depth and optional surface position at thumbnail pixel centers."""
    col, row = camera_project(vertices, cam)
    factor = size / photo_size
    image_xy = (np.column_stack((col, row)) + 0.5) * factor - 0.5
    _, _, direction = camera_axes(cam['phi'], cam['th'])
    depth = vertices @ direction
    distance = cam.get('D')
    reciprocal = None
    if distance:
        reciprocal = 1 / np.maximum(0.05 * distance, distance - (vertices - C0) @ direction)

    depth_map = np.full(size * size, -np.inf, np.float32)
    positions = np.full((size * size, 3), np.nan, np.float32) if with_points else None
    corners = image_xy[faces]
    bounds_low = np.maximum(0, np.ceil(corners.min(axis=1))).astype(int)
    bounds_high = np.minimum(size - 1, np.floor(corners.max(axis=1))).astype(int)
    sizes = np.maximum(0, bounds_high - bounds_low + 1)
    total_pixels = np.r_[0, np.cumsum(sizes[:, 0] * sizes[:, 1])]
    start = 0
    while start < len(faces):
        # Bound scratch allocations even when a few large triangles cover the whole image.
        pixel_limit = np.searchsorted(total_pixels, total_pixels[start] + 400_000, side='right') - 1
        stop = max(start + 1, min(start + 4096, pixel_limit))
        batch = slice(start, stop)
        ids, batch_corners = faces[batch], corners[batch]
        lo, spans = bounds_low[batch], sizes[batch]
        counts = spans[:, 0] * spans[:, 1]
        start = stop
        if not counts.any():
            continue

        candidates = np.repeat(np.arange(len(ids)), counts)
        offsets = np.arange(counts.sum()) - np.repeat(np.cumsum(counts) - counts, counts)
        width = spans[candidates, 0]
        x = lo[candidates, 0] + offsets % width
        y = lo[candidates, 1] + offsets // width

        a, b, c = batch_corners[candidates].transpose(1, 0, 2)
        edge1, edge2 = b - a, c - a
        delta = np.column_stack((x, y)) - a
        determinant = edge1[:, 0] * edge2[:, 1] - edge1[:, 1] * edge2[:, 0]
        valid = np.abs(determinant) > 1e-9
        divisor = np.where(valid, determinant, 1)
        u = (delta[:, 0] * edge2[:, 1] - delta[:, 1] * edge2[:, 0]) / divisor
        v = (edge1[:, 0] * delta[:, 1] - edge1[:, 1] * delta[:, 0]) / divisor
        weights = np.column_stack((1 - u - v, u, v))
        inside = valid & (weights.min(axis=1) >= -1e-7)
        if not inside.any():
            continue

        indices = ids[candidates[inside]]
        weights = weights[inside]
        if reciprocal is not None:
            weights *= reciprocal[indices]
            weights /= weights.sum(axis=1, keepdims=True)
        z = np.sum(depth[indices] * weights, axis=1)
        pixel = y[inside] * size + x[inside]
        order = np.lexsort((z, pixel))
        ordered_pixel = pixel[order]
        nearest = order[np.r_[ordered_pixel[1:] != ordered_pixel[:-1], True]]
        nearest = nearest[z[nearest] > depth_map[pixel[nearest]]]
        depth_map[pixel[nearest]] = z[nearest]
        if positions is not None:
            positions[pixel[nearest]] = np.einsum('ij,ijk->ik', weights[nearest], vertices[indices[nearest]])

    return depth_map.reshape(size, size), None if positions is None else positions.reshape(size, size, 3)


def reproject_photo(positions, target_mask, camera, source_depth, source_image, source_mask):
    """Pull source colors only where both masks and the source z-buffer agree."""
    valid_target = target_mask & np.isfinite(positions[:, :, 0])
    points = positions[valid_target]
    warped = np.full((*target_mask.shape, 3), 216, np.uint8)
    shared = np.zeros(target_mask.shape, bool)
    denominator = int(target_mask.sum())
    if not len(points):
        return warped, shared, denominator
    col, row = camera_project(points, camera)
    height, width = source_mask.shape
    in_frame = (col >= 1) & (row >= 1) & (col < width - 2) & (row < height - 2)
    col = np.clip(col, 0, width - 1)
    row = np.clip(row, 0, height - 1)
    size = source_depth.shape[0]
    x = np.clip(np.rint((col + 0.5) * size / width - 0.5).astype(int), 0, size - 1)
    y = np.clip(np.rint((row + 0.5) * size / height - 0.5).astype(int), 0, size - 1)
    _, _, direction = camera_axes(camera['phi'], camera['th'])
    z = points @ direction
    source_visible = np.abs(source_depth[y, x] - z) <= OVERLAY_DEPTH_TOLERANCE
    visible = in_frame & source_visible & (source_mask[np.rint(row).astype(int), np.rint(col).astype(int)] > 0)
    shared[valid_target] = visible
    if visible.any():
        # Thumbnail maps stay within OpenCV's remap size limits.
        map_x = np.zeros(target_mask.shape, np.float32)
        map_y = np.zeros_like(map_x)
        map_x[shared], map_y[shared] = col[visible], row[visible]
        warped[shared] = cv2.remap(source_image, map_x, map_y, cv2.INTER_LINEAR)[shared]
    return warped, shared, denominator


def load_overlay_view(folder, work, name):
    image = cv2.imread(str(folder / f'{name}.jpg'))
    mask = cv2.imread(str(work / f'mask_{name}.png'), cv2.IMREAD_GRAYSCALE)
    if image is None or mask is None or image.shape[:2] != mask.shape or image.shape[0] != image.shape[1]:
        raise ValueError(f'{name} 缺少同尺寸的正方形照片與遮罩')
    return image, mask


def render_overlay_row(label, detail, ref, warped, shared, delta):
    overlay = cv2.cvtColor(cv2.cvtColor(ref, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
    overlay = cv2.addWeighted(overlay, 0.5, np.full_like(overlay, 238), 0.5, 0)
    overlay[shared] = cv2.addWeighted(ref, 0.5, warped, 0.5, 0)[shared]
    heat = np.full_like(ref, 216)
    heat[shared] = cv2.applyColorMap(np.clip(delta.astype(np.float32) * 4, 0, 255).astype(np.uint8),
                                    cv2.COLORMAP_TURBO)[shared]
    tiles = [cv2.resize(image, (OVERLAY_TILE_SIZE, OVERLAY_TILE_SIZE), interpolation=cv2.INTER_AREA)
             for image in (ref, warped, overlay, heat)]
    row = np.full((OVERLAY_TILE_SIZE + 64, OVERLAY_TILE_SIZE * 4, 3), 255, np.uint8)
    cv2.putText(row, label, (8, 18), cv2.FONT_HERSHEY_SIMPLEX, .48, (28, 36, 48), 1, cv2.LINE_AA)
    cv2.putText(row, detail, (8, 38), cv2.FONT_HERSHEY_SIMPLEX, .48, (28, 36, 48), 1, cv2.LINE_AA)
    for i, text in enumerate(('Reference', 'Warped view', '50/50 overlay', 'Luma difference')):
        cv2.putText(row, text, (i * OVERLAY_TILE_SIZE + 8, 59), cv2.FONT_HERSHEY_SIMPLEX, .49,
                    (28, 36, 48), 1, cv2.LINE_AA)
    row[64:] = np.hstack(tiles)
    return row


def overlay_geometry_fields(reference, source, kpis):
    fields = dict(oblique_eye_median_px='', oblique_nose_median_px='', oblique_mouth_median_px='',
                  alignment_status='NOT_APPLICABLE', bilateral_eye_span_error_percent='',
                  bilateral_eye_span_status='NOT_APPLICABLE')
    if reference != FRONT or source not in {name for _, name, _ in CHEEKS}:
        return fields

    measurements = kpis.get(source, {})
    for label, column in zip(('眼部', '鼻部', '嘴部'),
                             ('oblique_eye_median_px', 'oblique_nose_median_px', 'oblique_mouth_median_px')):
        if label in measurements:
            fields[column] = f'{measurements[label][0]:.1f}'
    levels = {level for _, level in measurements.values()}
    fields['alignment_status'] = (FAIL if FAIL in levels else
                                  'NOT_MEASURED' if len(measurements) < 3 else
                                  WARN if WARN in levels else PASS)
    eye_span = kpis.get('bilateral_eye_span')
    fields['bilateral_eye_span_status'] = 'NOT_MEASURED'
    if eye_span is not None:
        fields['bilateral_eye_span_error_percent'] = f'{eye_span[0]:+.1f}'
        fields['bilateral_eye_span_status'] = eye_span[1]
    return fields


def report_view_overlays(folder, work, output, overlay_kpis=None):
    """Write diagnostic sheets and CSV without changing the baking acceptance decision."""
    folder, work, output = Path(folder), Path(work), Path(output)
    cameras = json.loads((work / 'cams33.json').read_text(encoding='utf-8'))
    with np.load(work / 'uvmesh.npz') as mesh:
        vertices, faces = mesh['pos'], mesh['tri']
    output.mkdir(parents=True, exist_ok=True)
    targets = {}
    for name, cam in cameras.items():
        slot = photo_slot(name)
        if slot in (('main', 0), ('main', 180), ('head', 0), ('head', 180)):
            targets[slot] = name
    if not targets:
        raise ValueError('缺少正面或背面的參考相機')

    rows_by_target = {}
    render_targets = {}
    for (kind, angle), name in sorted(targets.items()):
        image, mask = load_overlay_view(folder, work, name)
        _, positions = rasterize_surface(vertices, faces, cameras[name], photo_size=image.shape[0], with_points=True)
        render_targets[name] = (kind, angle, positions,
                                cv2.resize(image, (OVERLAY_SIZE, OVERLAY_SIZE), interpolation=cv2.INTER_AREA),
                                cv2.resize(mask, (OVERLAY_SIZE, OVERLAY_SIZE), interpolation=cv2.INTER_NEAREST) > 0)
        rows_by_target[name] = []

    fieldnames = ('reference', 'source', 'shared_pixels', 'coverage_percent', 'luma_median', 'luma_p90', 'status',
                  'coverage_status', 'luma_within_20_percent', 'luma_status',
                  *overlay_geometry_fields('', '', {}).keys())
    with (output / 'view_overlap.csv').open('w', encoding='utf-8', newline='') as log:
        writer = csv.DictWriter(log, fieldnames=fieldnames)
        writer.writeheader()
        for name, cam in sorted(cameras.items()):
            try:
                image, mask = load_overlay_view(folder, work, name)
            except ValueError as error:
                print(f'[WARN] 回投疊圖：{error}')
                continue
            source_depth, _ = rasterize_surface(vertices, faces, cam, photo_size=image.shape[0])
            for target, (kind, angle, positions, ref, target_mask) in render_targets.items():
                if name == target or (kind == 'head') != (cam['kind'] == 'head'):
                    continue
                warped, shared, denominator = reproject_photo(positions, target_mask, cam, source_depth, image, mask)
                count = int(shared.sum())
                coverage = count / max(1, denominator)
                delta = cv2.absdiff(cv2.cvtColor(ref, cv2.COLOR_BGR2GRAY),
                                    cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY))
                enough = coverage >= OVERLAY_MIN_COVERAGE
                median, p90, within = None, None, None
                if enough:
                    difference = delta[shared]
                    median = float(np.median(difference))
                    p90 = float(np.percentile(difference, 90))
                    within = 100 * float(np.mean(difference <= OVERLAY_LUMA_TOLERANCE))
                coverage_status = 'SUFFICIENT' if enough else 'LOW_COVERAGE'
                luma_status = ('NOT_MEASURED' if p90 is None else
                               'REVIEW' if p90 > OVERLAY_LUMA_TOLERANCE else 'WITHIN_LUMA_LIMIT')
                status = luma_status if enough else coverage_status
                geometry = overlay_geometry_fields(target, name, overlay_kpis or {})
                summary = f'P90 {p90:.1f}/255' if p90 is not None else 'P90 unavailable'
                label = f'{name} to {target}  |  overlap {coverage:.1%}  |  {summary}  |  {status}'
                detail = (f'Luma within {OVERLAY_LUMA_TOLERANCE}/255: {within:.1f}%'
                          if within is not None else 'Luma agreement: insufficient overlap')
                if geometry['alignment_status'] != 'NOT_APPLICABLE':
                    mouth = geometry['oblique_mouth_median_px'] or 'N/A'
                    detail += f'  |  Mouth (oblique) {mouth} px  |  Alignment {geometry["alignment_status"]}'
                    eye_span = geometry['bilateral_eye_span_error_percent']
                    if eye_span:
                        detail += f'  |  Eye span (both sides) {eye_span}%'
                rows_by_target[target].append(render_overlay_row(label, detail, ref, warped, shared, delta))
                writer.writerow(dict(reference=target, source=name, shared_pixels=count,
                                     coverage_percent=f'{100 * coverage:.2f}', coverage_status=coverage_status,
                                     luma_median='' if median is None else f'{median:.1f}',
                                     luma_p90='' if p90 is None else f'{p90:.1f}', status=status,
                                     luma_within_20_percent='' if within is None else f'{within:.2f}',
                                     luma_status=luma_status, **geometry))

    count = 0
    for target, rows in rows_by_target.items():
        if rows:
            kind, angle = render_targets[target][:2]
            path = output / f'{kind}_{"front" if angle == 0 else "back"}.png'
            if not cv2.imwrite(str(path), np.vstack(rows)):
                raise OSError(f'無法寫入 {path}')
            count += len(rows)
    print(f'[INFO] 正背面回投疊圖：{count} 組比對，輸出 {output}（灰底表示未共同可見）')


RING_ANGLES = tuple(range(0, 360, 45))
FRAME_PIXELS = 2048
PHOTO_SUFFIXES = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.tif', '.tiff', '.heic', '.heif', '.avif'}


def photo_slot(stem):
    if stem == 'top' or stem.startswith('top_'):
        return 'top', 0
    match = re.match(r'(el30|head|low20)_(\d{3})deg(?:$|[_\-.])', stem)
    if match:
        return match[1], int(match[2])
    match = re.match(r'\d{2}_(\d{3})deg(?:$|[_\-.])', stem)
    if match:
        return 'main', int(match[1])
    return None


def is_canonical_stem(stem, category, angle):
    if category == 'top':
        return stem == 'top'
    if category == 'main':
        front_prefix = stem.startswith('01_')
        return front_prefix == (angle == 0) and bool(re.fullmatch(r'\d{2}_\d{3}deg(?:_.+)?', stem))
    return stem == f'{category}_{angle:03d}deg'


def load_photos(folder, out):
    """Validate the names and bytes that the reconstruction stage will consume."""
    views = {}
    extra = {'top': {}, 'el30': {}, 'head': {}, 'low20': {}}
    out = Path(out).resolve()
    own_outputs = {out, *(out.with_stem(out.stem + suffix).with_suffix('.png')
                          for suffix in ('_top_check', '_silhouette_check', '_head_review'))}
    slots, pixels = {}, {}
    try:
        paths = sorted(Path(folder).iterdir())
    except OSError as error:
        report(FAIL, '照片資料夾', str(error))
        return views, extra
    for path in paths:
        if not path.is_file() or path.suffix.lower() not in PHOTO_SUFFIXES or path.resolve() in own_outputs:
            continue
        slot = photo_slot(path.stem.lower())
        if slot is None and path.suffix.lower() != '.jpg':
            continue   # Other preview formats are not read by the reconstruction.
        if slot is None:
            report(FAIL, path.name, '檔名不符合重建規格')
            continue

        category, angle = slot
        previous = slots.setdefault(slot, path.name)
        if previous != path.name:
            report(FAIL, path.name, f'與 {previous} 使用同一個 {category} {angle:03d}° 位置')
        if (angle not in RING_ANGLES or not is_canonical_stem(path.stem, category, angle)
                or path.suffix != '.jpg'):
            report(FAIL, path.name, '需要規格檔名及小寫 .jpg 副檔名')
            continue

        try:
            data = path.read_bytes()
        except OSError as error:
            report(FAIL, path.name, f'讀不到照片（{error}）')
            continue
        if not data.startswith(b'\xff\xd8\xff'):
            report(FAIL, path.name, '檔案內容須為 JPEG')
            continue
        image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            report(FAIL, path.name, 'JPEG 無法解碼')
            continue
        height, width = image.shape[:2]
        if (height, width) != (FRAME_PIXELS, FRAME_PIXELS):
            report(FAIL, path.name, f'實際尺寸 {width} × {height}，重建需要 {FRAME_PIXELS} × {FRAME_PIXELS}')
            continue

        digest = hashlib.sha256(image).digest()
        original = pixels.setdefault(digest, (slot, path.name))
        if original[0] != slot:
            report(FAIL, path.name, f'與 {original[1]} 的像素完全相同，須提供不同視角')
        ring = views if category == 'main' else extra[category]
        ring.setdefault(angle, dict(name=path.name, im=image))
    return views, extra


def review_head_photos(head_views, out):
    if len(head_views) > 1:
        previews = {a: (cv2.resize(v['im'], (128, 128), interpolation=cv2.INTER_AREA).astype(np.float32),
                        cv2.resize(v['m'].astype(np.uint8), (128, 128), interpolation=cv2.INTER_NEAREST) > 0)
                    for a, v in head_views.items()}
        for (a, (image, mask)), (b, (other, other_mask)) in combinations(previews.items(), 2):
            region = mask | other_mask
            if region.any() and np.abs(image[region] - other[region]).mean() < 3.0:
                report(WARN, '頭部疑似重複',
                       f'{head_views[a]["name"]} 與 {head_views[b]["name"]} 影像很接近，請複核拍攝角度')

    tiles = []
    for angle in (315, 0, 45):
        if angle not in head_views:
            continue
        view = head_views[angle]
        mask = view['m']
        top, bottom, _, _ = bbox(mask)
        last = top + round(0.72 * (bottom - top))
        head_bottom = top + round(0.58 * (bottom - top))
        cols = np.flatnonzero(mask[top:head_bottom + 1].any(axis=0))
        padding = max(8, round(0.04 * (bottom - top)))
        image = view['im'][max(0, top - padding):last + 1,
                           max(0, cols[0] - padding):cols[-1] + 1 + padding]
        height, width = image.shape[:2]
        scale = min(360 / width, 430 / height)
        crop = cv2.resize(image, (max(1, round(width * scale)), max(1, round(height * scale))),
                          interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR)
        tile = np.full((480, 380, 3), 255, np.uint8)
        left = (tile.shape[1] - crop.shape[1]) // 2
        tile[42:42 + crop.shape[0], left:left + crop.shape[1]] = crop
        cv2.putText(tile, view['name'], (12, 27), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (30, 30, 30), 1, cv2.LINE_AA)
        tiles.append(tile)
    if tiles:
        path = str(Path(out).with_suffix(''))
        path += '_head_review.png'
        if cv2.imwrite(path, np.hstack(tiles)):
            print(f'  頭部局部對照圖（複核左右臉頰、鼻翼和嘴角）: {path}')
        else:
            report(WARN, '頭部局部對照圖', f'無法寫入 {path}')


def photo_cheek_percentiles(view, horizontal_position):
    """Estimate cheek brightness in a silhouette-relative crop, without registration."""
    small = cv2.resize(view['im'], (512, 512), interpolation=cv2.INTER_AREA)
    mask = cv2.resize(view['m'].astype(np.uint8), (512, 512), interpolation=cv2.INTER_NEAREST) > 0
    top, bottom, _, _ = bbox(mask)
    height = bottom - top
    luma = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    samples = []
    # At these heights the centre patch in an oblique view is the visible cheek.
    for row in range(int(top + 0.42 * height), int(top + 0.54 * height)):
        columns = np.flatnonzero(mask[row])
        if columns.size < 16:
            continue
        first, last = columns[0], columns[-1]
        left = round(first + (last - first) * (horizontal_position - 0.06))
        right = round(first + (last - first) * (horizontal_position + 0.06))
        samples.extend(luma[row, left:right + 1][mask[row, left:right + 1]])
    if len(samples) < MIN_SAMPLES:
        return None
    return np.percentile(samples, (20, 50, 80))


def check_photo_cheek_brightness(head_views):
    if 0 not in head_views:
        report(WARN, '臉頰亮度粗篩', '缺少可取樣的正面照片')
        return
    for angle, cheek, front_position, side_position in (
            (45, '左臉頰', 0.73, 0.48), (315, '右臉頰', 0.27, 0.52)):
        label = f'{cheek} 0° / {angle}° 亮度粗篩'
        if angle not in head_views:
            report(WARN, label, '缺少可取樣的斜面照片')
            continue
        front = photo_cheek_percentiles(head_views[0], front_position)
        side = photo_cheek_percentiles(head_views[angle], side_position)
        if front is None or side is None:
            report(WARN, label, '臉頰取樣不足，請人工複核')
            continue
        difference = float(np.max(np.abs(front - side)))
        status = PASS if difference <= PHOTO_CHEEK_MAX_DIFF else WARN
        guidance = '，請比對頭部對照圖及光線' if status == WARN else ''
        report(status, label, f'亮度分位差最大 {difference:.1f} / 255'
                              f'（目標 ≤ {PHOTO_CHEEK_MAX_DIFF:g}）{guidance}')


def finish(out=None, camera_verified=True):
    failures = sum(r[0] == FAIL for r in results)
    warnings = sum(r[0] == WARN for r in results)
    passes = sum(r[0] == PASS for r in results)
    print(f'\n照片初篩總結: {failures} 個 FAIL, {warnings} 個 WARN, {passes} 個 PASS' +
          (f'   報告圖: {out}' if out else ''))
    if failures:
        print('有 FAIL：請先修正列出的問題再重建。')
    elif warnings:
        print('照片初篩有 WARN：請複核，烘焙前仍需檢查投影。')
    else:
        print('照片初篩通過：可以開始重建，烘焙前仍需檢查投影。')
    if not failures and not camera_verified:
        print('臉部一致性未通過完整驗證，相機使用較寬的搜尋範圍。')
    sys.exit(1 if failures else 0 if camera_verified else 3)


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description=f'check_turnaround {__version__}')
    ap.add_argument('--version', action='version', version=f'check_turnaround {__version__}')
    ap.add_argument('folder')
    ap.add_argument('--pose', choices=['tpose', 'apose'], default='tpose')
    ap.add_argument('--out', default='turnaround_report.png')
    ap.add_argument('--min-height', type=int, default=2000)
    ap.add_argument('--mode', choices=['ai', 'photo'], default='ai',
                    help='ai（預設）：AI 生成的圖可以重來，用嚴格門檻；photo：真實拍攝，門檻較寬')
    ap.add_argument('--head-overlap-work', metavar='WORK_DIR',
                    help='用重建中間檔檢查頭部重疊區亮度及五官對位')
    ap.add_argument('--view-overlay-dir', metavar='DIR', help='輸出各角度回投到正面/背面的疊圖與 CSV')
    ap.add_argument('--camera-check', action='store_true',
                    help='供相機校準使用：若無 FAIL 但第 11 項未全數通過，回傳 3')
    args = ap.parse_args()
    if args.view_overlay_dir and not args.head_overlap_work:
        ap.error('--view-overlay-dir 需要 --head-overlap-work')
    MODE['ai'] = args.mode == 'ai'
    print(f'check_turnaround 版本 {__version__}（模式 {args.mode}：' + ('AI 生成圖，嚴格門檻' if MODE['ai'] else '真實照片，較寬門檻') + '）')
    if args.head_overlap_work:
        overlay_kpis = {} if args.view_overlay_dir else None
        status = report_head_overlap(args.folder, args.head_overlap_work, overlay_kpis)
        if args.view_overlay_dir:
            try:
                report_view_overlays(args.folder, args.head_overlap_work, args.view_overlay_dir, overlay_kpis)
            except (OSError, KeyError, ValueError) as error:
                print(f'[WARN] 正背面回投疊圖：{error}')
        sys.exit(status)

    views, extra = load_photos(args.folder, args.out)
    print(f'主環找到 {len(views)} 張: ' + ', '.join(f'{a}°' for a in sorted(views)))
    for k, lab_ in (('top', '俯視'), ('el30', '俯角環'), ('head', '頭部特寫'), ('low20', '仰角')):
        if extra[k]:
            print(f'{lab_} {len(extra[k])} 張: ' + ', '.join(v['name'] for _, v in sorted(extra[k].items())))

    # ---- 0. completeness
    print('\n0. 完整性（還缺哪些圖）')
    ring = RING_ANGLES
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

    if any(item[0] == FAIL for item in results):
        finish()

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
        report(PASS if H >= args.min_height else strict(WARN), tag,
               f'解析度 {W}x{H}，人物高 {fig_h}px' + ('' if H >= args.min_height else f'（建議圖高 ≥ {args.min_height}）'))
        if t < 0.02 * H or b > 0.98 * H or l < 2 or r > W - 3:
            report(FAIL, tag, '人物碰到畫面邊緣，需完整入鏡並留白')
        bgL = float(np.median(bg[..., 0]))
        if bgL < 215:
            report(strict(WARN), tag, f'背景偏暗（L={bgL:.0f}），要純白背景')
        # floor shadow: dark pixels outside the figure in the bottom band
        band = slice(int(b - 0.06 * fig_h), min(H, int(b + 0.04 * fig_h)))
        Lb = lab[band, :, 0]; mb = m[band]
        dark = (Lb < np.median(bg[band, :, 0]) - 12) & ~cv2.dilate(mb.astype(np.uint8), np.ones((9, 9), np.uint8)).astype(bool)
        frac = dark.sum() / max(1, dark.size)
        if frac > 0.01:
            report(strict(WARN), tag, f'腳邊有地面陰影（{100 * frac:.1f}% 的底部區域），去背會受影響')

    good = {a: v for a, v in views.items() if v.get('m') is not None}
    if 0 not in good:
        sys.exit('正面圖去背失敗，無法繼續')

    # ---- 2. framing consistency
    print('\n2. 構圖一致性（每張人物高度、頭頂與腳底位置）')
    hs = np.array([v['fig_h'] for v in good.values()])
    spread = (hs.max() - hs.min()) / hs.mean()
    report(PASS if spread < T(0.01, 0.02) else WARN if spread < T(0.02, 0.04) else FAIL, '人物高度',
           f'差異 {100 * spread:.1f}%（應 < 2%：相機距離與焦距需相同）')
    tops = np.array([v['top'] / v['im'].shape[0] for v in good.values()])
    bots = np.array([v['bot'] / v['im'].shape[0] for v in good.values()])
    d = max(np.ptp(tops), np.ptp(bots))
    report(PASS if d < T(0.01, 0.02) else strict(WARN) if d >= T(0.02, 0.0) else WARN, '頭頂 / 腳底位置',
           f'差異 {100 * d:.1f}% 圖高（應 < {100 * T(0.01, 0.02):.0f}%：相機高度需固定）')

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
    report(PASS if sym < T(0.015, 0.03) else WARN if sym < 0.03 else strict(WARN), '左右手對稱',
           f'兩手高度差 {100 * sym:.1f}% 身高（應 < {100 * T(0.015, 0.03):.1f}%）')

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
            report(PASS if err <= T(5, 10) else WARN if err <= T(8, 10) else FAIL, f'{a:3d}°',
                   f'推算約 {est:.0f}°（應為 {expect}°，誤差 {err:.0f}°，應 ≤ {T(5, 10)}°）')

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
    pairs = [(0, 180, '0° vs 180°（正 / 背）', T(0.95, 0.90)), (90, 270, '90° vs 270°（左 / 右側）', T(0.95, 0.90)),
             (45, 225, '45° vs 225°', T(0.95, 0.90)), (135, 315, '135° vs 315°', T(0.95, 0.90)),
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
                report(strict(WARN), f'{a}° vs {b_}°',
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
            report(strict(WARN), f'{a}° 光線',
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
            report(PASS if dev < T(0.03, 0.08) else WARN if dev < T(0.05, 0.08) else FAIL, label,
                   f'胸/腰/臀/大腿/小腿最大差異 {100 * dev:.0f}%，在「{lv}」（應 < {100 * T(0.03, 0.08):.0f}%，'
                   f'≥ {100 * T(0.05, 0.08):.0f}% FAIL；腳踝見 7c）')

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
                report(PASS if dg < 0.015 else strict(WARN), f'腳間距 {a}° vs {(180 + a) % 360}°',
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
    TH = T(0.05, 0.08)
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
                    lvl = PASS if cov >= T(0.99, 0.97) else WARN if cov >= T(0.98, 0.93) else FAIL
                    why = '' if lvl == PASS else (
                        '；超出的部分主要在頭部（%d%%）→ 俯視相機太近、透視太強（頭被拍得太大），請用長焦距 / 正交投影、相機拉遠重新生成' % (100 * hshare)
                        if hshare > 0.5 else
                        '；超出的部分在：' + '、'.join(f'{k}（{100 * v:.0f}%）' for k, v in where_.items()) +
                        ' → 這些部位在俯視圖和主環裡的位置 / 大小不一致（或相機不在正上方），請重新生成 top.jpg，'
                        '讓髮髻、腳的位置和主環相同（對照圖紅色 = 只有俯視圖有，綠色 = 只有主環有，手臂的綠色正常）')
                    report(lvl, tag + ' 與主環一致性',
                           f'俯視圖身體中段有 {100 * cov:.1f}% 落在主環重建形狀之內（應 ≥ {100 * T(0.99, 0.97):.0f}%）；'
                           f'重合度 {cs:.2f}（含手臂 {fs:.2f}，主環看不到手臂上下厚度，只供參考）；對照圖 {ovp}' + why)
            if cat == 'head':
                hfrac = (b - t) / H_
                report(PASS if hfrac >= 0.6 else WARN, tag, f'頭到肩高度佔畫面 {100 * hfrac:.0f}%（應 ≥ 60%）')
            hs_.append(b - t); v['h'] = b - t
        if len(hs_) >= 2 and cat in ('el30', 'head', 'low20'):
            if cat == 'head':
                sp = (max(hs_) - min(hs_)) / np.mean(hs_); what = '各張頭部高度差'
            else:
                # tilted cameras: the figure height depends on the azimuth (arms tilt in the image), but views 180°
                # apart are mirror images of each other and must have the same height
                prs = [(items[a]['h'], items[a + 180]['h']) for a in (0, 45, 90, 135)
                       if a in items and a + 180 in items and 'h' in items[a] and 'h' in items[a + 180]]
                sp = max((abs(x - y) / ((x + y) / 2) for x, y in prs), default=0.0); what = '相差 180° 的兩張人物高度差'
            # perfect photos: head 0 %, el30 / low20 pairs up to 2.3 % (front and back are not exact mirrors from above)
            sp_pass = T(0.015, 0.03) if cat == 'head' else T(0.03, 0.03)
            sp_fail = T(0.03, 0.03) if cat == 'head' else T(0.05, 0.03)
            report(PASS if sp < sp_pass else WARN if sp < sp_fail else strict(WARN), f'{cat} 大小一致',
                   f'{what} {100 * sp:.1f}%（應 < {100 * sp_pass:.1f}%）')
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
                    report(PASS if abs(est_ - exp_) <= T(6, 12) else WARN if abs(est_ - exp_) <= T(9, 12) else FAIL, f'{cat} {a}° 角度',
                           f'推算約 {est_:.0f}°（應為 {exp_}°，±{T(6, 12)}° 內；俯 / 仰角會讓推算略有偏差）')
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
        report(strict(WARN) if flips else PASS, f'{cat} 翻轉複製', '；'.join(flips) if flips else '沒有發現左右翻轉複製的圖')
        # (c) lighting direction consistent within the ring
        # head close-ups: use only neck / shoulders (face vs hair colour would fake a lighting direction)
        ldr = {a: (light_dir(v['im'], v['m'], 0.75, 0.98) if cat == 'head' else light_dir(v['im'], v['m']))
               for a, v in okv.items()}
        strong_ = {a: d for a, d in ldr.items() if abs(d[0]) > 0.06 and (d[1] > 0.65 or d[1] < 0.35)}
        if len(strong_) >= max(3, 0.6 * len(okv)):
            maj = np.sign(sum(np.sign(d[0]) for d in strong_.values())) or 1.0
            odd_ = sorted(a for a, d in strong_.items() if np.sign(d[0]) != maj)
            report(strict(WARN) if odd_ else PASS, f'{cat} 光線方向',
                   f'{", ".join(f"{a}°" for a in odd_)} 的亮側和其他張相反，可能是左右翻轉做出來的' if odd_
                   else f'每張都是{"畫面左側" if maj > 0 else "畫面右側"}較亮，一致')
        else:
            report(PASS, f'{cat} 光線方向', '光線沒有明顯方向性，此項不判斷')

    review_head_photos({a: v for a, v in extra['head'].items() if v.get('m') is not None}, args.out)

    # ---- 9. exposure: skin lightness of every image vs. the main ring (big differences show as seams)
    print('\n9. 曝光一致性（每張圖的膚色亮度和主環比較）')
    allimgs = [(f'{a}°', v) for a, v in sorted(good.items())] + \
              [(f'{c} {a}', v) for c, items in extra.items() for a, v in sorted(items.items()) if v.get('m') is not None]
    lv = {k: skin_lightness(v['im'], v['m']) for k, v in allimgs}
    ref_ = [lv[f'{a}°'] for a in good if lv.get(f'{a}°')]
    if ref_:
        med = float(np.median(ref_))
        EXP = T(EXPOSURE_MAX_DIFF, 0.12)
        odd = [(k, x / med - 1) for k, x in lv.items() if x and abs(x / med - 1) > EXP]
        for k, d_ in odd:
            report(strict(WARN) if abs(d_) > T(0.10, 1.0) else WARN, f'{k} 曝光',
                   f'膚色亮度比主環{"亮" if d_ > 0 else "暗"} {100 * abs(d_):.0f}%（應在 ±{100 * EXP:g}% 內）；'
                                       f'光線 / 曝光要和主環相同，否則重建後會看到色差接縫')
        if not odd:
            report(PASS, '曝光一致', f'{len(lv)} 張的膚色亮度都在主環的 ±{100 * EXP:.0f}% 內')

    check_photo_cheek_brightness({a: v for a, v in extra['head'].items() if v.get('m') is not None})

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
            if not MODE['ai']:
                bp, bw = 0.04, 0.07
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
            lvl = PASS if p_ < T(PERSP_PASS, 0.03) else WARN if p_ < T(PERSP_WARN, 0.06) else FAIL
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

    # ---- 11. face consistency of the head close-ups
    face_results = []
    if extra.get('head'):
        print('\n11. 臉部一致性（頭部特寫 0° / 45° / 315°：找得到臉、五官比例、頭髮高度和臉的比例要一致）')
        face_results = face_check(extra)
        for lvl, lab, msg in face_results:
            report(lvl, lab, msg)

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

    camera_verified = bool(face_results) and all(lvl == PASS for lvl, _, _ in face_results)
    finish(args.out, camera_verified=not args.camera_check or camera_verified)


if __name__ == '__main__':
    main()
