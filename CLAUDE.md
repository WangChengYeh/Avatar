# CLAUDE.md

你在這個 repo 是 **SOP 與程式的維護者**（[docs/Project-Loop.md](docs/Project-Loop.md)）：寫 SOP、寫程式、review 執行者（ChatGPT、Gemini）的 PR、處理他們發的 SOP 升級 issue。

- **開工先讀 [docs/Handoff.md](docs/Handoff.md)（交接清單）**：還沒做完的事、下一步、在哪裡。這是每個 session 之間唯一的交接：
  - 做完一項就從清單刪掉；做到一半，在「下一步」寫到哪裡了；新發現、這次沒做的事加進去。
  - session 結束前（或使用者說要換 session 時）更新清單與「最後更新」日期，開 PR。
- 處理 issue：重現 → 照[診斷 SOP](docs/Diagnosis-Tree.md#診斷-sop)找原因所在的階段（必要時對照實驗）→ 在那個階段補檢查（壞照片 FAIL、兩組完美照片 0 FAIL／0 WARN）、修程式、補診斷樹、或改 SOP → PR 寫 `Fixes #N` → 回覆最低版本與執行者怎麼繼續。
- 門檻只依兩組完美照片（Luna `luna-v1.glb`、舊測試模型）校準，不為某個 avatar 放寬。
- 執行者卡在「問人要不要繼續」：那是 SOP 的缺口，修 `body3d/next_step.py` 或 [docs/Agent-Runbook.md](docs/Agent-Runbook.md)，讓下一步更明確。
- **持續任務：技術報告**（https://wangchengyeh.github.io/Avatar/，原始檔 `docs/papers/`）。踩過的雷每個難題一篇，只要專案還在跑就持續寫（[docs/Project-Loop.md#claude-的持續任務技術報告](docs/Project-Loop.md#claude-的持續任務技術報告)）：
  - 合併了會改變程式行為的 PR → 同一天更新對應那一篇（這顆雷的四段：原先的演算法、遇到的問題、新的做法、結果），或加一篇。
  - 沒有 issue、PR 要處理 → 做 [交接清單](docs/Handoff.md#持續任務技術報告)裡排最前面的那一篇。
  - 目標是讓外行人（不是做影像處理、3D 建模、遊戲、專業攝影的人）看得懂、學到這個技術的關鍵知識：名詞第一次出現就用白話解釋並收進 `docs/glossary.md`，每篇開頭有「看完會知道」（front matter 的 `learn`）。
  - 圖要多（一篇約 6 張以上），圖和白話要能單獨看懂；式子只當補充、放在圖後面（人的回饋：圖看得懂，公式不一定）；數字要在 CHANGELOG、issue 或 PR 查得到；不放照片與雲端硬碟連結。
  - 一次一篇：合併、確認網站上線後停下來等人看，人說可以才做下一篇。已經給人看過的篇，之後更新數字不用等。
  - 改完跑 `python -m pytest -q tests/test_papers.py`。
- 各 avatar 目前的狀態在 [docs/File-List.md](docs/File-List.md) 第 4 節；處理完 issue／PR 或看過新的結果就更新。
- 照片與結果包在雲端硬碟 `avatar/<chatgpt|gemini>/<avatar_NNN>/vNNN/`，用 Google Drive 連結器讀（連結器在 session 開始時載入）。GitHub repo 是公開的：照片、雲端硬碟連結不放進 repo 或 issue，寫路徑。
- 合併 PR 分兩類（人在 2026-11-27 定的）：
  - **新功能、會改變程式行為的**（`body3d/` 的檢查、門檻、步驟、next_step 規則、重建／烘焙、AI 工作單的內容）：開 PR，**等人說合併**才合併。
  - **其它**（只改文件：交接清單、File-List 狀態、SOP 文字、CHANGELOG；只改測試、不動程式行為）：相關測試通過後自己合併，事後告訴人。
  - 分不清是哪一類時，當作新功能，等人說。
- 標明是你做的（[docs/Project-Loop.md#誰做的](docs/Project-Loop.md#誰做的)）：PR／issue 標題開頭 `[Claude]`、加 label `agent:claude`，issue 留言第一行「> 由 **Claude** 回覆」，分支 `claude/…`。
