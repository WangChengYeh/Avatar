# Avatar · body3d

用 33 張環繞照片重建人物，輸出帶 22 根骨骼及 4K 貼圖的 GLB。預設輸出無光照與 PBR 兩個版本。

## 快速開始

需要 Python 3.10–3.12 和 Blender 4.2 以上。在 repo 根目錄執行：

```sh
python -m pip install -r requirements.txt
python body3d/run_all.py ./photos ./output --name body
```

`./photos` 放入 33 張 2048 × 2048 的 JPEG，使用小寫 `.jpg`。完整角度與檔名見[流程與驗收](docs/Workflow-and-Validation.md#輸入照片)，生圖時的相機距離、構圖與提示詞見[生圖規格](docs/Workflow-and-Validation.md#生圖規格)。

Blender 可從 PATH、Homebrew 或系統應用程式目錄尋找。也可用 `--blender /path/to/blender` 或 `BLENDER` 指定。要額外執行 Khronos glTF Validator，可在 repo 根目錄執行 `npm install gltf-validator`，或以 `GLTF_VALIDATOR_DIR` 指向已安裝該套件的 `node_modules`。

## 主要輸出

| 路徑 | 用途 |
| --- | --- |
| `output/body_rigged.glb` | 無光照版本，適合保留照片原有光影 |
| `output/body_rigged_lit.glb` | PBR 版本，會受場景光源影響 |
| `output/turnaround_report*.png` | 照片初篩與輪廓、頭部複核圖 |
| `output/view_overlays/` | 正背面回投疊圖與 KPI CSV |
| `output/v2_*.png` | Blender 預覽圖 |
| `output/fit_report.json` | 最終驗收：成品投影回 24 張全身原圖的剪影不一致（平均 > 10% 判 FAIL） |
| `output/run_all.log` | 18 步流程日誌，含檢查結果與可用的峰值記憶體紀錄 |
| `output/client/index.html` | 給客戶看的中文頁面：製作進度（每一步更新）、各階段圖（照片總覽、頭部對照、模型預覽、原圖對模型）、驗收總表與未通過／需複核清單（[SOP](docs/SOP.md#每個階段給客戶看什麼)） |
| `output/progress.json` | 18 個步驟的狀態與時間 |
| `output/deliver/body_stage{1..4}_*.zip` | 每個階段的成果：照片、重建、模型、成品驗收。關卡都通過是好的成果；有 FAIL 時檔名加 `_FAIL`，不能交付。每個 zip 有 SHA-256 manifest 與未通過清單（[SOP](docs/SOP.md#每個階段的成果)） |
| `output/work/` | 重跑單一步驟或進階檢查用的中間檔 |

每次都會把 4 個階段做完，每個階段在 `output/deliver/` 都有成果 zip：四道關卡（照片檢查、烘焙前檢查、GLB 驗證、成品與原圖比對 `fit`）通過是好的成果，有 `FAIL` 時繼續做完、成果檔名標 `_FAIL`，流程以結束碼 1 結束（程式出錯為 2）。只有全部 0 FAIL 才能交付，見 [SOP](docs/SOP.md)。`--stop-on-fail` 讓關卡一有 FAIL 就停。`--from STEP` 和 `--only STEP` 會使用既有的 `output/work/`。

## 常用指令

```sh
# 檢查照片（照片須先經 AI 修正；只有一套門檻）
python body3d/check_turnaround.py ./photos --out turnaround_report.png

# 驗證無光照 GLB，另存頭部渲染供複核
python body3d/verify_glb.py ./output/body_rigged.glb --expect-unlit --renders ./head-renders

# 將重建網格投影回輸入視角，檢查身體剪影
python body3d/fit_report.py ./output/work --region body

# MakeHuman 模板：乾淨拓樸、含手指的 Mixamo 骨架（需在 Blender 安裝 MPFB 擴充）
python body3d/run_all.py ./photos ./output --name body --template makehuman

# 跑測試；提供 33 張照片可加跑端到端
python -m pytest -q
python -m pytest -q --photos=./photos
```

可單獨分享 `check_turnaround.py`。照片初篩基本功能需要 `numpy` 和 `opencv-python`，第 11 / 11b 項的臉部檢查必須安裝 MediaPipe（`mediapipe==0.10.14`），沒裝時判 FAIL。

## Loop engineering

**一輪對應一個 GitHub Issue。** 開工時建立 Issue，寫下觀察到的差異、輸入與 GLB 版本、重現步驟及驗收條件。這一輪的分析、試修和回驗都記在同一個 Issue 或其留言。

- **問題分析與證據**：在 Issue 內嵌原圖、Three.js 渲染、對照圖或回投疊圖，標明角度和版本。記錄差異最早在哪一步出現，以及支撐判斷的量測和門檻。
- **重要中間結果與修改**：保留 checker 重現的結果、會影響判斷的試修與取捨，以及實際修改的照片、checker 或 3D 步驟。將相關 commit、PR 和檢查報告連回該 Issue。
- **驗收與下一輪**：在 Issue 內嵌同條件下的修正前後圖，記錄 KPI、PASS／FAIL 與 GLB 版本。GLB 只需記錄版本和驗收結果。驗收後關閉 Issue。下一輪開一個新 Issue，連回上一輪並說明延續的問題或新目標。

範例見 [耳部重影的分析、試修與驗收 #17](https://github.com/WangChengYeh/Avatar/issues/17)。下列步驟背後的理由見 [Loop engineering 的理論基礎](docs/Loop-Engineering-Theory.md)：人物是不動的虛擬人物，任何兩張圖對不上，不是 AI 畫錯就是程式估錯。

1. **比對 Three.js 與原圖。** 在 Three.js 載入目前的 GLB，輸出正面 0°、左側面 90°、背面 180°，有疑點時加上 45°／315° 或局部特寫。把模型擺到與原圖相同的姿勢（例如 T-pose），配對角度、相機投影和尺度，再對照同角度的全身照及頭部特寫。用疊圖和局部放大標出問題位置，記錄角度、部位、量測值及門檻。可依問題量測五官距離、輪廓偏移、亮度差 P90 或肩臂變形。另以 Yoga2 實際站姿和動作確認使用時的外觀。
2. **找出差異最早出現在哪一步。** 先比對原圖之間的同角度全身照與頭部特寫，再看不同角度回投到同一視角後的結果。若原圖已有五官比例、輪廓、色澤或亮度差異，走第 3 步。若原圖一致，以同一組照片逐步核對相機對齊、網格、UV 與貼圖烘焙、骨架權重、GLB 匯出與 Three.js 載入後的結果；修正最早出現差異的步驟，並加入能重現問題的檢查。若兩邊都有問題，分別修正及驗證。
3. **原圖有問題時，先改 checker，再修圖。** 把規則加到可單獨使用的 [`check_turnaround.py`](body3d/check_turnaround.py)，並先用未修正的照片重跑。如果原圖原本 PASS，先確認新版 checker 能在正確角度和部位報出目標問題。再修照片，用相同指令、門檻和比對條件重跑，確認該項由 FAIL 轉為 PASS，再確認其他角度及既有規則沒有新增 FAIL。保留修圖前後的數值、疊圖與檢查報告。
4. **重新生成 GLB 並回到 Three.js 驗收。** 用修正後的 33 張照片和最新版腳本，從頭在新的輸出目錄重建（完美合成照片四個階段的成果都是好的，#28）。確認 GLB 驗證通過，再用第 1 步的相同設定輸出三視圖，重測原本失敗的部位和 KPI。涉及肩臂時，另測站姿與抬手，確認貼圖和網格在動作中也符合預期。本輪試修時若仍超出門檻，在同一個 Issue 回到第 2 步繼續排查。

修圖從水平主環開始，先驗證 T-pose、人物比例、相機構圖，以及全身和同角度頭部特寫。等核心穩定後再修 30° 俯角、−20° 仰角與俯視。每次仍跑完整 33 張並記錄外圍差異。亮度驗收比較回投後共同可見的同一表面，畫面左右亮差和全圖膚色只供複核。

```sh
python body3d/check_turnaround.py ./photos-before --out report-before.png
python body3d/check_turnaround.py ./photos-fixed --out report-after.png
python body3d/run_all.py ./photos-fixed ./output-next --name body
python body3d/verify_glb.py ./output-next/body_rigged.glb --expect-unlit
```

### 跑 33 張原圖的同姿勢對照

在 repo 根目錄使用 Node.js 20 以上執行 [`scripts/compare_turnaround.mjs`](scripts/compare_turnaround.mjs)。腳本以 Three.js 載入無光照 GLB，使用 `cams33.json` 裡每張原圖的正交或透視相機投影。主環、俯角、仰角與頂視保留 T-pose，頭部特寫只將手臂放下，保持頭部、軀幹及世界座標固定。圖像以軟體光柵化輸出。 有原始拍攝或生成的可重現相機設定時，優先將視角、投影、焦距或正交尺度及構圖寫入相機表。若手上只有影像，在 Issue 標明使用的是估計校準參數。

```sh
npm install --no-save --package-lock=false three@0.180.0 sharp
node scripts/compare_turnaround.mjs --photos ./photos \
  --cameras ./output/work/cams33.json --model ./output/body_rigged.glb \
  --all-views --out ./comparison
```

重建時，俯角環固定 +30°，仰角環固定 −20°。重新驗收舊版時，先從相機校準階段重建，再把新 GLB 與同一次重建的 `cams33.json` 一起用於比對。

`--all-views` 輸出五組總覽圖，以及 `pairs/` 內 33 張逐角度 PNG。移除該旗標可快速輸出全身與耳部對照。提供 `--before ./previous/body_rigged.glb` 可加入修正前模型。全量比對的範例見 [Issue #19](https://github.com/WangChengYeh/Avatar/issues/19)。

例如 v1220 左側面曾看到肩膀接上臂處偏灰綠。先查看同角度原圖是否已有這塊色差；如果原圖正常，就沿著 UV／烘焙貼圖、靜止 GLB 到 Three.js 站姿逐步比較，找出色差第一次出現的位置，再決定要修哪一步。

## 文件

- [標準作業流程（SOP）](docs/SOP.md) · 每個階段的成果（好／_FAIL）、四道關卡、PASS／WARN／FAIL 怎麼處理、交付條件
- [流程與驗收](docs/Workflow-and-Validation.md) · 輸入規格、重跑步驟、照片與 GLB 檢查、回投 KPI
- [Loop engineering 的理論基礎](docs/Loop-Engineering-Theory.md) · 為什麼要先改 checker、以原圖為錨、找最早出現差異的步驟
- [版本與量測紀錄](CHANGELOG.md) · 重要修正、實測範圍和歷史限制
- [Avatar 正確性審查](docs/Avatar-Correctness-Review.md) · body3d 2.3.0 的原始報告及重現方式
