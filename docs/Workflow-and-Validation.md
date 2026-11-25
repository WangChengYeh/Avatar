# 流程與驗收

[返回 README](../README.md) · [版本與量測紀錄](../CHANGELOG.md)

## 輸入照片

每張須可解碼為 2048 × 2048 JPEG。四個環各 8 張，加一張俯視圖，共 33 張。每個環使用 `000`、`045`、`090`、`135`、`180`、`225`、`270`、`315` 八個角度。主環可加描述後綴，`01_` 保留給 0°。

| 組別 | 張數 | 檔名範例 |
| --- | ---: | --- |
| 水平全身 | 8 | `01_000deg_front.jpg`、`02_045deg.jpg` |
| 俯角 30° 全身 | 8 | `el30_000deg.jpg` |
| 水平頭部特寫 | 8 | `head_000deg.jpg` |
| 仰角 20° 全身 | 8 | `low20_000deg.jpg` |
| 正上方 | 1 | `top.jpg` |

檔名、JPEG 內容、尺寸、重複角度和相同像素會在輪廓檢查前驗證。頭部近似複製可用 `*_head_review.png` 複核。生圖時固定相機高度、曝光、白平衡與柔光設定，斜角視圖維持正交投影與相同人物比例。相機與人物中心的距離固定：全身圖（水平、俯角、仰角、俯視）同一構圖，畫面寬 1.95 m；頭部特寫同一構圖，放大為全身圖的 4 倍（畫面寬約 0.49 m）。具體構圖與提示詞見下節「生圖規格」。理由見 [Loop engineering 的理論基礎](Loop-Engineering-Theory.md)。

## 生圖規格

相機繞著人物轉，只改角度，距離與對準點不變（理由見 [Loop engineering 的理論基礎](Loop-Engineering-Theory.md)）。生成後用 `check_turnaround.py` 檢查：第 10d 項量距離，第 10e 項量對準點與俯仰角，第 6c 項粗篩光線，第 10f 項驗收共同表面亮度。成品是無光照 GLB，明暗應由 3D 軟體的燈光產生，不要畫進照片；光源跟著相機轉時，同一塊皮膚在不同角度亮度不同，烘焙後會有色差接縫。

| 組別 | 相機 | 構圖（2048 × 2048） |
| --- | --- | --- |
| 水平、俯角 30°、仰角 20°、俯視 | 全身圖共用同一個 3D 身體中心，距離全部相同 | 畫面寬 1.95 m。水平環人物高約佔 85%，頭頂和腳底各留約 8%，左右置中。同角度的三個環人物左右寬度相同，俯視圖與正面同寬 |
| 光線（全部 33 張） | 光線固定在人身上，不跟著相機轉 | 全方位均勻柔光，沒有方向性明暗、硬陰影與高光，盡量接近皮膚／衣服本身的顏色；曝光與白平衡固定。同一塊皮膚從任何角度看一樣亮 |
| 頭部特寫 | 對準點可自選（建議頭部中心），8 張相同；距離全部相同 | 全身圖的 4 倍放大，畫面寬約 0.49 m，頭寬約佔三分之一。頭頂在每張的同一高度（對準頭部中心時離上緣約 24%） |

每張都加上光線提示詞：

```text
even all-round soft light fixed to the subject, no directional shading, flat albedo-like colours,
fixed exposure and white balance across all views, the same skin and clothing brightness from every angle,
no hard shadows or highlights
```

全身圖每張再加上：

```text
same camera distance and framing in every full-body view, only the camera angle changes,
aim at the same 3D body centre, halfway up the figure on the vertical rotation axis,
place that point at the image centre; for the level ring the figure fills about 85 % of the image height,
orthographic projection, 200mm telephoto lens, camera very far away, no perspective distortion
```

頭部特寫每張加上：

```text
head close-up at 4x the full-body zoom, same camera distance in every close-up,
camera aimed at the centre of the head, head width about one third of the image width,
head top at the same height in every close-up, orthographic projection, no perspective distortion
```

其他要求（同一角色、固定種子、相機角度寫法、光線提示詞）見 `python body3d/check_turnaround.py --help` 列出的第九節。

## 18 步重建

| 階段 | `--from`／`--only` 可用的步驟 |
| --- | --- |
| 輸入與相機 | `check` → `cams` → `refine` |
| 幾何 | `arms` → `round` → `legs` → `mesh` |
| 頭部 | `headreg` → `face` → `face3d` |
| 貼圖與匯出 | `uv` → `bake` → `export` |
| 骨架與驗證 | `joints` → `rig` → `unlit` → `verify` → `fit` |

例：已有完整中間檔，修改骨架匯出後可從 `rig` 重新輸出並驗證。調查 UV 問題可單獨重跑 `uv`。

```sh
python body3d/run_all.py ./photos ./output --from rig --name body
python body3d/run_all.py ./photos ./output --only uv
```

預設貼圖解析度為 4096 × 4096，可用 `BODY3D_TEX=2048` 跑 2K 診斷。重跑時確認 `work/` 來自同一組照片與相容的上游步驟。

## 照片初篩

`check_turnaround.py` 預設使用 `--mode ai`。`--mode photo` 提供部分較寬的真實照片門檻。兩種模式都使用上述 33 張照片格式。

| 檢查 | 判讀 |
| --- | --- |
| 剪影一致性，第 10 項 | 藍色代表照片有、重建形狀未覆蓋的像素。AI 模式一般視角 ≤ 1% 通過。俯角／仰角 > 2.5% 失敗，其餘水平視角 > 2% 失敗。水平 90°／270° 採 ≤ 3% 通過、> 4% 失敗。Photo 模式使用 ≤ 4% 和 > 7%。紅色顯示形狀超出照片的區域。 |
| 透視，第 10b 項 | 依對角視角的兩手指尖中點偏移來估距離。在 AI 模式下，跨視角平均偏移 < 2% 半臂展通過、≥ 4% 失敗。 |
| 輪廓比例，第 10c 項 | 比對俯角／仰角環與同角度主環的手寬／臀寬、頭寬／臀寬。差異 ≥ 3% 警告；AI 模式 ≥ 5% 失敗，photo 模式 ≥ 5% 標示優先複核。完美照片 0–2%。 |
| 相機距離，第 10d 項 | 正交投影下傾角不改變畫面左右座標，同角度的俯角、仰角與水平全身圖人物寬度應相同，俯視圖與 0° 同寬。AI 模式差異 ≤ 1% 通過。俯角／仰角 > 2.5% 失敗，正上方 > 2% 失敗。頭部特寫的頭寬應為同角度全身圖的 4 倍，差異 ≤ 2% 通過、> 4% 失敗（側面 90°／270° 不比）。下半身寬度另行比對，用來分辨構圖比例與臂展偏差。 |
| 對準點與俯仰角，第 10e 項 | 由相差 180° 的正交剪影求出旋轉軸。AI 模式置中差 ≤ 5 mm 通過，俯角／仰角差 > 12 mm 失敗，其餘 > 10 mm 失敗。俯角／仰角環的目標仍為 +30°／−20°，角度差 ≤ 2° 通過、> 5° 失敗。側面與下半身尺度偏差超過 2% 的圖略過角度換算。同一環內的對準高度差 ≤ 10 mm 通過、> 25 mm 失敗。絕對對準另逐張量 3D 身體中心距畫面中央的水平與垂直偏差，兩軸均 ≤ 10 mm 通過，任一軸 > 25 mm 失敗。 |
| 光線方向，第 6c 項 | AI 模式下，畫面左右亮差 > 6% 提醒複核。不同角度露出的膚色、衣服、褲子和頭髮面積不同，這項量測可能反映材質差。是否有共同表面亮度差由第 10f 項驗收。 |
| 同一表面亮度，第 10f 項 | 把相鄰角度（水平 a／a+45°、俯角與仰角對同角度水平）投影到主環重建形狀的同一批表面點比亮度。AI 模式下，中位數差的絕對值 > 3 或 P90 > 18／255 判 WARN。共同取樣少於 200 點時標記未量測。超標的配對另列避開高反差邊界的結果，供複核回投對位。 |
| 曝光與臉頰亮度 | AI 模式下，膚色平均亮度與主環的差異 > 7% 提醒複核。0° 對 45°／315° 的臉頰粗篩比較取樣區的亮度分位數，最大差 ≤ 12/255。完美照片為 6% 與 11/255（每個角度看到的皮膚不同），同一表面的亮度由第 10f 項直接比較。 |
| 分區亮度，第 9b 項 | OpenCV 依去背輪廓、位置與 Lab 色度估計腳、上衣、褲子、頭髮和裸露皮膚。各區取 Lab L 中位數，和至少三張其他適用水平照片的同區中位數比較，差的絕對值 > 18/255 報 WARN。遮擋、裁切或取樣不足會標為未量測。 |

以 `--region-luma-dir <資料夾>` 輸出每張照片的分區疊圖及 `region_brightness.csv`。疊圖標色依序為腳部米黃、上衣粉紅、褲子藍色、頭髮橙色、皮膚綠色。分區規則適用這組白底、玫瑰色上衣、深色褲子、赤腳的照片。換裝、髮色或背景改變時，先用疊圖複核分區。
| 臉部一致性，第 11 項 | MediaPipe 在三張頭部特寫檢測五官，並比較眼到嘴／臉高、髮高／臉高。AI 模式校正後偏差絕對值 ≤ 2% 通過、> 4% 失敗。 |

流程以 `work/check_status.json` 記錄照片是否符合較窄相機搜尋的條件。符合時，相機角度只能偏離檔名 ±3°，而且相機距離固定：全身圖都用主環由身高算出的縮放，頭部特寫用其 4 倍，全身圖共用旋轉軸上離地半個身高的點（1.65 m 時為 82.5 cm），投影固定於畫面正中央（`BODY3D_RING_LOCK=1／0` 可強制開關）。Three.js 對照預設套用同一個全身對準點，查看原擬合相機時可加 `--fitted-cameras`。各張自由擬合與固定值的差距記在 `work/ring_consistency.json`。未安裝 MediaPipe 或第 11 項未全部通過時，會採用較寬的搜尋範圍。

## 烘焙前驗收與疊圖 KPI

完整流程在烘焙之前用已校準的相機和網格比對 0°、45°、315° 的臉部特寫。可單獨重跑並輸出疊圖：

```sh
python body3d/check_turnaround.py ./photos \
  --head-overlap-work ./output/work \
  --view-overlay-dir ./output/view_overlays
```

| 驗收 | 通過與失敗條件 |
| --- | --- |
| 同一皮膚位置的臉頰亮度差 | 取共同可見點的亮度絕對差 P90。> 12/255 判 WARN。 |
| 全身照與同角度頭部特寫 | 共同可見區的亮度差 P90 > 12/255 判 WARN。共同覆蓋 < 60% 判 FAIL，低於 80% 提醒複核。 |
| 眼、鼻、嘴投影偏移 | 用可見眼鼻點試算整體縮放與平移，再以嘴部驗證。以圖高 1% 為複核目標。有至少 3 個可見點的部位，校正後中位偏移 > 圖高 1.5% 時失敗。 |
| 五官尺寸與回投眼距 | 校正後差異同時 > 4% 和 2 px 時警告。關鍵尺寸同時 > 8% 和 5 px 時失敗。左右斜面各取一側可見端點，也可回投到正面估計雙眼中心距。 |

資料不足時，日誌會提示缺少特徵點或有效取樣。`view_overlays/` 把身體與頭部照片各自回投到正面及背面，每列包含參考、回投、50/50 疊圖與亮度差圖。灰底或淡化區域沒有共同可見的取樣。

`view_overlap.csv` 列出覆蓋率、亮度差中位數／P90、亮度差 ≤ 20/255 的比例。覆蓋率 < 5% 時，亮度欄留空。適用的斜面列另有眼、鼻、嘴校正後的中位偏移，以及兩張斜面合計的回投眼距。覆蓋率、亮度和對位各有狀態，疊圖 KPI 供複核，烘焙的退出碼由專用驗收檢查決定。

## 成品與原圖的最終驗收

第 18 步 `fit` 把成品網格用最終相機投影回 24 張全身原圖（`fit_report.py --accept`），量每張的剪影不一致比例，結果存在 `output/fit_report.json`。平均 ≤ 8% 通過、> 10% 失敗（流程結束碼 1，`--force` 只提示），單張 > 12% 另列 WARN。門檻依相機已知的完美合成照片校準：平均 5.6–6.6%，單張最高 9.3%。單張偏高時，先看那張照片在第 10、10d、10e 項的結果。

```sh
python body3d/fit_report.py ./output/work --accept
```

## GLB 與動作驗證

`verify_glb.py` 檢查 GLB 格式、骨架階層、綁定矩陣、權重、尺寸、貼圖與材質。蒙皮測試會將左上臂往下轉 70°，量測指尖與腳底，並檢查三角形邊是否異常拉長。頭部預覽從正面、左右 45° 與兩側檢查貼圖暗條紋。任何 `FAIL` 回傳結束碼 1。

```sh
python -m pytest -q tests/test_verify_glb.py tests/test_head_overlap.py tests/test_view_overlays.py
python -m pytest -q -m slow --photos=./photos
```

合成照片與驗證測試預設使用 `tests/data/body_rigged.glb`，可用 `BODY3D_GLB` 指定替代模型。若成品會進入 Yoga2 等動畫流程，可用該應用的實際姿勢測試肩部、手臂與腋下，並在目標裝置複核畫面。
