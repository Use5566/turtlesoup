# turtlesoup｜海龜湯思考實驗室

學生以班級、座號與五位數字密碼登入，用封閉問題探索故事。前台以 iPad 橫式為主，支援手機。GitHub Pages 提供靜態前台，Python FastAPI 提供登入、Gemini 判斷、遊戲保存與 Google 試算表同步。

目前是模擬版，不呼叫 Gemini。Google 試算表同步預設關閉；本機採教師提供的私密名冊。正式題庫尚待教師提供；`scripts/init_demo.py` 是公開、僅供測試的原創範例題，不能用來存放保密的正式湯底。

## 本機啟動

Python 3.12，於專案根目錄執行：

```powershell
python -m venv work/venv
./work/venv/Scripts/python.exe -m pip install -r requirements-dev.txt
./work/venv/Scripts/python.exe scripts/init_demo.py
./work/venv/Scripts/python.exe scripts/run_local.py
```

開啟 http://127.0.0.1:8765 。全新副本的合成示範帳號：999 班、01 號、12345。既有本機沙盒已有教師提供的私密名冊，請使用教師給的帳號。初始化不覆寫既有資料。本機啟動器只綁定 127.0.0.1，實體 iPad 連線須另行安排。

## 功能

- 名冊依欄名辨識「班級、座號、密碼」，可容忍其他欄位。座號 1 與 01 等同；密碼必須是五位半形數字。
- 兩小時登入憑證、重新登入撤銷舊憑證、登出、登入限流；每次資料 API 檢查學生身分。
- Bearer token 只存在前台記憶體，重新整理需重新登入；遊戲進度從資料庫恢復。跨站使用 Authorization，不依賴第三方 Cookie。
- 回答白名單：是／不是、對／不對、會／不會、有／沒有、可／不可、能／不能、無關。Gemini 結構化結果仍經後端驗證，額外解釋一律不顯示。
- 複合／開放式問題、資訊不足、供應商故障使用獨立系統訊息，不冒充「無關」。白名單限制格式，語意正確性仍須正式題庫與真實模型驗證。
- 每位學生每活動版本一個場次。題目內容雜湊變動建立新版本，舊場次保留；結束後不能再提問，不自動揭曉湯底。
- 每題最多 300 字、預設 30 次提問、每學生五分鐘最多 20 次新提問。失敗、改寫請求也計一次並記錄狀態。
- UUID 去重；正在處理時禁止第二題；重啟將未完成問題標為中斷，不自動重發可能已計費的 AI 請求。
- SQLite 本機保存；線上 preview／production 強制使用 PostgreSQL。待同步紀錄持久保留，Google 試算表供老師查閱、分析。

## 私密設定與模式

`private/local.env`：本機設定。`private/roster.json`：本機名冊。`private/puzzles.json`：題庫。`private/google-service-account.json`：Google 憑證。這些均被 Git 排除，不能放進 `web/`。

`APP_MODE=local`：本機前後台、SQLite、可模擬。`APP_MODE=preview`：線上測試、PostgreSQL、可模擬。`APP_MODE=production`：要求 PostgreSQL、Google 名冊與 Gemini。

Gemini 預留欄位：`GEMINI_API_KEY`、`GEMINI_MODEL=gemini-3.5-flash-lite`、`GEMINI_TEMPERATURE=0`、`GEMINI_MAX_OUTPUT_TOKENS=1024`。`AI_MODE=mock` 不送出 API 請求；日後設 `AI_MODE=gemini` 並填入金鑰才啟用。金鑰缺失不產生假回答。

題庫是 JSON 陣列，各題含 `id`、`version`、`title`、`surface`、`solution`、`facts`、`enabled`、`max_turns`；`mock_cases` 與 `mock_examples` 是可選本機固定範例。正式題庫只留後端私密儲存。活動目前由題庫管理，尚未實作試算表「活動設定」分頁或教師後台。

## Google 試算表

https://docs.google.com/spreadsheets/d/1CdLxYuVMC_YJ0hSRWoieaklwLJEdZHsi7MHVq-xyyOU/edit

名冊 gid 預設 0。程式先讀 metadata 解析真實分頁名稱，再讀有界範圍。名冊不送前台或 Gemini，密碼不寫入學習紀錄。名冊快取最多 30 秒；過期無法更新時停止認證。修改密碼／刪除學生會在快取更新後撤銷舊登入。

唯讀核對（不列出密碼）：

```powershell
./work/venv/Scripts/python.exe scripts/check_sheets.py
```

權限就緒且準備啟用線上紀錄後，明確執行：

```powershell
./work/venv/Scripts/python.exe scripts/init_sheet_logs.py --create
```

只建立「海龜湯互動紀錄」「海龜湯場次摘要」，不改名冊。接著設 `SHEETS_SYNC_ENABLED=true` 並重啟。每 30 秒批次同步；未建立分頁、權限不足或網路錯誤時，紀錄保留在資料庫等待補送。

| 分頁 | 欄位 |
| --- | --- |
| 海龜湯互動紀錄 | 請求編號、紀錄時間、班級、座號、活動編號、場次編號、題目版本、提問序號、學生問題、問句類型、AI回答、處理狀態、模型、總tokens |
| 海龜湯場次摘要 | 場次編號、班級、座號、活動編號、題目版本、開始時間、最後互動時間、提問總數、場次狀態、累計tokens、資料版本 |

每題／每場固定一列。時間為 Asia/Taipei，座號保留前導零，RAW 寫入避免學生文字被執行為公式。請勿在原始紀錄分頁直接排序、插列、刪列或修改內容，分析請另製副本。UUID 不符就停止寫入，避免覆蓋別筆資料。資料庫與表格配對備份，不可清空資料庫後沿用舊表格。

tokens 採 API 的 `totalTokenCount`，不重複加快取；缺值標記「未提供／資料不完整」。模擬模式是 `local-mock`、0 tokens，並非真實 Gemini。中斷後未知的供應商費用不能視為零。

## 驗證與限制

```powershell
./work/venv/Scripts/python.exe -m pytest tests --basetemp=work/pytest-run
node --check web/app.js
```

必須一個 worker、一個服務實例，互斥使用程序鎖；多實例須改共用交易鎖與工作租約。API 送出後中斷可能已產生供應商費用，不能宣稱外部呼叫恰好一次。系統不自動重試不確定結果。

已驗證 SQLite／模擬供應商；真實 Gemini、Google 線上寫入、PostgreSQL 連線與全班負載仍待部署測試。Render 欄位詳見 `DEPLOY.md`。

## GitHub TXT 測試題目

目前測試檔為專案根目錄的 `歐氏尖吻鮫.txt`。將 `PUZZLES_PATH` 設成 `歐氏尖吻鮫.txt`，後端便會載入部署版本中的 UTF-8 文字檔，不再讀取原本的 `/etc/secrets/puzzles.json`。本機設定已切換；Render 需由使用者修改變數並手動部署最新 commit。

純 TXT 全文會顯示為謎面，同時作為 AI 判斷依據；標題取檔名。此測試文章沒有分開的湯底，程式不自動編造答案。檔案已公開在 GitHub，內容不是保密題庫。若需要隱藏湯底，仍使用原有 JSON 題庫。修改 TXT 後重新部署，內容雜湊會產生新活動版本，舊場次仍保留原文。

`AI_MODE=mock` 不會進行自由問答判斷，TXT 未設定固定模擬答案；要測試真實 AI，由使用者設定 `AI_MODE=gemini` 和 `GEMINI_API_KEY`。`GEMINI_MAX_OUTPUT_TOKENS` 使用 `1024`，不可填 `50`。本次不呼叫付費模型、不操作 Render，也不修改 Google 試算表。六欄試算表的 D～F 同步仍待接入，目前同步器使用獨立紀錄分頁。
