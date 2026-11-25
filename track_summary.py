import os
import json
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timezone, timedelta

FR24_TOKEN = os.environ.get("FR24_API_TOKEN", "")
WEBHOOK_URL = os.environ.get("NOTIFY_WEBHOOK_URL", "")
BASE_URL = "https://fr24api.flightradar24.com/api"
STATE_FILE = "summary_state.json"

# ==========================================
# 在此維護要監控的 ICAO 呼號清單（可隨時增減）
# ==========================================
TARGET_CALLSIGNS = [
"ANA9415",
"AUA1477",
"BAW9172",
]

def get_taipei_now() -> datetime:
return datetime.now(timezone(timedelta(hours=8)))

def format_utc_to_tpe(iso_str: str) -> str:
if not iso_str:
return "未知 / 飛行中"
try:
dt_utc = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
dt_tpe = dt_utc.astimezone(timezone(timedelta(hours=8)))
return dt_tpe.strftime("%m-%d %H:%M (TPE)")
except Exception:
return iso_str

def load_notified_ids() -> dict:
if os.path.exists(STATE_FILE):
try:
with open(STATE_FILE, "r", encoding="utf-8") as f:
data = json.load(f)

# 自動清理超過 7 天的舊紀錄，保持快取輕量

cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).timestamp()

return {k: v for k, v in data.items() if v > cutoff}

except Exception:

pass

return {}

def save_notified_ids(notified_ids: dict) -> None:

with open(STATE_FILE, "w", encoding="utf-8") as f:

json.dump(notified_ids, f, ensure_ascii=False, indent=2)

def chunk_list(items: list, size: int = 15):

for i in range(0, len(items), size):

yield items[i : i + size]

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





def main() -> None:

if not FR24_TOKEN:

raise ValueError("缺少 FR24_API_TOKEN 環境變數")



now_utc = datetime.now(timezone.utc)

now_tpe = get_taipei_now()

time_str = now_tpe.strftime("%Y-%m-%d %H:%M")



# 查詢過去 24 小時內的飛航摘要，避免跨時段漏抓

dt_from = (now_utc - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%S")

dt_to = now_utc.strftime("%Y-%m-%dT%H:%M:%S")



print(f"[{time_str}] 開始掃描目標呼號清單（共 {len(TARGET_CALLSIGNS)} 組）...")

notified_ids = load_notified_ids()

new_flights = []



# FR24 API 單次最多支援 15 組逗號分隔呼號

for batch in chunk_list(TARGET_CALLSIGNS, 15):

params = {

"callsigns": ",".join(batch),

"flight_datetime_from": dt_from,

"flight_datetime_to": dt_to,

}

records = call_fr24_api("/flight-summary/light", params)

if records is None:

print("API 請求異常，跳過此批次。")

continue



for item in records:

fr24_id = str(item.get("fr24_id") or "")

if not fr24_id or fr24_id in notified_ids:

continue

new_flights.append(item)

notified_ids[fr24_id] = now_utc.timestamp()



if not new_flights:

print(f"[{time_str}] 無新增之目標航班紀錄。")

save_notified_ids(notified_ids)

return



lines = [f"📡 **不定期／特定航班飛航偵測 ({time_str})**"]

for f in new_flights:

callsign = f.get("callsign") or "N/A"

flight_no = f.get("flight") or "無航班號"

ac_type = f.get("type") or "未知機型"

reg = f.get("reg") or "未知機號"

orig = f.get("orig_iata") or f.get("orig_icao") or "未知"

dest = f.get("dest_iata") or f.get("dest_icao") or "未知"

takeoff = format_utc_to_tpe(f.get("datetime_takeoff"))

landed = format_utc_to_tpe(f.get("datetime_landed"))



lines.append(

f"- **呼號 / 航班**：`{callsign}` (`{flight_no}`)\n"

f" **機型 / 註冊號**：`{ac_type}` / `{reg}`\n"

f" **航線**：`{orig}` → `{dest}`\n"

f" **起飛 / 降落**：{takeoff} ～ {landed}"

)



send_notification("\n".join(lines))

save_notified_ids(notified_ids)





if __name__ == "__main__":

main()
