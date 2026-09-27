# 正式互動測試設定（七欄版）

已核對程式與截圖。公開後端 /healthz 回應 200，/api/config 顯示 Gemini 已啟用、試算表同步尚未啟用。截圖所有欄位均為有效設定，無需刪除。

## 必須補上或確認

| 環境變數 | 值 | 用途 |
| --- | --- | --- |
| APP_MODE | production | 正式模式檢查 |
| DATABASE_URL | 本專案 PostgreSQL 的 Internal Database URL | 保存登入、場次、問題與待同步資料；不要貼出密碼 |
| SHEETS_SYNC_ENABLED | true | 啟用 F、G 同步 |

APP_MODE=production 必須配合有效 PostgreSQL、Gemini、Google 名冊；未準備資料庫時請先建立並設定 DATABASE_URL，不可只改模式。現有 SQLite 資料不會自動搬到 PostgreSQL。

## 保留目前設定

| 環境變數 | 值 |
| --- | --- |
| AI_MODE | gemini |
| ALLOWED_ORIGINS | https://use5566.github.io |
| GEMINI_API_KEY | 保留既有私密金鑰 |
| GEMINI_MODEL | gemini-3.5-flash-lite |
| GEMINI_MAX_OUTPUT_TOKENS | 1024 |
| GEMINI_TEMPERATURE | 0 |
| GOOGLE_APPLICATION_CREDENTIALS | /etc/secrets/google-service-account.json |
| GOOGLE_ROSTER_GID | 0 |
| GOOGLE_SHEET_ID | 1CdLxYuVMC_YJ0hSRWoieaklwLJEdZHsi7MHVq-xyyOU |
| PUZZLES_PATH | 歐氏尖吻鮫.txt |
| ROSTER_MODE | google |

GEMINI_MODEL、GEMINI_MAX_OUTPUT_TOKENS、GEMINI_TEMPERATURE、GOOGLE_ROSTER_GID 的現值與預設相同，可以省略但仍有用途，建議保留以便核對。

可不填：SESSION_SECONDS（預設7200）、SYNC_SECONDS（預設30）。ROSTER_PATH 僅 file 模式使用，Google 模式不需設定。HOST 沒有程式用途，已從範例移除。TURTLESOUP_API_URL 僅建置 GitHub Pages 使用，不需設在 Render。PORT 由 Render 提供，無需自行固定。

Secret Files 只需要 google-service-account.json。舊 roster.json 與 puzzles.json 已不被本次 Google 名冊＋GitHub TXT 配置使用，可由你移除。

## 部署與驗收

Start Command：`uvicorn backend.app:create_app --factory --host 0.0.0.0 --port $PORT --workers 1 --no-access-log --no-proxy-headers`

保持一個 worker、一個服務實例。Health Check Path：`/healthz`。Pre-Deploy 留白。不需額外建立紀錄分頁。

1. 試算表首列必須依序是「班級、座號、密碼、謎底、謎面、互動紀錄、場次摘要」。F、G 初始留白。
2. 由你補齊變數並手動部署最新 GitHub commit。
3. 在 GitHub Pages 登入，確認只顯示謎面，活動名稱不顯示答案。
4. 提出一個封閉問題，確認回覆為允許的肯定／否定詞或「無關」；資訊不足或服務錯誤以系統訊息呈現，不冒充答案。
5. 等待約30～60秒，確認 F 出現問題與回答、G 出現場次摘要，前台顯示已同步。
6. 結束場次再等候同步，確認 G 的場次狀態為 finished。

F/G 是縮排 JSON，保留多場歷史並用 UUID 去重。不可在互動期間手動排序或編輯名冊；不可手動修改 F/G。超過單格容量或碰到不符格式的既有內容會停止覆寫，紀錄留在資料庫。

本次 46 項本機測試通過，含登入／提問／結束／F-G 寫入、重試去重、學生列換位、容量與既有資料保護。尚未代你部署 Render，因此新版真實 Gemini＋Google 寫入的線上全流程仍需部署後驗收。
