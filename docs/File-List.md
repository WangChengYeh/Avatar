# 重要檔案清單（file list）

[返回 README](../README.md) · [SOP](SOP.md) · [專案迴圈](Project-Loop.md) · [執行者 runbook](Agent-Runbook.md)

**一句話：要找什麼先看這一頁。** 這份清單由 Claude 維護，每次合併改到這裡列的東西就一起更新。人和三個 agent（Claude、ChatGPT、Gemini）都看同一份。

照片與結果包在雲端硬碟 `avatar/`，所有人都用 **Google Drive 連結器**讀寫，依資料夾或檔名找。這個 repo 是公開的，所以不放雲端硬碟的連結或人物照片。

## 1. 每個人先讀的

| 檔案 | 誰讀 | 內容 |
| --- | --- | --- |
| [docs/Handoff.md](Handoff.md) | Claude（每個新 session 先讀） | 還沒做完的事：下一步、在哪裡 |
| [docs/papers/](papers/)（[網站](https://wangchengyeh.github.io/Avatar/)） | 所有人 | 技術報告：每個難題一篇，理論與量測 |
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
| `body3d/next_step.py --workspace <avatar 資料夾>` | 執行者每做完一步就跑；它說下一步做什麼，並更新 `next_step.md`、`avatar_state.json`。等 Claude 時加 `--wait`：程式自己等，在沙盒逾時之前回來 |
| `body3d/run_all.py <photos> <output> --name <名稱>` | 整條流程（照片 → GLB），停或不停都打包各階段結果 |
| `body3d/check_turnaround.py <photos>` | 只跑照片檢查（第 1 關） |
| `body3d/run_all.py <photos> <新的輸出> --reuse <上一版的輸出>` | 同一組照片換了程式重跑：沿用上一版裡程式沒變的步驟（每一步的指紋記在 `work/checkpoint.json`），見 [SOP](SOP.md#改了程式之後從哪一步重跑) |
| `body3d/guides.py <photos> [<out>]` | 分段畫（先給輪廓再畫）：照六段量已有的照片、寫出下一段的輪廓圖與 `guides.md`；`--check` 只量。平常由 next_step 的 DRAW 狀態呼叫 |
| `body3d/orders.json` | Claude 對個別 avatar 的指令（`agent/avatar` → 做什麼）。執行者只照 next_step 做，不照 issue 留言做，所以要某個 avatar 做的事寫在這裡；next_step 每次 pull 之後讀 |
| `body3d/escalate.py <output> --agent … --avatar …` | 整理發給 Claude 的 issue 內文 |
| `body3d/data_repo.py publish／fetch／list` | GitHub 資料 repo `WangChengYeh/avatar_data` 的 Release（備用，預設不用：repo 是公開的；只在 `AVATAR_DATA_PUBLISH=1` 時上傳） |
| `body3d/diagnose.py photos|prebake …` | 單獨看一次診斷樹 |
| `dashboard/`（Google Apps Script） | 專案總覽網頁：每個 avatar、每一版、四關 FAIL／WARN／PASS、最終結果圖；部署在使用者的 Google 帳號，直接讀雲端硬碟（`dashboard/README.md`） |
| `python -m pytest tests` | 全部測試（約 35 分鐘）；`tests/test_steps.py`、`test_next_step.py`、`test_escalate.py` 幾秒 |
| `python tests/face_truth.py <真實模型.glb> <work>` | 量具，不是測試：完美照片重建出來的臉和渲染它的模型差多少（468 個特徵點的深度誤差）。改臉或頭的形狀之前先跑（`tests/data/luna-v1.glb`、`tests/data/body_rigged.glb`） |

## 3. 每一輪會產生的檔案

執行者的工作區：`avatar/<chatgpt|gemini>/<avatar_NNN>/`（每個 avatar 一個資料夾，每一輪一個版本 `vNNN`）。

| 位置 | 檔案 | 重要在哪 |
| --- | --- | --- |
| `<avatar>/next_step.md` | 下一步 | **人只要看這個**：目前狀態、原因、要做的事；最後一段「雲端硬碟」列出這一版要放到雲端硬碟的檔與位置 |
| `<avatar>/avatar_state.json` | next_step 的紀錄 | 每一輪的 FAIL、等待中的 issue／PR、`--wait` 學到的等待時限 |
| `<avatar>/wait_heartbeat.json` | `--wait` 的心跳 | 上一次等待有沒有被沙盒砍掉（沒有「done」＝被砍） |
| `<avatar>/issue.md`、`issue_title.txt` | 要發給 Claude 的 issue | ESCALATE 時才有；執行者用 gh 或 GitHub 連結器自己發 |
| `<avatar>/vNNN/photos/` | 這一輪的 33 張照片 | 重畫只改要改的幾張，其他複製上一版 |
| `<avatar>/vNNN/output/deliver/{name}_stage1_photos(_FAIL).zip` | 階段 1 結果包 | 照片、檢查報告、AI 修圖單（有 FAIL 時） |
| `…/{name}_stage2_reconstruction(_FAIL).zip` | 階段 2 | 相機、網格、頭部對照圖 |
| `…/{name}_stage3_models(_FAIL).zip` | 階段 3 | GLB（unlit／lit）與渲染圖 |
| `<avatar>/vNNN/output/deliver/{name}_vNNN_rigged.glb` | 無光照 GLB（檔名帶版本） | 跑到第 3 關才有；next_step 從 `output/{name}_rigged.glb` 複製出來，和結果包一起放上雲端硬碟，可以直接下載，各版本下載後不會同名 |
| `…/{name}_stage4_acceptance(_FAIL).zip` | 階段 4 | 成品對原圖的比對、`fit_report.json` |
| `<avatar>/vNNN/output/client/index.html` | 客戶頁 | 四個階段的進度、要做的事、結果包連結 |
| `<avatar>/vNNN/output/ai_fix_request/AI修圖單.md` | AI 修圖單 | 照片的問題：哪幾張、怎麼改、參考圖 |
| `<avatar>/vNNN/output/ai_code_request/AI改code單.md` | AI 改 code 單 | 程式的問題：哪個階段、哪些檔案 |
| `<avatar>/vNNN/output/gates.json`、`diagnosis.json` | 驗收總表、診斷 | 每一關的 FAIL／WARN／PASS、修的順序 |

`_FAIL` 結尾的結果包表示那一包不能交付，但一樣要放、一樣要看。

## 4. 目前各 avatar 的狀態

由 Claude 在每次處理 issue／PR 時更新（最後更新 2026-11-28，依雲端硬碟 `avatar/` 實際內容）。每個執行者的 avatar 各自從 `avatar_001` 編號。

| 執行者／Avatar | 雲端硬碟上的版本 | 最新結果 | 主要問題 | 相關 |
| --- | --- | --- | --- | --- |
| ChatGPT／avatar_001（R 系列） | v033 … v062 | v061（`--template makehuman`，body3d 2.21.0）：第 1 關 0 FAIL，停在第 2 關（3 項 FAIL，R58 是 7 項）；v062 是 pull 後用同一組照片重跑。R54 是最後一版跑完四關的：最終剪影 15.4% FAIL | 頭部特寫彼此不一致（相鄰一致、135／315 鏡像 0.893）；斜角全身照和水平環對不上 | #79、#65 |
| Gemini／avatar_001 | v002 … v015 | v015（body3d 2.24.1）：四關 0 FAIL、DONE，最終剪影 9.05%；頭部四組鏡像 0.956–0.977 | 側臉貼圖仍糊、肩膀有一塊手：四關沒有比成品貼圖與原圖的檢查（見交接清單）；v012 的第 3 關 FAIL（擺姿勢網格連續性）在 v014 沒有再出現，原因未查 | #84 |

模板：預設是 MakeHuman（body3d 2.36.0；身體、手指、骨架來自模板，頭用外殼的）。Blender 沒有 MakeHuman 擴充（MPFB）時 `run_all` 會自動安裝（`blender --online-mode --command extension install -s -e mpfb`），裝不了才退回外殼流程。用了哪一個、Blender 有沒有擴充、安裝做了什麼，印在 `run_all` 開頭，並寫在每一版的 `gates.json` 與結果包 `manifest.json`（`template`、`mpfb`、`mpfb_install`）、`next_step.md` 與總覽網頁。兩組完美照片與 Gemini v015 的照片，兩種模板都是四道關卡 0 FAIL（2.34.0）。

### 雲端硬碟上的資料夾（實際）

```
avatar/                       ← 所有人用 Google Drive 連結器讀寫
├── chatgpt/avatar_001/v033 … v062/    每一版放結果包（例：Avatar-R60_stage2_reconstruction_FAIL.zip）、gates.json、next_step.md
└── gemini/avatar_001/v002 … v015/     同上；body3d 2.22.0 起跑到第 3 關的版本另放無光照 GLB
```

所有人讀雲端硬碟的方式：Google Drive 連結器（依資料夾或檔名找、讀檔、放檔）。連結器是在 session 開始時載入，剛設定好的要開新的 session 才看得到。

還沒做完的事見[交接清單](Handoff.md)。
