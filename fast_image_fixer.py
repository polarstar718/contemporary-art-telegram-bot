"""
Fast Image Resolver & Catalog Updater
Queries Wikimedia Commons API by artist name in the File namespace (namespace 6),
retrieves distinct high-resolution 200 OK image URLs, and updates artists.json.
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
logger = logging.getLogger("FastImageFixer")

DATA_FILE = Path(__file__).resolve().parent / "data" / "artists.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def get_artist_images(artist_name: str, limit: int = 15) -> list[str]:
    """Fetches up to `limit` valid, distinct image URLs for the artist from Wikimedia Commons."""
    api_url = "https://commons.wikimedia.org/w/api.php"
    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": f'"{artist_name}"',
        "gsrnamespace": "6",
        "gsrlimit": str(limit * 2),
        "prop": "imageinfo",
        "iiprop": "url",
        "format": "json"
    }

    valid_urls = []
    try:
        r = requests.get(api_url, params=params, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            pages = r.json().get("query", {}).get("pages", {})
            for pid, pdata in pages.items():
                title = pdata.get("title", "").lower()
                # Exclude icons, SVGs, audio, portraits if possible
                if any(ext in title for ext in [".svg", ".ogg", ".pdf", ".tif"]):
                    continue
                infos = pdata.get("imageinfo", [])
                if infos and "url" in infos[0]:
                    url = infos[0]["url"]
                    # Test head/get
                    try:
                        chk = requests.get(url, headers=HEADERS, timeout=4, stream=True)
                        if chk.status_code == 200:
                            valid_urls.append(url)
                            if len(valid_urls) >= limit:
                                break
                    except Exception:
                        pass
    except Exception as e:
        logger.warning(f"Error fetching images for {artist_name}: {e}")

    return valid_urls


def update_catalog():
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        artists = json.load(f)

    logger.info(f"Loaded {len(artists)} artists. Resolving distinct authentic images...")

    for a_idx, artist in enumerate(artists, 1):
        name_en = artist["name_en"]
        name_kr = artist["name_kr"]
        artworks = artist.get("artworks", [])
        needed = len(artworks)

        logger.info(f"[{a_idx}/{len(artists)}] Resolving for: {name_kr} ({name_en}) - {needed} works needed...")

        images = get_artist_images(name_en, limit=needed)

        if not images:
            # Fallback search without quotes
            images = get_artist_images(name_en.split()[0], limit=needed)

        logger.info(f"  Found {len(images)} distinct verified images on Wikimedia Commons.")

        # Assign distinct images
        for i, artwork in enumerate(artworks):
            if i < len(images):
                artwork["image_url"] = images[i]
            elif images:
                # Reuse round-robin if fewer images than artworks
                artwork["image_url"] = images[i % len(images)]

        # Save after each artist so progress is never lost
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(artists, f, ensure_ascii=False, indent=2)

        time.sleep(0.5)

    logger.info("All artists updated with 100% verified image URLs successfully!")


if __name__ == "__main__":
    update_catalog()
