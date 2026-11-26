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
| Gemini avatar_001 v003 是 DONE（可交付） | 照 SOP 做交付檢查：下載 v003 四包，逐項看 WARN（照片 87、烘焙前 9、最終 4），在 App 匯入 GLB 截圖站姿與抬手；通過就在 File-List 改成已交付。v003 是 main `a2d18b7` 跑的，之後的修改沒有動到檢查 | 雲端硬碟 `avatar/gemini/avatar_001/v003` |
| ChatGPT avatar_001 卡在 el30_315deg 斜角照手臂（#79） | 已在 #79 回覆原因（近鏡頭的手臂畫太高）與做法（照「手臂位置」參考圖重畫，#77）；#80 讓新程式重新計算輪數。等 ChatGPT 回報 v049 之後的手臂切割；照新參考圖兩輪仍 FAIL 再查 | issue #79、雲端硬碟 `avatar/chatgpt/avatar_001/` |
| #65 還開著（R31 系列的 MakeHuman 臉部接縫） | MakeHuman 已在 #69 修好；等 ChatGPT 在照片過第 1 關後用 `--template makehuman` 跑完四關回報，再關閉。#79 處理同一個 avatar 的照片問題 | issue #65 |
| synth 完美照片用 MakeHuman，第 2 關右臉頰 1 個 WARN | P90 22.4／20（外殼流程 18.0）；查肩頸在 315° 的遮擋 | `check_turnaround.py` 頭部重疊、`mh_fit.py` |
| 中間角度與擺姿勢後的貼圖沒有直接的自動檢查 | 目前靠臉頰亮度、五官投影間接抓（R31 的臉部接縫就是在 App 裡才看到） | 第 3／4 關 |
| `test_camera_benchmark_perspective` 在 main 上失敗 | 用故意壞掉的透視照片跑基準，現在被照片檢查擋下回傳非零；基準應該用 `--force` 或接受非零 | `tests/test_run_all.py`、`body3d/camera_benchmark.py` |
| 肩帶附近貼圖色塊、兩腿內側暗線 | 兩種模板都有，照片與烘焙的問題 | `bake33.py` |
| GitHub 上已合併的舊分支（56 個以上，含這幾天的 claude/… 分支） | 人同意後刪掉（7 個沒合併的先逐一確認是否已被其他 PR 取代） | `git branch -r --merged origin/main` |
| 雲端硬碟上兩份不再使用的 `file_list.md` | 連結器對這些檔沒有編輯權限，由人刪掉 `avatar/chatgpt/file_list.md`、`avatar/gemini/file_list.md` | 雲端硬碟 |

## 怎麼拿到東西

- 照片與結果包：雲端硬碟 `avatar/<chatgpt|gemini>/<avatar_NNN>/vNNN/`，用 Google Drive 連結器讀（連結器在 session 開始時載入，剛設定好的要開新 session）。
- 問題與討論：GitHub issue（目前開著的是 #65、#79）；用 label `agent:<名字>` 篩選誰做的。
- 跑流程：本機 Blender 要裝 MPFB 擴充才能跑 `--template makehuman`；Python 套件照 `requirements.txt`。
