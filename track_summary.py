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
    req = urllib.request
