# 正式部署與湯底填寫

學生入口：https://turtlesoup-ytac.onrender.com/

## Render 只保留兩項

| 名稱 | 值 |
| --- | --- |
| GEMINI_API_KEY | 私密Gemini金鑰 |
| GOOGLE_APPLICATION_CREDENTIALS | /etc/secrets/google-service-account.json |

Secret Files 保留 google-service-account.json。不需 PostgreSQL、DATABASE_URL、額外磁碟。

Build Command：`pip install -r requirements.txt`

Start Command：`uvicorn backend.app:create_app --factory --host 0.0.0.0 --port $PORT --workers 1 --no-access-log --no-proxy-headers`

Health Check Path：`/healthz`。Pre-Deploy 留白。維持單一實例與單一worker。

## 核對新版

`/api/config` 的 `record_layout` 應顯示 `core-fk-v1`。新名冊 A～E 不變，F 作答狀況、G 第一題問答、H 第一題摘要、I 第二題問答、J 第二題摘要、K 總Token。沒有第二題時 I/J 留白。問答不顯示詳細時間或JSON。

## 湯底放置位置

https://github.com/Use5566/turtlesoup/blob/main/臺灣藍鵲.txt
https://github.com/Use5566/turtlesoup/blob/main/南亞夜鷹.txt

各檔案的【湯底】標記下一行填入完整答案與判斷依據，保留【謎面】段落。D/E只填題目名稱。兩題目前等待老師正式湯底，尚未開放AI提問。填好並部署後，返回活動列表重新進入。

## 驗收

1. 使用新名冊帳號登入，只看到被分配的題目。
2. 草稿等待35秒儲存，登出重登入可恢復。
3. 補齊湯底後正式提問，G/I顯示提問與回覆，K顯示實際用量。
4. 完成一題檢查H/J；有兩題者須兩題都結束，F才顯示完成。
5. 非上課時間重啟後端，確認進度、草稿和Token仍在。

「系統恢復資料（請勿編輯）」隱藏分頁保存恢復資料，勿刪除。F～K 不含系統備註。正常儲存不修改名冊 A～E。舊紀錄表保留為歷史，不會刪除。
