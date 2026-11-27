# 專案迴圈：三個 AI agent

[返回 README](../README.md) · [重要檔案清單](File-List.md) · [SOP](SOP.md) · [診斷 SOP 與診斷樹](Diagnosis-Tree.md)

**一句話：Claude 維護 SOP 與程式、經 GitHub 交付；ChatGPT 與 Gemini 各自照 SOP 開發一個 avatar；診斷處理不掉的就發 GitHub issue 給 Claude，Claude 改好 SOP／程式，ChatGPT／Gemini 更新後繼續。**

人只準備輸入與 token（見 [SOP](SOP.md#誰做什麼)）；下面三個 agent 做其他所有事。

## 三個角色怎麼操作

每個 agent 都有 **GitHub**（`gh` 或 GitHub 連結器）和 **Google Drive**（Google Drive 連結器）。GitHub 放 SOP、程式、issue、PR；雲端硬碟 `avatar/` 放照片與結果包。GitHub repo 是公開的：照片不放 GitHub、不附在 issue，issue 裡寫雲端硬碟的路徑。

| 誰 | 用 GitHub 做什麼 | 用雲端硬碟做什麼 | 什麼時候停 |
| --- | --- | --- | --- |
| **ChatGPT／Gemini**（執行者） | `git pull` main（next_step 自動檢查）；處理不掉時**自己發 issue**；程式改動開 PR；在 issue 回報重跑結果 | 每一版跑完，把結果包、無光照 GLB、`gates.json`、`next_step.md` 放到 `avatar/<自己>/<avatar_NNN>/vNNN/`（`next_step.md` 最後一段列出來） | 只有 DONE（等 Claude 時一直跑 `--wait`） |
| **Claude**（維護者） | 看 issue、PR；修 SOP／程式、開 PR（`Fixes #N`）；新功能的 PR 人說合併才合併，只改文件或測試的自己合併；回覆 issue；更新 [交接清單](Handoff.md) 與 [File-List](File-List.md) | 讀執行者的結果包重現問題（依路徑或檔名找） | 每個 session 結束前更新交接清單 |
| **人** | 看 issue；看新功能的 PR，說「合併」 | 看 `next_step.md`、客戶頁；準備 `avatar/` 資料夾與連結器權限 | — |

### 誰做的

三個 agent 多半用同一個 GitHub 帳號，看帳號分不出是誰。每一樣東西都要標明：

| 東西 | 怎麼標 |
| --- | --- |
| issue、PR 標題 | 開頭 `[ChatGPT]`、`[Gemini]` 或 `[Claude]` |
| label | `agent:chatgpt`、`agent:gemini`、`agent:claude`（升級 issue 另加 `sop-escalation`） |
| issue、PR 內文與每一則留言 | 第一行「> 由 **ChatGPT** 發／回報」（Claude 的 PR 結尾另有 Claude Code 的署名） |
| 分支 | `chatgpt/…`、`gemini/…`、`claude/…` |
| commit | 結尾一行 `Agent: ChatGPT`（Claude 用 `Co-Authored-By: Claude …`） |
| 雲端硬碟 | 每個 agent 只寫自己的資料夾 `avatar/<chatgpt|gemini>/` |

next_step 產生的 issue 已經帶好標題前綴、label 與第一行。人在 GitHub 用 label 篩選（例：`label:agent:gemini`）就看得到某個 agent 做的所有事。

**執行者一輪的實際操作**

1. 跑 `python body3d/next_step.py --workspace ~/avatar/<chatgpt|gemini>/<avatar_NNN>`，照它印的指令做（UPDATE／START／RUN／RETOUCH／CODE），做完再跑一次。
2. 每一版跑完：照 `next_step.md` 的「雲端硬碟」用連結器放檔。
3. 走到 ESCALATE：用 `gh issue create`（或 GitHub 連結器，標題與內文在 `issue_title.txt`、`issue.md`）發 issue，`--waiting-issue N` 登記；WAITING 時跑 `next_step.py … --wait`，程式自己每分鐘檢查 GitHub、在沙盒逾時之前回來，還沒等到就再跑一次（[runbook](Agent-Runbook.md)）。
4. Claude 合併修正後，下一次 next_step 給 UPDATE：pull、再跑一次 next_step（重建或檢查的程式有變才需要重跑）；跑完照 `next_step.md` 的「回報」在 issue 留言。
5. DONE：做[交付檢查](SOP.md#可以交付了嗎)，在 issue（或新的 issue）寫交付的雲端硬碟路徑。

**Claude 的實際操作**

1. 開工讀 [交接清單](Handoff.md)，`gh issue list`／`gh pr list` 看有沒有新的。
2. 有 issue：用 Drive 連結器拿 issue 寫的路徑裡的結果包，照[診斷 SOP](Diagnosis-Tree.md#診斷-sop) 找原因、補檢查或修程式，開 PR 寫 `Fixes #N`；改程式行為的等人說合併，只改文件或測試的自己合併（CLAUDE.md）。
3. 合併後在 issue 回覆：改了什麼、最低版本、執行者怎麼繼續；執行者回報解決才關閉。
4. 結束前更新交接清單與 File-List 的狀態，開 PR。

## 角色

| Agent | 負責 | 在 GitHub 上做什麼 |
| --- | --- | --- |
| **Claude** | SOP 與程式的擁有者：寫 SOP、寫程式、code review、處理升級的 issue | 開 PR、review、合併到 main；回覆並關閉 issue（所有 issue 都由 Claude 關閉，包括交付的 issue：複核過才關） |
| **ChatGPT** | 執行者：照 SOP 開發自己的 avatar（`avatar/chatgpt/avatar_001`…）：生圖、跑流程、照診斷修圖或改程式 | 從 main 取 SOP 與程式；程式改動開 PR 給 Claude review；處理不掉的發 issue |
| **Gemini** | 執行者：照 SOP 開發自己的 avatar（`avatar/gemini/avatar_001`…，同上） | 同上 |

SOP 只有一份，在 main：`docs/SOP.md`、`docs/Diagnosis-Tree.md`、`docs/Workflow-and-Validation.md` 與 `body3d/`。執行者不改 SOP 本身；要改就發 issue。

## 迴圈

```
            ┌───────────────────────── Claude ─────────────────────────┐
            │  SOP + 程式（main）  ←── PR、review、合併 ←── 修好 issue    │
            └──────────┬───────────────────────────────────▲──────────┘
                git pull main（SOP 版本）              GitHub issue（升級）
                       │                                   │
        ┌──────────────▼──────────────┐     ┌──────────────┴──────────────┐
        │ ChatGPT：chatgpt/avatar_001  │     │ Gemini：gemini/avatar_001    │
        │ 生圖 → run_all → 診斷 SOP     │     │ 生圖 → run_all → 診斷 SOP     │
        │ 修圖／改程式 → 重跑           │     │ 修圖／改程式 → 重跑           │
        │ 處理不掉 → 發 issue、等更新   │     │ 處理不掉 → 發 issue、等更新   │
        └─────────────────────────────┘     └─────────────────────────────┘
```

### 執行者（ChatGPT／Gemini）每一輪

**實際做法很簡單：照 [執行者 runbook](Agent-Runbook.md) 反覆跑 `python body3d/next_step.py --workspace ~/avatar/<chatgpt|gemini>/<avatar_NNN>`，照它說的做，只有 DONE 或 WAITING 才停。**（操作摘要見上面「三個角色怎麼操作」） 下面是 next_step 背後的規則。AGENTS.md（ChatGPT／Codex）、GEMINI.md（Gemini）會自動讀到這些指示。

1. `git pull` main（next_step 每次都會自動檢查，main 比本機新就給 UPDATE：pull、再跑一次 next_step），記下 SOP 版本：`python body3d/run_all.py --version` 與 `python body3d/check_turnaround.py --version`，以及 commit。
2. 照 [SOP](SOP.md) 做：生圖 → `run_all.py`（新的輸出資料夾）→ 看客戶頁。
3. 有 FAIL：照[診斷 SOP](Diagnosis-Tree.md#診斷-sop)：照順序（前面階段先修、信心高先修），照片就照 AI 修圖單重畫，程式就照 AI 改 code 單改程式、**開 PR 給 Claude review**（不直接推 main）。
4. 符合下面「什麼時候發 issue」任何一條 → 發 issue，這個 avatar 停在原地等 Claude；可以同時做別的、但不要繞過問題。
5. Claude 合併修正後：`git pull` main，**用新的輸出資料夾從頭重跑**，在 issue 回報結果（解決就請 Claude 關閉；沒解決就留言附新的診斷）。
6. 四包都是好的 → 照 [SOP 的交付條件](SOP.md#可以交付了嗎)交付。

### 什麼時候發 issue（任何一條就發）

| 情況 | 例子 |
| --- | --- |
| **診斷信心低或沒有對應的規則** | 診斷葉子信心「低」、「未分類」，或 FAIL 項目沒有診斷 |
| **同一個 FAIL 重畫 2 輪沒進步** | 照 AI 修圖單重畫兩次，同一項仍未通過，而且這兩次都沒有進步（可能是檢查或門檻的問題，不是圖的問題）。**進步**＝FAIL 的項目比上一輪少，或跑到更後面的關卡；有進步就繼續自己修。同一項連續 5 輪都還在，不管有沒有進步，也發。只算同一版程式跑的輪次（`git pull` 換了程式就重新算）。next_step 自動判斷 |
| **SOP 或檢查有缺口** | 後面的關卡 FAIL，但原因所在的階段沒有檢查抓得到（例：R17 前三關都過、第 4 關才 FAIL），而執行者無法確定該補什麼檢查。診斷樹把它追到指名的照片時（第 4 關：不一致最大的全身照）先照修圖單重畫，不發 |
| **程式出錯、或 AI 改 code 單做不完** | `run_all.py` 停在程式錯誤；改 code 單要改的地方超出單上的檔案；改完兩組完美照片不再全部通過 |
| **SOP 互相矛盾或不清楚** | 兩條規則衝突、步驟看不懂、文件和程式行為不一致 |
| **懷疑門檻錯** | 照片明顯沒問題卻 FAIL，或明顯有問題卻 PASS |

不用發的：照片的問題、診斷信心高、AI 修圖單照做就會好的 → 自己修。

### 怎麼發 issue

```sh
python body3d/escalate.py OUTPUT_DIR --agent ChatGPT --avatar avatar_001 --tried "重畫 el30_090 兩次，10i 仍 FAIL" > issue.md
gh issue create --title "[SOP] ChatGPT／avatar_001：<一句話>" --body-file issue.md
```

一般不用自己下這兩行：next_step 走到 ESCALATE 時已經寫好 `issue.md`、`issue_title.txt`。沒有 `gh` 就用 GitHub 連結器開 issue。

`escalate.py` 從輸出資料夾整理出 issue 內文：SOP／程式版本與 commit、驗收總表、診斷（照修的順序）、每一項未通過的原文、停在哪一步、`run_all.log` 最後幾十行。執行者再補：做過什麼、幾輪、自己的判斷。結果包（含 AI 修圖單／改 code 單）放在雲端硬碟，issue 寫路徑，不要把照片附在公開的 issue。

也可以直接用 GitHub 網頁的「SOP 升級（執行者 → Claude）」issue 表單。

### Claude 處理 issue

1. **重現**：用 Google Drive 連結器拿 issue 寫的雲端硬碟路徑裡的結果包（`stage1_photos(_FAIL).zip` 有 33 張照片），用同一版 SOP 從頭跑。
2. **照診斷 SOP 找原因所在的階段**（[診斷 SOP](Diagnosis-Tree.md#診斷-sop)）：照片、檢查缺口、程式、還是 SOP 本身。必要時做對照實驗（同一組照片只差一個變數）。
3. **改**：
   - 檢查缺口 → 在那個階段補檢查：這組照片會 FAIL、兩組完美照片仍 0 FAIL／0 WARN。
   - 程式 → 在那個階段修，兩組完美照片四道關卡仍全部通過。
   - 診斷樹 → 補分支或規則，讓下次信心高。
   - SOP → 改文件，消除矛盾、補缺的步驟。
4. **交付**：開 PR，內文寫 `Fixes #<issue>`、原因、補的檢查（前後數字）、驗收結果；更新 CHANGELOG。合併到 main。
5. **合併後執行者自動更新**：兩個執行者下一次跑 next_step 時都會拿到 UPDATE（`git pull`、再跑一次 next_step；重建或檢查的程式有變才需要重跑），不用另外通知。等 issue 的那一位也一樣：**issue 不用先關閉**，pull 之後程式變了，next_step 就不再等（登記等待時記下程式指紋；R33 因為 issue 開著而一直停在 WAITING），照新的 SOP 繼續，跑完把結果回覆到 issue（next_step.md 的「回報」）。issue 等執行者回報解決才關閉。
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
- **雲端硬碟** `avatar/<chatgpt|gemini>/<avatar_NNN>/vNNN/`：每個版本做完，執行者用 Google Drive 連結器放上四個階段的結果包、無光照 GLB（檔名帶版本：`<name>_vNNN_rigged.glb`，可以直接下載）、`gates.json`、`next_step.md`（`next_step.md` 的「雲端硬碟」一段會列出來）。這是三個 agent 之間交換照片與結果的地方，所有人都用連結器讀寫。GitHub repo 是公開的：照片不放 GitHub、不附在 issue。


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

issue 內文寫那個版本在雲端硬碟的路徑；Claude 用 Google Drive 連結器拿照片與結果包重現。

## 兩個 avatar 共用一份 SOP

- 一個 avatar 引起的修正會影響另一個：Claude 合併後在兩邊的 open issue 或 PR 留言，另一個執行者 pull 後也要從頭重跑一次。
- 門檻只依兩組完美照片校準，不依某一個 avatar 調；某個 avatar 的照片一直過不了，修的是照片（或補檢查），不是放寬門檻。
- 程式、SOP、issue、PR 在 GitHub `WangChengYeh/Avatar`；照片與結果在雲端硬碟 `avatar/`。
