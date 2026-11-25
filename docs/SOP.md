# 標準作業流程（SOP）

[返回 README](../README.md) · [流程與驗收](Workflow-and-Validation.md) · [Loop engineering 的理論基礎](Loop-Engineering-Theory.md)

一句話：**照片要先經 AI 修正才能進來；任何一道關卡有 FAIL 就不能交付。** `--force` 只用來診斷，不產生可交付的 GLB。

## 流程總覽

```
AI 生圖 / 修圖（33 張）
   │
   ▼
關卡 1 照片檢查 ──FAIL──► 回 AI 重畫該張（看報告的「→」建議）
   │ PASS / WARN
   ▼
重建（第 2–11 步：相機、外殼、網格、頭部對位、臉部特徵點、UV）
   │
   ▼
關卡 2 烘焙前檢查 ──FAIL──► 先查照片（多半是特寫角度 / 五官位置），再查重建步驟
   │
   ▼
烘焙、匯出、骨架（第 12–16 步）
   │
   ▼
關卡 3 GLB 驗證 ──FAIL──► 修程式（GLB 結構、骨架、材質、貼圖條紋）
   │
   ▼
關卡 4 最終驗收 ──FAIL──► 成品投影回原圖對不上：看單張 WARN 的照片第 10 / 10d / 10e 項
   │
   ▼
驗收總表全部 0 FAIL、未用 --force → 可交付 → Yoga2 匯入檢查
```

## 四道關卡

| 關卡 | 指令（`run_all.py` 自動執行） | 檢查什麼 | FAIL 時 |
| --- | --- | --- | --- |
| 1 照片檢查 | `check_turnaround.py PHOTOS` | 33 張照片本身：檔名、解析度、構圖、角度、相機距離、對準點、透視、光線、耳朵、臉部比例、頭部朝向 | 流程停止。重畫照片 |
| 2 烘焙前檢查 | `check_turnaround.py PHOTOS --head-overlap-work WORK` | 重建後的相機與網格：頭部特寫相機角度、全身與特寫的五官位置、頭部重疊區亮度 | 流程停止 |
| 3 GLB 驗證 | `verify_glb.py OUT/*.glb` | GLB 結構、骨架與蒙皮、身高、無光照材質、頭部貼圖條紋（unlit / lit 兩個檔各驗一次） | 流程停止 |
| 4 最終驗收 | `fit_report.py WORK --accept` | 成品網格投影回 24 張全身原圖的剪影不一致：平均 ≤ 8% PASS、> 10% FAIL；單張 > 12% WARN | 流程停止 |

每道關卡最後都印同一格式：

```
總結: N 個 FAIL, N 個 WARN, N 個 PASS，共 N 項
```

`run_all.py` 結束時（包括中途停止）印**驗收總表**，並寫入 `OUT/gates.json`。實例（polished 照片、MakeHuman 模板、`--force` 從第 12 步跑起，所以沒有關卡 1，也不能交付）：

```
驗收總表               FAIL  WARN  PASS  共計
  2 烘焙前檢查            8     7    22    37  ← FAIL
  3 GLB 驗證（unlit）     0     0    21    21
  3 GLB 驗證（lit）       0     0    20    20
  4 最終驗收              1    20     4    25  ← FAIL
  可交付: 否（用了 --force，只供診斷）
```

`gates.json` 另記 `force`（這次有沒有加 `--force`）和 `deliverable`（四道關卡都有結果、全部 0 FAIL、沒有 `--force`）。

## 每個階段給客戶看什麼

客戶是內部客戶：每個階段都給圖，FAIL 和 WARN 照實列出，不隱藏。`run_all.py` 結束時（包括中途停止）自動產生 `OUT/client/index.html`，也可以單獨執行 `python body3d/client_report.py PHOTOS OUT`。

| 階段 | 圖 | 客戶看什麼 |
| --- | --- | --- |
| 1 照片 | `01_photos.jpg`：33 張總覽（主環、+30°、−20°、頭部特寫、俯視） | 人、髮型、服裝、表情對不對；照片檢查的 FAIL / WARN 清單 |
| 2 烘焙前（頭部） | `02_head_review.png`、`02_head_overlap.png` | 全身照和頭部特寫的頭部是否一致；烘焙前檢查清單 |
| 3 模型 | `03_preview.jpg`：正面、3/4、側面、背面渲染 | 整體外觀、比例、貼圖；GLB 驗證清單 |
| 4 成品對照 | `04_body_compare.jpg`、`05_head_compare.jpg`：用輸入照片的規格相機拍模型，左原圖、右模型 | 兩邊應該一樣：臉的朝向、五官、輪廓、顏色；剪影吻合度（平均 ≥ 92% 通過） |

頁首另有驗收總表與「可交付／不可交付」。交付時把 `client/` 整個資料夾連同 GLB 一起給，Yoga2 的站姿、抬手截圖另外附上（目前要手動拍）。

## PASS / WARN / FAIL 怎麼處理

| 結果 | 意思 | 處理 |
| --- | --- | --- |
| PASS | 在完美照片 + 小餘裕的門檻內 | 不用處理 |
| WARN | 超出完美照片的範圍，但還不會直接造成模型或貼圖缺陷 | 可以繼續。交付前逐項看過，記在 Issue；同一項反覆出現或數量變多時，回頭修照片 |
| FAIL | 會直接造成重建缺陷（重影、接縫、錯位、變形），或規格錯誤 | 一定要清掉，不能交付。照片檢查的 FAIL 只能重畫照片，不改門檻遷就照片 |

門檻只有一套（1.38.0 起沒有 `--mode`），由完美合成照片（Luna `luna-v1.glb` 與舊測試模型，兩者都必須 0 FAIL / 0 WARN）加小餘裕校準。要改門檻，先證明完美照片仍是 0 FAIL / 0 WARN。

## `--force` 的規則

- 只用來**診斷**：照片有 FAIL 時，看問題會在後面哪一步、以什麼樣子出現。
- 加了 `--force` 的輸出**不能交付**，即使後面三道關卡都 PASS（`gates.json` 的 `deliverable` 一定是 `false`）。
- `--force` 時，照片檢查不鎖定相機角度，改用較寬的搜尋範圍（±10° / ±16°），結果本來就和正式流程不同。
- 不能用 `--force` 跳過缺少的依賴：沒裝 MediaPipe、找不到 Blender 一律先裝好。

## 交付條件（全部要符合）

1. 照片在新的資料夾，未經手動改名或覆蓋；用最新版 main 的腳本。
2. 從頭在**新的輸出目錄**重建，不加 `--force`，不用 `--from` / `--only` 接舊的中間檔。
3. `OUT/gates.json` 的 `deliverable` 為 `true`：四道關卡全部 0 FAIL。
4. 所有 WARN 已逐項看過並記在 Issue。
5. Three.js / Yoga2 匯入後，依 README 的 Loop engineering 第 1 步比對 0° / 90° / 180°（有疑點加 45° / 315° 與特寫），並測站姿與抬手。

## 一輪的步驟

1. 開 GitHub Issue，寫輸入照片版本、checker 版本、目標。
2. `python body3d/check_turnaround.py ./photos --out report.png` → 有 FAIL 就把報告「→」後面的建議交給 AI 重畫，重跑到 0 FAIL。
3. `python body3d/run_all.py ./photos ./output-新目錄 --name body`（不加 `--force`）。
4. 看驗收總表：
   - 任何 FAIL：依上面「FAIL 時」處理。原因在照片 → 回第 2 步；原因在程式 → 依 Loop engineering 第 2 步找最早出錯的步驟，先加能重現的檢查再修。
   - 0 FAIL：逐項看 WARN，記在 Issue。
5. Three.js / Yoga2 驗收（交付條件第 5 項）。
6. 在 Issue 貼上驗收總表、`gates.json`、前後對照圖，關閉 Issue。

## 已知限制

- MakeHuman 模板（`--template makehuman`）仍在試驗：側面輪廓是模板的通用臉，全身剪影吻合度比外殼流程差。預設的外殼流程才是交付路線。
- 檢查還沒涵蓋網格自我穿插；Yoga2 看到斑點或摺痕時，先用 Blender 實際渲染確認（`verify_glb --renders` 的頭部圖用點去畫，會冒出假的小點）。
