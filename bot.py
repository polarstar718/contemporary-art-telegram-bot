"""
Contemporary Art Daily Telegram Bot
Main Bot Application with PTB 22+ and APScheduler.
Delivers world-class contemporary artists (200+ Biennial Masters) every weekday at 08:00 AM KST.
Features rich docent cards, one-click visual links, real-time web search, and zero copyright issues.
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Set

# Ensure UTF-8 console output on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import pytz
import requests
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from config import (
    DELIVERY_HOUR,
    DELIVERY_MINUTE,
    SUBSCRIBERS_FILE,
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    TIMEZONE,
)
from curator import ArtCurator

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("ArtBot")

# Initialize Curator
curator = ArtCurator()


class SubscriberManager:
    """Manages chat IDs subscribed to weekday 08:00 AM broadcasts."""

    def __init__(self, filepath: Path):
        self.filepath = filepath
        self.subscribers: Set[str] = self._load()

        if TELEGRAM_CHAT_ID:
            self.subscribers.add(str(TELEGRAM_CHAT_ID))
            self._save()

    def _load(self) -> Set[str]:
        if not self.filepath.exists():
            return set()
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                return set(str(cid) for cid in data)
        except Exception as e:
            logger.error(f"Failed to load subscribers: {e}")
            return set()

    def _save(self) -> None:
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump(list(self.subscribers), f, ensure_ascii=False, indent=2)
            sync_subscribers_to_github(list(self.subscribers))
        except Exception as e:
            logger.error(f"Failed to save subscribers: {e}")

    def add(self, chat_id: str) -> bool:
        cid = str(chat_id)
        if cid not in self.subscribers:
            self.subscribers.add(cid)
            self._save()
            return True
        return False

    def remove(self, chat_id: str) -> bool:
        cid = str(chat_id)
        if cid in self.subscribers:
            self.subscribers.remove(cid)
            self._save()
            return True
        return False

    def get_all(self) -> Set[str]:
        return set(self.subscribers)


# GitHub Actions subscriber sync helper
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "").strip()
GITHUB_REPO = os.getenv("GITHUB_REPO", "polarstar718/contemporary-art-telegram-bot").strip()

def _sync_github_worker(subs: list[str]) -> None:
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return
    try:
        val = ",".join(subs)
        headers = {
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json",
            "X-GitHub-Api-Version": "2022-11-28"
        }
        url = f"https://api.github.com/repos/{GITHUB_REPO}/actions/variables/TELEGRAM_SUBSCRIBER_CHAT_IDS"
        r = requests.patch(url, headers=headers, json={"value": val}, timeout=8)
        if r.status_code == 404:
            create_url = f"https://api.github.com/repos/{GITHUB_REPO}/actions/variables"
            requests.post(create_url, headers=headers, json={"name": "TELEGRAM_SUBSCRIBER_CHAT_IDS", "value": val}, timeout=8)
        logger.info(f"Synchronized {len(subs)} subscribers to GitHub Actions cloud variable.")
    except Exception as e:
        logger.warning(f"Failed to sync subscribers to GitHub: {e}")

def sync_subscribers_to_github(subs: list[str]) -> None:
    import threading
    threading.Thread(target=_sync_github_worker, args=(subs,), daemon=True).start()


subscriber_mgr = SubscriberManager(SUBSCRIBERS_FILE)


# ---------------------------------------------------------------------------
# Message Sending Helper Functions
# ---------------------------------------------------------------------------

async def send_artist_package(
    bot,
    chat_id: int | str,
    artist: dict,
    is_today: bool = True,
) -> None:
    """
    Sends the complete Artist Package:
    Polite Korean Docent Card with Profile, Worldview, Style, Curated Masterpieces,
    and 3-Row Interactive Buttons (Instagram, Website, Google Arts, Random Artist).
    Fast, lightweight, 100% reliable.
    """
    text = curator.format_artist_intro(artist, is_today=is_today)
    buttons = curator.get_artist_keyboard_buttons(artist)
    reply_markup = InlineKeyboardMarkup(buttons)

    await bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
        reply_markup=reply_markup,
    )


# ---------------------------------------------------------------------------
# Bot Command Handlers
# ---------------------------------------------------------------------------

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Welcomes the user and automatically subscribes the chat to weekday broadcasts."""
    chat = update.effective_chat
    user = update.effective_user
    chat_id = str(chat.id)

    is_new = subscriber_mgr.add(chat_id)
    name = user.first_name if user else "미술 애호가"
    total_count = len(curator.artists)

    welcome_msg = (
        f"안녕하세요, <b>{name}</b>님! 🏛️✨\n"
        f"세계적인 <b>동시대 현대미술가(Contemporary Artists)</b> 큐레이션 봇에 오신 것을 환영합니다.\n\n"
        f"📌 <b>서비스 안내:</b>\n"
        f"• <b>발송 주기:</b> 주중(월~금) 매일 <b>오전 08:00 (한국 시간 KST)</b>\n"
        f"• <b>큐레이션 대상:</b> 베니스·광주·휘트니 비엔날레, 카셀 도큐멘타 등 공인된 <b>{total_count}여 명의 글로벌 거장 풀</b>\n"
        f"• <b>장르 구성:</b> 현대 회화, 조각, 사진, 미디어아트, 설치, 드로잉 등 <b>전 장르 자유 균등 발송</b>\n"
        f"• <b>콘텐츠:</b> 알기 쉬운 도슨트 해설(작품관·특징), 주요 대표작 목록, 공식 인스타그램 및 실물 갤러리 원클릭 링크\n\n"
        f"✅ <i>현재 채팅방({chat_id})이 매일 아침 8시 정기 발송 수신처로 자동 등록되었습니다.</i>\n\n"
        f"<b>사용 가능한 명령어:</b>\n"
        f"• /today : 오늘 선정된 작가의 심층 도슨트 카드를 지금 즉시 감상\n"
        f"• /random : 등록된 {total_count}명의 비엔날레 작가 중 무작위 1명 탐색\n"
        f"• /search &lt;작가명&gt; : 원하는 작가를 웹(Web)에서 실시간 검색하여 즉시 도록 생성\n"
        f"• /list : 큐레이션된 {total_count}인 작가 풀 장르별 통계 확인\n"
        f"• /status : 봇 운영 상태 및 구독 현황 확인\n"
        f"• /unsubscribe : 매일 아침 자동 알림 수신 해제\n"
        f"• /help : 상세 도움말 보기\n\n"
        f"지금 바로 <b>/today</b> 또는 <b>/random</b> 을 입력해 오늘의 미술을 만나보세요!"
    )

    await update.message.reply_text(
        text=welcome_msg,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays detailed help and commands."""
    total_count = len(curator.artists)
    help_text = (
        f"📖 <b>[현대미술 큐레이션 봇 도움말]</b>\n\n"
        f"<b>1. 정기 발송 안내</b>\n"
        f"매주 월요일부터 금요일까지, 매일 오전 <b>08:00 (KST)</b>에 비엔날레 참여 거장 "
        f"<b>총 {total_count}인</b> 중 중복 없이 매일 새로운 작가의 심층 도슨트 카드가 발송됩니다.\n\n"
        f"<b>2. 주요 명령어</b>\n"
        f"• <b>/today</b> - 오늘의 작가 즉시 조회 (기다리지 않고 바로 보기)\n"
        f"• <b>/random</b> - 랜덤 작가 감상 (회화·조각·사진·미디어 전 장르)\n"
        f"• <b>/search &lt;작가명&gt;</b> - 전 세계 어떤 작가든 웹 실시간 검색 & 도록 생성\n"
        f"• <b>/list</b> - 아카이브 장르별 구성 및 작가 현황 확인\n"
        f"• <b>/subscribe</b> - 아침 8시 자동 알림 재등록\n"
        f"• <b>/unsubscribe</b> - 자동 알림 수신 해제\n"
        f"• <b>/status</b> - 서버 시간 및 현재 구독 상태 확인\n\n"
        f"<b>3. 작품 실물 감상 팁</b>\n"
        f"도슨트 카드 하단의 <b>[📷 인스타그램]</b>, <b>[🌐 공식 웹사이트]</b>, <b>[🎨 구글 아츠 갤러리]</b> 버튼을 누르시면 "
        f"원클릭으로 고화질 공식 실물 작품들을 즉시 감상하실 수 있습니다."
    )
    await update.message.reply_text(
        text=help_text,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )


async def today_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Delivers today's featured artist on demand to the requester."""
    chat_id = update.effective_chat.id
    try:
        artist = curator.get_today_artist(record_history=True)
        await send_artist_package(context.bot, chat_id, artist, is_today=True)
    except Exception as e:
        logger.error(f"Error in today_command: {e}", exc_info=True)
        await update.message.reply_text(f"❌ 도슨트 카드를 불러오는 도중 오류가 발생했습니다: {e}")


async def random_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Delivers a randomly picked artist from the curated catalog."""
    chat_id = update.effective_chat.id
    try:
        artist = curator.get_random_artist()
        await send_artist_package(context.bot, chat_id, artist, is_today=False)
    except Exception as e:
        logger.error(f"Error in random_command: {e}", exc_info=True)
        await update.message.reply_text(f"❌ 작가를 불러오는 도중 오류가 발생했습니다: {e}")


async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Searches for an artist in the catalog or queries the web in real-time."""
    query = " ".join(context.args).strip() if context.args else ""
    if not query:
        await update.message.reply_text(
            "🔍 <b>[웹 실시간 미술가 검색]</b>\n\n"
            "찾고 싶으신 미술가의 이름을 함께 입력해 주세요.\n\n"
            "💡 <b>사용 예시:</b>\n"
            "• <code>/search 데이비드 호크니</code>\n"
            "• <code>/search Banksy</code>\n"
            "• <code>/search 줄리 메레투</code>\n"
            "• <code>/search 서도호</code>\n"
            "• <code>/search 이미래</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    chat_id = update.effective_chat.id
    status_msg = await update.message.reply_text(
        f"🌐 <b>'{query}'</b> 미술가를 웹(Wikipedia 및 비엔날레 아카이브)에서 검색 중입니다...\n"
        f"잠시만 기다려 주세요 (약 1~2초 소요)",
        parse_mode=ParseMode.HTML,
    )

    # 1. Search in existing catalog first
    q_low = query.lower()
    found_artist = None
    for a in curator.artists:
        if q_low in a.get("name_kr", "").lower() or q_low in a.get("name_en", "").lower() or q_low in a.get("id", "").lower():
            found_artist = a
            break

    # 2. If not found in catalog, search the web dynamically via Wikipedia API
    if not found_artist:
        try:
            from web_curator import search_web_for_artist
            found_artist = await asyncio.to_thread(search_web_for_artist, query)
            if found_artist:
                curator.artists.append(found_artist)
                with open(curator.filepath, "w", encoding="utf-8") as f:
                    json.dump(curator.artists, f, ensure_ascii=False, indent=2)
                curator.reload()
                logger.info(f"Live web search successfully added new artist '{found_artist['name_kr']}'")
        except Exception as e:
            logger.error(f"Dynamic web search error for '{query}': {e}")

    try:
        await status_msg.delete()
    except Exception:
        pass

    if found_artist:
        await send_artist_package(
            bot=context.bot,
            chat_id=chat_id,
            artist=found_artist,
            is_today=False,
        )
    else:
        await update.message.reply_text(
            f"❌ <b>'{query}'</b>에 대한 미술가 정보를 웹에서 찾지 못했습니다.\n\n"
            f"💡 <b>검색 팁:</b>\n"
            f"• 영문 이름(예: <code>/search David Hockney</code>)으로 시도해 보세요.\n"
            f"• <code>/list</code> 명령어로 이미 등록된 200여 명의 거장 풀을 확인해 보세요.",
            parse_mode=ParseMode.HTML,
        )


async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays structured statistics and overview of the 200+ artists catalog."""
    total_count = len(curator.artists)

    # Categorize counts
    paint_count = sum(1 for a in curator.artists if any(k in a.get("category", "") for k in ["회화", "페인팅", "드로잉", "단색화"]))
    sculpt_count = sum(1 for a in curator.artists if any(k in a.get("category", "") for k in ["조각", "입체", "모노하"]))
    install_count = sum(1 for a in curator.artists if any(k in a.get("category", "") for k in ["설치", "공간", "에어로센"]))
    media_count = sum(1 for a in curator.artists if any(k in a.get("category", "") for k in ["미디어", "비디오", "사운드", "디지털", "CGI"]))
    photo_count = sum(1 for a in curator.artists if any(k in a.get("category", "") for k in ["사진", "포토", "개념"]))

    text = (
        f"🏛️ <b>[글로벌 비엔날레 현대미술가 아카이브 현황]</b>\n\n"
        f"현재 총 <b>{total_count}인</b>의 공인된 현대미술 거장이 등록되어 있으며, "
        f"주중 매일 아침 1인씩 <b>약 1년간 중복 없이</b> 새로운 작가를 만나보실 수 있습니다.\n\n"
        f"<b>📊 장르별 큐레이션 분포:</b>\n"
        f"• 🎨 <b>현대 회화:</b> 약 {paint_count}인 (호크니, 도이그, 리히터, 메레투, 박서보 등)\n"
        f"• 🗿 <b>현대 조각 및 입체:</b> 약 {sculpt_count}인 (곰리, 카푸어, 시몬 리, 서도호, 이우환 등)\n"
        f"• ✨ <b>설치 및 공간 예술:</b> 약 {install_count}인 (엘리아손, 쿠사마, 시오타, 구정아 등)\n"
        f"• 🎬 <b>미디어, 비디오 & 사운드:</b> 약 {media_count}인 (백남준, 비올라, 자파, 아나돌 등)\n"
        f"• 📷 <b>현대 사진 및 개념 미술:</b> 약 {photo_count}인 (틸만스, 셔먼, 거스키, 크루거 등)\n\n"
        f"💡 <i>/today 로 오늘 작가를 감상하시거나, /random 으로 무작위 탐색, "
        f"또는 /search &lt;작가명&gt; 으로 원하는 작가를 웹에서 즉시 찾아보실 수 있습니다.</i>"
    )
    await update.message.reply_text(
        text=text,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )


async def subscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Subscribes the current chat to daily 08:00 AM weekday notifications."""
    chat_id = str(update.effective_chat.id)
    if subscriber_mgr.add(chat_id):
        await update.message.reply_text(
            f"✅ 알림 수신 등록이 완료되었습니다!\n"
            f"매주 월~금요일 오전 <b>08:00 (KST)</b>에 오늘의 현대미술 도슨트를 보내드립니다.",
            parse_mode=ParseMode.HTML,
        )
    else:
        await update.message.reply_text(
            f"ℹ️ 이미 매일 아침 08:00 정기 알림을 구독 중인 채팅방입니다.",
            parse_mode=ParseMode.HTML,
        )


async def unsubscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Unsubscribes the current chat from daily notifications."""
    chat_id = str(update.effective_chat.id)
    if subscriber_mgr.remove(chat_id):
        await update.message.reply_text(
            "🔕 매일 아침 08:00 자동 알림 수신이 해제되었습니다.\n"
            "언제든 /subscribe 로 다시 등록하시거나 /today 로 수동 조회가 가능합니다."
        )
    else:
        await update.message.reply_text("ℹ️ 현재 구독 중인 목록에 등록되어 있지 않습니다.")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays bot operational status, current time, and subscriber count."""
    now_kst = datetime.now(curator.tz).strftime("%Y-%m-%d %H:%M:%S")
    is_weekday = curator.is_weekday()
    weekday_str = curator.get_weekday_korean()
    sub_count = len(subscriber_mgr.get_all())
    artists_count = len(curator.artists)

    text = (
        f"📊 <b>[현대미술 큐레이션 봇 운영 상태]</b>\n\n"
        f"• <b>현재 한국 시각 (KST):</b> {now_kst} ({weekday_str})\n"
        f"• <b>주중 여부:</b> {'평일 (월~금, 발송 대상)' if is_weekday else '주말 (발송 쉬어감)'}\n"
        f"• <b>정기 발송 시각:</b> 매주 월~금 오전 {DELIVERY_HOUR:02d}:{DELIVERY_MINUTE:02d} KST\n"
        f"• <b>아카이브 작가 수:</b> {artists_count}명 (약 1년간 중복 없는 큐레이션)\n"
        f"• <b>활성 구독자 수:</b> {sub_count}개 채팅방\n"
        f"• <b>시스템 상태:</b> 정상 구동 중 (Online 🟢)"
    )
    await update.message.reply_text(text=text, parse_mode=ParseMode.HTML)


# ---------------------------------------------------------------------------
# Callback Query Handler (Inline Buttons)
# ---------------------------------------------------------------------------

async def artist_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles inline button clicks such as '🎲 다른 비엔날레 작가 감상하기'."""
    query = update.callback_query
    await query.answer()

    data = query.data or ""
    if data == "random_artist":
        artist = curator.get_random_artist()
        await send_artist_package(
            bot=context.bot,
            chat_id=update.effective_chat.id,
            artist=artist,
            is_today=False
        )


# ---------------------------------------------------------------------------
# Daily Weekday Scheduler Job (08:00 AM KST)
# ---------------------------------------------------------------------------

async def daily_weekday_broadcast(bot) -> None:
    """
    Executed Monday through Friday at 08:00 AM KST.
    Picks today's featured artist and delivers it to all subscribers.
    """
    logger.info("Executing daily weekday broadcast job (08:00 AM KST)...")

    if not curator.is_weekday():
        logger.info("Today is weekend. Skipping scheduled delivery.")
        return

    subscribers = subscriber_mgr.get_all()
    if not subscribers:
        logger.warning("No subscribers registered for broadcast.")
        return

    try:
        today_artist = curator.get_today_artist(record_history=True)
        logger.info(
            f"Today's featured artist: {today_artist['name_kr']} ({today_artist['name_en']})"
        )
    except Exception as e:
        logger.error(f"Failed to pick today's artist: {e}", exc_info=True)
        return

    success_count = 0
    for chat_id in subscribers:
        try:
            logger.info(f"Delivering daily artist to chat_id: {chat_id}")
            await send_artist_package(bot, chat_id, today_artist, is_today=True)
            success_count += 1
            await asyncio.sleep(0.5)
        except Exception as e:
            logger.error(f"Failed delivery to {chat_id}: {e}")

    logger.info(
        f"Daily broadcast complete. Delivered to {success_count}/{len(subscribers)} chats."
    )


async def post_init(application: Application) -> None:
    """Initializes APScheduler inside the active asyncio event loop."""
    scheduler = AsyncIOScheduler(timezone=pytz.timezone(TIMEZONE))
    scheduler.add_job(
        daily_weekday_broadcast,
        trigger="cron",
        day_of_week="mon-fri",
        hour=DELIVERY_HOUR,
        minute=DELIVERY_MINUTE,
        args=[application.bot],
        id="daily_art_broadcast",
        replace_existing=True,
    )
    scheduler.start()
    application.bot_data["scheduler"] = scheduler
    logger.info(
        f"APScheduler started: Weekday broadcast set at {DELIVERY_HOUR:02d}:{DELIVERY_MINUTE:02d} KST."
    )


async def post_shutdown(application: Application) -> None:
    """Cleanly shuts down the scheduler."""
    scheduler = application.bot_data.get("scheduler")
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("APScheduler stopped.")


# ---------------------------------------------------------------------------
# Application Startup & Main Entry
# ---------------------------------------------------------------------------

def main() -> None:
    if not TELEGRAM_BOT_TOKEN:
        print("\n" + "=" * 65)
        print(" [!] TELEGRAM_BOT_TOKEN이 설정되지 않았습니다.")
        print(" contemporary_art_bot/.env 파일에 봇 토큰을 입력해 주세요.")
        print(" (발급 가이드: 텔레그램 @BotFather 에게 /newbot 전송)")
        print("=" * 65 + "\n")
        sys.exit(1)

    print("\n" + "=" * 65)
    print(" 🏛️ [동시대 현대미술 큐레이션 텔레그램 봇]")
    print(f" • 운영 시간대: {TIMEZONE} (한국 시간)")
    print(f" • 정기 발송 시간: 매주 월~금요일 오전 {DELIVERY_HOUR:02d}:{DELIVERY_MINUTE:02d}")
    print(f" • 큐레이션 풀: {len(curator.artists)}인 거장 (비엔날레 전 장르 아카이브)")
    print(" • 상태: 봇 인스턴스 초기화 중...")
    print("=" * 65 + "\n")

    application = (
        ApplicationBuilder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    # Register Command Handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("today", today_command))
    application.add_handler(CommandHandler("random", random_command))
    application.add_handler(CommandHandler("search", search_command))
    application.add_handler(CommandHandler("list", list_command))
    application.add_handler(CommandHandler("subscribe", subscribe_command))
    application.add_handler(CommandHandler("unsubscribe", unsubscribe_command))
    application.add_handler(CommandHandler("status", status_command))

    # Register Callback Query Handler for Interactive Buttons
    application.add_handler(
        CallbackQueryHandler(artist_callback_handler)
    )

    # Start Polling
    logger.info("Bot polling started. Press Ctrl+C to terminate.")
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
