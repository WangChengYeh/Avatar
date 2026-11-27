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
| Gemini avatar_001：v010 四關 0 FAIL、9.8%，模型仍不對；v013 第 1 關 FAIL（head_090／head_270 鏡像 0.891） | 照片要修的已在 #84 通知：head_090 與 head_270 一起重畫（一張以另一張的鏡像為準）、全身圖統一站姿、側面照手臂正對鏡頭。等 Gemini 重畫後回報。分析見 CHANGELOG「Gemini v010 品質分析」 | issue #84 |
| **Gemini v012 第 3 關 FAIL：擺姿勢網格連續性**（6 條三角形邊超過 8 cm 和原長 4 倍，body3d 2.22.0，外殼流程） | 照片過了第 1、2 關，是程式的問題：從雲端硬碟拿 v012 的照片重現，查骨架權重（`rig.py`、`joints.py`）與 `verify_glb.py` 的門檻 | `avatar/gemini/avatar_001/v012/`、`verify_glb.py` |
| ChatGPT avatar_001：v060 停在第 2 關（頭部特寫相鄰一致），用 `--template makehuman` | 自己照修圖單重畫中（#95：有進步就不發 issue）。R54 的照片在新門檻下第 1 關 FAIL 12 項；135／315 的特寫鏡像 0.893（1.48.0 起會 FAIL）。等回報 | issue #79 |
| 側面全身照的手臂沒有正對鏡頭：手掌烘焙到肩膀上 | 沒有檢查（Gemini v010）。補照片檢查：90°／270° 全身圖的手臂只該剩手掌端面 | `check_turnaround.py`、`bake33.py` |
| 雙腳站姿每張不同卻通過第 1 關 | v010 腳的體積 73% 至少被一張照片判成不是身體（完美照片 22–50%）；第 7b／7c 項沒抓到。補檢查 | `check_turnaround.py` 第 7b 項 |
| 照片檢查未通過（`--force`）時頭部相機逐張對位會對歪 | v010：特寫尺度 3800–4000（規格 4199），45° 特寫對歪，第 2 關多 5 個 FAIL。只影響診斷用的重跑 | `headreg33.py`、`camera.py` |
| `--wait` 還沒在執行者的環境實跑過 | 第一次用到時看 `wait_heartbeat.json` 與 `avatar_state.json` 的 `wait`：有沒有被砍、學到的時限 | `next_step.py` |
| #65 還開著（R31 系列的 MakeHuman 臉部接縫） | MakeHuman 已在 #69 修好；本機 MPFB 已重裝、R52 MakeHuman 跑通。等 ChatGPT 在照片過第 1 關後用 `--template makehuman` 跑完四關回報，再關閉。#79 處理同一個 avatar 的照片問題 | issue #65 |
| synth 完美照片用 MakeHuman，第 2 關右臉頰 1 個 WARN | P90 22.4／20（外殼流程 18.0）；查肩頸在 315° 的遮擋 | `check_turnaround.py` 頭部重疊、`mh_fit.py` |
| 中間角度與擺姿勢後的貼圖沒有直接的自動檢查 | 目前靠臉頰亮度、五官投影間接抓（R31 的臉部接縫就是在 App 裡才看到） | 第 3／4 關 |
| 肩帶附近貼圖色塊、兩腿內側暗線 | 兩種模板都有，照片與烘焙的問題 | `bake33.py` |
| 雲端硬碟上兩份不再使用的 `file_list.md` | 連結器對這些檔沒有編輯權限，由人刪掉 `avatar/chatgpt/file_list.md`、`avatar/gemini/file_list.md` | 雲端硬碟 |

## 怎麼拿到東西

- 照片與結果包：雲端硬碟 `avatar/<chatgpt|gemini>/<avatar_NNN>/vNNN/`，用 Google Drive 連結器讀（連結器在 session 開始時載入，剛設定好的要開新 session）。
- 問題與討論：GitHub issue（目前開著的是 #65、#79、#84）；用 label `agent:<名字>` 篩選誰做的。
- 跑流程：本機 Blender 要裝 MPFB 擴充才能跑 `--template makehuman`；Python 套件照 `requirements.txt`。
- 專案總覽（每個 avatar、每一版、四關 FAIL／WARN／PASS、最終結果圖）：`dashboard/` 的 Google Apps Script，部署在使用者的 Google 帳號，直接讀雲端硬碟（安裝步驟見 `dashboard/README.md`）。
