import os
import json
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timezone, timedelta

FR24_TOKEN = os.environ.get("FR24_API_TOKEN", "")
WEBHOOK_URL = os.environ.get("NOTIFY_WEBHOOK_URL", "")
BASE_URL = "https://fr24api.flightradar24.com/api"
TARGETS_FILE = "targets.json"
TARGET_AIRPORT = "TPE"


def to_taipei_str(utc_iso_str: str) -> str:
    if not utc_iso_str:
        return "無紀錄"
    try:
        clean_str = utc_iso_str.replace("Z", "+00:00")
        dt_utc = datetime.fromisoformat(clean_str)
        if dt_utc.tzinfo is None:
            dt_utc = dt_utc.replace(tzinfo=timezone.utc)
        dt_tpe = dt_utc.astimezone(timezone(timedelta(hours=8)))
        return dt_tpe.strftime("%Y-%m-%d %H:%M:%S (TST)")
    except Exception:
        return utc_iso_str


def load_registrations() -> list:
    if not os.path.exists(TARGETS_FILE):
        return []
    with open(TARGETS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return [r.strip().upper() for r in data.get("registrations", []) if r.strip()]


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
            return json.loads(resp.read().decode("utf-8"))
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
    data = json.dumps({"content": message[:1950]}).encode("utf-8")
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

    regs = load_registrations()
    if not regs:
        print("targets.json 追蹤清單為空，結束執行。")
        return

    now_utc = datetime.now(timezone.utc)
    from_utc = now_utc - timedelta(hours=24)

    params = {
        "registrations": ",".join(regs[:15]),
        "flight_datetime_from": from_utc.strftime("%Y-%m-%dT%H:%M:%S"),
        "flight_datetime_to": now_utc.strftime("%Y-%m-%dT%H:%M:%S"),
    }

    print(f"回溯 {params['registrations']} 過去 24 小時紀錄...")
    res = call_fr24_api("/flight-summary/full", params)
    if res is None:
        return

    all_flights = res.get("data", [])
    report_lines = ["📡 **指定機隊過去 24 小時最後訊號日報**"]

    for reg in regs[:15]:
        reg_flights = [f for f in all_flights if (f.get("reg") or "").upper() == reg]
        if not reg_flights:
            continue

        reg_flights.sort(key=lambda x: x.get("last_seen") or x.get("first_seen") or "", reverse=True)
        latest = reg_flights[0]

        tpe_hit = any(
            (f.get("orig_iata") == TARGET_AIRPORT or f.get("dest_iata") == TARGET_AIRPORT)
            for f in reg_flights
        )
        badge = " **[TPE]** " if tpe_hit else ""
        flight_no = latest.get("flight") or latest.get("callsign") or "無航班號"
        ac_type = latest.get("type") or "未知機型"
        orig = latest.get("orig_iata") or "未知"
        dest = latest.get("dest_iata") or "未知"
        last_seen_tpe = to_taipei_str(latest.get("last_seen"))
        ended = "地面" if latest.get("flight_ended") else "空中"

        report_lines.append(
            f"\n• {badge}**`{reg}`**（`{ac_type}`｜共 `{len(reg_flights)}` 趟）\n"
            f"  └ 最後訊號：`{last_seen_tpe}`（{ended}）\n"
            f"  └ 最後航段：`{flight_no}`（`{orig} → {dest}`）"
        )

    send_notification("\n".join(report_lines))


if __name__ == "__main__":
    main()
