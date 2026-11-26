# 專案迴圈：三個 AI agent

[返回 README](../README.md) · [重要檔案清單](File-List.md) · [SOP](SOP.md) · [診斷 SOP 與診斷樹](Diagnosis-Tree.md)

**一句話：Claude 維護 SOP 與程式、經 GitHub 交付；ChatGPT 與 Gemini 各自照 SOP 開發一個 avatar；診斷處理不掉的就發 GitHub issue 給 Claude，Claude 改好 SOP／程式，ChatGPT／Gemini 更新後繼續。**

人只準備輸入與 token（見 [SOP](SOP.md#誰做什麼)）；下面三個 agent 做其他所有事。

## 角色

| Agent | 負責 | 在 GitHub 上做什麼 |
| --- | --- | --- |
| **Claude** | SOP 與程式的擁有者：寫 SOP、寫程式、code review、處理升級的 issue | 開 PR、review、合併到 main；回覆並關閉 issue |
| **ChatGPT** | 執行者：照 SOP 開發 **avatar A**：生圖、跑流程、照診斷修圖或改程式 | 從 main 取 SOP 與程式；程式改動開 PR 給 Claude review；處理不掉的發 issue |
| **Gemini** | 執行者：照 SOP 開發 **avatar B**（同上） | 同上 |

SOP 只有一份，在 main：`docs/SOP.md`、`docs/Diagnosis-Tree.md`、`docs/Workflow-and-Validation.md` 與 `body3d/`。執行者不改 SOP 本身；要改就發 issue。

## 迴圈

```
            ┌───────────────────────── Claude ─────────────────────────┐
            │  SOP + 程式（main）  ←── PR、review、合併 ←── 修好 issue    │
            └──────────┬───────────────────────────────────▲──────────┘
                git pull main（SOP 版本）              GitHub issue（升級）
                       │                                   │
        ┌──────────────▼──────────────┐     ┌──────────────┴──────────────┐
        │ ChatGPT：avatar A            │     │ Gemini：avatar B             │
        │ 生圖 → run_all → 診斷 SOP     │     │ 生圖 → run_all → 診斷 SOP     │
        │ 修圖／改程式 → 重跑           │     │ 修圖／改程式 → 重跑           │
        │ 處理不掉 → 發 issue、等更新   │     │ 處理不掉 → 發 issue、等更新   │
        └─────────────────────────────┘     └─────────────────────────────┘
```

### 執行者（ChatGPT／Gemini）每一輪

**實際做法很簡單：照 [執行者 runbook](Agent-Runbook.md) 反覆跑 `python body3d/next_step.py --workspace ~/avatar/<chatgpt|gemini>/<avatar_NNN>`，照它說的做，只有 DONE 或 WAITING 才停。** 下面是 next_step 背後的規則。AGENTS.md（ChatGPT／Codex）、GEMINI.md（Gemini）會自動讀到這些指示。

1. `git pull` main（next_step 每次都會自動檢查，main 比本機新就給 UPDATE：pull、從頭重跑），記下 SOP 版本：`python body3d/run_all.py --version` 與 `python body3d/check_turnaround.py --version`，以及 commit。
2. 照 [SOP](SOP.md) 做：生圖 → `run_all.py`（新的輸出資料夾）→ 看客戶頁。
3. 有 FAIL：照[診斷 SOP](Diagnosis-Tree.md#診斷-sop)：照順序（前面階段先修、信心高先修），照片就照 AI 修圖單重畫，程式就照 AI 改 code 單改程式、**開 PR 給 Claude review**（不直接推 main）。
4. 符合下面「什麼時候發 issue」任何一條 → 發 issue，這個 avatar 停在原地等 Claude；可以同時做別的、但不要繞過問題。
5. Claude 合併修正後：`git pull` main，**用新的輸出資料夾從頭重跑**，在 issue 回報結果（解決就請 Claude 關閉；沒解決就留言附新的診斷）。
6. 四包都是好的 → 照 [SOP 的交付條件](SOP.md#可以交付了嗎)交付。

### 什麼時候發 issue（任何一條就發）

| 情況 | 例子 |
| --- | --- |
| **診斷信心低或沒有對應的規則** | 診斷葉子信心「低」、「未分類」，或 FAIL 項目沒有診斷 |
| **同一個 FAIL 修了 2 輪還在** | 照 AI 修圖單重畫兩次，同一項仍未通過（可能是檢查或門檻的問題，不是圖的問題） |
| **SOP 或檢查有缺口** | 後面的關卡 FAIL，但原因所在的階段沒有檢查抓得到（例：R17 前三關都過、第 4 關才 FAIL），而執行者無法確定該補什麼檢查 |
| **程式出錯、或 AI 改 code 單做不完** | `run_all.py` 停在程式錯誤；改 code 單要改的地方超出單上的檔案；改完兩組完美照片不再全部通過 |
| **SOP 互相矛盾或不清楚** | 兩條規則衝突、步驟看不懂、文件和程式行為不一致 |
| **懷疑門檻錯** | 照片明顯沒問題卻 FAIL，或明顯有問題卻 PASS |

不用發的：照片的問題、診斷信心高、AI 修圖單照做就會好的 → 自己修。

### 怎麼發 issue

```sh
python body3d/escalate.py OUTPUT_DIR --agent ChatGPT --avatar avatar-A --tried "重畫 el30_090 兩次，10i 仍 FAIL" > issue.md
gh issue create --title "[SOP] avatar-A：<一句話>" --body-file issue.md
```

`escalate.py` 從輸出資料夾整理出 issue 內文：SOP／程式版本與 commit、驗收總表、診斷（照修的順序）、每一項未通過的原文、停在哪一步、`run_all.log` 最後幾十行。執行者再補：做過什麼、幾輪、自己的判斷。各階段的 `_FAIL.zip`（含 AI 修圖單／改 code 單）拖進 issue 留言附上。

也可以直接用 GitHub 網頁的「SOP 升級（執行者 → Claude）」issue 表單。

### Claude 處理 issue

1. **重現**：用 issue 附的照片與 SOP 版本從頭跑；拿不到照片就請執行者附 `stage1_photos(_FAIL).zip`。
2. **照診斷 SOP 找原因所在的階段**（[診斷 SOP](Diagnosis-Tree.md#診斷-sop)）：照片、檢查缺口、程式、還是 SOP 本身。必要時做對照實驗（同一組照片只差一個變數）。
3. **改**：
   - 檢查缺口 → 在那個階段補檢查：這組照片會 FAIL、兩組完美照片仍 0 FAIL／0 WARN。
   - 程式 → 在那個階段修，兩組完美照片四道關卡仍全部通過。
   - 診斷樹 → 補分支或規則，讓下次信心高。
   - SOP → 改文件，消除矛盾、補缺的步驟。
4. **交付**：開 PR，內文寫 `Fixes #<issue>`、原因、補的檢查（前後數字）、驗收結果；更新 CHANGELOG。合併到 main。
5. **合併後執行者自動更新**：兩個執行者下一次跑 next_step 時都會拿到 UPDATE（`git pull`、用目前的照片從頭重跑），不用另外通知。等 issue 的那一位也一樣：**issue 不用先關閉**，pull 之後程式變了，next_step 就不再等（登記等待時記下程式指紋；R33 因為 issue 開著、gh 沒登入而一直停在 WAITING），照新的 SOP 繼續，跑完把結果回覆到 issue（next_step.md 的「回報」）。issue 等執行者回報解決才關閉。
6. **回覆 issue**：改了什麼、需要的最低版本（`run_all.py --version`／`check_turnaround.py --version`）、執行者要怎麼繼續（例：「pull main ≥ 1.41.1，新的輸出資料夾從頭跑；el30_090 等 7 張照 AI 修圖單重畫」）。等執行者回報解決再關閉。

### 執行者的程式 PR（Claude review）

執行者照 AI 改 code 單改程式時開 PR，用 PR 模板。Claude review 的標準：

- 改在原因所在的階段，沒有在後面的步驟補前面的錯；沒有手動修中間檔。
- 補的檢查：出問題的照片 FAIL、兩組完美照片 0 FAIL／0 WARN（附數字）。
- 兩組完美照片從頭跑，四道關卡全部 0 FAIL／0 WARN、可交付。
- 相關測試通過；新檢查有測試。
- 不影響另一個 avatar：改了共用的檢查或門檻時，PR 寫清楚另一個 avatar 會不會因此多出 FAIL（Claude 會在 issue 或 PR 裡通知另一個執行者）。

## avatar 放在哪裡

照片與結果放兩個地方：

- **執行者自己的機器**：工作區，每個執行者一個資料夾、每個 avatar 一個資料夾、每一輪一個版本（下圖）。
- **GitHub 資料 repo** [`WangChengYeh/avatar_data`](https://github.com/WangChengYeh/avatar_data)：每個版本做完，next_step 自動上傳成一個 Release（tag `<agent>-<avatar>-vNNN`，附件 `photos.zip`、四個階段的結果包、`gates.json`、`diagnosis.json`、`next_step.md`）。這是三個 agent 之間交換照片與結果的地方；照片是人物照片，資料 repo 建議設成私人。


```
~/avatar/
├── chatgpt/                      ← ChatGPT 負責的 avatar
│   └── avatar_001/               ← 一個 avatar（工作區 WS）
│       ├── v001/                 ← 一個版本（一輪）
│       │   ├── photos/           ← 這一輪的 33 張照片
│       │   └── output/           ← run_all 的輸出（deliver/、client/…）
│       ├── v002/ …               ← 重畫或重跑都開下一個版本，複製上一版的照片，不覆蓋舊的
│       ├── avatar_state.json     ← next_step 的記錄（每一輪的 FAIL、等待中的 issue／PR）
│       ├── next_step.md          ← 下一步（人只要看這個）
│       └── issue.md              ← 要發給 Claude 的 issue 內文（需要時才有）
└── gemini/
    └── avatar_001/ …             ← 每個執行者的 avatar 各自從 001 編號
```

issue 內文附上那個版本的 Release 連結；Claude 用 `python body3d/data_repo.py fetch <tag> DIR` 下載照片與結果包重現（`data_repo.py list chatgpt/avatar_001` 列出版本）。

## 兩個 avatar 共用一份 SOP

- 一個 avatar 引起的修正會影響另一個：Claude 合併後在兩邊的 open issue 或 PR 留言，另一個執行者 pull 後也要從頭重跑一次。
- 門檻只依兩組完美照片校準，不依某一個 avatar 調；某個 avatar 的照片一直過不了，修的是照片（或補檢查），不是放寬門檻。
- 程式與 SOP 在 `WangChengYeh/Avatar`；照片與結果在 `WangChengYeh/avatar_data` 的 Release。
