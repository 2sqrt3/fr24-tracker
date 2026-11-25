import json
import re
import urllib.error
import urllib.parse
import urllib.request


def _fetch_from_jetphotos(clean_reg: str, high_res: bool, timeout: int) -> tuple[str | None, str]:
    page_url = f"https://www.jetphotos.com/registration/{urllib.parse.quote(clean_reg)}"
    req = urllib.request.Request(
        page_url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.jetphotos.com/",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
        },
        method="GET",
    )
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
    except urllib.error.HTTPError as e:
        print(f"[JetPhotos 略過 ({e.code})] {clean_reg}，自動切換至 Planespotters API...")
    except Exception as e:
        print(f"[JetPhotos 略過] {clean_reg}: {e}")

    return None, page_url


def _fetch_from_planespotters(clean_reg: str, timeout: int) -> tuple[str | None, str]:
    """使用 Planespotters.net 官方公開 JSON API 取得最新飛機照片（支援雲端 IP）"""
    api_url = f"https://api.planespotters.net/pub/photos/reg/{urllib.parse.quote(clean_reg)}"
    fallback_page = f"https://www.planespotters.net/search?q={urllib.parse.quote(clean_reg)}"
    req = urllib.request.Request(
        api_url,
        headers={
            "User-Agent": "FR24-Discord-Tracker/1.0",
            "Accept": "application/json",
        },
        method="GET",
    )
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
    except Exception as e:
        print(f"[Planespotters 略過] {clean_reg}: {e}")

    return None, fallback_page


def get_latest_jetphotos(
    registration: str, high_res: bool = False, timeout: int = 10
) -> dict[str, str | None]:
    """
    取得指定機身註冊編號的最新照片資訊：
    優先嘗試 JetPhotos，若雲端 IP 遭 403 阻擋則自動無縫切換至 Planespotters 官方 API。
    """
    clean_reg = registration.strip().upper()

    # 1. 優先嘗試 JetPhotos
    image_url, page_url = _fetch_from_jetphotos(clean_reg, high_res, timeout)

    # 2. 若 JetPhotos 回傳 403 或無照片，改用 Planespotters 官方 API
    if not image_url:
        image_url, page_url = _fetch_from_planespotters(clean_reg, timeout)

    return {
        "registration": clean_reg,
        "image_url": image_url,
        "page_url": page_url,
    }
