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
