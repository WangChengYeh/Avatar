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
| Gemini avatar_001 v003／v006：四關 0 FAIL，但**不能交付** | 頭部側面糊掉、最終剪影 9.9%（接近 FAIL 線）。PR #92 收緊頭部特寫門檻（v003 的 10–17 現在會 FAIL）；已在 #84 請 pull 後加 `--force` 重跑、照修圖單重畫。等回報 | issue #84 |
| ChatGPT avatar_001：R54 卡第 4 關（15.4%）、側面頭部仍糊 | PR #92：最終剪影 FAIL 也出修圖單（R54 乾跑：重畫 el30_135、low20_135、low20_045、el30_315、el30_225、el30_045），頭部特寫 > 8 判 FAIL、整組 8 張一次重畫。已在 #79 請 pull 後加 `--force` 重跑。等回報 | issue #79、PR #92 |
| 照片檢查（第 1 關）沒抓到 R54 斜角照和水平環對不上 | R54 第 1 關 0 FAIL，最終剪影斜角 21–27%。PR #92 讓第 4 關出修圖單繞過去，但第 1 關的缺口還在：找出第 10 系列（輪廓上限、斜角照手臂）為什麼放過這些照片，補檢查 | `check_turnaround.py` 第 10 項、`r54` 的 fit_report |
| #65 還開著（R31 系列的 MakeHuman 臉部接縫） | MakeHuman 已在 #69 修好；本機 MPFB 已重裝、R52 MakeHuman 跑通。等 ChatGPT 在照片過第 1 關後用 `--template makehuman` 跑完四關回報，再關閉。#79 處理同一個 avatar 的照片問題 | issue #65 |
| synth 完美照片用 MakeHuman，第 2 關右臉頰 1 個 WARN | P90 22.4／20（外殼流程 18.0）；查肩頸在 315° 的遮擋 | `check_turnaround.py` 頭部重疊、`mh_fit.py` |
| 中間角度與擺姿勢後的貼圖沒有直接的自動檢查 | 目前靠臉頰亮度、五官投影間接抓（R31 的臉部接縫就是在 App 裡才看到） | 第 3／4 關 |
| 肩帶附近貼圖色塊、兩腿內側暗線 | 兩種模板都有，照片與烘焙的問題 | `bake33.py` |
| 雲端硬碟上兩份不再使用的 `file_list.md` | 連結器對這些檔沒有編輯權限，由人刪掉 `avatar/chatgpt/file_list.md`、`avatar/gemini/file_list.md` | 雲端硬碟 |

## 怎麼拿到東西

- 照片與結果包：雲端硬碟 `avatar/<chatgpt|gemini>/<avatar_NNN>/vNNN/`，用 Google Drive 連結器讀（連結器在 session 開始時載入，剛設定好的要開新 session）。
- 問題與討論：GitHub issue（目前開著的是 #65、#79、#84）；用 label `agent:<名字>` 篩選誰做的。
- 跑流程：本機 Blender 要裝 MPFB 擴充才能跑 `--template makehuman`；Python 套件照 `requirements.txt`。
