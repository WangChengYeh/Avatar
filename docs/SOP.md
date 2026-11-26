# 標準作業流程（SOP）

[返回 README](../README.md) · [流程與驗收](Workflow-and-Validation.md) · [Loop engineering 的理論基礎](Loop-Engineering-Theory.md)

**一句話：四個階段，每個階段沒有 FAIL 才進下一個；FAIL 的當下也會交出一包結果；四包都是好的才能交付。**

## 你要做的事

1. **準備 33 張照片**（AI 生圖、修圖完成），放進一個新的資料夾。規格見[輸入照片](Workflow-and-Validation.md#輸入照片)與[生圖規格](Workflow-and-Validation.md#生圖規格)。
2. **執行一行指令**，輸出到一個新的資料夾：

   ```sh
   python body3d/run_all.py ./photos ./output-0601 --name body
   ```

3. **打開 `output-0601/client/index.html`** 看結果。跑的時候也可以開著，它每 20 秒自動更新。
4. 看畫面最上面：
   - 綠色「**可以交付**」→ 到[可以交付了嗎](#可以交付了嗎)。
   - 紅色「**不能交付**」→ 看紅框「**要修的項目**」，到[停下來時怎麼辦](#停下來時怎麼辦)。

## 你會看到什麼

### 客戶頁（`client/index.html`）

停在照片檢查的樣子（R14 照片，2 項未通過）：

![停在照片檢查](sop/client_stopped.jpg)

由上往下：

1. **進度**：停在哪一步、用了多久。四個方塊是四個階段：灰色未開始、黃色進行中、綠色完成、紅色停止。
2. **可以交付／不能交付**。
3. **要修的項目**（紅框）：每一個未通過項目，「→」後面是怎麼修。只要有 FAIL，這裡就會列出來，需複核（WARN）不放進來。
4. **驗收總表**：每道關卡的未通過、需複核、通過、共計。
5. **各階段**：每個階段的圖、結果包下載連結、未通過與需複核清單（未通過排在前面）。

四個階段都通過的樣子（Luna 完美照片）：

![四個階段都完成](sop/client_done.jpg)

### 終端機

停下來時（最後幾行）：

```
[ 1/18] check
停在步驟 check: 照片檢查有 FAIL（見 run_all.log / turnaround_report.png）。修正照片，或加 --force 繼續做完供診斷
     階段 1 成果（有未通過，標 _FAIL）：output-0601/deliver/body_stage1_photos_FAIL.zip

驗收總表               FAIL  WARN  PASS  共計
  1 照片檢查              2    88   218   308  ← FAIL
  可交付: 否（有 FAIL）
```

全部通過時：

```
[ 1/18] check
     階段 1 成果（好，可交付）：output-0601/deliver/body_stage1_photos.zip
[ 2/18] cams
   …
[12/18] bake
     階段 2 成果（好，可交付）：output-0601/deliver/body_stage2_reconstruction.zip
   …
[17/18] verify
     階段 3 成果（好，可交付）：output-0601/deliver/body_stage3_models.zip
[18/18] fit

驗收總表               FAIL  WARN  PASS  共計
  1 照片檢查              0     0   304   304
  2 烘焙前檢查            0     0    37    37
  3 GLB 驗證（unlit）     0     0    21    21
  3 GLB 驗證（lit）       0     0    20    20
  4 最終驗收              0     0    25    25
  可交付: 是
     階段 4 成果（好，可交付）：output-0601/deliver/body_stage4_acceptance.zip
```

結束碼：跑到最後、跑過的關卡全部 0 FAIL 為 0；停下或有 FAIL 為 1。

### 結果包（`deliver/` 資料夾）

每個階段結束就多一包。檔名就是結果：

| 你看到 | 意思 |
| --- | --- |
| `body_stage1_photos.zip` | 階段 1 好的結果，可交付 |
| `body_stage1_photos_FAIL.zip` | 階段 1 不好：有 FAIL，或停在這個階段。有多少給多少，可以看、可以留存，不能交付 |

停在照片檢查時，資料夾裡只有 `body_stage1_photos_FAIL.zip`；四個階段都通過時是四包好的：

```
deliver/body_stage1_photos.zip
deliver/body_stage2_reconstruction.zip
deliver/body_stage3_models.zip
deliver/body_stage4_acceptance.zip
```

## 四個階段：每個階段你看到什麼、拿到什麼

| 階段 | 做什麼 | 客戶頁的圖 | 結果包 | 通過 | 未通過（停下） |
| --- | --- | --- | --- | --- | --- |
| 1 照片 | 檢查 33 張照片 | 33 張總覽 | `stage1_photos`：33 張原檔＋照片檢查報告 | 進階段 2 | 重畫照片 |
| 2 重建 | 第 2–11 步：相機、外形、網格、頭部對位、臉部、UV；最後烘焙前檢查 | 全身與頭部特寫的頭部對照、疊圖 | `stage2_reconstruction`：相機、人體網格、對照圖 | 進階段 3 | 多半是照片（特寫角度、五官位置），回階段 1 |
| 3 模型 | 第 12–17 步：烘焙貼圖、匯出、骨架、材質；最後驗證 GLB | 正面、3/4、側面、背面 | `stage3_models`：兩個 GLB＋預覽圖 | 進階段 4 | 程式的問題 |
| 4 成品驗收 | 第 18 步：用照片的相機拍模型，和原圖比 | 左原圖、右模型（全身 8 角度、頭部 8 角度） | `stage4_acceptance`：對照圖、數字 | 四包都好 → 交付 | 先看照片檢查第 10 / 10d / 10e 項 |

## 停下來時怎麼辦

1. 看客戶頁紅框「**要修的項目**」：每一項都有**診斷**（[診斷樹](Diagnosis-Tree.md)走到的葉子）：原因、誰要修（照片／程式）、信心、怎麼修、一路問過的問題與數字。同樣的內容在 `OUT/diagnosis.json` 與 `_FAIL.zip` 裡的 `manifest.json`（`diagnosis`、`failures`）。
2. 照診斷的「誰要修」處理（診斷信心低時，人工再看一次）：
   - **照片的問題**（照片檢查未通過，或烘焙前檢查的頭部、五官錯位）：把「→」後面的建議交給 AI 重畫那幾張，放進新的照片資料夾。
   - **程式的問題**（GLB 驗證未通過、程式出錯）：交給工程師，依 README 的 Loop engineering 第 2 步找最早出錯的步驟，先加能重現的檢查再修。
3. 用新的輸出資料夾從頭再跑一次。
4. **照片的錯只在照片修。** 不能在後面的步驟手動補（例如手動平移某張特寫的相機）：那樣的結果無法重現，也不能交付。

### 自動修正

照片檢查未通過時，`run_all.py` 先看能不能自動修：每一項都要是**經過證明**的修正（對照實驗裡讓後面的關卡變好，見[診斷樹](Diagnosis-Tree.md#自動修正的條件)），而且修完用同一項檢查驗證通過，才修；修正後的照片另存在 `OUT/photos_fixed_rN/`，原檔不動，記在 `autofix.json`。有任何一項不是，就停下交給 AI 重畫。目前沒有經過證明的修正，所以未通過一律停下。`--no-autofix` 關掉。

### 想先看到 GLB：`--force`

```sh
python body3d/run_all.py ./photos ./output-0601-force --name body --force
```

有 FAIL 也做完四個階段，拿得到 GLB 和每個階段的結果包，用來看問題在後面怎麼出現。但從第一個 FAIL 起全部是 `_FAIL`，**不能交付**；照片未通過時，重建用較寬的相機搜尋範圍（±10° / ±16°），結果本來就和照片修好後不同。缺少 MediaPipe、Blender 時一律先裝好，`--force` 不能跳過。

### 只想先檢查照片

```sh
python body3d/deliver.py stage1 ./photos ./output-0601
```

只做階段 1：檢查並打包照片（好 → `stage1_photos.zip`，結束碼 0；不好 → `stage1_photos_FAIL.zip`，結束碼 1）。

## 可以交付了嗎

全部打勾才交付：

- [ ] 客戶頁顯示綠色「可以交付」，`gates.json` 的 `deliverable` 為 `true`。
- [ ] `deliver/` 有四包，沒有任何 `_FAIL`。
- [ ] 這次是從頭在新的輸出資料夾跑的：沒有 `--force`，沒有 `--from`／`--only`；照片在新的資料夾、沒有手動改名或覆蓋；用最新版 main。
- [ ] 需複核（WARN）逐項看過，記在 Issue。
- [ ] 在 Three.js／Yoga2 匯入 GLB，比對 0°／90°／180°（有疑點加 45°／315° 與特寫），並測站姿與抬手（README 的 Loop engineering 第 1 步）。

交付內容：四個好的結果包、`client/` 整個資料夾、Yoga2 站姿／抬手截圖。在 Issue 貼上驗收總表、`gates.json`、四包的位置與前後對照圖，關閉 Issue。

---

## 附錄

### 規則

1. 這個階段沒有 FAIL，才進下一個階段；有 FAIL 就停。
2. FAIL 的當下也會有一包結果：停下的階段有多少給多少（`_FAIL`），之前通過的階段各有一包好的。程式出錯停下時也一樣。
3. 例外：`--force` 做完四個階段，只供診斷，從第一個 FAIL 起全部 `_FAIL`。
4. 四包都是好的，才能交付。
5. 照片的錯只在階段 1 修，不在後面手動補。

### 每個階段的成果

| 結果包 | 內容 | 好的條件 |
| --- | --- | --- |
| `{name}_stage1_photos` | 33 張照片原檔（2048 × 2048 JPEG，檔名照規格）＋照片檢查報告 | 關卡 1 0 FAIL，33 張齊全 |
| `{name}_stage2_reconstruction` | 相機 `cams33.json`、人體網格（`body33s.ply`，MakeHuman 版 `body_mh.ply`）、頭部對照圖與回投疊圖 | 關卡 1–2 0 FAIL |
| `{name}_stage3_models` | 兩個 GLB（`{name}_rigged.glb` 無光照、`{name}_rigged_lit.glb`）＋預覽圖 | 關卡 1–3 0 FAIL |
| `{name}_stage4_acceptance` | 原圖對模型對照圖、`fit_report.json`、`gates.json` | 關卡 1–4 0 FAIL |

同一個階段同時只會有好或 `_FAIL` 其中一包（每次打包先刪掉舊的）。每包的 `manifest.json`：

| 欄位 | 內容 |
| --- | --- |
| `deliverable` | 好（`true`）或不好（`false`） |
| `gates` | 這個階段和之前每道關卡的 FAIL / WARN / PASS |
| `failures` | 每一個未通過項目的原文 |
| `missing` | 缺少的檔：缺照片，或停在這個階段時還沒做出來的檔 |
| `stopped` | 停在這個階段時：停在哪一步、原因 |
| `sha256` | 包裡每個檔的 SHA-256，用來確認拿到的是同一份 |

### 四道關卡

| 關卡 | 指令（`run_all.py` 自動執行） | 檢查什麼 |
| --- | --- | --- |
| 1 照片檢查 | `check_turnaround.py PHOTOS` | 33 張照片本身：檔名、解析度、構圖、角度、相機距離、對準點、透視、光線、耳朵、臉部比例、頭部朝向、特寫與全身的臉部位置 |
| 2 烘焙前檢查 | `check_turnaround.py PHOTOS --head-overlap-work WORK` | 重建後的相機與網格：頭部特寫相機角度、全身與特寫的五官位置、頭部重疊區亮度 |
| 3 GLB 驗證 | `verify_glb.py OUT/*.glb` | GLB 結構、骨架與蒙皮、身高、無光照材質、頭部貼圖條紋（unlit／lit 兩個檔各驗一次） |
| 4 最終驗收 | `fit_report.py WORK --accept` | 成品網格投影回 24 張全身原圖的剪影不一致：平均 ≤ 8% PASS、> 10% FAIL；單張 > 12% WARN |

每道關卡最後都印：`總結: N 個 FAIL, N 個 WARN, N 個 PASS，共 N 項`。各項門檻見[流程與驗收](Workflow-and-Validation.md)。

### PASS / WARN / FAIL

| 結果 | 客戶頁寫法 | 意思 | 處理 |
| --- | --- | --- | --- |
| PASS | 通過 | 在完美照片 + 小餘裕的門檻內 | 不用處理 |
| WARN | 需複核 | 超出完美照片的範圍，但還不會直接造成模型或貼圖缺陷 | 結果包仍是好的。交付前逐項看過、記在 Issue；同一項反覆出現或變多時，回頭修照片 |
| FAIL | 未通過 | 會直接造成重建缺陷（重影、接縫、錯位、變形），或規格錯誤 | 結果包是 `_FAIL`，一定要清掉。照片的 FAIL 只能重畫照片，不改門檻遷就照片 |

門檻只有一套：照片一律要先經 AI 修正才進來，門檻由完美合成照片（Luna `luna-v1.glb` 與舊測試模型，兩者都必須 0 FAIL／0 WARN）加小餘裕校準。要改門檻，先證明完美照片仍是 0 FAIL／0 WARN。

### 每個階段給客戶看什麼

客戶是內部客戶：每個階段都給圖和結果包，未通過與需複核照實列出，頁面全部中文。`client/index.html` 每一步開始與結束時更新（進行中每 20 秒自動重新整理），全部結束或停下時再完整產生一次（含 Blender 渲染的原圖對模型）。單獨產生：`python body3d/client_report.py PHOTOS OUT`。

| 階段 | 圖 | 客戶看什麼 |
| --- | --- | --- |
| 1 照片 | `01_photos.jpg`：33 張總覽（水平、俯角 30°、仰角 20°、頭部特寫、俯視） | 人、髮型、服裝、表情對不對 |
| 2 重建 | `02_head_review.png`、`02_head_overlap.png` | 全身照和頭部特寫的頭部是否一致 |
| 3 模型 | `03_preview.jpg`：正面、3/4、側面、背面渲染 | 整體外觀、比例、貼圖 |
| 4 成品驗收 | `04_body_compare.jpg`、`05_head_compare.jpg`：用照片的規格相機拍模型，左原圖、右模型 | 兩邊應該一樣：臉的朝向、五官、輪廓、顏色；剪影吻合度（平均 ≥ 92% 通過） |

### 已知限制

- MakeHuman 模板（`--template makehuman`）仍在試驗：側面輪廓是模板的通用臉，全身剪影吻合度比外殼流程差。預設的外殼流程才是交付路線。
- 檢查還沒涵蓋網格自我穿插；Yoga2 看到斑點或摺痕時，先用 Blender 實際渲染確認（`verify_glb --renders` 的頭部圖用點去畫，會冒出假的小點）。
- Yoga2 的站姿、抬手截圖還要手動拍。
