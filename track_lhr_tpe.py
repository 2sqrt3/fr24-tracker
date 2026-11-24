import os
import json
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timezone, timedelta

FR24_TOKEN = os.environ.get("FR24_API_TOKEN", "")
WEBHOOK_URL = os.environ.get("NOTIFY_WEBHOOK_URL", "")
BASE_URL = "https://fr24api.flightradar24.com/api"

TARGET_ROUTE = "LHR-TPE"
EXCLUDED_FLIGHTS = {"CI82", "CI082"}
EXCLUDED_CALLSIGNS = {"CAL82", "CAL082"}


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


def main() -> None:
    if not FR24_TOKEN:
        raise ValueError("缺少 FR24_API_TOKEN 環境變數")

    now_tpe = get_taipei_now()
    time_str = now_tpe.strftime("%Y-%m-%d %H:%M")
    print(f"[{time_str}] 開始查詢 {TARGET_ROUTE} 在途航班（排除 CI82）...")

    # 使用 full 端點以取得機型 (type) 與註冊編號 (reg)
    data = call_fr24_api("/live/flight-positions/full", {"routes": TARGET_ROUTE})
    if data is None:
        print("API 請求異常，結束本次執行。")
        return

    matched_flights = []
    for f in data:
        flight_no = (f.get("flight") or "").strip().upper()
        callsign = (f.get("callsign") or "").strip().upper()

        if flight_no in EXCLUDED_FLIGHTS or callsign in EXCLUDED_CALLSIGNS:
            print(f"已忽略排除航班：{flight_no or callsign}")
            continue

        matched_flights.append(f)

    if not matched_flights:
        print(f"[{time_str}] 目前 {TARGET_ROUTE} 無非 CI82 之在途航班。")
        return

    lines = [f"✈️ **{TARGET_ROUTE} 特定航班偵測通知 ({time_str})**"]
    for f in matched_flights:
        flight_no = f.get("flight") or "無航班號"
        callsign = f.get("callsign") or "N/A"
        ac_type = f.get("type") or "未知機型"
        reg = f.get("reg") or "未知機號"
        lat = f.get("lat")
        lon = f.get("lon")
        alt = f.get("alt")
        gspeed = f.get("gspeed")

        lines.append(
            f"- **航班**：`{flight_no}` (呼號 `{callsign}`)\n"
            f"  **機型 / 註冊號**：`{ac_type}` / `{reg}`\n"
            f"  **位置與高度**：({lat}, {lon})｜高度 `{alt} ft`｜地速 `{gspeed} kts`"
        )

    send_notification("\n".join(lines))


if __name__ == "__main__":
    main()
