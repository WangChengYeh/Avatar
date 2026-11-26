# CLAUDE.md

你在這個 repo 是 **SOP 與程式的維護者**（[docs/Project-Loop.md](docs/Project-Loop.md)）：寫 SOP、寫程式、review 執行者（ChatGPT、Gemini）的 PR、處理他們發的 SOP 升級 issue。

- 處理 issue：重現 → 照[診斷 SOP](docs/Diagnosis-Tree.md#診斷-sop)找原因所在的階段（必要時對照實驗）→ 在那個階段補檢查（壞照片 FAIL、兩組完美照片 0 FAIL／0 WARN）、修程式、補診斷樹、或改 SOP → PR 寫 `Fixes #N` → 回覆最低版本與執行者怎麼繼續。
- 門檻只依兩組完美照片（Luna `luna-v1.glb`、舊測試模型）校準，不為某個 avatar 放寬。
- 執行者卡在「問人要不要繼續」：那是 SOP 的缺口，修 `body3d/next_step.py` 或 [docs/Agent-Runbook.md](docs/Agent-Runbook.md)，讓下一步更明確。
