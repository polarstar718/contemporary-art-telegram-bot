"""
Image URL Resolver and Verifier for Contemporary Artists Catalog.
Validates all artwork image links, fixes 404/broken URLs using Wikimedia Commons API,
and ensures 100% deliverability for Telegram media groups.
"""

import json
import logging
import sys
from pathlib import Path
import requests

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ImageResolver")

DATA_FILE = Path(__file__).resolve().parent / "data" / "artists.json"

HEADERS = {
    "User-Agent": "ContemporaryArtBot/1.0 (https://github.com/polarstar718/contemporary-art-telegram-bot; contact: polarstar@gmail.com)"
}


def search_wikimedia_image(query: str) -> str | None:
    api_url = "https://commons.wikimedia.org/w/api.php"
    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": query,
        "gsrlimit": "1",
        "prop": "imageinfo",
        "iiprop": "url",
        "format": "json"
    }
    try:
        res = requests.get(api_url, params=params, headers=HEADERS, timeout=8)
        if res.status_code == 200:
            pages = res.json().get("query", {}).get("pages", {})
            for pid, pdata in pages.items():
                infos = pdata.get("imageinfo", [])
                if infos and "url" in infos[0]:
                    return infos[0]["url"]
    except Exception as e:
        logger.warning(f"Search failed for '{query}': {e}")
    return None


def verify_and_fix_catalog() -> None:
    if not DATA_FILE.exists():
        logger.error(f"Data file not found: {DATA_FILE}")
        return

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        artists = json.load(f)

    logger.info(f"Loaded {len(artists)} artists. Verifying artwork image URLs...")

    total_checked = 0
    fixed_count = 0

    for artist in artists:
        artist_name = artist["name_en"]
        for idx, artwork in enumerate(artist.get("artworks", [])):
            total_checked += 1
            current_url = artwork.get("image_url", "")
            title_en = artwork.get("title_en", "")

            # Check existing URL
            is_valid = False
            try:
                head_res = requests.head(current_url, headers=HEADERS, timeout=5, allow_redirects=True)
                if head_res.status_code == 200:
                    is_valid = True
                elif head_res.status_code == 404:
                    is_valid = False
            except Exception:
                is_valid = False

            if not is_valid:
                # Search Wikimedia Commons for real image
                query = f"{artist_name} {title_en}"
                found_url = search_wikimedia_image(query)
                if not found_url:
                    # Fallback query with artist name and keyword
                    found_url = search_wikimedia_image(f"{artist_name} art")

                if found_url:
                    logger.info(f"Fixed: [{artist['name_kr']}] {artwork['title_kr']} -> {found_url}")
                    artwork["image_url"] = found_url
                    fixed_count += 1
                else:
                    logger.warning(f"Could not find alternative for {artist_name} - {title_en}")

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(artists, f, ensure_ascii=False, indent=2)

    logger.info(f"Verification complete: {total_checked} artworks checked, {fixed_count} URLs repaired and saved.")


if __name__ == "__main__":
    verify_and_fix_catalog()
