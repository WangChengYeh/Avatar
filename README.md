# body3d 2.1.0 — 33 張 T-pose 照片 → 附骨架 GLB（全部 Python）

## 安裝
- Python 3.10–3.12：`pip install -r requirements.txt`
- Blender 4.2 以上（UV、匯出、骨架三步用 `blender -b --python` 執行 Python 腳本）。
  自動尋找 PATH / Homebrew / /Applications，或 `--blender 路徑`、環境變數 `BLENDER`。
- 選用：Node.js + `npm install gltf-validator`，verify_glb.py 會一併跑 Khronos 驗證器
  （放在本資料夾，或設定 `GLTF_VALIDATOR_DIR=.../node_modules`）。

## 一支指令跑完整流程
    python body3d/run_all.py 照片資料夾 輸出資料夾 [--force] [--name body]

16 步：照片檢查 → 相機 → 外殼 → 手臂 → 圓滑 → 腿部嚴格雕刻 → 網格 → 頭部對位 → 臉部特徵點 → UV → 貼圖烘焙
→ 匯出 → 關節 → 骨架 → 無光照材質 → GLB 驗證。約 3 分鐘。
- 照片檢查有 FAIL 會停下，`--force` 強制繼續。
- `--from 步驟` 從某步重跑、`--only 步驟` 只跑一步（中間檔在 輸出資料夾/work）。
- 輸出：`body_rigged.glb`（無光照，建議）、`body_rigged_lit.glb`、`v2_*.png` 預覽、`turnaround_report.png`、`run_all.log`。

## 個別工具
    python body3d/check_turnaround.py 照片資料夾        # 照片規範檢查（規範全文在檔頭註解）
    python body3d/verify_glb.py model.glb --expect-unlit  # GLB 驗證（取代 three.js 檢查頁）
    python body3d/fit_report.py 輸出資料夾/work            # 模型投影回每張照片比對剪影（分辨照片問題 / 腳本問題）

verify_glb.py 檢查：GLB 格式、22 根骨頭名稱與父子階層、Hips 為根、蒙皮網格為根節點、
綁定矩陣、骨骼索引、權重加總 = 1、最多 4 根骨頭、高度 / 地面 / 朝向 / T-pose、貼圖可解碼、
無光照材質，並用 numpy 線性蒙皮實際擺姿勢（左上臂往下 70°，指尖要往下、腳不能動）。
有 FAIL 時結束碼 1。

## 測試
    pytest -q                                   # 約 3 分鐘（需要 Blender 渲染合成照片）
    pytest -q --photos=照片資料夾                # 另外跑完整端到端（要用 = 連接）

- test_checker.py：合成的 33 張照片要通過；缺俯視圖、缺環上一張、角度對調、翻轉複製、灰白雜點、曝光不足都要被抓出來
- test_verify_glb.py：好模型通過；骨頭改名、父子錯、權重不歸一、缺貼圖、該無光照卻沒有、非 GLB 都要 FAIL；四元數數學
- test_run_all.py：照片 FAIL 時流程會停；合成照片跑前半段得到 1.65 m、手臂完整、封閉的網格；腿部不能超出照片剪影（fit_report）；端到端兩個 GLB 都通過驗證、腿部剪影吻合
- tests/data/body_rigged.glb 是測試用模型（v9）；可用環境變數 BODY3D_GLB 換成別的

## 2.1.0：小腿內側凸塊（腳本問題，不是照片問題）
外殼投票「容許 3 張不同意」，但兩腿之間的縫只有 45° / 225° 附近幾張看得到，票數不夠就留下一條殘留。
照片裡的縫是乾淨的（fit_report：修正前主環腿部平均超出照片 5991 px，修正後 57 px）。
legs33.py 在腳踝到胯下上方 12 cm 改用主環 8 張嚴格雕刻：任何一張清楚看到是空的就削掉。

## 已知問題
- 腿以外（手臂、軀幹）仍用寬鬆投票，整體剪影比照片略大
- 右肩頂偏灰（照片本身的陰影）；45° 視角臉頰有淡接縫
- 腳踝附近在個別視角會被多削 1–2 px（嚴格雕刻的代價；從 12 cm 起雕會讓腳踝外殼殘留回來，整體較差）
