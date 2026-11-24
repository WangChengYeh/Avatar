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

## 文件

- [流程與驗收](docs/Workflow-and-Validation.md) · 輸入規格、重跑步驟、照片與 GLB 檢查、回投 KPI
- [版本與量測紀錄](CHANGELOG.md) · 重要修正、實測範圍和歷史限制
- [Avatar 正確性審查](docs/Avatar-Correctness-Review.md) · body3d 2.3.0 的原始報告及重現方式
