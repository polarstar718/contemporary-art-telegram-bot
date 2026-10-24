"""
Standalone Daily Art Dispatcher for GitHub Actions and Scheduled Jobs.
Sends Today's Artist Docent Card + 10 Artwork Photos directly to Telegram.
Runs seamlessly in headless / serverless cloud environments.
"""

import os
import sys
import json
import logging
from datetime import datetime
from pathlib import Path
import requests

# Ensure UTF-8 output
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ArtDispatcher")

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from curator import ArtCurator

# Load configuration from environment or .env
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

if not BOT_TOKEN:
    # Try reading from .env if present
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("TELEGRAM_BOT_TOKEN="):
                BOT_TOKEN = line.split("=", 1)[1].strip()
            elif line.startswith("TELEGRAM_CHAT_ID="):
                CHAT_ID = line.split("=", 1)[1].strip()


def send_message(token: str, chat_id: str, text: str) -> bool:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }
    res = requests.post(url, json=payload, timeout=20)
    if res.status_code == 200:
        logger.info(f"Intro message successfully sent to chat {chat_id}")
        return True
    else:
        logger.error(f"Failed to send intro message: {res.status_code} - {res.text}")
        return False


def send_media_group(token: str, chat_id: str, media_list: list) -> bool:
    url = f"https://api.telegram.org/bot{token}/sendMediaGroup"
    payload = {
        "chat_id": chat_id,
        "media": media_list
    }
    res = requests.post(url, json=payload, timeout=30)
    if res.status_code == 200:
        logger.info(f"Media group (album of {len(media_list)} photos) successfully sent to chat {chat_id}")
        return True
    else:
        logger.warning(f"sendMediaGroup returned {res.status_code}: {res.text}. Retrying individual photos...")
        # Fallback: send individual photos
        for item in media_list:
            photo_url = item["media"]
            caption = item.get("caption", "")
            p_res = requests.post(
                f"https://api.telegram.org/bot{token}/sendPhoto",
                json={"chat_id": chat_id, "photo": photo_url, "caption": caption, "parse_mode": "HTML"},
                timeout=15
            )
            if p_res.status_code != 200:
                logger.warning(f"Failed photo {photo_url}: {p_res.status_code}")
        return True


def dispatch() -> None:
    if not BOT_TOKEN or not CHAT_ID:
        logger.error("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are required.")
        sys.exit(1)

    curator = ArtCurator()

    # Verify weekday in Korea Time (Mon=0, Fri=4)
    if not curator.is_weekday():
        logger.info("Today is a weekend in Korea. Skipping daily dispatch.")
        return

    today_artist = curator.get_today_artist(record_history=True)
    logger.info(f"Today's Featured Artist: {today_artist['name_kr']} ({today_artist['name_en']})")

    # 1. Send Docent Intro Message
    intro_html = curator.format_artist_intro(today_artist, is_today=True)
    send_message(BOT_TOKEN, CHAT_ID, intro_html)

    # 2. Prepare 1st Batch of 10 Artworks
    batch, has_next, start_idx, total = curator.get_artworks_batch(today_artist, page=1, batch_size=10)

    media_list = []
    for idx, artwork in enumerate(batch, start=start_idx):
        caption = curator.format_artwork_caption(today_artist, artwork, idx)
        media_list.append({
            "type": "photo",
            "media": artwork["image_url"],
            "caption": caption,
            "parse_mode": "HTML"
        })

    if media_list:
        send_media_group(BOT_TOKEN, CHAT_ID, media_list)

    # 3. Send Closing Summary Note
    closing_note = (
        f"✨ <b>{today_artist['name_kr']}</b> (<i>{today_artist['name_en']}</i>) 작가의 대표작 10점 전송을 완료했습니다.\n\n"
        f"💡 <i>PC가 켜져 있을 때 텔레그램에서 <b>@Yerim_art_bot</b> 에게 /today 또는 /random 을 입력하시면 "
        f"전체 {total}점의 추가 도록과 다른 작가들의 작품도 실시간으로 감상하실 수 있습니다.</i>"
    )
    send_message(BOT_TOKEN, CHAT_ID, closing_note)
    logger.info("Daily art dispatch completed successfully!")


if __name__ == "__main__":
    dispatch()
