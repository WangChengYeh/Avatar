# AGENTS.md（給 ChatGPT／Codex 等 agent）

這個 repo 的工作照 SOP 做，你是**執行者**，負責一個 avatar：照 [docs/Agent-Runbook.md](docs/Agent-Runbook.md) 做。

**最重要的一條：每做完一步就跑**

```sh
python body3d/next_step.py --workspace WS --avatar AVATAR --agent ChatGPT
```

**照它印出的指令做，做完再跑一次，在同一個回覆／同一輪裡一直做下去。只有狀態是 DONE 或 WAITING 才可以停下來；不要停下來問人要不要繼續。每次停下來時，最後貼出 `WS/next_step.md`。**

- 不用自己記得去 GitHub 抓新的 SOP：next_step 每次都會先 `git fetch`，main 有新的就給 UPDATE（`git pull`、重跑）。
- 角色與升級規則：[docs/Project-Loop.md](docs/Project-Loop.md)。SOP 由 Claude 維護；你不改 SOP、門檻或檢查來讓自己過關。
- 程式改動開 PR 給 Claude review（`.github/pull_request_template.md`），不直接推 main。
- 處理不掉的：`body3d/escalate.py` 整理內文，發 GitHub issue 給 Claude（next_step 會告訴你什麼時候）。
