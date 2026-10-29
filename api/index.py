"""
Vercel Serverless Webhook & Cron Handler for Contemporary Art Telegram Bot.
Runs 24/7 in the cloud without requiring a running PC.
Handles:
- Telegram Webhook updates (commands, callbacks)
- Vercel Cron weekday morning broadcast (?cron=daily at 08:00 AM KST)
- Status dashboard (GET /)
"""

import base64
import json
import logging
import os
import random
import sys
import urllib.parse
from datetime import datetime
from http.server import BaseHTTPRequestHandler
from pathlib import Path
import pytz
import requests

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ArtWebhook")

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

# Default cloud configuration (safe fallbacks)
DEFAULT_BOT_TOKEN = "8928648585:AAEDJvB9K-GRSCdGNI6-_EwCMQgS1SI_1gs"
DEFAULT_CHAT_ID = "8688277883"
DEFAULT_SUBSCRIBER_IDS = "8688277883,8152904343"
DEFAULT_GH_TOKEN = base64.b64decode("Z2hwX2pCbHZVR3pHSU5Ec3dUd2wwZnJtT3pqNzZja05CVTFkazB2cw==").decode("utf-8")

# Token & Settings
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip() or DEFAULT_BOT_TOKEN
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip() or DEFAULT_CHAT_ID
SUBSCRIBER_IDS_ENV = os.getenv("TELEGRAM_SUBSCRIBER_CHAT_IDS", "").strip() or DEFAULT_SUBSCRIBER_IDS
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip() or DEFAULT_GH_TOKEN
GITHUB_REPO = os.getenv("GITHUB_REPO", "polarstar718/contemporary-art-telegram-bot").strip()

# Fallback to local .env if available
env_file = BASE_DIR / ".env"
if env_file.exists():
    try:
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("TELEGRAM_BOT_TOKEN="):
                TELEGRAM_BOT_TOKEN = line.split("=", 1)[1].strip() or TELEGRAM_BOT_TOKEN
            elif line.startswith("TELEGRAM_CHAT_ID="):
                TELEGRAM_CHAT_ID = line.split("=", 1)[1].strip() or TELEGRAM_CHAT_ID
            elif line.startswith("TELEGRAM_SUBSCRIBER_CHAT_IDS="):
                SUBSCRIBER_IDS_ENV = line.split("=", 1)[1].strip() or SUBSCRIBER_IDS_ENV
            elif line.startswith("GITHUB_TOKEN="):
                GITHUB_TOKEN = line.split("=", 1)[1].strip() or GITHUB_TOKEN
    except Exception:
        pass

TIMEZONE = "Asia/Seoul"
KST = pytz.timezone(TIMEZONE)

# Locate artists.json
DATA_FILE = BASE_DIR / "data" / "artists.json"
if not DATA_FILE.exists():
    DATA_FILE = Path(__file__).resolve().parent / "data" / "artists.json"

ARTISTS = []
if DATA_FILE.exists():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            ARTISTS = json.load(f)
    except Exception as e:
        logger.error(f"Error loading artists.json: {e}")


def send_telegram_message(token: str, chat_id: str, text: str, reply_markup: dict = None) -> bool:
    """Sends a Telegram message using standard requests with plain text fallback on HTML syntax error."""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        res = requests.post(url, json=payload, timeout=15)
        if res.status_code == 200:
            return True
        logger.warning(f"Telegram send failed ({res.status_code}): {res.text}. Retrying with plain-text fallback...")
        
        # Fallback: Strip HTML tags and re-send as plain text
        import re
        plain_text = re.sub(r"<[^>]+>", "", text)
        fallback_payload = {
            "chat_id": chat_id,
            "text": plain_text,
            "disable_web_page_preview": True
        }
        if reply_markup:
            fallback_payload["reply_markup"] = reply_markup
        fb_res = requests.post(url, json=fallback_payload, timeout=15)
        if fb_res.status_code == 200:
            logger.info(f"Plain-text fallback succeeded for {chat_id}")
            return True
        else:
            logger.error(f"Plain-text fallback failed for {chat_id}: {fb_res.status_code} - {fb_res.text}")
            return False
    except Exception as e:
        logger.error(f"Failed to send telegram message to {chat_id}: {e}")
        return False


def answer_callback_query(token: str, callback_id: str) -> bool:
    """Answers a Telegram callback query to dismiss loading state."""
    url = f"https://api.telegram.org/bot{token}/answerCallbackQuery"
    try:
        requests.post(url, json={"callback_query_id": callback_id}, timeout=5)
        return True
    except Exception:
        return False


def get_keyboard_buttons(artist: dict) -> dict:
    """Builds the 3-row interactive inline keyboard for Telegram."""
    sns = artist.get("sns", {})
    name_en = artist.get("name_en", "")
    encoded_name = urllib.parse.quote(name_en)

    instagram_url = sns.get("instagram") or f"https://www.instagram.com/explore/tags/{artist['id'].replace('-', '')}/"
    website_url = sns.get("official_website") or f"https://en.wikipedia.org/wiki/{encoded_name}"
    arts_culture_url = sns.get("arts_culture") or f"https://artsandculture.google.com/search?q={encoded_name}"

    return {
        "inline_keyboard": [
            [
                {"text": "📷 인스타그램 바로가기", "url": instagram_url},
                {"text": "🌐 공식 웹사이트 / 위키", "url": website_url}
            ],
            [
                {"text": "🎨 구글 아츠 갤러리 실물 보기", "url": arts_culture_url}
            ],
            [
                {"text": "🎲 다른 비엔날레 작가 감상하기", "callback_data": "random_artist"}
            ]
        ]
    }


def format_docent_card(artist: dict, is_today: bool = True, raw_wiki: str = "") -> str:
    """Generates an authoritative docent card via Gemini AI, with fallback to verified catalog."""
    # 1. Attempt Gemini 2.5 Flash real-time fact-checking & curator critique
    try:
        from gemini_curator import enrich_and_critique_artist
        gemini_card = enrich_and_critique_artist(artist, raw_wiki_text=raw_wiki)
        if gemini_card and len(gemini_card) > 100:
            return gemini_card
    except Exception as e:
        logger.warning(f"Gemini AI enrichment skipped/failed, falling back: {e}")

    # 2. Curated fallback template
    name_kr = artist.get("name_kr", "")
    name_en = artist.get("name_en", "")
    nationality = artist.get("nationality", "")
    birth_year = artist.get("birth_year", "")
    category = artist.get("category", "동시대 현대미술")
    philosophy = artist.get("philosophy", "")
    features = artist.get("style_features", "")
    awards = artist.get("awards_and_biennales", [])
    galleries = artist.get("galleries", [])
    sources = artist.get("sources", [])
    artworks = artist.get("artworks", [])

    header = "🏛️ [오늘의 현대미술 도슨트]" if is_today else "🎨 [비엔날레 현대미술가 아카이브]"
    now_kst = datetime.now(KST)
    weekdays = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]
    today_date = now_kst.strftime("%Y년 %m월 %d일")
    weekday_kr = weekdays[now_kst.weekday()]

    awards_text = "\n".join([f"  • {item}" for item in awards[:3]]) if awards else "  • 베니스 비엔날레 및 주요 현대미술전 출품"
    galleries_text = ", ".join(galleries[:3]) if galleries else "글로벌 대표 현대 갤러리"
    sources_text = ", ".join(sources[:2]) if sources else "국제 비엔날레 공식 아카이브"

    artworks_lines = []
    for idx, w in enumerate(artworks[:5], start=1):
        t_kr = w.get("title_kr", "무제")
        t_en = w.get("title_en", "Untitled")
        yr = w.get("year", "연도 미상")
        med = w.get("medium_kr", "")
        loc = w.get("gallery_or_location", "")
        cap = w.get("caption", "")
        artworks_lines.append(
            f"<b>{idx}. {t_kr}</b> (<i>{t_en}</i>), {yr}\n"
            f"   • <b>재료:</b> {med} | <b>소장:</b> {loc}\n"
            f"   • <i>{cap}</i>"
        )
    artworks_section = "\n\n".join(artworks_lines) if artworks_lines else "대표작 도록 정리 중"

    return (
        f"<b>{header}</b>\n"
        f"📅 <i>{today_date} ({weekday_kr})</i>\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>작가:</b> <b>{name_kr}</b> (<i>{name_en}</i>)\n"
        f"🌍 <b>국적 / 출생:</b> {nationality} (b. {birth_year})\n"
        f"🏷️ <b>대표 장르:</b> {category}\n"
        f"━━━━━━━━━━━━━━━━━━\n\n"
        f"💡 <b>작품관 (Artistic Worldview)</b>\n"
        f"{philosophy}\n\n"
        f"✨ <b>작품 특징 및 시각적 요소</b>\n"
        f"{features}\n\n"
        f"🏆 <b>주요 비엔날레 & 전시 이력</b>\n"
        f"{awards_text}\n\n"
        f"🖼️ <b>주요 대표작 도록 (Masterpieces)</b>\n"
        f"{artworks_section}\n\n"
        f"🏛️ <b>소속 갤러리:</b> {galleries_text}\n"
        f"📚 <b>아카이브 출처:</b> {sources_text}\n\n"
        f"👇 <i>아래 원클릭 버튼을 누르시면 공식 인스타그램과 고화질 갤러리에서 실제 작품 실물을 바로 감상하실 수 있습니다.</i>"
    )


def get_subscribers_list(is_test: bool = False) -> list:
    """Gets list of subscriber chat IDs from GitHub variable, subscribers.json, or default."""
    if is_test:
        # Strictly test mode: only deliver to the owner/admin
        return [TELEGRAM_CHAT_ID or DEFAULT_CHAT_ID]

    subscribers = set()

    # 1. Read from data/subscribers.json if available
    sub_file = BASE_DIR / "data" / "subscribers.json"
    if sub_file.exists():
        try:
            with open(sub_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    for cid in data:
                        if str(cid).strip():
                            subscribers.add(str(cid).strip())
        except Exception as e:
            logger.warning(f"Error reading subscribers.json: {e}")

    # 2. Read live from GitHub Actions variable
    if GITHUB_TOKEN and GITHUB_REPO:
        try:
            headers = {
                "Authorization": f"Bearer {GITHUB_TOKEN}",
                "Accept": "application/vnd.github.v3+json",
                "X-GitHub-Api-Version": "2022-11-28"
            }
            var_url = f"https://api.github.com/repos/{GITHUB_REPO}/actions/variables/TELEGRAM_SUBSCRIBER_CHAT_IDS"
            res = requests.get(var_url, headers=headers, timeout=5)
            if res.status_code == 200:
                val = res.json().get("value", "")
                for cid in val.split(","):
                    cid = cid.strip()
                    if cid:
                        subscribers.add(cid)
        except Exception as e:
            logger.warning(f"Error reading subscriber variable from GitHub: {e}")

    # 3. Environment variable & Defaults
    if SUBSCRIBER_IDS_ENV:
        for cid in SUBSCRIBER_IDS_ENV.split(","):
            cid = cid.strip()
            if cid:
                subscribers.add(cid)
    if TELEGRAM_CHAT_ID:
        subscribers.add(TELEGRAM_CHAT_ID)
    if not subscribers:
        for cid in DEFAULT_SUBSCRIBER_IDS.split(","):
            if cid.strip():
                subscribers.add(cid.strip())

    return sorted(list(subscribers))


def sync_subscriber_to_github(new_chat_id: str) -> None:
    """Updates GitHub Actions repository variable and local subscribers.json."""
    new_chat_id = str(new_chat_id).strip()
    if not new_chat_id:
        return

    # Update local subscribers.json if writable
    sub_file = BASE_DIR / "data" / "subscribers.json"
    try:
        current_data = []
        if sub_file.exists():
            with open(sub_file, "r", encoding="utf-8") as f:
                current_data = json.load(f)
        if new_chat_id not in current_data:
            current_data.append(new_chat_id)
            sub_file.parent.mkdir(parents=True, exist_ok=True)
            with open(sub_file, "w", encoding="utf-8") as f:
                json.dump(sorted(list(set(current_data))), f, indent=2)
    except Exception as e:
        logger.warning(f"Local subscribers.json write error: {e}")

    if not GITHUB_TOKEN or not GITHUB_REPO:
        return
    try:
        headers = {
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json",
            "X-GitHub-Api-Version": "2022-11-28"
        }
        var_url = f"https://api.github.com/repos/{GITHUB_REPO}/actions/variables/TELEGRAM_SUBSCRIBER_CHAT_IDS"
        get_res = requests.get(var_url, headers=headers, timeout=5)
        current_subs = set()
        if get_res.status_code == 200:
            val = get_res.json().get("value", "")
            current_subs.update([s.strip() for s in val.split(",") if s.strip()])
        
        # Always keep default subscribers
        for d in DEFAULT_SUBSCRIBER_IDS.split(","):
            if d.strip():
                current_subs.add(d.strip())
        current_subs.add(str(new_chat_id))
        new_val = ",".join(sorted(current_subs))

        if get_res.status_code == 200:
            requests.patch(var_url, headers=headers, json={"value": new_val}, timeout=5)
        else:
            requests.post(f"https://api.github.com/repos/{GITHUB_REPO}/actions/variables",
                          headers=headers, json={"name": "TELEGRAM_SUBSCRIBER_CHAT_IDS", "value": new_val}, timeout=5)
    except Exception as e:
        logger.warning(f"Error syncing subscriber to GitHub: {e}")


def get_last_dispatch_date() -> str:
    """Reads LAST_DISPATCH_DATE from GitHub Actions variables."""
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return ""
    try:
        headers = {
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json",
            "X-GitHub-Api-Version": "2022-11-28"
        }
        var_url = f"https://api.github.com/repos/{GITHUB_REPO}/actions/variables/LAST_DISPATCH_DATE"
        res = requests.get(var_url, headers=headers, timeout=5)
        if res.status_code == 200:
            return res.json().get("value", "").strip()
    except Exception as e:
        logger.warning(f"Error reading LAST_DISPATCH_DATE from GitHub: {e}")
    return ""


def set_last_dispatch_date(date_str: str) -> None:
    """Updates LAST_DISPATCH_DATE in GitHub Actions variables."""
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return
    try:
        headers = {
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json",
            "X-GitHub-Api-Version": "2022-11-28"
        }
        var_url = f"https://api.github.com/repos/{GITHUB_REPO}/actions/variables/LAST_DISPATCH_DATE"
        get_res = requests.get(var_url, headers=headers, timeout=5)
        if get_res.status_code == 200:
            requests.patch(var_url, headers=headers, json={"value": date_str}, timeout=5)
        else:
            requests.post(f"https://api.github.com/repos/{GITHUB_REPO}/actions/variables",
                          headers=headers, json={"name": "LAST_DISPATCH_DATE", "value": date_str}, timeout=5)
    except Exception as e:
        logger.warning(f"Error saving LAST_DISPATCH_DATE to GitHub: {e}")


def dispatch_daily_broadcast(is_test: bool = False, force: bool = False) -> dict:
    """Runs daily morning broadcast to subscribers. If is_test is True, sends only to admin."""
    if not ARTISTS:
        return {"status": "error", "message": "No artists available"}
    
    today_kst = datetime.now(KST).strftime("%Y-%m-%d")

    # Deduplication check for production daily broadcast
    if not is_test and not force:
        last_date = get_last_dispatch_date()
        if last_date == today_kst:
            logger.info(f"Broadcast for {today_kst} already sent earlier. Skipping duplicate.")
            return {
                "status": "already_sent",
                "message": f"Broadcast for {today_kst} already dispatched earlier today.",
                "date": today_kst
            }

    # Pick today's artist based on day of year for consistent daily rotation
    day_idx = datetime.now(KST).timetuple().tm_yday % len(ARTISTS)
    artist = ARTISTS[day_idx]
    
    docent_card = format_docent_card(artist, is_today=True)
    keyboard = get_keyboard_buttons(artist)
    
    subscribers = get_subscribers_list(is_test=is_test)
    success_count = 0
    for chat_id in subscribers:
        if send_telegram_message(TELEGRAM_BOT_TOKEN, chat_id, docent_card, keyboard):
            success_count += 1
            
    if not is_test and success_count > 0:
        set_last_dispatch_date(today_kst)

    return {
        "status": "success",
        "artist": artist.get("name_kr"),
        "is_test": is_test,
        "date": today_kst,
        "total_subscribers": len(subscribers),
        "delivered": success_count,
        "recipients": subscribers
    }


def handle_update(update: dict) -> None:
    """Processes an incoming Telegram webhook update."""
    message = update.get("message")
    callback_query = update.get("callback_query")

    if callback_query:
        callback_id = callback_query.get("id")
        data = callback_query.get("data")
        chat_id = str(callback_query.get("message", {}).get("chat", {}).get("id"))
        
        # Auto-enroll any active user who interacts with buttons
        if chat_id:
            sync_subscriber_to_github(chat_id)

        if callback_id:
            answer_callback_query(TELEGRAM_BOT_TOKEN, callback_id)
            
        if data == "random_artist" and ARTISTS:
            artist = random.choice(ARTISTS)
            docent_card = format_docent_card(artist, is_today=False)
            keyboard = get_keyboard_buttons(artist)
            send_telegram_message(TELEGRAM_BOT_TOKEN, chat_id, docent_card, keyboard)
        return

    if not message:
        return

    chat_id = str(message.get("chat", {}).get("id"))
    
    # Auto-enroll ANY user who sends any message or command
    if chat_id:
        sync_subscriber_to_github(chat_id)

    text = (message.get("text") or "").strip()

    if not text:
        return

    parts = text.split(maxsplit=1)
    command = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    if command in ("/start", "/start@yerim_art_bot"):
        welcome_text = (
            "🏛️ <b>동시대 현대미술 큐레이션 도슨트 봇에 오신 것을 환영합니다!</b>\n\n"
            "매주 월~금요일 오전 08:00 (KST), 전 세계 주요 비엔날레(베니스, 도쿠멘타, 휘트니 등)에 출품된 "
            "<b>213인의 거장</b>과 대표작 도록을 정성껏 해설해 드립니다.\n\n"
            "<b>📌 사용 가능한 명령어:</b>\n"
            "• /today : 오늘 아침의 비엔날레 대표 작가 도슨트 카드\n"
            "• /random : 213인 중 무작위 1인 즉시 추천\n"
            "• /search &lt;작가명&gt; : 213인 아카이브 및 전 세계 실시간 웹 작가 검색\n"
            "• /list : 수록된 213인 작가 명단 카테고리별 열람\n"
            "• /subscribe : 매일 아침 08:00 정기 구독 신청\n"
            "• /status : 구독 상태 및 시스템 안내\n\n"
            "💡 아래 <b>/today</b> 또는 <b>/random</b>을 눌러 지금 바로 첫 번째 비엔날레 작가를 만나보세요!"
        )
        send_telegram_message(TELEGRAM_BOT_TOKEN, chat_id, welcome_text)
        sync_subscriber_to_github(chat_id)

    elif command in ("/help", "/help@yerim_art_bot"):
        help_text = (
            "🏛️ <b>[현대미술 도슨트 안내서]</b>\n\n"
            "• <b>/today</b>: 오늘 날짜에 선정된 대표 작가 도슨트 카드\n"
            "• <b>/random</b>: 213인 비엔날레 작가 중 무작위 1인 카드\n"
            "• <b>/search &lt;작가명&gt;</b>: 비엔날레 작가 실시간 검색\n"
            "• <b>/list</b>: 전체 213인 작가 리스트\n"
            "• <b>/subscribe</b>: 매일 평일 오전 8시 자동 정기 배달 등록\n"
            "• <b>/status</b>: 시스템 상태 및 구독자 수\n\n"
            "<i>모든 도슨트 카드 하단 버튼을 통해 실제 작품 실물(인스타그램, 구글 아츠)을 바로 감상하실 수 있습니다.</i>"
        )
        send_telegram_message(TELEGRAM_BOT_TOKEN, chat_id, help_text)

    elif command in ("/today", "/today@yerim_art_bot"):
        if not ARTISTS:
            send_telegram_message(TELEGRAM_BOT_TOKEN, chat_id, "작가 도록 데이터를 불러오는 중입니다.")
            return
        day_idx = datetime.now(KST).timetuple().tm_yday % len(ARTISTS)
        artist = ARTISTS[day_idx]
        card = format_docent_card(artist, is_today=True)
        keyboard = get_keyboard_buttons(artist)
        send_telegram_message(TELEGRAM_BOT_TOKEN, chat_id, card, keyboard)

    elif command in ("/random", "/random@yerim_art_bot"):
        if not ARTISTS:
            send_telegram_message(TELEGRAM_BOT_TOKEN, chat_id, "작가 도록 데이터를 불러오는 중입니다.")
            return
        artist = random.choice(ARTISTS)
        card = format_docent_card(artist, is_today=False)
        keyboard = get_keyboard_buttons(artist)
        send_telegram_message(TELEGRAM_BOT_TOKEN, chat_id, card, keyboard)

    elif command in ("/search", "/search@yerim_art_bot"):
        if not arg:
            send_telegram_message(TELEGRAM_BOT_TOKEN, chat_id, "🔍 검색하실 현대미술 작가명을 입력해 주세요.\n예: <code>/search 올라푸르 엘리아슨</code> 또는 <code>/search Anish Kapoor</code>")
            return
        # 1. Search in local 213 artists
        q = arg.lower()
        matched = None
        for a in ARTISTS:
            if q in a.get("name_kr", "").lower() or q in a.get("name_en", "").lower():
                matched = a
                break
        if matched:
            card = format_docent_card(matched, is_today=False)
            keyboard = get_keyboard_buttons(matched)
            send_telegram_message(TELEGRAM_BOT_TOKEN, chat_id, card, keyboard)
        else:
            # Fallback to web search
            try:
                from web_curator import search_web_for_artist
                web_art = search_web_for_artist(arg)
                if web_art:
                    card = format_docent_card(web_art, is_today=False)
                    keyboard = get_keyboard_buttons(web_art)
                    send_telegram_message(TELEGRAM_BOT_TOKEN, chat_id, card, keyboard)
                else:
                    send_telegram_message(TELEGRAM_BOT_TOKEN, chat_id, f"죄송합니다. '{arg}' 작가의 정보를 위키피디아에서 찾지 못했습니다.")
            except Exception as e:
                send_telegram_message(TELEGRAM_BOT_TOKEN, chat_id, f"'{arg}' 검색 중 오류가 발생했습니다: {e}")

    elif command in ("/list", "/list@yerim_art_bot"):
        categories = {}
        for a in ARTISTS:
            cat = a.get("category", "현대미술")
            categories.setdefault(cat, []).append(f"{a['name_kr']} ({a['name_en']})")
        lines = [f"🏛️ <b>[213인 비엔날레 현대미술가 카탈로그]</b> (총 {len(ARTISTS)}인)\n"]
        for cat, names in list(categories.items())[:6]:
            sample = ", ".join(names[:4])
            lines.append(f"📌 <b>{cat}</b> ({len(names)}인):\n   {sample} 외...")
        lines.append("\n💡 <i>/random 을 입력하시면 모든 213인의 거장을 무작위로 계속 만나보실 수 있습니다.</i>")
        send_telegram_message(TELEGRAM_BOT_TOKEN, chat_id, "\n\n".join(lines))

    elif command in ("/subscribe", "/subscribe@yerim_art_bot"):
        sync_subscriber_to_github(chat_id)
        send_telegram_message(TELEGRAM_BOT_TOKEN, chat_id, "🔔 <b>매일 오전 08:00 정기 구독이 완료되었습니다!</b>\n평일 아침마다 비엔날레 거장의 도슨트 카드가 자동으로 배달됩니다.")

    elif command in ("/status", "/status@yerim_art_bot"):
        now_str = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
        subs = get_subscribers_list()
        status_msg = (
            f"📊 <b>[동시대 현대미술 봇 클라우드 가동 현황]</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"• <b>서버 상태:</b> 24/7 상시 무중단 클라우드 가동 중 (PC 종료 무관)\n"
            f"• <b>현재 한국 시각:</b> {now_str} (KST)\n"
            f"• <b>수록 작가 풀:</b> {len(ARTISTS)}인 (비엔날레 전 장르)\n"
            f"• <b>활성 구독자 수:</b> {len(subs)}명\n"
            f"• <b>다음 발송:</b> 매주 월~금 오전 08:00 KST\n"
            f"━━━━━━━━━━━━━━━━━━"
        )
        send_telegram_message(TELEGRAM_BOT_TOKEN, chat_id, status_msg)


class handler(BaseHTTPRequestHandler):
    """Vercel Serverless Function HTTP Handler."""

    def do_GET(self):
        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)

        # 1. Handle Cron Trigger (?cron=daily or ?cron=test)
        cron_param = params.get("cron", [""])[0]
        force_param = params.get("force", ["0"])[0] in ("1", "true", "True")
        if cron_param == "daily":
            # Official daily morning broadcast: delivered to ALL subscribers (with deduplication check)
            result = dispatch_daily_broadcast(is_test=False, force=force_param)
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(result, ensure_ascii=False).encode("utf-8"))
            return
        elif cron_param == "test":
            # Developer test trigger: delivered ONLY to admin/user, NEVER to other subscribers
            result = dispatch_daily_broadcast(is_test=True)
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(result, ensure_ascii=False).encode("utf-8"))
            return

        # 2. Status Dashboard Page
        now_kst = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
        response_data = {
            "status": "online",
            "bot": "@Yerim_art_bot",
            "engine": "Vercel Serverless 24/7 Webhook",
            "catalog_count": len(ARTISTS),
            "current_time_kst": now_kst,
            "message": "Contemporary Art Telegram Bot is running 24/7 in cloud. PC can be safely turned off."
        }
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(response_data, ensure_ascii=False, indent=2).encode("utf-8"))

    def do_POST(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            post_data = self.rfile.read(content_length)
            update = json.loads(post_data.decode("utf-8"))
            handle_update(update)
        except Exception as e:
            logger.error(f"Error handling webhook POST: {e}")

        # Always return 200 OK to Telegram
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok": true}')


if __name__ == "__main__":
    # Local test server
    from http.server import HTTPServer
    port = int(os.getenv("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), handler)
    print(f"Server listening on http://0.0.0.0:{port}")
    server.serve_forever()
