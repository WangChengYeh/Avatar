# Avatar · body3d

用 33 張環繞照片重建人物，輸出帶 22 根骨骼及 4K 貼圖的 GLB。預設輸出無光照與 PBR 兩個版本。

## 快速開始

需要 Python 3.10–3.12 和 Blender 4.2 以上。在 repo 根目錄執行：

```sh
python -m pip install -r requirements.txt
python body3d/run_all.py ./photos ./output --name body
```

`./photos` 放入 33 張 2048 × 2048 的 JPEG，使用小寫 `.jpg`。完整角度與檔名見[流程與驗收](docs/Workflow-and-Validation.md#輸入照片)。

Blender 可從 PATH、Homebrew 或系統應用程式目錄尋找。也可用 `--blender /path/to/blender` 或 `BLENDER` 指定。要額外執行 Khronos glTF Validator，可在 repo 根目錄執行 `npm install gltf-validator`，或以 `GLTF_VALIDATOR_DIR` 指向已安裝該套件的 `node_modules`。

## 主要輸出

| 路徑 | 用途 |
| --- | --- |
| `output/body_rigged.glb` | 無光照版本，適合保留照片原有光影 |
| `output/body_rigged_lit.glb` | PBR 版本，會受場景光源影響 |
| `output/turnaround_report*.png` | 照片初篩與輪廓、頭部複核圖 |
| `output/view_overlays/` | 正背面回投疊圖與 KPI CSV |
| `output/v2_*.png` | Blender 預覽圖 |
| `output/run_all.log` | 17 步流程日誌，含檢查結果與可用的峰值記憶體紀錄 |
| `output/work/` | 重跑單一步驟或進階檢查用的中間檔 |

照片初篩或烘焙前檢查出現 `FAIL` 時，流程會停止。`--force` 可繼續輸出供診斷，最終 GLB 驗證仍會執行。`--from STEP` 和 `--only STEP` 會使用既有的 `output/work/`。

## 常用指令

```sh
# 檢查照片（預設為 AI 模式）
python body3d/check_turnaround.py ./photos --out turnaround_report.png

# 驗證無光照 GLB，另存頭部渲染供複核
python body3d/verify_glb.py ./output/body_rigged.glb --expect-unlit --renders ./head-renders

# 將重建網格投影回輸入視角，檢查身體剪影
python body3d/fit_report.py ./output/work --region body

# 跑測試；提供 33 張照片可加跑端到端
python -m pytest -q
python -m pytest -q --photos=./photos
```

可單獨分享 `check_turnaround.py`。照片初篩基本功能需要 `numpy` 和 `opencv-python`，第 11 項的臉部檢查另外使用 MediaPipe。

## Loop engineering

**一輪對應一個 GitHub Issue。** 開工時建立 Issue，寫下觀察到的差異、輸入與 GLB 版本、重現步驟及驗收條件。這一輪的分析、試修和回驗都記在同一個 Issue 或其留言。

- **問題分析與證據**：附原圖、Three.js 渲染、對照圖或回投疊圖，標明角度和版本。記錄差異最早在哪一步出現，以及支撐判斷的量測和門檻。
- **重要中間結果與修改**：保留 checker 重現的結果、會影響判斷的試修與取捨，以及實際修改的照片、checker 或 3D 步驟。相關 commit、PR、檢查報告及產出都連回該 Issue。
- **驗收與下一輪**：附同條件下的修正前後圖、KPI、PASS／FAIL 和新 GLB。驗收後關閉 Issue。下一輪開一個新 Issue，連回上一輪並說明延續的問題或新目標。

範例見 [耳部重影的分析、試修與驗收 #17](https://github.com/WangChengYeh/Avatar/issues/17)。

1. **比對 Three.js 與原圖。** 在 Three.js 載入目前的 GLB，輸出正面 0°、左側面 90°、背面 180°，有疑點時加上 45°／315° 或局部特寫。把模型擺到與原圖相同的姿勢（例如 T-pose），配對角度、相機投影和尺度，再對照同角度的全身照及頭部特寫。用疊圖和局部放大標出問題位置，記錄角度、部位、量測值及門檻。可依問題量測五官距離、輪廓偏移、亮度差 P90 或肩臂變形。另以 Yoga2 實際站姿和動作確認使用時的外觀。
2. **找出差異最早出現在哪一步。** 先比對原圖之間的同角度全身照與頭部特寫，再看不同角度回投到同一視角後的結果。若原圖已有五官比例、輪廓、色澤或亮度差異，走第 3 步。若原圖一致，以同一組照片逐步核對相機對齊、網格、UV 與貼圖烘焙、骨架權重、GLB 匯出與 Three.js 載入後的結果；修正最早出現差異的步驟，並加入能重現問題的檢查。若兩邊都有問題，分別修正及驗證。
3. **原圖有問題時，先改 checker，再修圖。** 把規則加到可單獨使用的 [`check_turnaround.py`](body3d/check_turnaround.py)，並先用未修正的照片重跑。如果原圖原本 PASS，先確認新版 checker 能在正確角度和部位報出目標問題。再修照片，用相同指令、門檻和比對條件重跑，確認該項由 FAIL 轉為 PASS，再確認其他角度及既有規則沒有新增 FAIL。保留修圖前後的數值、疊圖與檢查報告。
4. **重新生成 GLB 並回到 Three.js 驗收。** 用修正後的 33 張照片和最新版腳本，從頭在新的輸出目錄重建，省略 `--force`。確認 GLB 驗證通過，再用第 1 步的相同設定輸出三視圖，重測原本失敗的部位和 KPI。涉及肩臂時，另測站姿與抬手，確認貼圖和網格在動作中也符合預期。本輪試修時若仍超出門檻，在同一個 Issue 回到第 2 步繼續排查。

```sh
python body3d/check_turnaround.py ./photos-before --out report-before.png
python body3d/check_turnaround.py ./photos-fixed --out report-after.png
python body3d/run_all.py ./photos-fixed ./output-next --name body
python body3d/verify_glb.py ./output-next/body_rigged.glb --expect-unlit
```

例如 v1220 左側面曾看到肩膀接上臂處偏灰綠。先查看同角度原圖是否已有這塊色差；如果原圖正常，就沿著 UV／烘焙貼圖、靜止 GLB 到 Three.js 站姿逐步比較，找出色差第一次出現的位置，再決定要修哪一步。

## 文件

- [流程與驗收](docs/Workflow-and-Validation.md) · 輸入規格、重跑步驟、照片與 GLB 檢查、回投 KPI
- [版本與量測紀錄](CHANGELOG.md) · 重要修正、實測範圍和歷史限制
- [Avatar 正確性審查](docs/Avatar-Correctness-Review.md) · body3d 2.3.0 的原始報告及重現方式
