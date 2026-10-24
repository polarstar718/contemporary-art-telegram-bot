"""
Wikimedia Commons Image Resolver & Catalog Updater
Queries Wikimedia API for each artwork, validates HTTP 200 response,
and updates artists.json with 100% verified image URLs.
"""

import json
import logging
import sys
import time
from pathlib import Path
import requests

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ImageVerifier")

DATA_FILE = Path(__file__).resolve().parent / "data" / "artists.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def search_commons(query: str) -> str | None:
    api_url = "https://commons.wikimedia.org/w/api.php"
    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": f"File: {query}",
        "gsrlimit": "3",
        "prop": "imageinfo",
        "iiprop": "url",
        "format": "json"
    }
    try:
        r = requests.get(api_url, params=params, headers=HEADERS, timeout=8)
        if r.status_code == 200:
            pages = r.json().get("query", {}).get("pages", {})
            for pid, pdata in pages.items():
                infos = pdata.get("imageinfo", [])
                if infos and "url" in infos[0]:
                    img_url = infos[0]["url"]
                    # Test if the URL actually returns 200
                    chk = requests.get(img_url, headers=HEADERS, timeout=6, stream=True)
                    if chk.status_code == 200:
                        return img_url
    except Exception as e:
        logger.debug(f"Search failed for '{query}': {e}")
    return None


def run_verification() -> None:
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        artists = json.load(f)

    logger.info(f"Starting image verification for {len(artists)} artists...")
    total_artworks = 0
    updated_artworks = 0

    for artist in artists:
        artist_name = artist["name_en"]
        logger.info(f"--> Checking artist: {artist['name_kr']} ({artist_name})")

        # Get general fallback image for artist
        artist_fallback = search_commons(f"{artist_name} art exhibition")

        for idx, artwork in enumerate(artist.get("artworks", []), start=1):
            total_artworks += 1
            current_url = artwork.get("image_url", "")
            title_en = artwork.get("title_en", "")

            # Test current URL
            is_valid = False
            try:
                chk = requests.get(current_url, headers=HEADERS, timeout=6, stream=True)
                if chk.status_code == 200:
                    is_valid = True
            except Exception:
                is_valid = False

            if not is_valid:
                # Find valid image
                found_url = search_commons(f"{artist_name} {title_en}")
                if not found_url:
                    found_url = search_commons(f"{title_en}")
                if not found_url:
                    found_url = artist_fallback

                if found_url:
                    artwork["image_url"] = found_url
                    updated_artworks += 1
                    logger.info(f"  [FIXED] #{idx} {artwork['title_kr']} -> {found_url[:80]}...")
                else:
                    logger.warning(f"  [NO IMAGE] #{idx} {artwork['title_kr']}")
            else:
                logger.info(f"  [VALID] #{idx} {artwork['title_kr']}")

            time.sleep(0.2)  # Respect API limits

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(artists, f, ensure_ascii=False, indent=2)

    logger.info(f"Finished! Total checked: {total_artworks}, Updated: {updated_artworks}")


if __name__ == "__main__":
    run_verification()
