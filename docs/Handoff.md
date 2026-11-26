# 交接清單（Handoff）

[返回 README](../README.md) · [重要檔案清單](File-List.md) · [專案迴圈](Project-Loop.md)

**每個新的 Claude session 開工前先讀這一頁。** 這裡只列還沒做完的事；目前各 avatar 的狀態見[重要檔案清單](File-List.md#4-目前各-avatar-的狀態)。

規則：
- 做完一項就從這裡刪掉；開始做但沒做完，就在「下一步」寫到哪裡了。
- 新發現、這次沒做的事加進來，寫清楚下一步和在哪裡（檔案、雲端硬碟路徑、issue／PR 編號）。
- 改這一頁和改程式一樣走 PR；每次 session 結束前更新一次「最後更新」。

最後更新：2026-11-27

| 項目 | 下一步 | 在哪裡 |
| --- | --- | --- |
| Gemini avatar_001 v002 四關看起來都過了 | 下載 `gates.json` 與四包，確認 0 FAIL、照 SOP 做交付檢查（WARN 逐項看、在 App 匯入 GLB 截圖站姿與抬手）；可交付就在 File-List 改狀態 | 雲端硬碟 `avatar/gemini/avatar_001/v002` |
| ChatGPT avatar_001 v047 還在第 1 關 | 看 `Avatar-R47_stage1_photos_FAIL.zip` 的 manifest：是不是已經改成指名手臂、手臂有沒有變好；沒進步就在 #65 回覆 | 雲端硬碟 `avatar/chatgpt/avatar_001/v047`、issue #65 |
| #65 還開著 | 等 ChatGPT 回報 R31 系列（現在是 R47）重畫、`--template makehuman` 重跑後的第 4 關數字 | issue #65 |
| synth 完美照片用 MakeHuman，第 2 關右臉頰 1 個 WARN | P90 22.4／20（外殼流程 18.0）；查肩頸在 315° 的遮擋 | `check_turnaround.py` 頭部重疊、`mh_fit.py` |
| 中間角度與擺姿勢後的貼圖沒有直接的自動檢查 | 目前靠臉頰亮度、五官投影間接抓（R31 的臉部接縫就是在 App 裡才看到） | 第 3／4 關 |
| `test_camera_benchmark_perspective` 在 main 上失敗 | 用故意壞掉的透視照片跑基準，現在被照片檢查擋下回傳非零；基準應該用 `--force` 或接受非零 | `tests/test_run_all.py`、`body3d/camera_benchmark.py` |
| 肩帶附近貼圖色塊、兩腿內側暗線 | 兩種模板都有，照片與烘焙的問題 | `bake33.py` |
| GitHub 上 56 個已合併的舊分支 | 人同意後刪掉（7 個沒合併的先逐一確認是否已被其他 PR 取代） | `git branch -r --merged origin/main` |

## 怎麼拿到東西

- 照片與結果包：雲端硬碟 `avatar/<chatgpt|gemini>/<avatar_NNN>/vNNN/`，用 Google Drive 連結器讀（連結器在 session 開始時載入，剛設定好的要開新 session）。
- 問題與討論：GitHub issue（目前開著的是 #65）。
- 跑流程：本機 Blender 要裝 MPFB 擴充才能跑 `--template makehuman`；Python 套件照 `requirements.txt`。
