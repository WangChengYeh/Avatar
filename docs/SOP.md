# 標準作業流程（SOP）

[返回 README](../README.md) · [流程與驗收](Workflow-and-Validation.md) · [Loop engineering 的理論基礎](Loop-Engineering-Theory.md)

**一句話：四個階段，每個階段沒有 FAIL 才進下一個；FAIL 的當下也會交出一包結果；四包都是好的才能交付。**

## 名詞

| 名詞 | 意思 |
| --- | --- |
| 階段 | 照片 → 重建 → 模型 → 成品驗收，共 4 個 |
| 關卡 | 每個階段結尾的檢查，結果是 PASS／WARN／FAIL |
| 結果包 | 每個階段打包的 zip，在 `OUT/deliver/` |
| 好的結果包 | `{name}_stageN_xxx.zip`：這個階段和之前的關卡全部 0 FAIL |
| 不好的結果包 | `{name}_stageN_xxx_FAIL.zip`：有 FAIL、或流程停在這個階段。有多少給多少，可以看、可以留存，不能交付 |
| 交付 | 四包都是好的，加上客戶頁與 Yoga2 驗收 |

## 四個階段的規則

| 階段 | 做什麼 | 關卡 | 結果包 |
| --- | --- | --- | --- |
| 1 照片 | AI 生圖／修圖，33 張 | 照片檢查 | `stage1_photos` |
| 2 重建 | 第 2–11 步：相機、外殼、網格、頭部對位、臉部特徵點、UV | 烘焙前檢查 | `stage2_reconstruction` |
| 3 模型 | 第 12–17 步：烘焙貼圖、匯出、骨架、材質 | GLB 驗證 | `stage3_models` |
| 4 成品驗收 | 第 18 步：成品投影回原圖比對 | 最終驗收 | `stage4_acceptance` |

1. **這個階段沒有 FAIL，才進下一個階段。** 關卡有 FAIL 就停，回去修：照片的問題回階段 1，程式的問題回出錯的那一步。修好後從頭再跑。
2. **FAIL 的當下也會有一包結果。** 停下的那個階段做出多少就打包多少，成為 `_FAIL.zip`；之前通過的階段各有一包好的結果。程式出錯停下時也一樣。
3. **例外：要跑完拿 GLB，加 `--force`。** 有 FAIL 也做完四個階段，拿到 GLB 和每個階段的結果包；但從第一個 FAIL 起全部是 `_FAIL`，只用來看問題，不能交付。
4. **四包都是好的，才能交付。**
5. **照片的錯只在階段 1 修。** 後面的關卡發現照片的問題（例如烘焙前檢查的臉部錯位），回階段 1 重畫照片、從頭跑。不能在後面的步驟手動補（例如手動平移某張特寫的相機）：那樣的結果無法重現，也不能交付。

```
AI 生圖 / 修圖（33 張）
   │
階段 1 照片 ── 照片檢查 ──FAIL──► stage1_photos_FAIL.zip，停：重畫照片
   │ 通過 → stage1_photos.zip
階段 2 重建 ── 烘焙前檢查 ──FAIL──► stage2_reconstruction_FAIL.zip，停：多半是照片，回階段 1
   │ 通過 → stage2_reconstruction.zip
階段 3 模型 ── GLB 驗證 ──FAIL──► stage3_models_FAIL.zip，停：修程式
   │ 通過 → stage3_models.zip
階段 4 成品驗收 ── 最終驗收 ──FAIL──► stage4_acceptance_FAIL.zip，停：先看照片第 10 / 10d / 10e 項
   │ 通過 → stage4_acceptance.zip
四包都是好的 → 可以交付 → Yoga2 匯入檢查
```

## 怎麼跑

```sh
python body3d/run_all.py ./photos ./output-新目錄 --name body          # 正式：有 FAIL 就停
python body3d/run_all.py ./photos ./output-新目錄 --name body --force  # 要跑完拿 GLB：只供診斷
python body3d/deliver.py stage1 ./photos ./output-新目錄                # 只做階段 1：檢查並打包照片
```

- 結果包在 `OUT/deliver/`，客戶頁在 `OUT/client/index.html`，各關卡數字在 `OUT/gates.json`。
- 結束碼：跑到最後、跑過的關卡全部 0 FAIL 為 0；停下或有 FAIL 為 1。`deliver.py stage1`：好 0、不好 1。
- 結束時（包括中途停下）印**驗收總表**：

```
驗收總表               FAIL  WARN  PASS  共計
  1 照片檢查              2    88   218   308  ← FAIL
  2 烘焙前檢查            0     8    29    37
  3 GLB 驗證（unlit）     0     0    21    21
  3 GLB 驗證（lit）       0     0    20    20
  4 最終驗收              1    15     9    25  ← FAIL
  可交付: 否（有 FAIL）
```

這是 R14 aligned 照片加 `--force` 的實例：照片檢查 2 項 FAIL，四個階段仍做完，四包都是 `_FAIL`（階段 2 的關卡本身 0 FAIL，但建在未通過的照片上，所以也是 `_FAIL`）。不加 `--force` 時停在照片檢查，只交出 `stage1_photos_FAIL.zip`。Luna 完美照片四道關卡 0 FAIL、四包都是好的、可交付。

### `--force` 的規則

- 只用來**診斷**：看問題會在後面哪一步、以什麼樣子出現。
- 從第一個 FAIL 起的結果包全部 `_FAIL`，即使後面的關卡都通過也不能交付。
- 照片未通過時，重建改用較寬的相機搜尋範圍（±10° / ±16°；照片通過時鎖定為檔名角度），所以結果本來就和照片修好後不同。
- 不能用 `--force` 跳過缺少的依賴：沒裝 MediaPipe、找不到 Blender，一律先裝好。

## 每個階段的成果

| 結果包 | 內容 | 好的條件 |
| --- | --- | --- |
| `{name}_stage1_photos` | 33 張照片原檔（2048 × 2048 JPEG，檔名照規格）＋照片檢查報告 | 關卡 1 0 FAIL，33 張齊全 |
| `{name}_stage2_reconstruction` | 相機 `cams33.json`、人體網格（`body33s.ply`，MakeHuman 版 `body_mh.ply`）、頭部對照圖與回投疊圖 | 關卡 1–2 0 FAIL |
| `{name}_stage3_models` | 兩個 GLB（`{name}_rigged.glb` 無光照、`{name}_rigged_lit.glb`）＋預覽圖 | 關卡 1–3 0 FAIL |
| `{name}_stage4_acceptance` | 原圖對模型對照圖（全身 8 角度、頭部特寫 8 角度）、`fit_report.json`、`gates.json` | 關卡 1–4 0 FAIL |

同一個階段同時只會有好或 `_FAIL` 其中一包：每次打包都先刪掉舊的。每包都有 `manifest.json`：

| 欄位 | 內容 |
| --- | --- |
| `deliverable` | 好（`true`）或不好（`false`） |
| `gates` | 這個階段和之前每道關卡的 FAIL / WARN / PASS |
| `failures` | 每一個未通過項目的原文 |
| `missing` | 缺少的檔：缺照片，或流程停在這個階段時還沒做出來的檔 |
| `stopped` | 流程停在這個階段時：停在哪一步、原因 |
| `sha256` | 包裡每個檔的 SHA-256，用來確認拿到的是同一份 |

## 四道關卡

| 關卡 | 指令（`run_all.py` 自動執行） | 檢查什麼 | FAIL 多半要修哪裡 |
| --- | --- | --- | --- |
| 1 照片檢查 | `check_turnaround.py PHOTOS` | 33 張照片本身：檔名、解析度、構圖、角度、相機距離、對準點、透視、光線、耳朵、臉部比例、頭部朝向、特寫與全身的臉部位置 | 照片：照報告「→」後面的建議重畫 |
| 2 烘焙前檢查 | `check_turnaround.py PHOTOS --head-overlap-work WORK` | 重建後的相機與網格：頭部特寫相機角度、全身與特寫的五官位置、頭部重疊區亮度 | 多半是照片（特寫角度、五官位置），再查重建步驟 |
| 3 GLB 驗證 | `verify_glb.py OUT/*.glb` | GLB 結構、骨架與蒙皮、身高、無光照材質、頭部貼圖條紋（unlit／lit 兩個檔各驗一次） | 程式 |
| 4 最終驗收 | `fit_report.py WORK --accept` | 成品網格投影回 24 張全身原圖的剪影不一致：平均 ≤ 8% PASS、> 10% FAIL；單張 > 12% WARN | 先看單張 WARN 的照片在照片檢查第 10 / 10d / 10e 項的結果 |

每道關卡最後都印同一格式：`總結: N 個 FAIL, N 個 WARN, N 個 PASS，共 N 項`。

## PASS / WARN / FAIL 怎麼處理

| 結果 | 意思 | 處理 |
| --- | --- | --- |
| PASS | 在完美照片 + 小餘裕的門檻內 | 不用處理 |
| WARN | 超出完美照片的範圍，但還不會直接造成模型或貼圖缺陷 | 結果包仍是好的。交付前逐項看過、記在 Issue；同一項反覆出現或數量變多時，回頭修照片 |
| FAIL | 會直接造成重建缺陷（重影、接縫、錯位、變形），或規格錯誤 | 結果包是 `_FAIL`，不能交付，一定要清掉。照片的 FAIL 只能重畫照片，不改門檻遷就照片 |

門檻只有一套（照片檢查 1.38.0 起沒有 `--mode`）：照片一律要先經 AI 修正才進來，門檻由完美合成照片（Luna `luna-v1.glb` 與舊測試模型，兩者都必須 0 FAIL／0 WARN）加小餘裕校準。要改門檻，先證明完美照片仍是 0 FAIL／0 WARN。

## 每個階段給客戶看什麼

客戶是內部客戶：每個階段都給圖和結果包，未通過與需複核照實列出，不隱藏。頁面全部用中文。

`OUT/client/index.html` 在每一步開始與結束時更新，進行中每 20 秒自動重新整理，隨時打開都看得到：

- 4 個階段各自是 未開始／進行中／完成／停止，18 個步驟的狀態與時間；
- 停下時：停在哪一步、幾項未通過、該怎麼處理；
- 每個階段的結果包與下載連結：「成果（好，可交付）」或「成果（有未通過，不好，不能交付）」；
- 驗收總表（未通過／需複核／通過／共計）與「可以交付／不能交付」。

全部結束（或停下）時再完整產生一次，含 Blender 渲染的原圖對模型。也可以單獨執行 `python body3d/client_report.py PHOTOS OUT`。

| 階段 | 圖 | 客戶看什麼 |
| --- | --- | --- |
| 1 照片 | `01_photos.jpg`：33 張總覽（水平、俯角 30°、仰角 20°、頭部特寫、俯視） | 人、髮型、服裝、表情對不對；照片檢查清單 |
| 2 重建 | `02_head_review.png`、`02_head_overlap.png` | 全身照和頭部特寫的頭部是否一致；烘焙前檢查清單 |
| 3 模型 | `03_preview.jpg`：正面、3/4、側面、背面渲染 | 整體外觀、比例、貼圖；模型檔驗證清單 |
| 4 成品驗收 | `04_body_compare.jpg`、`05_head_compare.jpg`：用照片的規格相機拍模型，左原圖、右模型 | 兩邊應該一樣：臉的朝向、五官、輪廓、顏色；剪影吻合度（平均 ≥ 92% 通過） |

## 一輪的步驟

1. 開 GitHub Issue，寫輸入照片版本、checker 版本、目標。
2. 跑 `run_all.py`（新的輸出目錄、不加 `--force`），看客戶頁、驗收總表與 `deliver/`。
3. 停在某一關：看 `_FAIL.zip` 的 `failures` 或客戶頁清單，找出是哪一項。
   - 照片的問題 → 把報告「→」後面的建議交給 AI 重畫，回第 2 步。
   - 程式的問題 → 依 README 的 Loop engineering 第 2 步找最早出錯的步驟，先加能重現的檢查再修，回第 2 步。
   - 需要看問題在後面怎麼出現 → 另開一個輸出目錄加 `--force` 跑完，只用來診斷。
4. 四包都是好的：逐項看 WARN 並記在 Issue；做 Yoga2 驗收（交付條件第 5 項）。
5. 在 Issue 貼上驗收總表、`gates.json`、四包的位置與前後對照圖，關閉 Issue。

## 交付條件（全部要符合）

1. 照片在新的資料夾，未經手動改名或覆蓋；用最新版 main 的腳本。
2. 從頭在**新的輸出目錄**重建：不加 `--force`，不用 `--from`／`--only` 接舊的中間檔。
3. `OUT/deliver/` 四包都是好的（沒有 `_FAIL`），`OUT/gates.json` 的 `deliverable` 為 `true`。
4. 所有 WARN 已逐項看過並記在 Issue。
5. Three.js／Yoga2 匯入後，依 README 的 Loop engineering 第 1 步比對 0°／90°／180°（有疑點加 45°／315° 與特寫），並測站姿與抬手。

交付內容：四個好的結果包、`client/` 整個資料夾、Yoga2 站姿／抬手截圖。

## 已知限制

- MakeHuman 模板（`--template makehuman`）仍在試驗：側面輪廓是模板的通用臉，全身剪影吻合度比外殼流程差。預設的外殼流程才是交付路線。
- 檢查還沒涵蓋網格自我穿插；Yoga2 看到斑點或摺痕時，先用 Blender 實際渲染確認（`verify_glb --renders` 的頭部圖用點去畫，會冒出假的小點）。
- Yoga2 的站姿、抬手截圖還要手動拍。
