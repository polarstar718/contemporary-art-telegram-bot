"""
Standalone Daily Art Dispatcher for GitHub Actions, Scheduled Cron, and Testing.
Sends Today's Artist Docent Card + 10 Artwork Photos directly to Telegram.
Supports broadcasting to all registered subscribers or isolated testing.
"""

import os
import sys
import json
import logging
import io
import time
from datetime import datetime
from pathlib import Path
import requests
from PIL import Image

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

# Strictly compliant User-Agent for Wikimedia Commons
SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "ContemporaryArtBot/1.0 (https://github.com/polarstar718/contemporary-art-telegram-bot; polarstar718@artbot.org)"
})


def optimize_image_bytes(raw_bytes: bytes, max_size: int = 1280) -> bytes:
    """Resizes high-res images to max 1280px JPEG for lightning fast Telegram delivery."""
    try:
        with Image.open(io.BytesIO(raw_bytes)) as im:
            im = im.convert("RGB")
            im.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
            out_io = io.BytesIO()
            im.save(out_io, format="JPEG", quality=85, optimize=True)
            return out_io.getvalue()
    except Exception:
        return raw_bytes


def download_image(url: str) -> bytes | None:
    try:
        res = SESSION.get(url, timeout=12)
        if res.status_code == 200 and len(res.content) > 500:
            return optimize_image_bytes(res.content)
        else:
            logger.warning(f"Download status for {url}: {res.status_code} (len: {len(res.content)})")
    except Exception as e:
        logger.warning(f"Failed to download image {url}: {e}")
    return None


def send_message(token: str, chat_id: str, text: str) -> bool:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }
    try:
        res = requests.post(url, json=payload, timeout=20)
        if res.status_code == 200:
            logger.info(f"Message successfully sent to chat {chat_id}")
            return True
        else:
            logger.error(f"Failed to send message: {res.status_code} - {res.text}")
            return False
    except Exception as e:
        logger.error(f"Error sending message to {chat_id}: {e}")
        return False


def send_media_group(token: str, chat_id: str, batch: list, artist: dict, start_idx: int, curator) -> bool:
    """
    Downloads images directly into memory and uploads them via multipart/form-data.
    This completely avoids Telegram's 'WEBPAGE_CURL_FAILED' issue.
    """
    files = {}
    media = []

    for idx, artwork in enumerate(batch, start=start_idx):
        img_bytes = download_image(artwork["image_url"])
        caption = curator.format_artwork_caption(artist, artwork, idx)

        if img_bytes:
            file_key = f"photo_{idx}"
            files[file_key] = (f"photo_{idx}.jpg", img_bytes, "image/jpeg")
            media.append({
                "type": "photo",
                "media": f"attach://{file_key}",
                "caption": caption,
                "parse_mode": "HTML"
            })
        else:
            logger.warning(f"Skipping failed image for #{idx} {artwork.get('title_kr')}")

    if not media:
        logger.warning("No images could be prepared for media group.")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMediaGroup"
    try:
        res = requests.post(
            url,
            data={"chat_id": chat_id, "media": json.dumps(media)},
            files=files if files else None,
            timeout=60
        )
        if res.status_code == 200:
            logger.info(f"Media group (album of {len(media)} photos) delivered to chat {chat_id}")
            return True
        else:
            logger.warning(f"sendMediaGroup returned {res.status_code}: {res.text}")
            return False
    except Exception as e:
        logger.error(f"Failed to deliver media group to {chat_id}: {e}")
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

    # 2. Environment variable (useful in GitHub Actions / cloud)
    if SUBSCRIBER_IDS_ENV:
        for cid in SUBSCRIBER_IDS_ENV.split(","):
            cid = cid.strip()
            if cid:
                targets.add(cid)

    # 3. Fallback to primary CHAT_ID if list is otherwise empty
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

    # 1. Prepare Docent Intro
    intro_html = curator.format_artist_intro(today_artist, is_today=True)

    # 2. Prepare 1st Batch of 10 Artworks
    batch, has_next, start_idx, total = curator.get_artworks_batch(today_artist, page=1, batch_size=10)

    # 3. Prepare Closing Note
    closing_note = (
        f"✨ <b>{today_artist['name_kr']}</b> (<i>{today_artist['name_en']}</i>) 작가의 대표작 10점 전송을 완료했습니다.\n\n"
        f"💡 <i>PC가 켜져 있을 때 텔레그램에서 <b>@Yerim_art_bot</b> 에게 /today 또는 /random 을 입력하시면 "
        f"전체 {total}점의 추가 도록과 다른 작가들의 작품도 실시간으로 감상하실 수 있습니다.</i>"
    )

    success_count = 0
    for cid in subscribers:
        logger.info(f"--> Sending artist package to chat {cid}...")
        # Step A: Intro message
        send_message(BOT_TOKEN, cid, intro_html)
        time.sleep(0.5)

        # Step B: Photo Album
        if batch:
            send_media_group(BOT_TOKEN, cid, batch, today_artist, start_idx, curator)
            time.sleep(0.5)

        # Step C: Closing note
        send_message(BOT_TOKEN, cid, closing_note)
        success_count += 1
        time.sleep(1.0)  # Gentle rate limit between subscribers

    logger.info(f"Dispatch finished! Successfully sent to {success_count}/{len(subscribers)} chats.")


if __name__ == "__main__":
    is_test_run = "--test" in sys.argv
    force_run = "--force" in sys.argv or is_test_run
    dispatch(force=force_run, is_test=is_test_run)
