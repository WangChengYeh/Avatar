# 重要檔案清單（file list）

[返回 README](../README.md) · [SOP](SOP.md) · [專案迴圈](Project-Loop.md) · [執行者 runbook](Agent-Runbook.md)

**一句話：要找什麼先看這一頁。** 這份清單由 Claude 維護，每次合併改到這裡列的東西就一起更新。人和三個 agent（Claude、ChatGPT、Gemini）都看同一份。

照片與結果包在雲端硬碟 `avatar/`，所有人都用 **Google Drive 連結器**讀寫，依資料夾或檔名找。這個 repo 是公開的，所以不放雲端硬碟的連結或人物照片。

## 1. 每個人先讀的

| 檔案 | 誰讀 | 內容 |
| --- | --- | --- |
| [docs/SOP.md](SOP.md) | 所有人 | 四個階段、四道關卡、可以交付了嗎 |
| [docs/Agent-Runbook.md](Agent-Runbook.md) | ChatGPT、Gemini | 反覆跑 next_step、每個狀態怎麼做、什麼時候可以停 |
| [AGENTS.md](../AGENTS.md)／[GEMINI.md](../GEMINI.md) | ChatGPT／Gemini | 自動讀到的入口，指向 runbook |
| [docs/Project-Loop.md](Project-Loop.md) | 所有人 | 誰負責什麼、什麼時候發 issue、Claude 怎麼處理 |
| [docs/Diagnosis-Tree.md](Diagnosis-Tree.md) | 遇到 FAIL 時 | 先找哪個階段、照片還是程式、修的順序 |
| [docs/Workflow-and-Validation.md](Workflow-and-Validation.md) | 生圖、看門檻時 | 33 張照片規格、生圖提示詞、每一項檢查與門檻 |
| [CHANGELOG.md](../CHANGELOG.md) | 更新後 | 每次改了什麼、為什麼、前後數字 |

## 2. 程式入口

| 檔案 | 什麼時候用 |
| --- | --- |
| `body3d/next_step.py --workspace <avatar 資料夾>` | 執行者每做完一步就跑；它說下一步做什麼，並更新 `next_step.md`、`avatar_state.json` |
| `body3d/run_all.py <photos> <output> --name <名稱>` | 整條流程（照片 → GLB），停或不停都打包各階段結果 |
| `body3d/check_turnaround.py <photos>` | 只跑照片檢查（第 1 關） |
| `body3d/escalate.py <output> --agent … --avatar …` | 整理發給 Claude 的 issue 內文 |
| `body3d/data_repo.py publish／fetch／list` | GitHub 資料 repo `WangChengYeh/avatar_data` 的 Release（備用，預設不用：repo 是公開的；只在 `AVATAR_DATA_PUBLISH=1` 時上傳） |
| `body3d/diagnose.py photos|prebake …` | 單獨看一次診斷樹 |

## 3. 每一輪會產生的檔案

執行者的工作區：`avatar/<chatgpt|gemini>/<avatar_NNN>/`（每個 avatar 一個資料夾，每一輪一個版本 `vNNN`）。

| 位置 | 檔案 | 重要在哪 |
| --- | --- | --- |
| `<avatar>/next_step.md` | 下一步 | **人只要看這個**：目前狀態、原因、要做的事；最後一段「雲端硬碟」列出這一版要放到雲端硬碟的檔與位置 |
| `<avatar>/avatar_state.json` | next_step 的紀錄 | 每一輪的 FAIL、等待中的 issue／PR |
| `<avatar>/issue.md`、`issue_title.txt` | 要發給 Claude 的 issue | ESCALATE 時才有；沒有 gh 就交給人發 |
| `<avatar>/vNNN/photos/` | 這一輪的 33 張照片 | 重畫只改要改的幾張，其他複製上一版 |
| `<avatar>/vNNN/output/deliver/{name}_stage1_photos(_FAIL).zip` | 階段 1 結果包 | 照片、檢查報告、AI 修圖單（有 FAIL 時） |
| `…/{name}_stage2_reconstruction(_FAIL).zip` | 階段 2 | 相機、網格、頭部對照圖 |
| `…/{name}_stage3_models(_FAIL).zip` | 階段 3 | GLB（unlit／lit）與渲染圖 |
| `…/{name}_stage4_acceptance(_FAIL).zip` | 階段 4 | 成品對原圖的比對、`fit_report.json` |
| `<avatar>/vNNN/output/client/index.html` | 客戶頁 | 四個階段的進度、要做的事、結果包連結 |
| `<avatar>/vNNN/output/ai_fix_request/AI修圖單.md` | AI 修圖單 | 照片的問題：哪幾張、怎麼改、參考圖 |
| `<avatar>/vNNN/output/ai_code_request/AI改code單.md` | AI 改 code 單 | 程式的問題：哪個階段、哪些檔案 |
| `<avatar>/vNNN/output/gates.json`、`diagnosis.json` | 驗收總表、診斷 | 每一關的 FAIL／WARN／PASS、修的順序 |

`_FAIL` 結尾的結果包表示那一包不能交付，但一樣要放、一樣要看。

## 4. 目前各 avatar 的狀態

由 Claude 在每次處理 issue／PR 時更新（最後更新 2026-11-27，依雲端硬碟 `avatar/` 實際內容）。每個執行者的 avatar 各自從 `avatar_001` 編號。

| 執行者／Avatar | 雲端硬碟上的版本 | 最新結果 | 主要問題 | 相關 |
| --- | --- | --- | --- | --- |
| ChatGPT／avatar_001（R 系列） | v033、v038、v041、v045、v047 | v047：`Avatar-R47_stage1_photos_FAIL.zip`（第 1 關 FAIL，內容尚未分析） | v033–v041 8 輪卡在第 10i 項：3 張斜對角的手臂和水平環不同。照片檢查 1.43（#70）起直接指名 el30_315、low20_045、low20_315 的手臂與 el30_045 的身體；v047 是第一個在 1.43 之後的版本 | issue #65 |
| Gemini／avatar_001 | v002 | 四個階段的結果包都不是 `_FAIL`（`body_stage1_photos.zip` … `body_stage4_acceptance.zip`、`gates.json`、`next_step.md`） | 尚未確認；要照 [可以交付了嗎](SOP.md#可以交付了嗎) 做交付檢查 | — |

模板：預設外殼流程；`--template makehuman` 從 body3d 2.18 起頭用外殼的、身體擬合到照片，兩組完美照片四道關卡 0 FAIL（#69）。

### 雲端硬碟上的資料夾（實際）

```
avatar/                       ← 所有人用 Google Drive 連結器讀寫
├── chatgpt/avatar_001/v033 … v047/    每一版放結果包（例：Avatar-R47_stage1_photos_FAIL.zip）
└── gemini/avatar_001/v002/            四個階段結果包、gates.json、next_step.md
```

所有人讀雲端硬碟的方式：Google Drive 連結器（依資料夾或檔名找、讀檔、放檔）。連結器是在 session 開始時載入，剛設定好的要開新的 session 才看得到。

## 5. 交接：還沒做完的事

給接手的 Claude session（以及人）。做完一項就從這裡刪掉。

| 項目 | 下一步 | 在哪裡 |
| --- | --- | --- |
| Gemini avatar_001 v002 四關看起來都過了 | 下載 `gates.json` 與四包，確認 0 FAIL、照 SOP 做交付檢查（WARN 逐項看、在 App 匯入 GLB 截圖站姿與抬手）；可交付就在 File-List 改狀態 | 雲端硬碟 `avatar/gemini/avatar_001/v002` |
| ChatGPT avatar_001 v047 還在第 1 關 | 看 `Avatar-R47_stage1_photos_FAIL.zip` 的 manifest：是不是已經改成指名手臂、手臂有沒有變好；沒進步就在 #65 回覆 | 雲端硬碟 `avatar/chatgpt/avatar_001/v047`、issue #65 |
| #65 還開著 | 等 ChatGPT 回報 R31 系列（現在是 R47）重畫、`--template makehuman` 重跑後的第 4 關數字 | issue #65 |
| synth 完美照片用 MakeHuman，第 2 關右臉頰 1 個 WARN | P90 22.4／20（外殼流程 18.0）；查肩頸在 315° 的遮擋 | `check_turnaround.py` 頭部重疊、`mh_fit.py` |
| 中間角度與擺姿勢後的貼圖沒有直接的自動檢查 | 目前靠臉頰亮度、五官投影間接抓（R31 的臉部接縫就是在 App 裡才看到） | 第 3／4 關 |
| `test_camera_benchmark_perspective` 在 main 上失敗 | 用故意壞掉的透視照片跑基準，現在被照片檢查擋下回傳非零；基準應該用 `--force` 或接受非零 | `tests/test_run_all.py`、`body3d/camera_benchmark.py` |
| 肩帶附近貼圖色塊、兩腿內側暗線 | 兩種模板都有，照片與烘焙的問題 | `bake33.py` |
