from jetphotos_fetcher import get_latest_jetphotos

photo = get_latest_jetphotos("JA787A")

if photo["image_url"]:
    print("圖片直連:", photo["image_url"])
    print("圖庫頁面:", photo["page_url"])
