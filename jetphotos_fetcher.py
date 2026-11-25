import re
import urllib.parse
import urllib.request


def get_latest_jetphotos(
    registration: str, high_res: bool = False, timeout: int = 10
) -> dict[str, str | None]:
    """
    從 JetPhotos 抓取指定機身註冊編號的最新照片資訊。
    """
    clean_reg = registration.strip().upper()
    page_url = f"https://www.jetphotos.com/registration/{urllib.parse.quote(clean_reg)}"

    req = urllib.request.Request(
        page_url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/128.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
        method="GET",
    )

    image_url = None
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            html = resp.read().decode("utf-8", errors="ignore")

        matches = re.findall(
            r'https://cdn\.jetphotos\.com/(?:400|full)/[^"\'\s>]+?\.(?:jpg|jpeg|png)',
            html,
            re.IGNORECASE,
        )
        if matches:
            image_url = (
                matches[0].replace("/400/", "/full/") if high_res else matches[0]
            )
    except Exception as e:
        print(f"[JetPhotos Fetch Warning] {clean_reg}: {e}")

    return {
        "registration": clean_reg,
        "image_url": image_url,
        "page_url": page_url,
    }
