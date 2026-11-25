# fr24-tracker
## 基本功能
程式利用呼叫**flightradar api** 擷取特定航班資料，並以**discord**通知使用者\
程式會定期定時調閱api資料庫，提供四大功能資料：\
\
**追蹤特定飛機/航司不特定飛機是否前往TPE**，例如*JA787A*或*ANA*\
**追蹤特定飛機是否在TPE地面**，例如*JA787A*\
**追蹤特定航線有無飛機飛行**，例如*LHR-TPE*航線\
**追蹤特定航班號有無飛機飛行**，例如*ANA9415*號航班
## 環境設定
Name：`FR24_API_TOKEN` ／ Secret：貼上你的 Flightradar24 API Token（測試階段可先放免費的 Sandbox Token）。\
Name：`NOTIFY_WEBHOOK_URL` ／ Secret：貼上你的 Discord Webhook 網址（若暫時不設定，程式只會在執行紀錄中印出文字，不會報錯）。
## 追蹤特定飛機/航司
### 模組名稱
`track_fleet_tpe.py` 與`track_fleet_tpe.yml`/
### 飛機與航司設置
於`track_fleet_tpe.py`內\
```
# 1. 設定要追蹤的目標飛機註冊編號
TARGET_REGISTRATIONS = [ #加入想追蹤的飛機註冊號]

# 2. 設定要追蹤的目標航空公司 3 碼 ICAO 代碼（可逗號擴充多間）
TARGET_AIRLINES_ICAO = [ #加入想追蹤的航空公司 3 碼 ICAO 代碼]
```
例如\
```
# 1. 設定要追蹤的目標飛機註冊編號
TARGET_REGISTRATIONS = ["JA787A", "B-18001","D-ABPB"]

# 2. 設定要追蹤的目標航空公司 3 碼 ICAO 代碼（可逗號擴充多間）
TARGET_AIRLINES_ICAO = [ "BAW","ANA", "GTI"]
```
