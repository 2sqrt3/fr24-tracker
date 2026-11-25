import os
import json
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timezone, timedelta

FR24_TOKEN = os.environ.get("FR24_API_TOKEN", "")
WEBHOOK_URL = os.environ.get("NOTIFY_WEBHOOK_URL", "")
BASE_URL = "https://fr24api.flightradar24.com/api"

# ==============================================================================
# 【航線與排除規則設定區】— 修改此區塊可新增或刪除條件
# 說明：
# 1. "exclude_airlines"：填入 3 碼航空公司 ICAO 代碼
# 常見代碼：CAL=中華航空, EVA=長榮航空
# 2. "exclude_flights" ：填入特定排除的「航班號」或「呼號」（如 CI82, CAL82）
# ==============================================================================
ROUTE_CONFIG = {
"ANC-TPE": {
"exclude_airlines": ["CAL", "EVA", "SJX"],
"exclude_flights": ["5X500","UPS500"],
},
"LHR-TPE": {
"exclude_airlines": ["CAL"],
"exclude_flights": [],
},
"FRA-TPE": {
"exclude_airlines": ["CAL", "BOX"],
"exclude_flights": [],
},
"AMS-TPE": {
"exclude_airlines": ["CAL", "KLM", "SJX"],
"exclude_flights": [],
},
"MXP-TPE": {
"exclude_airlines": ["CAL", "EVA", "SJX"],
"exclude_flights": [],
},
"GUM-TPE": {
"exclude_airlines": ["CAL", "UAL"],
"exclude_flights": [],
},
"LGW-TPE": {
"exclude_airlines": ["CAL", "EVA"],
"exclude_flights": [],
},
"VIE-TPE": {
"exclude_airlines": ["CAL", "EVA", "SJX"],
"exclude_flights": [],
},
"BKK-TPE": {
"exclude_airlines": ["CAL", "EVA", "THA", "SJX"],
"exclude_flights": [],
},
}

def get_taipei_now() -> datetime:
return datetime.now(timezone(timedelta(hours=8)))
def call_fr24_api(endpoint: str, params: dict):
query_string = urllib.parse.urlencode(params)
url = f"{BASE_URL}{endpoint}?{query_string}"
req = urllib.request.Request(
url,
headers={
"Authorization": f"Bearer {FR24_TOKEN}",
"Accept": "application/json",
"Accept-Version": "v1",
"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
},
method="GET",
)
try:
with urllib.request.urlopen(req, timeout=15) as resp:

payload = json.loads(resp.read().decode("utf-8"))

return payload.get("data", [])

except urllib.error.HTTPError as e:

print(f"[API Error] HTTP {e.code}: {e.read().decode('utf-8', errors='ignore')}")

return None

except Exception as e:

print(f"[Request Error] {e}")

return None

def send_notification(message: str) -> None:

if not WEBHOOK_URL:

print(f"[模擬通知]\n{message}")

return

data = json.dumps({"content": message}).encode("utf-8")

req = urllib.request.Request(

WEBHOOK_URL,

data=data,

headers={"Content-Type": "application/json", "User-Agent": "FR24-Tracker/1.0"},

method="POST",

)

try:

with urllib.request.urlopen(req, timeout=10) as resp:

print(f"[通知發送成功] HTTP {resp.status}")

except Exception as e:

print(f"[通知發送失敗] {e}")

def is_excluded(flight_data: dict, rule: dict) -> bool:

excl_airlines = {a.strip().upper() for a in rule.get("exclude_airlines", [])}

excl_flights = {fl.strip().upper() for fl in rule.get("exclude_flights", [])}



op_as = (flight_data.get("operating_as") or "").strip().upper()

callsign = (flight_data.get("callsign") or "").strip().upper()

flight_no = (flight_data.get("flight") or "").strip().upper()



# 1. 檢查是否屬於排除的航空公司（比對營運商 ICAO 代碼或呼號前 3 碼）

if op_as in excl_airlines:

return True

if any(callsign.startswith(code) for code in excl_airlines):

return True



# 2. 檢查是否屬於排除的特定航班號或呼號

if flight_no in excl_flights or callsign in excl_flights:

return True



return False





def main() -> None:

if not FR24_TOKEN:

raise ValueError("缺少 FR24_API_TOKEN 環境變數")



if not ROUTE_CONFIG:

print("ROUTE_CONFIG 為空，無需查詢。")

return



now_tpe = get_taipei_now()

time_str = now_tpe.strftime("%Y-%m-%d %H:%M")



# 將所有設定的航線合併為單一字串（例如 "ANC-TPE,LHR-TPE,FRA-TPE,AMS-TPE"）一次查詢

routes_query = ",".join(ROUTE_CONFIG.keys())

print(f"[{time_str}] 開始查詢航線：{routes_query}")



data = call_fr24_api("/live/flight-positions/full", {"routes": routes_query})

if data is None:

print("API 請求異常，結束本次執行。")

return



# 依航線分類儲存符合條件的班機

matched_by_route = {route: [] for route in ROUTE_CONFIG}



for f in data:

orig = (f.get("orig_iata") or "").strip().upper()

dest = (f.get("dest_iata") or "").strip().upper()

route_key = f"{orig}-{dest}"



if route_key not in ROUTE_CONFIG:

continue



rule = ROUTE_CONFIG[route_key]

if is_excluded(f, rule):

ident = f.get("flight") or f.get("callsign") or "未知"

print(f"[{route_key}] 已忽略排除班機：{ident}")

continue



matched_by_route[route_key].append(f)



# 組合通知訊息

lines = [f"✈️ **指定航線特殊航班偵測 ({time_str})**"]

total_matched = 0



for route_key, flights in matched_by_route.items():

if not flights:

continue

total_matched += len(flights)

lines.append(f"\n**【{route_key}】**")

for f in flights:

flight_no = f.get("flight") or "無航班號(貨機/包機)"

callsign = f.get("callsign") or "N/A"

ac_type = f.get("type") or "未知機型"

reg = f.get("reg") or "未知機號"

lat = f.get("lat")

lon = f.get("lon")

alt = f.get("alt")

gspeed = f.get("gspeed")



lines.append(

f"- **航班 / 呼號**：`{flight_no}` / `{callsign}`\n"

f" **機型 / 註冊號**：`{ac_type}` / `{reg}`\n"

f" **位置與動態**：({lat}, {lon})｜高度 `{alt} ft`｜地速 `{gspeed} kts`"

)

if total_matched == 0:
print(f"[{time_str}] 所有監控航線皆無符合條件的特殊航班。")
return

send_notification("\n".join(lines))

if __name__ == "__main__":

main()
