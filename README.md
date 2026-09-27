# turtlesoup｜海龜湯思考實驗室

GitHub Pages 提供前台，Render 提供登入與 Gemini 判斷，Google 試算表保存場次、問答與草稿。Render 不需要 PostgreSQL 或持久磁碟。

## Render 只填兩項

- `GEMINI_API_KEY`：私密金鑰。
- `GOOGLE_APPLICATION_CREDENTIALS=/etc/secrets/google-service-account.json`：搭配同名 Secret File。

Render 平台的 `RENDER=true` 會套用正式設定：Google 名冊、Gemini 3.5 Flash Lite、temperature 0、max output tokens 1024、gid 0、現有試算表與 GitHub Pages 來源。其他舊環境變數（包括 DATABASE_URL）不會覆寫正式設定，可移除。

## 七欄試算表

首列依序為「班級、座號、密碼、謎底、謎面、互動紀錄、場次摘要」。前三欄驗證身分；謎底對應 GitHub 根目錄的同名 TXT，謎面才是學生看到的文字。活動名稱不揭露答案。TXT 已公開在 GitHub，不是保密資料。

F 保存問答紀錄，G 保存摘要與 `_restore` 恢復資料（含當次題目快照、問答及草稿），以 UUID 去重。密碼與 API 金鑰不存入 F/G，也不傳給 AI。每列保存多場歷史。請勿手動編輯 F/G；有既有非系統格式內容時會停止恢復或寫入，不清空原資料。

## 保存與恢復

- 前台每 35 秒儲存尚未送出的問題與問句類型；後端每 35 秒補送尚未成功的紀錄。
- 開始場次、提問前後、結束與正常登出都會確認雲端保存。儲存失敗回傳錯誤，保留頁面重試，不假稱成功。
- AI 呼叫前先保存請求。重啟若遇到未完成請求，標記中斷，不自動重送付費 API。
- Render 使用記憶體 SQLite 作執行期索引，啟動從 Google Sheets 恢復；沒有額外資料庫服務。讀取失敗不以空資料覆蓋試算表。
- 重新登入後選同一活動即可接續，已結束的場次仍保持結束。活動版本變動會建立新場次。
- 登入有效期按使用中的 API 請求延長，閒置兩小時後需重新登入；密碼變動仍會撤銷登入。

瀏覽器關閉、斷網、背景分頁節流或裝置當機，可能使最近未成功保存的草稿無法恢復。35 秒不是關機時的保存保證。正常離開請用登出；草稿非空時關閉頁面會提示。

## 本機與測試

本機預設 file 名冊、mock AI、SQLite 私密檔案，不呼叫真實 Gemini。`private/local.env`、名冊、憑證均不提交 GitHub。

```powershell
python -m venv work/venv
./work/venv/Scripts/python.exe -m pip install -r requirements-dev.txt
./work/venv/Scripts/python.exe scripts/init_demo.py
./work/venv/Scripts/python.exe scripts/run_local.py
./work/venv/Scripts/python.exe -m pytest tests --basetemp=work/pytest-run
node --test tests/autosave.cjs
```

舊 file 模式的獨立紀錄分頁功能僅保留給本機相容測試，正式七欄模式不用執行 `init_sheet_logs.py`。

## 運作限制

單一服務實例、單一 worker；部署重啟期間不要繼續上課提問。這不是多實例同步系統。使用期間不要排序或移動名冊；Google Sheets 沒有條件式寫入。F/G 單格接近49,000 UTF-16單位時會拒絕新增並提示未保存，需先由老師封存紀錄；不得直接刪除恢復資料。已在記憶體但未同步的修改若遇服務中斷仍可能遺失。

舊版 F/G 摘要可依同名 TXT 恢復；已變更的題目版本無法繼續提問。只有舊 PostgreSQL 而尚未同步到 Sheets 的資料不會自動遷移。

回答只允許肯定／否定配對及無關。資訊不足、問題需改寫、模型服務錯誤使用系統訊息，不冒充答案。詳見 DEPLOY.md。
