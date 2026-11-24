# Avatar 正確性審查

2026-11-24 · 審閱對象為 WangChengYeh/Avatar 維護者 · body3d 2.3.0 · [main @ fff1f02](https://github.com/WangChengYeh/Avatar/commit/fff1f02b1fde4813afa5d9fe8560f837665c8a24)

## 結論

合成照片重建的全身外輪廓平均有 **7.68%** 的像素面積差異。現有驗證能檢查骨架、蒙皮和貼圖解碼，但實測頭部貼圖加上黑條仍可通過。Blender 指令在 UV 失敗時回報成功，預設 4K 烘焙也在本次環境兩度被系統終止。

## 實測結果

| 檢查項目 | 結果 | 證據範圍 |
| --- | --- | --- |
| 身體剪影 | 水平環 7.73%、俯角環 7.92%、仰角環 7.37%，24 視角平均 7.68%。鎖定已知角度後，平均降至 6.15% | 使用 repo 的測試 GLB 渲染 33 張正交圖，依各組相機投影回輸入照片。[量測程式](https://github.com/WangChengYeh/Avatar/blob/fff1f02b1fde4813afa5d9fe8560f837665c8a24/body3d/fit_report.py#L39-L56) |
| 腿部剪影 | 水平環平均差異 2.41%，平均多出 66.5 像素 | `extra` 有 3 像素容許範圍，低於端到端測試的 600 像素門檻。[測試條件](https://github.com/WangChengYeh/Avatar/blob/fff1f02b1fde4813afa5d9fe8560f837665c8a24/tests/test_run_all.py#L35-L47) |
| 俯角相機 | 8 張實際 30° 的正交影像估成 16°–26.5°，正面那張另被估成 5 m 透視相機。用真正的 4 m 透視圖時，8 張俯角圖估成 3.0–4.25 m | 使用渲染時的相機設定作為基準。[估計方法](https://github.com/WangChengYeh/Avatar/blob/fff1f02b1fde4813afa5d9fe8560f837665c8a24/body3d/steps/cams33.py#L90-L149) |
| 測試套件 | 預設 `pytest -q` 為 31 通過、1 跳過。單獨執行跳過的端到端測試時，4K 烘焙被終止，測試失敗 | Python 3.12.14、Blender 4.3.2、OpenCV 5.1.0 |

剪影差異的分母是照片剪影面積。這項比對使用重建時的照片，並跳過頭部特寫與正上方視角。下節另列使用提供照片的補測結果。[指標實作](https://github.com/WangChengYeh/Avatar/blob/fff1f02b1fde4813afa5d9fe8560f837665c8a24/body3d/fit_report.py#L44-L56)

## 提供的 33 視角照片補測

輸入為 `turnaround_full_33views_2048_v190_allpass.zip`。33 張 JPEG 均可解碼且為 2048 × 2048。重建沿用同一版程式與 T-pose 設定，環境和前述合成測試相同。

| 項目 | 補測結果 |
| --- | --- |
| 輸入照片檢查 | v1.11.0 回報 **13 FAIL、9 WARN、92 PASS**。第 10 項有 8 筆剪影失敗，第 10c 項有 5 筆寬度比失敗。一般重建會停在照片檢查，本次以 `--force` 繼續診斷。 |
| 身體剪影 | 水平環 **8.27%**、俯角環 **11.48%**、仰角環 **10.29%**。24 個身體視角平均 **10.01%**，最高是仰角 315° 的 **17.21%**。 |
| 腿部剪影 | 水平環平均差異 **4.07%**，平均超出照片 **94.8 px**，低於既有端到端測試的 600 px 門檻。 |
| 相機與照片一致性 | 第 10b 項的三環指尖透視指標均通過，介於 0.3%–0.5% 半臂展。第 10c 項仍發現頭寬／臀寬比在俯角 180° 為 **+14%**、仰角 315° 為 **−16%**。這兩類檢查量的是不同特徵，資料不足以把差異歸因於透視。 |
| 預設 4K 流程 | 完成網格、頭部對位與 UV 後，烘焙記錄 **14,562,078** 個貼圖像素並被 SIGKILL 終止（結束碼 `-9`）。 |
| 2K 診斷 | 同一份網格只在本機把貼圖設定改為 2048 × 2048，隨後沿用原程式匯出。兩個 GLB 均通過內建及 Khronos 驗證，0 FAIL、0 WARN。 |

重建相機把標為 30° 的俯角環估為 **14°–19.5°**，把標為 −20° 的仰角環估為 **−10.5° 至 −4°**。這是相對檔名角度的差異，這組照片的真實相機參數未知。優先複查仰角 315° 與俯角 180°，兩張同時有顯著的比例差異與較大的成品剪影差異。

從完成綁骨的無光照 GLB 渲染正面、左右 45° 與左右側面。相較輸入頭部特寫，兩側臉頰仍可見長條色帶，315° 斜視最明顯，呈灰暗色並自太陽穴延伸至下顎。這些色帶直接出現在重建成品中。頭部對位的 90° 側面估成 107.5°，可作為調查接縫時的線索。兩個 GLB 通過結構驗證，但此成品仍有可見貼圖接縫，五官比例也需另做特徵點比對。

## 重現指令

在 repo 根目錄執行。以下指令會產生與審查相同類型的輸入與報表。

```sh
blender -b --factory-startup --python tests/render_synth.py -- tests/data/body_rigged.glb /tmp/avatar-synth
python -m pytest -q
python -m pytest -q -m slow --photos=/tmp/avatar-synth
python body3d/fit_report.py /path/to/output/work --region body
```

## 發現與驗收條件

### 1. UV 腳本失敗時，命令列仍顯示完成

在全新的輸出目錄執行 `python body3d/run_all.py ./photos ./fresh-output --only uv`。缺少 `work/body33s.ply` 時，Blender 會在 log 留下 PLY 匯入例外，`run_all.py` 卻輸出「完成」並回傳 0。用同一份 Blender 腳本加上 `--python-exit-code 1` 重試，匯入錯誤會回傳 1。重用工作目錄時，這個漏判也可能讓後續步驟讀到前次產物。[子程序判斷](https://github.com/WangChengYeh/Avatar/blob/fff1f02b1fde4813afa5d9fe8560f837665c8a24/body3d/run_all.py#L49-L59) · [Blender 參數](https://github.com/WangChengYeh/Avatar/blob/fff1f02b1fde4813afa5d9fe8560f837665c8a24/body3d/run_all.py#L83-L86)

**驗收**　任一 Blender 腳本拋出例外時，CLI 應回傳非零結束碼，並指出失敗步驟。缺少網格的 UV 測試應能捕捉這次漏判。

### 2. 預設 4K 貼圖烘焙中途終止

以 repo 的合成正交影像執行 `pytest -q -m slow --photos=<合成照片資料夾>`。前 10 步完成，烘焙記錄約 **1,647 萬個貼圖像素**後遭終止，子程序結束碼為 `-9`（SIGKILL）。本次環境約有 9.7 GiB RAM，無 swap。程式會同時建立多個與貼圖像素數量成正比的陣列。將 OpenCV 限為 2 個執行緒後獨立重試 4K 烘焙，仍被 SIGKILL 終止，峰值常駐記憶體約 6.4 GiB。資料符合記憶體壓力的跡象，系統終止原因仍待確認。[端到端測試](https://github.com/WangChengYeh/Avatar/blob/fff1f02b1fde4813afa5d9fe8560f837665c8a24/tests/test_run_all.py#L35-L47) · [烘焙配置與陣列](https://github.com/WangChengYeh/Avatar/blob/fff1f02b1fde4813afa5d9fe8560f837665c8a24/body3d/steps/bake33.py#L8-L36)

同一組中間檔以 2K 貼圖進行診斷時，烘焙峰值常駐記憶體約 2.6 GiB。接著沿用原程式匯出、綁骨與驗證，兩個 GLB 都通過內建及 Khronos 驗證。這是調降解析度後的診斷結果，預設 4K 流程仍待驗證。

**驗收**　在至少一個明確記錄 RAM 上限的參考環境，以預設 4K 設定跑完 16 步，並記錄峰值記憶體，確認兩個 GLB 可通過驗證。

### 3. GLB 通過驗證時，頭部貼圖仍可能有黑條

複製 repo 的測試 GLB，只在嵌入的 4096 × 4096 `Head` JPEG 貼圖加入黑色直線，每條 24 像素寬、間距 175 像素。正面渲染中可見黑條穿過眼周、臉頰與嘴部。內建驗證仍為 **19 PASS、0 WARN、0 FAIL**，加上 Khronos 驗證則為 **20 PASS、0 WARN、0 FAIL**。這重現的是成品檢查漏判。原有黑條究竟來自拍攝、視角對位、遮擋或補色，仍需使用出現問題的原始照片與成品再定位。[貼圖驗證](https://github.com/WangChengYeh/Avatar/blob/fff1f02b1fde4813afa5d9fe8560f837665c8a24/body3d/verify_glb.py#L233-L257) · [貼圖烘焙](https://github.com/WangChengYeh/Avatar/blob/fff1f02b1fde4813afa5d9fe8560f837665c8a24/body3d/steps/bake33.py#L130-L177)

**驗收**　以正常貼圖與加入黑條的貼圖做成對測試。比對成品的正面、左右 45° 和左右側面頭部渲染圖，檢查臉頰、鼻翼與嘴角，並保留睫毛、鼻孔等原本偏暗的細節。

### 4. 剪影擬合可產生看似合理但有偏差的相機

2.3.0 只會替俯角與仰角環搜尋透視距離，水平主環仍以正交建模，頭部特寫也維持水平正交。俯角偏差在已知相機設定的合成圖上重現。將 `BODY3D_MAX_DPHI` 與 `BODY3D_MAX_DTH` 都設為 0，保留同一輸入與其他重建設定後，全身平均剪影差異由 7.68% 降至 6.15%。現有透視測試允許 16 張正交圖中最多 3 張被誤判，也允許實際 4 m 的俯角視圖估在 2.5–6.5 m；現有斷言給了相機估計較寬的容差。[水平環設定](https://github.com/WangChengYeh/Avatar/blob/fff1f02b1fde4813afa5d9fe8560f837665c8a24/body3d/steps/cams33.py#L32-L42) · [頭部對位](https://github.com/WangChengYeh/Avatar/blob/fff1f02b1fde4813afa5d9fe8560f837665c8a24/body3d/steps/headreg33.py#L11-L27) · [既有測試](https://github.com/WangChengYeh/Avatar/blob/fff1f02b1fde4813afa5d9fe8560f837665c8a24/tests/test_run_all.py#L70-L80)

**驗收**　用已知相機參數的合成組分別記錄角度誤差、透視誤判數、全身剪影差異與頭部特徵點的投影誤差。實際人物的臉部驗收需使用同一組原始照片做多視角對照。

首要修正是讓 Blender 腳本的失敗傳到 CLI，並穩定完成預設 4K 烘焙。若驗收目標包含人物相似度，應把多視角臉部比對納入交付測試。
