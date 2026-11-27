<!-- docs/Project-Loop.md：執行者的程式 PR 由 Claude review；Claude 自己的 PR 也照這份寫 -->
<!-- 誰做的（docs/Project-Loop.md#誰做的）：標題開頭 [ChatGPT]／[Gemini]／[Claude]，加 label agent:<名字>，分支 <名字>/… -->

> 由 **<!-- ChatGPT／Gemini／Claude -->** 開

## 為什麼

- 來源：<!-- Fixes #issue，或 AI 改 code 單（avatar、輸出資料夾） -->
- 診斷葉子：<!-- 原因所在的階段、原因、信心 -->

## 補的檢查（在原因所在的階段）

| 照片組 | 改前 | 改後 |
| --- | --- | --- |
| 出問題的照片 | | FAIL |
| Luna 完美照片 | | 0 FAIL／0 WARN |
| 舊完美照片 | | 0 FAIL／0 WARN |

## 改了什麼

<!-- 檔案、做法；在原因所在的階段修，沒有在後面的步驟補、沒有手動修中間檔 -->

## 驗收

- [ ] 出問題的照片：補的檢查由 FAIL 變 PASS（或改出下一輪的 AI 修圖單）
- [ ] 兩組完美照片從頭跑 `run_all.py`：四道關卡全部 0 FAIL／0 WARN、可交付
- [ ] 相關測試通過；新檢查有測試（壞的情況 FAIL、完美照片 PASS）
- [ ] CHANGELOG、docs/Diagnosis-Tree.md（新分支或規則）已更新
- [ ] 技術報告（docs/papers/，Claude 的持續任務）：<!-- 更新了第 N 篇／新增一篇／這次不需要，因為… -->
- [ ] 另一個 avatar：<!-- 共用的檢查或門檻改了嗎？會不會多出 FAIL？ -->
