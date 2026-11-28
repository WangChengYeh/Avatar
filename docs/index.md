---
layout: default
title: 目錄
summary: 從 33 張 AI 生成的照片重建可動的 3D 人物：每個難題一篇，附理論與量測。
---

# Avatar 技術報告

Avatar 把一個虛擬人物的 33 張 AI 生成照片，重建成可以擺姿勢的 3D 模型（無光照 GLB）。照片由 AI 畫，重建由程式做，三個 AI（Claude、ChatGPT、Gemini）輪流修到四道驗收關卡都通過。

做的過程中踩過的雷，每個難題整理成一篇（不限篇數，有新的難題就加）。每一顆雷都寫四件事：**原先的演算法**、**遇到的問題**、**新的做法**、**結果**，附理論與量到的數字。

標示「舊格式」的幾篇是較早的寫法（摘要、問題、理論、方法、數據），會一篇一篇改寫。

<ul class="toc">
{%- assign papers = site.pages | where: "layout", "paper" | sort: "number" -%}
{%- for p in papers %}
<li>
  <span class="num">{{ p.number }}</span>
  <div>
    <h3><a href="{{ p.url | relative_url }}">{{ p.title }}</a><span class="status status-{{ p.state }}">{{ site.state_names[p.state] }}</span>{% unless p.revised %}<span class="status status-draft">舊格式，待改寫</span>{% endunless %}</h3>
    <p>{{ p.summary }}</p>
  </div>
</li>
{%- endfor %}
</ul>

不熟的名詞（剪影、外殼、烘焙、骨架…）可以查[名詞小辭典]({{ '/glossary.html' | relative_url }})。這些報告是寫給沒學過影像處理、3D 建模、遊戲製作或攝影的人看的：目標是讀完能懂這個技術的關鍵道理。

## 共同的設定

**輸入。** 33 張 2048 × 2048 的圖：水平、俯角 30°、仰角 20° 三圈全身照各 8 張（每 45° 一張），頭部特寫一圈 8 張，正上方 1 張。規格是「人物擺 T-pose 不動，一台正交相機繞著拍」：全身圖畫面寬 1.95 m、對準離地半個身高的點；特寫放大 4 倍。

**流程。** 18 步：照片檢查 → 相機 → 外殼雕刻 → 手臂、腿、軀幹 → 網格 → 頭部對位與修整 → 臉部立體 → UV → 烘焙 → 匯出 → 骨架 → 驗證 → 與原圖比對。

**四道關卡。** 每一關印出 FAIL／WARN／PASS 的項數，有 FAIL 就停。

| 關卡 | 檢查什麼 | 程式 |
| --- | --- | --- |
| 1 照片檢查 | 33 張圖是不是同一個人、同一台相機 | `check_turnaround.py` |
| 2 烘焙前檢查 | 相機對位後，頭部特寫在模型表面上是否一致 | `check_turnaround.py --head-overlap-work` |
| 3 GLB 驗證 | 格式、骨架、權重、擺姿勢後的網格、頭部貼圖暗條 | `verify_glb.py` |
| 4 最終驗收 | 成品投影回 24 張全身原圖，剪影差多少；再和 8 張全身圖、8 張頭部特寫一塊一塊比（頭髮、皮膚、每件衣物） | `fit_report.py --accept`、`part_compare.py` |

**完美照片。** 把一個已知的 3D 人物用規格相機渲染成 33 張。相機、形狀都已知，所以它量出的誤差全是程式自己的。門檻都從它校準。用了兩個模型：Yoga2 的教練 `luna-v1.glb`（下文稱 luna）與較早的測試模型（下文稱 synth）。

**樣本代號。** 各篇引用的 AI 照片以執行者的版本編號稱呼：

| 代號 | 是什麼 |
| --- | --- |
| v190、v1210、v1220、v1240、polished | 專案早期的幾組 AI 照片 |
| R13、R17、R31、R33–R67 | ChatGPT 執行的 avatar_001 的各版（R = round；雲端硬碟上寫成 v013、v017…） |
| Gemini v003–v015 | Gemini 執行的 avatar_001 的各版 |

**數字的來源。** 每個數字都出自 repo 的[版本與量測紀錄]({{ site.repo }}/blob/main/CHANGELOG.md)、issue 或 PR，各篇文末列出。量測條件（哪一版程式、哪一組照片）寫在數字旁；跨版本的數字不一定能直接相比。

## 其他文件

- [流程與驗收]({{ site.repo }}/blob/main/docs/Workflow-and-Validation.md)：每一項檢查的門檻。
- [Loop engineering 的理論基礎]({{ site.repo }}/blob/main/docs/Loop-Engineering-Theory.md)：七條推論的原文。
- [標準作業流程（SOP）]({{ site.repo }}/blob/main/docs/SOP.md)與[專案迴圈]({{ site.repo }}/blob/main/docs/Project-Loop.md)：三個 AI 怎麼分工。
- [交接清單]({{ site.repo }}/blob/main/docs/Handoff.md)：目前還沒做完的事。
