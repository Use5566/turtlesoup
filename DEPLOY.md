# 正式部署與湯底填寫

學生入口：https://turtlesoup-ytac.onrender.com/

## Render 環境變數仍只保留兩項

| 名稱 | 值 |
| --- | --- |
| GEMINI_API_KEY | 私密 Gemini 金鑰 |
| GOOGLE_APPLICATION_CREDENTIALS | /etc/secrets/google-service-account.json |

Secret Files 保留 `google-service-account.json`。不需要 PostgreSQL、DATABASE_URL 或其他同步環境變數。

## 必須先掛載持久磁碟

本版改用持久 SQLite 暫存問答，避免試算表同步失敗時，Render 重啟遺失尚未同步的內容。

在 Render 的本專案 Web Service 後台設定：

| 欄位 | 設定 |
| --- | --- |
| Instance Type | 支援持久磁碟的付費方案 |
| Disks → Add Disk → Mount Path | `/var/data` |
| Size | 起始 1 GB，可依使用量增加 |
| Instance Count | 1 |

程式固定將資料庫寫入 `/var/data/turtlesoup/turtlesoup.db`，相關 WAL 檔案也留在同一目錄。必須掛載真正的持久磁碟，僅建立普通資料夾無法跨部署保存；程式發現 `/var/data` 未掛載時會拒絕啟動並顯示設定提示。

掛載磁碟會觸發部署，請選在沒有學生使用時操作。第一次啟動會讀取試算表的既有紀錄；後續重啟保留本機待同步資料。不要刪除磁碟、資料庫或試算表的隱藏恢復分頁。

新版以持久資料庫保存作答，試算表是同步副本。只清空 F～K 或隱藏分頁不會重設學生進度；需要清除時請先備份，再安排一致的重設流程。已有待同步紀錄時，不要刪除學生或更改其班級／座號，以免身分不符使整批同步暫停。

官方說明：[Render Persistent Disks](https://render.com/docs/disks)。磁碟的自動快照保留期與資料本身的保留期限不同；本機資料與試算表都應保留。

## 建置與啟動

Build Command：`pip install -r requirements.txt`

Start Command：`uvicorn backend.app:create_app --factory --host 0.0.0.0 --port $PORT --workers 1 --no-access-log --no-proxy-headers`

Health Check Path：`/healthz`。Pre-Deploy 留白。維持單一實例與單一 worker。

## 核對新版

`/api/config` 的 `build` 應為 `20261117-batch-sync`，`record_layout` 應為 `core-fk-v2`。每次交付另附 GitHub 提交版本號，請核對 Render 部署的提交。

每次問答先保存至伺服器的持久 SQLite，背景工作每 3 秒合併有異動學生的紀錄送至試算表。沒有異動就不寫，失敗會延長等待後重試；不會每 3 秒開啟多個並行寫入。前台草稿仍每 35 秒保存一次，正常登出前再保存。

同步採單一寫入者，每批完成後至少等待 3 秒；正常情況每分鐘最多 20 批，慢請求不補跑漏掉的週期。失敗依序等待約 6、12、24、48、60 秒並加入小幅隨機延遲，成功後恢復正常間隔。每批最多處理 100 個待同步場次，包含該場次全部待同步問答；30 位學生各 20 次可合併為一批。名冊每 30 秒更新，讀取失敗也冷卻 30 秒，期間回報無法核對身分。

畫面會區分「已保存至伺服器 · 等待同步試算表」與「已儲存至試算表」。前者表示已保存，可正常登出；若出現未成功保存的錯誤，則保留頁面重試。

## 名冊與題庫

正式名冊：https://docs.google.com/spreadsheets/d/17LPzhH0CzpiRa_Our-qLanGF7IUJq1COVIjRJ6XI8Qw/edit?gid=0

A～E 保留班級、座號、密碼、謎面1、謎面2。前台班級為 1～7，座號為 1～29。F 作答狀況、G 第一題問答、H 第一題摘要、I 第二題問答、J 第二題摘要、K 累計總 Token。問答只顯示學生問題與主持人回覆，沒有詳細時間或 JSON 標示。

目前只開放名冊「謎面1」的臺灣藍鵲，登入直接進入。每場上限 20 次，不提供手動結束；未滿 20 次登出後可接續，已達或超過 20 次可登入瀏覽。南亞夜鷹暫不開放，題目與歷史紀錄保留。

湯底檔案位於 GitHub `main` 最外層：

- https://github.com/Use5566/turtlesoup/blob/main/臺灣藍鵲.txt
- https://github.com/Use5566/turtlesoup/blob/main/南亞夜鷹.txt

各檔案的 `【湯底】` 標記下一行填入完整答案與判斷依據，保留 `【謎面】` 段落。試算表 D/E 只填題目名稱。湯底已由老師提供；後續修改 TXT 需部署，重新進入時使用新題目版本。GitHub 為公開庫，TXT 不具保密性。

## 驗收

1. 核對 Render 持久磁碟掛載、提交版本及 `/api/config` 的 build。
2. 登入直接進入第一題；草稿等待 35 秒保存，登出重登入確認恢復。
3. 提問後先見到已保存至伺服器，正常同步後顯示已儲存至試算表；G/H/K 應有問答、次數與用量。
4. 確認滿 20 次後只能瀏覽，未滿 20 次可再次登入接續。
5. 在隔離測試環境模擬試算表失敗及程序重啟，確認待同步問題、答案、草稿與 Token 保留，恢復連線後只補寫一次；不要在學生上課時中斷正式服務。

「系統恢復資料（請勿編輯）」隱藏分頁保存恢復資料，勿刪除。F～K 不含系統備註。正常儲存不修改名冊 A～E，舊紀錄表保留。
