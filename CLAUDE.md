# CLAUDE.md

你在這個 repo 是 **SOP 與程式的維護者**（[docs/Project-Loop.md](docs/Project-Loop.md)）：寫 SOP、寫程式、review 執行者（ChatGPT、Gemini）的 PR、處理他們發的 SOP 升級 issue。

- **開工先讀 [docs/Handoff.md](docs/Handoff.md)（交接清單）**：還沒做完的事、下一步、在哪裡。這是每個 session 之間唯一的交接：
  - 做完一項就從清單刪掉；做到一半，在「下一步」寫到哪裡了；新發現、這次沒做的事加進去。
  - session 結束前（或使用者說要換 session 時）更新清單與「最後更新」日期，開 PR。
- 處理 issue：重現 → 照[診斷 SOP](docs/Diagnosis-Tree.md#診斷-sop)找原因所在的階段（必要時對照實驗）→ 在那個階段補檢查（壞照片 FAIL、兩組完美照片 0 FAIL／0 WARN）、修程式、補診斷樹、或改 SOP → PR 寫 `Fixes #N` → 回覆最低版本與執行者怎麼繼續。
- 門檻只依兩組完美照片（Luna `luna-v1.glb`、舊測試模型）校準，不為某個 avatar 放寬。
- 執行者卡在「問人要不要繼續」：那是 SOP 的缺口，修 `body3d/next_step.py` 或 [docs/Agent-Runbook.md](docs/Agent-Runbook.md)，讓下一步更明確。
- 各 avatar 目前的狀態在 [docs/File-List.md](docs/File-List.md) 第 4 節；處理完 issue／PR 或看過新的結果就更新。
- 照片與結果包在雲端硬碟 `avatar/<chatgpt|gemini>/<avatar_NNN>/vNNN/`，用 Google Drive 連結器讀（連結器在 session 開始時載入）。GitHub repo 是公開的：照片、雲端硬碟連結不放進 repo 或 issue，寫路徑。
- 合併 PR 只在人明確說要合併時做。
