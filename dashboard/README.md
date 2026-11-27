# Avatar 專案總覽：Google Apps Script 版

在你的 Google 帳號裡執行，直接讀 Drive 的 `avatar/` 資料夾：不用 API 金鑰、不用 Google Cloud、資料夾不必公開。

## 安裝（約 5 分鐘，只做一次）

1. 開 https://script.google.com ，按「新專案」，專案名稱改成「Avatar 專案總覽」。
2. 左邊「專案設定」（齒輪）→ 勾「在編輯器中顯示 appsscript.json 資訊清單檔案」。
3. 回到「編輯器」，把三個檔案的內容貼進去：
   - `Code.gs`：取代預設的 `程式碼.gs`（或 `Code.gs`）的全部內容。
   - `appsscript.json`：取代全部內容。
   - `Index.html`：按「＋」→「HTML」，名稱打 `Index`（不要加 .html），貼上全部內容。
4. 按「儲存」。
5. 右上「部署」→「新增部署作業」→ 類型選「網頁應用程式」：
   - 執行身分：我
   - 誰可以存取：只有我自己
   - 按「部署」。第一次會要求授權：選你的帳號 →「進階」→「前往 Avatar 專案總覽（不安全）」→「允許」。
     （「未經驗證」是因為這是你自己寫的指令碼，不是 Google 審核過的 App；它只要求「讀取 Drive」和「連線到外部服務（讀 Drive 檔案的一部分）」。）
6. 複製「網頁應用程式」網址（`https://script.google.com/macros/s/…/exec`），加進書籤；iPhone 上用 Safari 開、登入同一個 Google 帳號、分享 →「加入主畫面」。

## 更新程式

改了 `Code.gs` 或 `Index.html` 之後：「部署」→「管理部署作業」→ 鉛筆 → 版本選「新版本」→「部署」。網址不變。

## 它讀什麼

- `avatar/<執行者>/avatar_NNN/vNNN/` 底下檔名有 `_stageN_` 的 zip。
- 每一版最後一關的 zip 裡的 `manifest.json`（各關 FAIL／WARN／PASS）與 `fit_report.json`（最終剪影）。
- 點一版時：第 4 關的 `04_body_compare.jpg`、`05_head_compare.jpg`，第 3 關的 `v2_three_q*.png`。
- 只下載 zip 的目錄和這幾個檔案（HTTP Range），不會整包下載；檢查數字存在瀏覽器裡，下次開更快。
