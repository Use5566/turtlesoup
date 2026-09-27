# Render 最少設定（三項）

新版會利用 Render 平台自帶的 `RENDER=true` 自動套用正式設定，不需自行新增 RENDER。平台說明：https://render.com/docs/environment-variables

## 只需保留的 Environment Variables

| 名稱 | 值 |
| --- | --- |
| GEMINI_API_KEY | 既有 Gemini 私密金鑰 |
| GOOGLE_APPLICATION_CREDENTIALS | /etc/secrets/google-service-account.json |
| DATABASE_URL | 本專案 PostgreSQL 的 Internal Database URL |

DATABASE_URL 仍然必要。本次簡化設定介面，沒有移除持久資料庫；若尚未建立 PostgreSQL，需先準備，否則新版會明確拒絕啟動。原 SQLite 資料不會自動搬遷。

Secret Files 保留 `google-service-account.json`。金鑰及資料庫連線字串不要放 GitHub。

## 已固定在程式內

正式模式、Gemini、Google 名冊、啟用試算表同步、現有試算表 ID、gid 0、GitHub Pages 來源、TXT 題庫目錄、Gemini 3.5 Flash Lite、temperature 0、max output tokens 1024、登入有效期7200秒、同步間隔30秒。

部署新版時可以刪除舊的 APP_MODE、AI_MODE、ROSTER_MODE、ROSTER_PATH、SHEETS_SYNC_ENABLED、ALLOWED_ORIGINS、PUZZLES_PATH、GOOGLE_SHEET_ID、GOOGLE_ROSTER_GID、GEMINI_MODEL、GEMINI_TEMPERATURE、GEMINI_MAX_OUTPUT_TOKENS、SESSION_SECONDS、SYNC_SECONDS；新版在 Render 不讀取這些覆寫值。HOST、TURTLESOUP_API_URL 也不需設定。不要刪除 Render 平台自帶的 PORT 或 RENDER。

本機不在 Render 時，仍支援 `.env.example` 的開發選項，預設 mock／file／SQLite／同步關閉，不會自動啟用付費 AI。

## 部署與驗收

先備妥上述三項與 Secret File，再手動部署新版。Start Command 保持：

`uvicorn backend.app:create_app --factory --host 0.0.0.0 --port $PORT --workers 1 --no-access-log --no-proxy-headers`

Health Check Path：`/healthz`。Pre-Deploy 留白。維持單一 worker 與服務實例。

1. 試算表首列依序為「班級、座號、密碼、謎底、謎面、互動紀錄、場次摘要」。
2. 學生的謎底填「歐氏尖吻鮫」，謎面填學生應看到的文字；後端以 GitHub 根目錄同名 TXT 作判斷依據。
3. 登入 GitHub Pages、提出封閉問題，等待約30～60秒，確認 F/G 有紀錄。
4. 結束場次，再確認 G 狀態更新為 finished。

F/G 使用縮排 JSON 並保留多場歷史。不要手動編輯 F/G 或在同步時排序名冊；非預期內容及容量超限會停止覆寫並保留資料庫紀錄。

53 項本機測試通過；尚未代為部署 Render，也未驗證新版真實 Gemini／PostgreSQL／Google 寫入的線上全流程。
