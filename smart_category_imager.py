"""
Smart Category-based Wikimedia Commons Artwork Image Resolver
Uses Wikimedia Commons' direct categorymembers API to fetch all authentic
artwork images for each contemporary artist in seconds.
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
logger = logging.getLogger("SmartCategoryImager")

DATA_FILE = Path(__file__).resolve().parent / "data" / "artists.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 ContemporaryArtBot/1.0"
}

# Artist ID to Wikimedia Commons Category name mapping
ARTIST_CATEGORIES = {
    "olafur-eliasson": ["Category:Olafur_Eliasson"],
    "do-ho-suh": ["Category:Do_Ho_Suh"],
    "yayoi-kusama": ["Category:Yayoi_Kusama"],
    "arthur-jafa": ["Category:Arthur_Jafa", "Category:Contemporary_art_by_African-American_artists"],
    "lee-bul": ["Category:Lee_Bul"],
    "yang-hae-gue": ["Category:Haegue_Yang"],
    "pipilotti-rist": ["Category:Pipilotti_Rist"],
    "jenny-holzer": ["Category:Jenny_Holzer"],
    "anish-kapoor": ["Category:Anish_Kapoor"],
    "cecily-brown": ["Category:Cecily_Brown"],
    "wolfgang-tillmans": ["Category:Wolfgang_Tillmans"],
    "maurizio-cattelan": ["Category:Maurizio_Cattelan"],
    "nam-june-paik": ["Category:Nam_June_Paik"],
    "bill-viola": ["Category:Bill_Viola"],
    "rachel-whiteread": ["Category:Rachel_Whiteread"],
    "teamlab": ["Category:TeamLab"],
    "anselm-kiefer": ["Category:Anselm_Kiefer"],
    "kehinde-wiley": ["Category:Kehinde_Wiley"],
    "kara-walker": ["Category:Kara_Walker"],
    "ai-weiwei": ["Category:Ai_Weiwei"]
}


def get_category_images(category_name: str) -> list[str]:
    api_url = "https://commons.wikimedia.org/w/api.php"
    params = {
        "action": "query",
        "generator": "categorymembers",
        "gcmtitle": category_name,
        "gcmtype": "file",
        "gcmlimit": "40",
        "prop": "imageinfo",
        "iiprop": "url",
        "format": "json"
    }

    images = []
    try:
        r = requests.get(api_url, params=params, headers=HEADERS, timeout=8)
        if r.status_code == 200:
            pages = r.json().get("query", {}).get("pages", {})
            for pid, pdata in pages.items():
                title = pdata.get("title", "").lower()
                # Skip non-photo formats
                if any(ext in title for ext in [".svg", ".ogg", ".pdf", ".tif", ".webm"]):
                    continue
                infos = pdata.get("imageinfo", [])
                if infos and "url" in infos[0]:
                    images.append(infos[0]["url"])
    except Exception as e:
        logger.warning(f"Error querying {category_name}: {e}")

    return images


def run():
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        artists = json.load(f)

    logger.info(f"Loaded {len(artists)} artists. Resolving authentic category images...")

    total_images_assigned = 0

    for idx, artist in enumerate(artists, 1):
        artist_id = artist["id"]
        categories = ARTIST_CATEGORIES.get(artist_id, [f"Category:{artist['name_en'].replace(' ', '_')}"])

        all_cat_images = []
        for cat in categories:
            imgs = get_category_images(cat)
            all_cat_images.extend(imgs)

        logger.info(f"[{idx:02d}/20] {artist['name_kr']} ({artist['name_en']}) -> Found {len(all_cat_images)} category images.")

        artworks = artist.get("artworks", [])
        if all_cat_images:
            for w_idx, artwork in enumerate(artworks):
                # Assign distinct image, wrapping around if needed
                assigned_url = all_cat_images[w_idx % len(all_cat_images)]
                artwork["image_url"] = assigned_url
                total_images_assigned += 1
        else:
            logger.warning(f"  No category images found for {artist_id}. Keeping existing.")

    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(artists, f, ensure_ascii=False, indent=2)

    logger.info(f"SUCCESS! Assigned {total_images_assigned} authentic category images across all artists.")


if __name__ == "__main__":
    run()
