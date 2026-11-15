# turtlesoup｜海龜湯思考實驗室

學生入口：https://turtlesoup-ytac.onrender.com/ 。Render 同時提供前後台，GitHub 保存程式與題庫。

## 正式名冊與紀錄

使用 https://docs.google.com/spreadsheets/d/17LPzhH0CzpiRa_Our-qLanGF7IUJq1COVIjRJ6XI8Qw/edit?gid=0 的「工作表1」。

| 欄 | 名稱 | 填寫者 |
| --- | --- | --- |
| A | 班級 | 老師：1～3位半形數字 |
| B | 座號 | 老師：1～99，同班不重複 |
| C | 密碼 | 老師：五位半形數字，保留前導零 |
| D | 謎面1 | 老師：題目檔名，如臺灣藍鵲 |
| E | 謎面2 | 老師：題目檔名，如南亞夜鷹；未分配則留白 |
| F | 作答狀況 | 系統：尚未開始／進行中／已完成所有指定題目 |
| G | 謎面1互動紀錄 | 系統：學生提問、主持人回覆 |
| H | 謎面1場次摘要 | 系統：提問次數、尚未開始／進行中／已結束 |
| I | 謎面2互動紀錄 | 系統：學生提問、主持人回覆 |
| J | 謎面2場次摘要 | 系統：提問次數與狀態 |
| K | 累計總Token | 系統：所有場次實際總token，只加總一次 |

沒有第二題時 I/J 留白。完成自己所有指定題目才標示完成，不代表系統判定答對。正文不顯示JSON、UUID、詳細時間、模型或單次token；學生原始問題文字仍完整保留。恢復資料保存在獨立隱藏分頁，請勿刪除。未知API用量顯示「資料不完整」，不以0冒充。

原 turtlesoup_logs 七欄表保留為歷史資料，不再承接新版正式寫入。切換時只依班級座號遷移相同學生，舊表不刪除。

## 題庫及湯底位置

GitHub main 最外層有 `臺灣藍鵲.txt`、`南亞夜鷹.txt`。格式為：

```text
【謎面】
學生看到的題目敘述。

【湯底】
老師提供的完整真相、解釋及 AI 判斷依據。
```

只編輯【湯底】後的內容即可補答案。不要把答案填入試算表 D/E；D/E 是題目名稱。湯底留白時可看謎面，但系統不呼叫AI。修改TXT需要重新部署，並重新進入題目建立新版本。GitHub 為公開庫，TXT 不具保密性。

## 儲存與恢復

前台每35秒保存草稿。開始場次、提問前後、結束及正常登出另行保存；正常使用會延長登入期限。Google Sheets 是正式儲存來源，記憶體 SQLite 只作執行期索引，不需要 PostgreSQL。重啟從隱藏分頁恢復場次、問題、草稿及去重識別。

保存失敗回報未儲存；提問前保存失敗不呼叫付費模型。重啟後未完成的AI請求標記中斷，不自動重送。斷網、強制關閉或裝置休眠時，尚未成功儲存的草稿仍可能遺失。

只允許單一服務實例與一個worker。使用期間不要排序／移動名冊，不要手動改 F～K 或隱藏分頁。試算表沒有條件式寫入，程式只能重讀檢查變動；每格接近容量上限時會停止寫入，需先封存紀錄。

## Render 與本機測試

Render 只填 GEMINI_API_KEY 和 GOOGLE_APPLICATION_CREDENTIALS，後者為 /etc/secrets/google-service-account.json。其餘正式設定由程式固定。

```powershell
./work/venv/Scripts/python.exe -m pytest tests --basetemp=work/pytest-run
node --test tests/autosave.cjs
```

本機預設 mock AI，保留舊版格式測試以驗證相容性。私密檔案與實際密碼不可上傳GitHub。更多部署步驟見 DEPLOY.md。
