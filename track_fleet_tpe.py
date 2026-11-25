import os
import json
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timezone, timedelta

FR24_TOKEN = os.environ.get("FR24_API_TOKEN", "")
WEBHOOK_URL = os.environ.get("NOTIFY_WEBHOOK_URL", "")
BASE_URL = "https://fr24api.flightradar24.com/api"
STATE_FILE = "fleet_cooldown.json"

# 設定要追蹤的目標飛機註冊編號
TARGET_REGISTRATIONS = [
    "B-LRJ",
    "B-LJE",
    "B-KQU",
    "N527DN",
    "N522DZ",
    "N521DN",
]

# 設為 23.5 小時，避免隔天同一小時因排程提前數秒觸發而誤判仍在冷卻期
COOLDOWN_HOURS = 23.5


def get_taipei_now() -> datetime:
    return datetime.now(timezone(timedelta(hours=8)))


def load_cooldowns() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_cooldowns(state: dict) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


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
    cooldowns = load_cooldowns()

    # 1. 過濾掉仍在 24 小時冷卻期內的飛機
    active_targets = []
    cleaned_cooldowns = {}
    for reg in TARGET_REGISTRATIONS:
        reg_upper = reg.strip().upper()
        last_hit_str = cooldowns.get(reg_upper)
        if last_hit_str:
            last_hit_dt = datetime.fromisoformat(last_hit_str)
            elapsed_hours = (now_tpe - last_hit_dt).total_seconds() / 3600.0
            if elapsed_hours < COOLDOWN_HOURS:
                print(f"[冷卻略過] {reg_upper}（距離上次命中僅 {elapsed_hours:.1f} 小時）")
                cleaned_cooldowns[reg_upper] = last_hit_str
                continue
        active_targets.append(reg_upper)

    if not active_targets:
        print(f"[{time_str}] 所有目標機號皆在 24 小時冷卻期內，本次不呼叫 API（消耗 0 點）。")
        save_cooldowns(cleaned_cooldowns)
        return

    # 2. 將未冷卻的飛機合併為單次批次查詢
    reg_param = ",".join(active_targets)
    print(f"[{time_str}] 查詢飛往 TPE 之目標機隊 ({len(active_targets)} 架)：{reg_param}")

    data = call_fr24_api(
        "/live/flight-positions/full",
        {"registrations": reg_param, "airports": "inbound:TPE"},
    )
    if data is None:
        print("API 請求異常，保留原冷卻狀態。")
        save_cooldowns(cleaned_cooldowns)
        return

    if not data:
        print(f"[{time_str}] 目前無目標飛機正在飛往 TPE。")
        save_cooldowns(cleaned_cooldowns)
        return

    # 3. 處理命中航班、更新冷卻時間並組合通知
    lines = [f"🛬 **目標機隊飛往 TPE 偵測通知 ({time_str})**"]
    for f in data:
        reg = (f.get("reg") or "未知機號").strip().upper()
        flight_no = f.get("flight") or f.get("callsign") or "無航班號"
        ac_type = f.get("type") or "未知機型"
        orig = f.get("orig_iata") or f.get("orig_icao") or "未知出發地"
        lat = f.get("lat")
        lon = f.get("lon")
        alt = f.get("alt")

        # 記錄命中時間，啟動未來 24 小時冷卻
        cleaned_cooldowns[reg] = now_tpe.isoformat()

        lines.append(
            f"- **機號 / 機型**：`{reg}` (`{ac_type}`)\n"
            f"  **航線與班號**：`{orig} → TPE`｜航班 `{flight_no}`\n"
            f"  **即時位置**：({lat}, {lon})｜高度 `{alt} ft`（已啟動 24h 冷卻）"
        )

    save_cooldowns(cleaned_cooldowns)
    send_notification("\n".join(lines))


if __name__ == "__main__":
    main()
