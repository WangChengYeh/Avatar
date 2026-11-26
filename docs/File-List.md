# 重要檔案清單（file list）

[返回 README](../README.md) · [SOP](SOP.md) · [專案迴圈](Project-Loop.md) · [執行者 runbook](Agent-Runbook.md)

**一句話：要找什麼先看這一頁。** 這份清單由 Claude 維護，每次合併改到這裡列的東西就一起更新。人和三個 agent（Claude、ChatGPT、Gemini）都看同一份。

這個 repo 是公開的，所以這裡**不放雲端硬碟的分享連結**（照片是人物照片）。每一版的檔案與連結記在雲端硬碟的 `avatar/<chatgpt|gemini>/file_list.md`（見[下面](#雲端硬碟上的-file_listmd)）。

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
| `body3d/next_step.py --workspace <avatar 資料夾>` | 執行者每做完一步就跑；它說下一步做什麼，並更新 `next_step.md`、`avatar_state.json`、自己的 `file_list.md` |
| `body3d/run_all.py <photos> <output> --name <名稱>` | 整條流程（照片 → GLB），停或不停都打包各階段結果 |
| `body3d/check_turnaround.py <photos>` | 只跑照片檢查（第 1 關） |
| `body3d/escalate.py <output> --agent … --avatar …` | 整理發給 Claude 的 issue 內文 |
| `body3d/data_repo.py publish／fetch／list` | 和 GitHub 資料 repo `WangChengYeh/avatar_data` 交換照片與結果 |
| `body3d/diagnose.py photos|prebake …` | 單獨看一次診斷樹 |

## 3. 每一輪會產生的檔案

執行者的工作區：`avatar/<chatgpt|gemini>/<avatar_NNN>/`（每個 avatar 一個資料夾，每一輪一個版本 `vNNN`）。

| 位置 | 檔案 | 重要在哪 |
| --- | --- | --- |
| `<avatar>/next_step.md` | 下一步 | **人只要看這個**：目前狀態、原因、要做的事 |
| `<avatar>/avatar_state.json` | next_step 的紀錄 | 每一輪的 FAIL、等待中的 issue／PR、上傳結果 |
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

由 Claude 在每次處理 issue／PR 時更新。

| Avatar | 執行者 | 最新版本 | 停在 | 主要問題 | 相關 |
| --- | --- | --- | --- | --- | --- |
| avatar_001（R 系列） | ChatGPT | v041（R41） | 階段 1 照片檢查：第 10i 項全視角外殼覆蓋 6 FAIL | v033–v041 8 輪沒進步：3 張斜對角的手臂和水平環不同（#70 後會直接指名：el30_315、low20_045、low20_315 的手臂，el30_045 的身體） | issue #65、PR #70 |
| avatar_002 | Gemini | — | — | 還沒有結果回報 | — |

模板：預設外殼流程；`--template makehuman` 從 body3d 2.18 起頭用外殼的、身體擬合到照片，兩組完美照片四道關卡 0 FAIL（#69）。

## 雲端硬碟上的 file_list.md

每個執行者各一份，放在自己的資料夾：`avatar/chatgpt/file_list.md`（ChatGPT）、`avatar/gemini/file_list.md`（Gemini）。由各自的 next_step 每一輪自動更新，只寫自己的，一個版本一列：

| 欄位 | 內容 |
| --- | --- |
| agent／avatar／版本 | 例：chatgpt／avatar_001／v041 |
| 時間 | 這一輪結果的時間 |
| 結果 | 四道關卡的 FAIL／WARN、是否可交付 |
| 下一步 | next_step 的狀態（RETOUCH、ESCALATE…） |
| 結果包 | `deliver/` 裡的檔名 |
| 分享連結 | 留空：要給 Claude 看的那一版，由人或執行者在雲端硬碟填上分享連結 |

這兩份不進 GitHub（有人物照片的連結）。要 Claude 看某一版時，給它那個執行者的 `file_list.md` 或那個檔案的分享連結即可。
