# Render 前後台整合：兩項設定與真人測試

## 正式題庫與五欄分配（最新）

名冊首列為「班級、座號、密碼、謎面1、謎面2」。班級支援1～3位半形數字，密碼五位數；題目欄填 TXT 名稱，空白表示不指派。每位學生只看到其名冊列指定的活動。

GitHub 根目錄正式題目為 `臺灣藍鵲.txt`、`南亞夜鷹.txt`。原三個測試 TXT 已從 main 移除。兩題目前只填教師提供的謎面，等待教師在【湯底】後補入正式答案；湯底空白時可查看謎面，但後端不呼叫 AI。補完 TXT 並重新部署後，重新進入活動即可使用新版本。舊互動紀錄不會被刪除。

以下四欄格式為舊版相容說明。

## 正式四欄登入名冊（最新）

登入名冊使用 https://docs.google.com/spreadsheets/d/17LPzhH0CzpiRa_Our-qLanGF7IUJq1COVIjRJ6XI8Qw/edit?gid=0 ，工作表1，首列為「班級、座號、密碼、謎面」。此處「謎面」填題目名稱／TXT 檔名，例如「拳擊蟹」，不是完整故事。一位學生一列，密碼為五位半形數字。空名冊可啟動服務，但不能登入。

既有七欄試算表只作互動紀錄與恢復資料儲存，不再作正式登入來源。新學生開始活動時自動新增紀錄列，不複製密碼。Render 仍只需原本兩項環境變數。

現有三題保留原故事設定；新增題目 TXT 請使用下列格式，前台只顯示【謎面】與【湯底】之間的文字：

```text
【謎面】
學生看到的故事。
【湯底】
完整真相與 AI 判斷依據。
```

登入頁保留，學生登入後只取得名冊指定的活動。既有班級座號若有紀錄會恢復原進度，不要將同一帳號改派其他學生。

以下七欄說明適用於紀錄表與舊版相容格式。

學生入口：https://turtlesoup-ytac.onrender.com/

前後台現在由同一個 Render Web Service 提供，不需新增 Static Site。GitHub 保存程式碼與 TXT，舊 Pages 只有轉址頁。需手動部署此版本後，新首頁才會生效。

| Environment Variable | 值 |
| --- | --- |
| GEMINI_API_KEY | 你的 Gemini 金鑰 |
| GOOGLE_APPLICATION_CREDENTIALS | /etc/secrets/google-service-account.json |

Secret Files 保留 `google-service-account.json`。不需要 DATABASE_URL、PostgreSQL 或額外磁碟。所有其他原先手動新增的模式、模型、試算表、路徑及同步設定可移除，新版在 Render 不讀取這些值；平台自帶 RENDER、PORT 不要刪除。

Build Command：`pip install -r requirements.txt`

Start Command：`uvicorn backend.app:create_app --factory --host 0.0.0.0 --port $PORT --workers 1 --no-access-log --no-proxy-headers`

Health Check Path：`/healthz`。Pre-Deploy 留白。由你手動部署最新 commit，維持單一實例與單一 worker。

## 真人測試順序

1. 部署後開啟 Render 網址，以試算表帳號登入。
2. 選題確認只顯示謎面，不顯示 TXT 全文與答案。
3. 輸入草稿但不送出，等待35秒確認已儲存，登出再登入接續，確認草稿及問句類型恢復。
4. 正式提問，確認肯定／否定或無關回答；查看 F/G 保存內容。
5. 結束場次，登出再登入，確認歷史與結束狀態保留。
6. 在非上課時間重啟後端，再登入檢查歷史與草稿仍在。

自動儲存不是強制登出，也不會將草稿送給 Gemini。每35秒保存草稿，正常登出前額外保存；活躍使用會延長登入有效期。

斷網、強制關閉瀏覽器或裝置休眠可能使最新未成功儲存的內容遺失。F/G 顯示純文字互動與摘要，恢復資料保存在儲存格備註，請勿刪除備註或手動修改；上課期間勿排序名冊。試算表讀寫失敗時會顯示未保存，請保留頁面重試。

本機自動化測試覆蓋登入、問答白名單、重試去重、草稿、登出與重啟恢復、舊版紀錄遷移、儲存失敗與損壞資料保護。真實 Gemini、Google 權限與新版 Render 部署仍須上述線上驗收；未代為操作 Render。

新版啟動會自動把舊 F/G JSON 轉成純文字，保留所有互動及恢復資料。部署前不要手動清空舊 JSON，舊程式仍需讀取它。可讀正文不顯示 UUID、模型、tokens 或題目全文；必要系統資料移到備註。
