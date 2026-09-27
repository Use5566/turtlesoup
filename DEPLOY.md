# Render 前後台整合：兩項設定與真人測試

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
