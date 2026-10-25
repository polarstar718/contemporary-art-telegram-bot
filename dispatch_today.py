"""
Standalone Daily Art Dispatcher for GitHub Actions, Scheduled Cron, and Testing.
Delivers Today's Artist Docent Card with direct links to Telegram subscribers.
Fast, lightweight, 100% reliable, zero copyright/payload issues.
"""

import os
import sys
import json
import logging
import time
import urllib.parse
from datetime import datetime
from pathlib import Path
import requests

# Ensure UTF-8 output on Windows
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
SUBSCRIBER_IDS_ENV = os.getenv("TELEGRAM_SUBSCRIBER_CHAT_IDS", "").strip()

if not BOT_TOKEN:
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("TELEGRAM_BOT_TOKEN="):
                BOT_TOKEN = line.split("=", 1)[1].strip()
            elif line.startswith("TELEGRAM_CHAT_ID="):
                CHAT_ID = line.split("=", 1)[1].strip()
            elif line.startswith("TELEGRAM_SUBSCRIBER_CHAT_IDS="):
                SUBSCRIBER_IDS_ENV = line.split("=", 1)[1].strip()


def send_docent_card(token: str, chat_id: str, artist: dict, curator: ArtCurator) -> bool:
    """Sends the formatted docent text card with direct visual exploration links."""
    text = curator.format_artist_intro(artist, is_today=True)
    sns = artist.get("sns", {})
    name_en = artist.get("name_en", "")
    encoded_name = urllib.parse.quote(name_en)

    instagram_url = sns.get("instagram") or f"https://www.instagram.com/explore/tags/{artist['id'].replace('-', '')}/"
    website_url = sns.get("official_website") or f"https://en.wikipedia.org/wiki/{encoded_name}"
    arts_culture_url = sns.get("arts_culture") or f"https://artsandculture.google.com/search?q={encoded_name}"

    inline_keyboard = [
        [
            {"text": "📷 인스타그램 바로가기", "url": instagram_url},
            {"text": "🌐 공식 웹사이트 / 위키", "url": website_url}
        ],
        [
            {"text": "🎨 구글 아츠 갤러리 실물 보기", "url": arts_culture_url}
        ]
    ]

    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
        "reply_markup": {
            "inline_keyboard": inline_keyboard
        }
    }

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        res = requests.post(url, json=payload, timeout=20)
        if res.status_code == 200:
            logger.info(f"Docent card successfully sent to chat {chat_id}")
            return True
        else:
            logger.error(f"Failed to send docent card to {chat_id}: {res.status_code} - {res.text}")
            return False
    except Exception as e:
        logger.error(f"Error sending message to {chat_id}: {e}")
        return False


def get_subscribers(is_test: bool = False) -> list[str]:
    """Retrieves target chat IDs: single chat for test, all subscribers for broadcast."""
    if is_test:
        return [CHAT_ID] if CHAT_ID else []

    targets = set()

    # 1. Local subscribers.json
    sub_file = BASE_DIR / "data" / "subscribers.json"
    if sub_file.exists():
        try:
            with open(sub_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    targets.update(str(s) for s in data if str(s).strip())
        except Exception as e:
            logger.warning(f"Error reading subscribers.json: {e}")

    # 2. Environment variable (GitHub Actions / Cloud)
    if SUBSCRIBER_IDS_ENV:
        for cid in SUBSCRIBER_IDS_ENV.split(","):
            cid = cid.strip()
            if cid:
                targets.add(cid)

    # 3. Fallback to primary CHAT_ID if list is empty
    if not targets and CHAT_ID:
        targets.add(CHAT_ID)

    return list(targets)


def dispatch(force: bool = False, is_test: bool = False) -> None:
    if not BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN is required.")
        sys.exit(1)

    curator = ArtCurator()

    # Verify weekday in Korea Time (Mon=0, Fri=4) unless forced or testing
    if not force and not is_test and not curator.is_weekday():
        logger.info("Today is a weekend in Korea. Skipping daily dispatch.")
        return

    today_artist = curator.get_today_artist(record_history=not is_test)
    logger.info(f"Target Artist: {today_artist['name_kr']} ({today_artist['name_en']}) [Test: {is_test}]")

    subscribers = get_subscribers(is_test=is_test)
    logger.info(f"Dispatching to {len(subscribers)} recipients: {subscribers}")

    success_count = 0
    for cid in subscribers:
        logger.info(f"--> Sending docent card to chat {cid}...")
        if send_docent_card(BOT_TOKEN, cid, today_artist, curator):
            success_count += 1
        time.sleep(0.5)

    logger.info(f"Dispatch finished! Successfully sent to {success_count}/{len(subscribers)} chats.")


if __name__ == "__main__":
    is_test_run = "--test" in sys.argv
    force_run = "--force" in sys.argv or is_test_run
    dispatch(force=force_run, is_test=is_test_run)
