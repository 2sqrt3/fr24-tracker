import json
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def _fetch_from_planespotters(clean_reg: str, timeout: int) -> tuple[str | None, str]:
    api_url = f"https://api.planespotters.net/pub/photos/reg/{urllib.parse.quote(clean_reg)}"
    fallback_page = f"https://www.planespotters.net/search?q={urllib.parse.quote(clean_reg)}"
    headers = {
        **BROWSER_HEADERS,
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.planespotters.net/",
    }
    req = urllib.request.Request(api_url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        photos = data.get("photos", [])
        if photos:
            latest = photos[0]
            img_url = (
                latest.get("thumbnail_large", {}).get("src")
                or latest.get("thumbnail", {}).get("src")
            )
            page_url = latest.get("link") or fallback_page
            return img_url, page_url
    except Exception:
        pass
    return None, fallback_page


def _fetch_from_jetphotos(clean_reg: str, high_res: bool, timeout: int) -> tuple[str | None, str]:
    page_url = f"https://www.jetphotos.com/registration/{urllib.parse.quote(clean_reg)}"
    headers = {**BROWSER_HEADERS, "Referer": "https://www.jetphotos.com/"}
    req = urllib.request.Request(page_url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
        matches = re.findall(
            r'https://cdn\.jetphotos\.com/(?:400|full)/[^"\'\s>]+?\.(?:jpg|jpeg|png)',
            html,
            re.IGNORECASE,
        )
        if matches:
            img = matches[0].replace("/400/", "/full/") if high_res else matches[0]
            return img, page_url
    except Exception:
        pass
    return None, page_url


def _fetch_from_airport_data(clean_reg: str, timeout: int) -> tuple[str | None, str]:
    """從 Airport-Data.com 公開航空圖庫 API 抓取照片（對雲端 IP 友善）"""
    api_url = f"https://airport-data.com/api/ac_thumb.json?r={urllib.parse.quote(clean_reg)}&n=1"
    fallback_page = f"https://www.airport-data.com/aircraft/{urllib.parse.quote(clean_reg)}.html"
    req = urllib.request.Request(api_url, headers=BROWSER_HEADERS, method="GET")
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if data.get("status") == 200 and data.get("data"):
            first = data["data"][0]
            img_url = first.get("image")
            page_url = first.get("link") or fallback_page
            if img_url:
                return img_url, page_url
    except Exception:
        pass
    return None, fallback_page


def _fetch_from_wikimedia(clean_reg: str, timeout: int) -> tuple[str | None, str]:
    """從 Wikimedia Commons 官方 API 搜尋該機身註冊編號的最新實拍照片"""
    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": f'filetype:bitmap "{clean_reg}"',
        "gsrnamespace": "6",  # 僅搜尋檔案 (File:)
        "gsrlimit": "5",
        "prop": "imageinfo",
        "iiprop": "url",
        "iiurlwidth": "800",
        "format": "json",
    }
    api_url = f"https://commons.wikimedia.org/w/api.php?{urllib.parse.urlencode(params)}"
    fallback_page = f"https://commons.wikimedia.org/w/index.php?search={urllib.parse.quote(clean_reg)}"

    # Wikimedia 官方規範要求提供具識別性的 User-Agent
    headers = {
        "User-Agent": "FR24FlightTrackerBot/1.0 (https://github.com/actions; aviation-spotter)",
        "Accept": "application/json",
    }
    req = urllib.request.Request(api_url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        pages = data.get("query", {}).get("pages", {})
        if not pages:
            return None, fallback_page

        # 篩選標題確實包含該註冊編號的檔案，並依上傳順序（pageid 由大到小）取最新一張
        reg_compact = clean_reg.replace("-", "")
        matched_pages = []
        for page in pages.values():
            title_upper = (page.get("title") or "").upper()
            if clean_reg in title_upper or reg_compact in title_upper:
                matched_pages.append(page)

        matched_pages.sort(key=lambda p: p.get("pageid", 0), reverse=True)
        for page in matched_pages:
            info_list = page.get("imageinfo", [])
            if info_list:
                info = info_list[0]
                img_url = info.get("thumburl") or info.get("url")
                page_url = info.get("descriptionurl") or fallback_page
                if img_url:
                    return img_url, page_url
    except Exception:
        pass

    return None, fallback_page


def get_latest_jetphotos(
    registration: str, high_res: bool = False, timeout: int = 10
) -> dict[str, str | None]:
    """
    依序透過 Planespotters -> JetPhotos -> Airport-Data -> Wikimedia Commons
    取得指定機身註冊編號的實拍照片，確保在 GitHub Actions 雲端環境也能穩定回傳圖片。
    """
    clean_reg = registration.strip().upper()

    sources = [
        ("Planespotters", lambda: _fetch_from_planespotters(clean_reg, timeout)),
        ("JetPhotos", lambda: _fetch_from_jetphotos(clean_reg, high_res, timeout)),
        ("Airport-Data", lambda: _fetch_from_airport_data(clean_reg, timeout)),
        ("Wikimedia Commons", lambda: _fetch_from_wikimedia(clean_reg, timeout)),
    ]

    for source_name, fetch_fn in sources:
        img_url, page_url = fetch_fn()
        if img_url:
            print(f"[圖片取得成功] {clean_reg} (來源: {source_name})")
            return {
                "registration": clean_reg,
                "image_url": img_url,
                "page_url": page_url,
            }

    print(f"[圖片略過] {clean_reg} 目前於各公開圖庫皆無可用圖片")
    return {
        "registration": clean_reg,
        "image_url": None,
        "page_url": f"https://www.jetphotos.com/registration/{urllib.parse.quote(clean_reg)}",
    }
