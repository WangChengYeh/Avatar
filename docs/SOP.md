# 標準作業流程（SOP）

[返回 README](../README.md) · [流程與驗收](Workflow-and-Validation.md) · [Loop engineering 的理論基礎](Loop-Engineering-Theory.md)

一句話：**關卡有 FAIL 就停，但停下前做出來的東西一定交出來：通過是好的成果，未通過是不好的成果（`_FAIL`）；只有四道關卡全部通過才能交付。** 照片要先經 AI 修正才能進來；未通過的項目一定要清掉（回去修照片或修程式），不能用手動修正遮掉。

## 四個階段的規則

| 階段 | 關卡 | 結果包 |
| --- | --- | --- |
| 1 照片 | 照片檢查 | `stage1_photos` |
| 2 重建 | 烘焙前檢查 | `stage2_reconstruction` |
| 3 模型 | GLB 驗證 | `stage3_models` |
| 4 成品驗收 | 最終驗收 | `stage4_acceptance` |

1. **這個階段沒有 FAIL，才到下一個階段。** 關卡有 FAIL 就停在這個階段，回去修（照片 → 階段 1；程式 → 該步驟），修好再從頭跑。
2. **FAIL 的當下也會有一包結果。** 停下時，這個階段做出來的東西打包成 `_FAIL.zip`（有多少給多少，`manifest.json` 寫明停在哪、哪幾項未通過）；之前通過的階段各有一包好的結果。
3. **例外：要跑完拿 GLB 時加 `--force`。** 有 FAIL 也繼續做完四個階段，拿到 GLB 和每個階段的結果包，但從第一個 FAIL 起全部是 `_FAIL`，只供診斷，不能交付。
4. **四個階段都沒有 FAIL，四包都是好的，才能交付。**

## 流程總覽

`run_all.py` 每個階段結束就打包成果。關卡有 FAIL 時流程停下，但停下的那個階段做出多少就打包多少（`_FAIL`），之前已完成的階段也都有成果。程式出錯停下時一樣。`--force` 讓流程有 FAIL 也繼續做完（只供診斷，之後的成果全部 `_FAIL`）。

```
AI 生圖 / 修圖（33 張）
   │
   ▼
階段 1 照片 ── 關卡 1 照片檢查 ──► 成果 stage1_photos(.zip | _FAIL.zip)
   │
   ▼
階段 2 重建（第 2–11 步：相機、外殼、網格、頭部對位、臉部特徵點、UV）
   │ ── 關卡 2 烘焙前檢查 ──► 成果 stage2_reconstruction(.zip | _FAIL.zip)
   ▼
階段 3 模型（第 12–17 步：烘焙、匯出、骨架、材質）
   │ ── 關卡 3 GLB 驗證 ──► 成果 stage3_models(.zip | _FAIL.zip)
   ▼
階段 4 成品驗收（第 18 步）
   │ ── 關卡 4 最終驗收 ──► 成果 stage4_acceptance(.zip | _FAIL.zip)
   ▼
四道關卡全部 0 FAIL → 可以交付 → Yoga2 匯入檢查
任何一關 FAIL → 停在那一關，做出來的東西打包成 _FAIL.zip 交出來 → 看哪一項 → 回去修（照片 → 階段 1；程式 → 該步驟）→ 從頭重跑
```

## 每個階段的成果

成果都在 `OUT/deliver/`。檔名表示好或不好：

- **好**：`{name}_stageN_xxx.zip`。這個階段和它之前的關卡全部 0 FAIL，是可交付的成果。
- **不好**：`{name}_stageN_xxx_FAIL.zip`。這個階段或之前的關卡有 FAIL，或流程停在這個階段。有多少給多少，供檢查、給客戶看、留存，但不能交付。

同一個階段同時只會有其中一個：每次打包都先刪掉舊的兩個。每個 zip 都有 `manifest.json`：

| 欄位 | 內容 |
| --- | --- |
| `deliverable` | 好（`true`）或不好（`false`） |
| `gates` | 這個階段和之前每道關卡的 FAIL / WARN / PASS |
| `failures` | 每一個未通過項目的原文 |
| `missing` | 缺少的檔（缺照片；流程停在這個階段時，還沒做出來的檔） |
| `stopped` | 流程停在這個階段時：停在哪一步、原因 |
| `sha256` | zip 裡每個檔的 SHA-256，用來確認拿到的是同一份 |

| 階段 | 成果 zip | 內容 | 好的條件 |
| --- | --- | --- | --- |
| 1 照片 | `{name}_stage1_photos` | 33 張照片原檔（2048 × 2048 JPEG，檔名照規格）＋照片檢查報告 | 關卡 1 0 FAIL，33 張齊全 |
| 2 重建 | `{name}_stage2_reconstruction` | 相機 `cams33.json`、人體網格（`body33s.ply`，MakeHuman 版 `body_mh.ply`）、頭部對照圖與回投疊圖 | 關卡 1–2 0 FAIL |
| 3 模型 | `{name}_stage3_models` | 兩個 GLB（`{name}_rigged.glb` 無光照、`{name}_rigged_lit.glb`）＋預覽圖 | 關卡 1–3 0 FAIL |
| 4 成品驗收 | `{name}_stage4_acceptance` | 原圖對模型對照圖（全身 8 角度、頭部特寫 8 角度）、`fit_report.json`、`gates.json` | 關卡 1–4 0 FAIL |
| 交付 | 四個好的 zip ＋ `client/` 整個資料夾 ＋ Yoga2 站姿／抬手截圖 | | 見「交付條件」 |

只打包照片、不重建時：`python body3d/deliver.py stage1 PHOTOS OUT`（結束碼：好 0、不好 1）。

**下一個階段從上一個階段好的成果開始。** 有 FAIL 時預設就停在那裡；用 `--force` 拿不好的成果繼續做，只是為了看清楚問題會在後面怎麼出現，那些成果也一律是 `_FAIL`。後面的關卡發現照片的問題（例如烘焙前檢查的臉部錯位），要回到階段 1 修照片，重新產生好的 `stage1_photos.zip`，再從頭跑；不能在後面用手動修正補照片的錯（例如手動平移某張特寫的相機），那樣的結果無法重現，也不能交付。

## 四道關卡

| 關卡 | 指令（`run_all.py` 自動執行） | 檢查什麼 | 有 FAIL 時 |
| --- | --- | --- | --- |
| 1 照片檢查 | `check_turnaround.py PHOTOS` | 33 張照片本身：檔名、解析度、構圖、角度、相機距離、對準點、透視、光線、耳朵、臉部比例、頭部朝向、特寫與全身的臉部位置 | 停下；照片照樣打包成 `stage1_photos_FAIL.zip`。要修：重畫照片 |
| 2 烘焙前檢查 | `check_turnaround.py PHOTOS --head-overlap-work WORK` | 重建後的相機與網格：頭部特寫相機角度、全身與特寫的五官位置、頭部重疊區亮度 | 停下；階段 2 成果打包成 `_FAIL`。要修：多半是照片（特寫角度、五官位置），再查重建步驟 |
| 3 GLB 驗證 | `verify_glb.py OUT/*.glb` | GLB 結構、骨架與蒙皮、身高、無光照材質、頭部貼圖條紋（unlit / lit 兩個檔各驗一次） | 停下；兩個 GLB 照樣打包成 `stage3_models_FAIL.zip`。要修：程式 |
| 4 最終驗收 | `fit_report.py WORK --accept` | 成品網格投影回 24 張全身原圖的剪影不一致：平均 ≤ 8% PASS、> 10% FAIL；單張 > 12% WARN | 停下；對照圖與數字打包成 `stage4_acceptance_FAIL.zip`。要修：先看單張 WARN 的照片第 10 / 10d / 10e 項 |

每道關卡最後都印同一格式：

```
總結: N 個 FAIL, N 個 WARN, N 個 PASS，共 N 項
```

`run_all.py` 結束時印**驗收總表**、寫入 `OUT/gates.json`（各關卡數字與 `deliverable`）。結束碼：四道關卡全部 0 FAIL 為 0，其餘為 1。實例（R14 aligned 照片加 `--force`：照片檢查有 2 項 FAIL，繼續做完供診斷，成果全部是 `_FAIL`；不加 `--force` 時停在照片檢查，只交出 `stage1_photos_FAIL.zip`。Luna 完美照片四道關卡 0 FAIL、四個成果都是好的、可交付）：

```
驗收總表               FAIL  WARN  PASS  共計
  1 照片檢查              2    88   218   308  ← FAIL
  2 烘焙前檢查            0     8    29    37
  3 GLB 驗證（unlit）     0     0    21    21
  3 GLB 驗證（lit）       0     0    20    20
  4 最終驗收              1    15     9    25  ← FAIL
  可交付: 否（有 FAIL）

deliver/body_stage1_photos_FAIL.zip
deliver/body_stage2_reconstruction_FAIL.zip   ← 關卡 2 本身 0 FAIL，但建在未通過的照片上，所以也是 _FAIL
deliver/body_stage3_models_FAIL.zip
deliver/body_stage4_acceptance_FAIL.zip
```

## `--force` 的規則

- 只用來**診斷**：關卡有 FAIL 時繼續做完，看問題會在後面哪一步、以什麼樣子出現。
- 之後的成果全部是 `_FAIL`，不能交付，即使後面的關卡都通過。
- 照片未通過時，重建用較寬的相機搜尋範圍（±10° / ±16°），結果本來就和照片修好後不同。
- 不能用 `--force` 跳過缺少的依賴：沒裝 MediaPipe、找不到 Blender 一律先裝好。

## 每個階段給客戶看什麼

客戶是內部客戶：每個階段都給圖和成果，未通過（FAIL）和需複核（WARN）照實列出，不隱藏。頁面全部用中文。

`OUT/client/index.html` 在 `run_all.py` **每一步開始與結束時更新**，流程進行中每 20 秒自動重新整理，客戶隨時打開都看得到進度：

- 4 個階段（照片、重建、模型、成品驗收）各自是 未開始／進行中／完成／停止；
- 18 個步驟的狀態與花費時間、已用時間；
- 每個階段的成果 zip：「成果（好，可交付）」或「成果（有未通過，不好，不能交付）」，都有下載連結。

全部結束時再完整產生一次，含 Blender 渲染的原圖對模型。也可以單獨執行 `python body3d/client_report.py PHOTOS OUT`。

| 階段 | 圖 | 客戶看什麼 |
| --- | --- | --- |
| 1 照片 | `01_photos.jpg`：33 張總覽（水平、俯角 30°、仰角 20°、頭部特寫、俯視） | 人、髮型、服裝、表情對不對；照片檢查的未通過／需複核清單 |
| 2 重建 | `02_head_review.png`、`02_head_overlap.png` | 全身照和頭部特寫的頭部是否一致；烘焙前檢查清單 |
| 3 模型 | `03_preview.jpg`：正面、3/4、側面、背面渲染 | 整體外觀、比例、貼圖；模型檔驗證清單 |
| 4 成品驗收 | `04_body_compare.jpg`、`05_head_compare.jpg`：用輸入照片的規格相機拍模型，左原圖、右模型 | 兩邊應該一樣：臉的朝向、五官、輪廓、顏色；剪影吻合度（平均 ≥ 92% 通過） |

頁首另有驗收總表（未通過／需複核／通過／共計）與「可以交付／不能交付」。

## PASS / WARN / FAIL 怎麼處理

| 結果 | 意思 | 處理 |
| --- | --- | --- |
| PASS | 在完美照片 + 小餘裕的門檻內 | 不用處理 |
| WARN | 超出完美照片的範圍，但還不會直接造成模型或貼圖缺陷 | 成果仍是好的。交付前逐項看過，記在 Issue；同一項反覆出現或數量變多時，回頭修照片 |
| FAIL | 會直接造成重建缺陷（重影、接縫、錯位、變形），或規格錯誤 | 成果是不好的（`_FAIL`），不能交付。一定要清掉：照片的 FAIL 只能重畫照片，不改門檻遷就照片 |

門檻只有一套（1.38.0 起沒有 `--mode`），由完美合成照片（Luna `luna-v1.glb` 與舊測試模型，兩者都必須 0 FAIL / 0 WARN）加小餘裕校準。要改門檻，先證明完美照片仍是 0 FAIL / 0 WARN。


## 交付條件（全部要符合）

1. 照片在新的資料夾，未經手動改名或覆蓋；用最新版 main 的腳本。
2. 從頭在**新的輸出目錄**重建，不加 `--force`，不用 `--from` / `--only` 接舊的中間檔。
3. `OUT/deliver/` 四個階段都是好的 zip（沒有 `_FAIL`），`OUT/gates.json` 的 `deliverable` 為 `true`。
4. 所有 WARN 已逐項看過並記在 Issue。
5. Three.js / Yoga2 匯入後，依 README 的 Loop engineering 第 1 步比對 0° / 90° / 180°（有疑點加 45° / 315° 與特寫），並測站姿與抬手。

## 一輪的步驟

1. 開 GitHub Issue，寫輸入照片版本、checker 版本、目標。
2. `python body3d/run_all.py ./photos ./output-新目錄 --name body`：看 `client/index.html`、驗收總表與 `deliver/` 的成果。
3. 停在某一關（成果是 `_FAIL`）：看是哪一項。
   - 照片的問題 → 把報告「→」後面的建議交給 AI 重畫，回第 2 步（新的輸出目錄）。
   - 程式的問題 → 依 Loop engineering 第 2 步找最早出錯的步驟，先加能重現的檢查再修，回第 2 步。
4. 四個階段都是好的：逐項看 WARN，記在 Issue；做 Three.js / Yoga2 驗收（交付條件第 5 項）。
5. 在 Issue 貼上驗收總表、`gates.json`、四個成果 zip 的位置與前後對照圖，關閉 Issue。

## 已知限制

- MakeHuman 模板（`--template makehuman`）仍在試驗：側面輪廓是模板的通用臉，全身剪影吻合度比外殼流程差。預設的外殼流程才是交付路線。
- 檢查還沒涵蓋網格自我穿插；Yoga2 看到斑點或摺痕時，先用 Blender 實際渲染確認（`verify_glb --renders` 的頭部圖用點去畫，會冒出假的小點）。
