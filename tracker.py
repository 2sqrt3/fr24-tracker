import os
import json
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timezone, timedelta

# 環境變數設定
FR24_TOKEN = os.environ.get("FR24_API_TOKEN", "")
WEBHOOK_URL = os.environ.get("NOTIFY_WEBHOOK_URL", "")
BASE_URL = "https://fr24api.flightradar24.com/api"
STATE_FILE = "flight_state.json"

# 追蹤目標設定
TARGET_FLIGHT = "NH851"
TARGET_REG = "JA787A"
TARGET_HEX = "84C276"  # JA787A 專屬 24-bit ICAO Hex 編碼


def get_taipei_now() -> datetime:
    return datetime.now(timezone(timedelta(hours=8)))


def load_state(today_str: str) -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
                if state.get("date") == today_str:
                    return state
        except Exception:
            pass
    # 每日初始化狀態
    return {
        "date": today_str,
        "checked_dispatch": False,
        "is_target_active": False,
        "notified_dispatch": False,
        "landed": False,
    }


def save_state(state: dict) -> None:
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
        print(f"[模擬通知] {message}")
        return

    # 支援 Discord Webhook 格式（若使用 Telegram 請改為對應 Bot API URL）
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
    today_str = now_tpe.strftime("%Y-%m-%d")
    state = load_state(today_str)

    # 若今日已確認降落，直接結束不耗點
    if state["landed"]:
        print(f"[{today_str}] 今日追蹤任務已完成，跳過查詢。")
        return

    # ==========================================
    # 階段一：確認今日派飛 (消耗 1 點)
    # ==========================================
    if not state["checked_dispatch"]:
        print(f"[{now_tpe.strftime('%H:%M')}] 執行階段一：確認 {TARGET_FLIGHT} 是否由 {TARGET_REG} 執飛...")
        # 查詢當日 UTC 00:00 至 12:00 (涵蓋台灣時間 08:00 - 20:00)
        utc_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        params = {
            "flights": TARGET_FLIGHT,
            "registrations": TARGET_REG,
            "flight_datetime_from": f"{utc_date}T00:00:00",
            "flight_datetime_to": f"{utc_date}T12:00:00",
        }
        data = call_fr24_api("/flight-summary/light", params)
        state["checked_dispatch"] = True

        if data:
            state["is_target_active"] = True
            if not state["notified_dispatch"]:
                msg = (
                    f"✈️ **派飛確認通知 ({today_str})**\n"
                    f"今日 **{TARGET_FLIGHT}** (HND → TSA) 確認由 **{TARGET_REG}** 值飛！\n"
                    f"已自動啟動在途位置追蹤。"
                )
                send_notification(msg)
                state["notified_dispatch"] = True
        else:
            print(f"[{today_str}] 今日 {TARGET_FLIGHT} 尚未起飛或非 {TARGET_REG} 執飛。")
            # 若已超過台灣時間 09:30 仍無紀錄，鎖定今日非目標機型以節省點數
            if now_tpe.hour >= 9 and now_tpe.minute >= 30:
                state["is_target_active"] = False
            else:
                # 尚未起飛（如延誤），允許下次排程再確認一次派飛
                state["checked_dispatch"] = False

        save_state(state)
        return

    # ==========================================
    # 階段二：即時位置追蹤 (僅在命中時執行，每次 6 點)
    # ==========================================
    if state["is_target_active"]:
        print(f"[{now_tpe.strftime('%H:%M')}] 執行階段二：追蹤 {TARGET_REG} ({TARGET_FLIGHT}) 即時位置...")
        live_data = call_fr24_api(
            "/live/flight-positions/light",
            {"flights": TARGET_FLIGHT, "hex": TARGET_HEX},
        )

        if live_data:
            flight = live_data[0]
            lat = flight.get("lat")
            lon = flight.get("lon")
            alt = flight.get("alt")
            gspeed = flight.get("gspeed")
            print(f"目前位置: ({lat}, {lon}), 高度: {alt} ft, 地速: {gspeed} kts")

            # 當接近台北松山機場 (25.069°N, 121.552°E) 且高度低於 5,000 呎時發送進場提醒
            if lat and lon and (24.5 <= lat <= 25.5) and (121.0 <= lon <= 122.2) and (alt is not None and alt < 5000):
                send_notification(
                    f"🛬 **進場提醒**：**{TARGET_REG}** ({TARGET_FLIGHT}) 已進入台北空域，"
                    f"目前高度 **{alt} ft**，準備降落松山機場！"
                )
                state["landed"] = True
        else:
            # 若已過台灣時間 11:30 且空中已無訊號，判定已降落並結束今日追蹤
            if now_tpe.hour >= 11 and now_tpe.minute >= 30:
                print("航班已降落，結束今日追蹤。")
                state["landed"] = True

        save_state(state)


if __name__ == "__main__":
    main()
    data = call_fr24_api("/flight-summary/light", params)
        if data is None:
            print("API 請求失敗，保留狀態待下次重試。")
            return
        state["checked_dispatch"] = True
