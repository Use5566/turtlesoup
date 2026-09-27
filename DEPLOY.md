# Render 逐欄設定與 GitHub Pages 連接

本專案由使用者自行操作 Render。先啟用線上模擬版，不填 Gemini 金鑰。前台與後端分開，不能把 Python 當成 Static Site。

## 1. 先準備 PostgreSQL

為避免 Render 重新啟動遺失遊戲紀錄，線上模式要求 PostgreSQL。若尚無本專案資料庫，可在 Render 選 New → Postgres。

| 欄位 | 填法 |
| --- | --- |
| Name | turtlesoup-db |
| Project | 選 turtlesoup 專案；沒有可先不選 |
| Database | turtlesoup |
| User | turtlesoup |
| Region | Singapore；若不可選，選同一個可用區域，後端也用相同區域 |
| PostgreSQL Version | 使用 Render 預設支援版本 |
| Instance Type | 測試可選 Free（若帳號有名額）；正式使用另選適合方案 |

Free Postgres 會在建立 30 天後到期，每個 workspace 只允許一個 Free Postgres。它是測試選項，不是永久免費資料庫。不要為此刪除其他專案資料庫。建立後取得 **Internal Database URL**，稍後填入後端 `DATABASE_URL`；這是私密連線字串，不放到 GitHub。

官方：https://render.com/docs/free

## 2. 建立 Python Web Service

Render → New → Web Service → 連接 GitHub 的 `Use5566/turtlesoup`。

| 欄位 | 填法 |
| --- | --- |
| Source Code | Use5566/turtlesoup |
| Name | turtlesoup（若已使用可改 turtlesoup-api） |
| Project | 選同一個 turtlesoup 專案，或留白 |
| Language / Runtime | Python 3 |
| Branch | main |
| Region | 與 PostgreSQL 相同 |
| Root Directory | 留白 |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `uvicorn backend.app:create_app --factory --host 0.0.0.0 --port $PORT --workers 1 --no-access-log --no-proxy-headers` |
| Instance Type | 先選 Free 作測試；正式班級使用再評估 |
| Health Check Path | `/healthz` |
| Auto-Deploy | 先選 Off，避免日後 GitHub 更新自動變更後端；有意啟用時再選 On Commit |
| Pre-Deploy Command | 留白 |
| Dockerfile / Docker Command | 不使用，留白 |

Free Web Service 閒置後會休眠，下一次喚醒可能約一分鐘；本機 SQLite 檔案不會在重啟／重新部署後保留，所以不能替代 PostgreSQL。

## 3. Environment Variables

先填下表可啟動「模擬版」。值不要加引號。

| Key | Value | 用途 |
| --- | --- | --- |
| PYTHON_VERSION | 3.12.10 | Python 版本 |
| APP_MODE | preview | 線上模擬／驗證階段 |
| DATABASE_URL | 貼上 PostgreSQL 的 Internal Database URL | 持久保存紀錄，私密 |
| ROSTER_MODE | file | 先使用私密名冊，等 Google 權限完成再改 google |
| ROSTER_PATH | /etc/secrets/roster.json | 名冊 Secret File |
| PUZZLES_PATH | /etc/secrets/puzzles.json | 題目與湯底 Secret File |
| AI_MODE | mock | 不使用 Gemini、不消耗 AI tokens |
| GEMINI_MODEL | gemini-3.5-flash-lite | 預留正式模型 |
| GEMINI_API_KEY | 留白；介面不接受空值時暫不新增此列 | 預留，不填假金鑰 |
| GEMINI_TEMPERATURE | 0 | 預留生成參數 |
| GEMINI_MAX_OUTPUT_TOKENS | 1024 | 預留輸出上限，含結構化輸出所需空間 |
| GOOGLE_SHEET_ID | 1CdLxYuVMC_YJ0hSRWoieaklwLJEdZHsi7MHVq-xyyOU | 指定試算表 |
| GOOGLE_ROSTER_GID | 0 | 名冊分頁 ID |
| GOOGLE_APPLICATION_CREDENTIALS | /etc/secrets/google-service-account.json | Google 憑證 Secret File |
| SHEETS_SYNC_ENABLED | false | 等權限與紀錄分頁驗證後再開啟 |
| SYNC_SECONDS | 30 | 試算表批次同步間隔 |
| SESSION_SECONDS | 7200 | 登入有效秒數 |
| ALLOWED_ORIGINS | https://use5566.github.io | 只填來源，不加 /turtlesoup/ 路徑 |

Render 提供 `PORT`，不用自行新增。`HOST` 也不用新增。不要把私密環境變數填入 GitHub Pages 的 config.js。

## 4. Secret Files

在 Render 的 Secret Files 新增以下檔案，使用本機專案 `private/` 中的同名內容。名稱大小寫一致，不加路徑：

| Filename | 本機來源 | 說明 |
| --- | --- | --- |
| roster.json | private/roster.json | 教師提供的四筆私密名冊 |
| puzzles.json | private/puzzles.json | 目前的示範題；正式題目之後替換 |
| google-service-account.json | private/google-service-account.json | Google 服務帳戶憑證，僅 Google 模式需要 |

Secret File 在執行環境位於 `/etc/secrets/檔名`。不要把這些檔案上傳 GitHub。

## 5. 連接 GitHub Pages

Render 部署成功後，複製實際產生的 HTTPS 服務網址；不要假設一定是 turtlesoup.onrender.com。

GitHub `Use5566/turtlesoup` → 開啟 `docs/config.js` → 編輯，把 `apiBase` 的空字串改成實際 Render HTTPS 網址，不加 `/api`。此檔只需修改網址，保留雙引號與其餘 JSON 格式。

Commit 至 main 後，GitHub Pages 會重新發布前台設定。這不操作 Render。

GitHub Pages Source 選 **Deploy from a branch**，Branch 選 **main**，Folder 選 **/docs**。沒有後端網址時也能先發布入口畫面，但會顯示尚未連線，無法登入。`docs/` 只含公開前台檔案，不含後端或私密檔案。

後續修改前台原始碼時，在本機設定 `TURTLESOUP_API_URL` 為實際後端網址，執行 `python scripts/build_pages.py`，將產生的 `docs/` 一併提交。若環境變數未設定，建置器會保留既有 docs/config.js 中的網址；不要在此放任何金鑰。

## 6. 日後啟用 Google 與 Gemini

Google 權限完成後，先在本機 `scripts/check_sheets.py` 唯讀核對；再明確執行 `scripts/init_sheet_logs.py --create` 建立兩個紀錄分頁，確認後才將 `ROSTER_MODE=google`、`SHEETS_SYNC_ENABLED=true`。

Gemini 準備好後填入私密 `GEMINI_API_KEY`，改 `AI_MODE=gemini`。完整驗證通過後改 `APP_MODE=production`。模型可用性、題目判斷品質、班級配額與 PostgreSQL 恢復必須實際驗證，不能以 `/healthz` 成功代替。

## GitHub TXT 測試題目

目前測試檔為專案根目錄的 `歐氏尖吻鮫.txt`。將 `PUZZLES_PATH` 設成 `歐氏尖吻鮫.txt`，後端便會載入部署版本中的 UTF-8 文字檔，不再讀取原本的 `/etc/secrets/puzzles.json`。本機設定已切換；Render 需由使用者修改變數並手動部署最新 commit。

純 TXT 全文會顯示為謎面，同時作為 AI 判斷依據；標題取檔名。此測試文章沒有分開的湯底，程式不自動編造答案。檔案已公開在 GitHub，內容不是保密題庫。若需要隱藏湯底，仍使用原有 JSON 題庫。修改 TXT 後重新部署，內容雜湊會產生新活動版本，舊場次仍保留原文。

`AI_MODE=mock` 不會進行自由問答判斷，TXT 未設定固定模擬答案；要測試真實 AI，由使用者設定 `AI_MODE=gemini` 和 `GEMINI_API_KEY`。`GEMINI_MAX_OUTPUT_TOKENS` 使用 `1024`，不可填 `50`。本次不呼叫付費模型、不操作 Render，也不修改 Google 試算表。六欄試算表的 D～F 同步仍待接入，目前同步器使用獨立紀錄分頁。

## 七欄名冊指定題目（優先於純 TXT 全文模式）

名冊含「謎底」「謎面」兩個欄名時，按登入學生所在列指定題目。「謎底」填 `歐氏尖吻鮫`，後端從 `PUZZLES_PATH` 所在目錄讀取 `歐氏尖吻鮫.txt` 作為判斷資料；「謎面」填學生應看到的文字。活動標題統一為「海龜湯挑戰」，API 不傳謎底或 TXT 全文。任一欄空白時該學生沒有活動，不沿用其他學生的題目。欄名存在時不退回全文展示。

Render 保持 `ROSTER_MODE=google`、`GOOGLE_ROSTER_GID=0`，並設定 `PUZZLES_PATH=歐氏尖吻鮫.txt`。名冊更新最多快取 30 秒；TXT 更新需重新部署。只有未包含這兩欄的舊名冊才使用前述純 TXT 全文模式。公開 GitHub 的 TXT 仍可由原始碼瀏覽，此修改只防止遊戲介面直接顯示答案。

「互動紀錄」「場次摘要」兩欄尚未串接寫入，現有同步仍使用獨立分頁；本次未變更試算表內容或 Render 設定。
