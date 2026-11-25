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

# 1. 設定要追蹤的目標飛機註冊編號
TARGET_REGISTRATIONS = [
    "B-LRJ",
    "B-LJE",
    "B-KQU",
    "N527DN",
    "N522DZ",
    "N521DN",
]
# 2. 設定要追蹤的目標航空公司 3 碼 ICAO 代碼（可逗號擴充多間）
TARGET_AIRLINES_ICAO = [
    "BAW","AUA","TUI","DLH","NOS",
]

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


def is_in_cooldown(key: str, cooldowns: dict, now_tpe: datetime, cleaned_out: dict) -> bool:
    last_hit_str = cooldowns.get(key)
    if not last_hit_str:
        return False
    try:
        last_hit_dt = datetime.fromisoformat(last_hit_str)
        elapsed_hours = (now_tpe - last_hit_dt).total_seconds() / 3600.0
        if elapsed_hours < COOLDOWN_HOURS:
            cleaned_out[key] = last_hit_str
            return True
    except Exception:
        pass
    return False


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


def format_flight_line(f: dict, tag: str) -> str:
    reg = (f.get("reg") or "未知機號").strip().upper()
    flight_no = f.get("flight") or f.get("callsign") or "無航班號"
    operator = (f.get("operating_as") or "未知").strip().upper()
    ac_type = f.get("type") or "未知機型"
    orig = f.get("orig_iata") or f.get("orig_icao") or "未知出發地"
    lat = f.get("lat")
    lon = f.get("lon")
    alt = f.get("alt")

    return (
        f"- **[{tag}] 機號 / 機型**：`{reg}` (`{ac_type}`)｜營運商 `{operator}`\n"
        f"  **航線與班號**：`{orig} → TPE`｜航班 `{flight_no}`\n"
        f"  **即時位置**：({lat}, {lon})｜高度 `{alt} ft`"
    )


def main() -> None:
    if not FR24_TOKEN:
        raise ValueError("缺少 FR24_API_TOKEN 環境變數")

    now_tpe = get_taipei_now()
    time_str = now_tpe.strftime("%Y-%m-%d %H:%M")
    cooldowns = load_cooldowns()
    cleaned_cooldowns = {}
    notify_lines = []

    # ====================================================
    # 任務 A：查詢 10 架指定機號飛往 TPE（先剔除冷卻名單）
    # ====================================================
    active_regs = []
    for reg in TARGET_REGISTRATIONS:
        reg_upper = reg.strip().upper()
        if is_in_cooldown(reg_upper, cooldowns, now_tpe, cleaned_cooldowns):
            print(f"[冷卻略過] {reg_upper} 仍在 24 小時冷卻期內")
        else:
            active_regs.append(reg_upper)

    if active_regs:
        reg_param = ",".join(active_regs)
        print(f"[{time_str}] 查詢指定機隊 ({len(active_regs)} 架) 飛往 TPE：{reg_param}")
        reg_data = call_fr24_api(
            "/live/flight-positions/full",
            {"registrations": reg_param, "airports": "inbound:TPE"},
        )
        if reg_data:
            for f in reg_data:
                reg = (f.get("reg") or f.get("fr24_id") or "UNKNOWN").strip().upper()
                cleaned_cooldowns[reg] = now_tpe.isoformat()
                notify_lines.append(format_flight_line(f, "指定機號"))
    else:
        print(f"[{time_str}] 所有指定機號皆在冷卻期內，跳過任務 A。")

    # ====================================================
    # 任務 B：查詢指定航空公司（如 BAW）所有飛往 TPE 之班機
    # ====================================================
    if TARGET_AIRLINES_ICAO:
        airline_param = ",".join(a.strip().upper() for a in TARGET_AIRLINES_ICAO)
        print(f"[{time_str}] 查詢目標航空 ({airline_param}) 飛往 TPE 之航班...")
        airline_data = call_fr24_api(
            "/live/flight-positions/full",
            {"operating_as": airline_param, "airports": "inbound:TPE"},
        )
        if airline_data:
            for f in airline_data:
                # 優先以機號作為冷卻鍵值（與任務 A 共用，避免重複通知），無機號時退回 fr24_id
                cooldown_key = (f.get("reg") or f.get("fr24_id") or "").strip().upper()
                if cooldown_key and is_in_cooldown(cooldown_key, cooldowns, now_tpe, cleaned_cooldowns):
                    print(f"[冷卻略過] 目標航空航班 {cooldown_key} 已於 24 小時內通知過")
                    continue
                if cooldown_key:
                    cleaned_cooldowns[cooldown_key] = now_tpe.isoformat()
                notify_lines.append(format_flight_line(f, f"目標航空 {airline_param}"))

    # 儲存最新冷卻狀態並發送整合通知
    save_cooldowns(cleaned_cooldowns)

    if notify_lines:
        header = f"🛬 **TPE 特定航班偵測通知 ({time_str})**\n"
        send_notification(header + "\n".join(notify_lines))
    else:
        print(f"[{time_str}] 本次檢查無新增命中航班。")


if __name__ == "__main__":
    main()
