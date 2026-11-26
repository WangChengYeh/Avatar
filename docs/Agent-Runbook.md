# 執行者 runbook（ChatGPT／Gemini）

[專案迴圈](Project-Loop.md) · [SOP](SOP.md) · [診斷 SOP](Diagnosis-Tree.md#診斷-sop)

你負責一個 avatar，從開始做到交付。**不要停下來問人要不要繼續**：人只準備輸入與 token，其他都是你的工作。

## 唯一的迴圈

```sh
python body3d/next_step.py --workspace WS --avatar AVATAR --agent AGENT
```

1. 跑上面這行（WS 是這個 avatar 的工作區資料夾，第一次給一個新的空資料夾）。
2. 它印出**一個狀態**和要照做的指令（也寫在 `WS/next_step.md`）。
3. **照指令做完，回到第 1 步。**

| 狀態 | 你做什麼 | 可以停嗎 |
| --- | --- | --- |
| UPDATE | GitHub 上的 main 有新的 SOP／程式：`git pull`，用目前的照片從頭重跑（新的輸出資料夾） | 不行 |
| START | 照生圖規格生 33 張照片放進 `WS/photos_v1`，跑 `run_all.py` | 不行，做完回第 1 步 |
| RUN | 跑它給的 `run_all.py`（可能先 `git pull`） | 不行 |
| RETOUCH | 把 AI 修圖單交給生圖（你自己的生圖工具），重畫指定的照片，複製整組到 `WS/photos_v(N+1)` 再覆蓋重畫的，跑 `run_all.py` | 不行 |
| CODE | 照 AI 改 code 單改程式、開 PR 給 Claude，用 `--waiting-pr N` 登記 | 不行，登記後回第 1 步 |
| ESCALATE | 用它寫好的內文 `gh issue create`，附上 `_FAIL.zip`，用 `--waiting-issue N` 登記 | 不行，登記後回第 1 步 |
| WAITING | 等 Claude 處理 issue／PR；之後再跑第 1 步，解決了它會叫你 pull、重跑 | **可以** |
| DONE | 做交付檢查（看 WARN 記在 Issue、Yoga2 匯入截圖），交付 | **可以** |

## 規則

- **不用自己記得去 GitHub 抓新的**：next_step 每次都先 `git fetch`，main 比本機新就給 UPDATE（pull、重跑）。Claude 合併的修正（不管是不是為你的 avatar），你下一次跑 next_step 就會拿到。抓不到 GitHub（沒網路）時它照本機的版本繼續，並在 `avatar_state.json` 的 `update_check` 寫原因。

- 只有 **DONE** 和 **WAITING** 可以停下來。其他狀態一律照做、再跑 next_step。
- 不要問人「要繼續嗎」「要不要修」「要不要發 issue」：next_step 已經決定了。要決定的事情（例如同一個 FAIL 修了 2 輪還在要不要升級）它都照[專案迴圈](Project-Loop.md#什麼時候發-issue任何一條就發)的規則判斷好了。
- 不要改 SOP、門檻、檢查來讓自己過關；不要手動修中間檔（`cams33.json`、網格…）。覺得 SOP 或門檻錯，next_step 會走到 ESCALATE，或你自己發 issue。
- 每一輪用新的照片資料夾（`photos_vN`）與新的輸出資料夾（`out_vN`），不覆蓋舊的：next_step 靠它們判斷「同一個 FAIL 有沒有一直出現」。
- 做不到 next_step 要求的事（例如沒有生圖工具、沒有 `gh` 權限）：這就是 ESCALATE 的理由，發 issue 說明，不要停在原地等人。
- 每次回報給人時，附上 `WS/next_step.md` 的內容：人只需要看狀態。

## 啟動提示詞（第一次交給 agent 時貼上）

ChatGPT／Gemini 用**聊天介面**時，每回覆一次就結束一輪，不會自動讀 `AGENTS.md`／`GEMINI.md`。開始時把下面整段貼給它一次（換掉 AVATAR、AGENT、WS）：

```text
你是這個 repo（https://github.com/WangChengYeh/Avatar）的執行者，負責開發 AVATAR，照 docs/Agent-Runbook.md 做。
規則：
1. 每做完一步就跑：python body3d/next_step.py --workspace WS --avatar AVATAR --agent AGENT（它每次都會先檢查 GitHub 上有沒有新的 SOP，有就叫你 git pull、重跑）
2. 照它印出的指令做，做完再跑一次。在同一個回覆裡一直做下去，不要做完一步就結束回覆。
3. 只有狀態是 DONE 或 WAITING 才可以結束回覆。其他狀態（START、RUN、RETOUCH、CODE、ESCALATE）都不可以停，也不要問我要不要繼續。
4. 每次結束回覆時，最後貼出 WS/next_step.md 的內容。
5. 如果因為長度或工具限制必須中斷，最後一行寫「未完成：下一步是 <next_step.md 的狀態>」。我回「繼續」時，你直接從 next_step 接著做，不要重新規劃、不要問問題。
6. 做不到 next_step 要求的事（例如沒有生圖工具、沒有 gh 權限），就照 ESCALATE 發 issue 說明，不要停下來等我。
```

用 **agent 模式**（Codex CLI／Codex 雲端、Gemini CLI、ChatGPT agent）時，它們會自動讀 `AGENTS.md`／`GEMINI.md`，通常不需要貼；不確定就照樣貼一次。

人要做的只有兩件事：一開始貼這段提示詞；agent 停在 WAITING 或「未完成」時回一句「繼續」。
