"""
Contemporary Art Daily Telegram Bot
Main Bot Application with PTB 22+ and APScheduler.
Delivers world-class contemporary artists every weekday at 08:00 AM KST.
"""

import asyncio
import json
import logging
import sys

# Ensure UTF-8 console output on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from datetime import datetime
from pathlib import Path
from typing import Set

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
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

# Configure Logging
import sys

# Force UTF-8 stdout for Windows consoles
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

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

        # Seed with TELEGRAM_CHAT_ID from config if provided
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


subscriber_mgr = SubscriberManager(SUBSCRIBERS_FILE)


# ---------------------------------------------------------------------------
# Message Sending Helper Functions
# ---------------------------------------------------------------------------

async def send_artist_package(
    bot,
    chat_id: int | str,
    artist: dict,
    is_today: bool = True,
    start_page: int = 1,
) -> None:
    """
    Sends the complete Artist Package:
    Step 1: Introductory docent message (Worldview, Style, Awards, SNS, Sources)
    Step 2: 1st batch of 10 artwork images (sendMediaGroup)
    Step 3: Interactive inline button for viewing additional 10~20 artworks
    """
    # 1. Send Docent Intro Message
    intro_text = curator.format_artist_intro(artist, is_today=is_today)
    await bot.send_message(
        chat_id=chat_id,
        text=intro_text,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=False,
    )

    # 2. Prepare Page 1 Artworks (up to 10 photos)
    batch, has_next, start_idx, total = curator.get_artworks_batch(
        artist, page=start_page, batch_size=10
    )

    if batch:
        media_group = []
        for idx, artwork in enumerate(batch, start=start_idx):
            caption = curator.format_artwork_caption(artist, artwork, idx)
            media_group.append(
                InputMediaPhoto(
                    media=artwork["image_url"],
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                )
            )

        try:
            await bot.send_media_group(chat_id=chat_id, media=media_group)
        except Exception as e:
            logger.warning(
                f"send_media_group failed with direct URLs: {e}. Sending fallback descriptions."
            )
            # Fallback text if network/Telegram image URL fetch times out
            fallback_text = (
                f"⚠️ <b>[도록 텍스트 안내]</b> 텔레그램 서버의 외부 이미지 로딩 지연으로 "
                f"대표작 {len(batch)}점의 도록 목록을 텍스트로 먼저 안내해 드립니다:\n\n"
            )
            for idx, artwork in enumerate(batch, start=start_idx):
                fallback_text += f"{curator.format_artwork_caption(artist, artwork, idx)}\n\n"
            await bot.send_message(
                chat_id=chat_id,
                text=fallback_text[:4000],
                parse_mode=ParseMode.HTML,
            )

    # 3. Send Navigation & Next Batch Button if more artworks exist
    if has_next:
        next_page = start_page + 1
        next_start = start_idx + len(batch)
        next_end = min(total, next_start + 9)
        keyboard = [
            [
                InlineKeyboardButton(
                    f"🖼️ 추가 작품 10점 더 보기 ({next_start}~{next_end}번)",
                    callback_data=f"more_artworks:{artist['id']}:{next_page}",
                )
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await bot.send_message(
            chat_id=chat_id,
            text=(
                f"총 <b>{total}점</b> 중 대표작 10점을 감상하셨습니다.\n"
                f"아래 버튼을 누르시면 <b>추가 작품 ({next_start}~{next_end}번)</b>을 바로 확인하실 수 있습니다."
            ),
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML,
        )
    else:
        await bot.send_message(
            chat_id=chat_id,
            text=(
                f"✨ <b>{artist['name_kr']}</b> (<i>{artist['name_en']}</i>) 작가의 "
                f"등록된 모든 작품(총 {total}점)을 감상하셨습니다.\n\n"
                f"💡 내일 주중 아침 08:00에 또 다른 거장의 작품으로 찾아뵙겠습니다!"
            ),
            parse_mode=ParseMode.HTML,
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

    welcome_msg = (
        f"안녕하세요, <b>{name}</b>님! 🏛️✨\n"
        f"세계적인 <b>동시대 현대미술가(Contemporary Artists)</b> 큐레이션 봇에 오신 것을 환영합니다.\n\n"
        f"📌 <b>서비스 안내:</b>\n"
        f"• <b>발송 주기:</b> 주중(월~금) 매일 <b>오전 08:00 (한국 시간 KST)</b>\n"
        f"• <b>큐레이션 대상:</b> 베니스 비엔날레, 터너상, 카셀 도큐멘타, 아트바젤 등 공인된 세계 최고 작가\n"
        f"• <b>장르 구성:</b> 설치미술, 공간 예술, 미디어아트 위주(주 3~4회) + 회화/조각/사진 균형(주 1~2회)\n"
        f"• <b>콘텐츠:</b> 알기 쉬운 도슨트 해설(작품관·특징), 영문 원문 병기, 실제 작품 도록 10~30점, 인스타그램 및 출처\n\n"
        f"✅ <i>현재 채팅방({chat_id})이 매일 오전 8시 알림 수신처로 자동 등록되었습니다.</i>\n\n"
        f"<b>사용 가능한 명령어:</b>\n"
        f"• /today : 오늘 선정된 작가의 작품과 해설을 지금 즉시 감상\n"
        f"• /random : 20명의 현대미술 거장 중 무작위 작가 1명 탐색\n"
        f"• /list : 큐레이션된 전체 작가 풀 목록 및 장르 확인\n"
        f"• /status : 봇 운영 상태 및 구독 현황 확인\n"
        f"• /unsubscribe : 매일 아침 자동 알림 수신 해제\n"
        f"• /help : 상세 도움말 보기\n\n"
        f"지금 바로 <b>/today</b> 를 입력해 오늘의 작가를 만나보세요!"
    )

    await update.message.reply_text(
        text=welcome_msg,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Displays detailed help and commands."""
    help_text = (
        f"📖 <b>[현대미술 큐레이션 봇 도움말]</b>\n\n"
        f"<b>1. 정기 발송 안내</b>\n"
        f"매주 월요일부터 금요일까지, 매일 오전 <b>08:00 (KST)</b>에 새로운 현대미술가의 "
        f"작품관, 특징, 공식 SNS, 그리고 10~30점의 실제 작품 도록이 자동 발송됩니다.\n\n"
        f"<b>2. 주요 명령어</b>\n"
        f"• <b>/today</b> - 오늘의 작가 즉시 조회 (기다리지 않고 바로 보기)\n"
        f"• <b>/random</b> - 랜덤 작가 감상 (다양한 사조 탐색)\n"
        f"• <b>/list</b> - 전체 큐레이션 작가 풀 20명 목록 보기\n"
        f"• <b>/subscribe</b> - 아침 8시 자동 알림 재등록\n"
        f"• <b>/unsubscribe</b> - 자동 알림 수신 해제\n"
        f"• <b>/status</b> - 서버 시간 및 현재 구독 상태 확인\n\n"
        f"<b>3. 작품 감상 팁</b>\n"
        f"기본 10장의 대표작 앨범을 감상하신 후, 메시지 하단의 "
        f"<b>[🖼️ 추가 작품 10점 더 보기]</b> 버튼을 누르면 이어서 등록된 20~30점의 작품을 감상하실 수 있습니다."
    )
    await update.message.reply_text(text=help_text, parse_mode=ParseMode.HTML)


async def today_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Delivers today's featured artist immediately on demand."""
    chat_id = update.effective_chat.id
    status_msg = await update.message.reply_text("🎨 오늘의 현대미술 거장 정보를 불러오는 중입니다...")

    try:
        artist = curator.get_today_artist(record_history=True)
        await send_artist_package(context.bot, chat_id, artist, is_today=True)
        try:
            await status_msg.delete()
        except Exception:
            pass
    except Exception as e:
        logger.error(f"Error in today_command: {e}", exc_info=True)
        await update.message.reply_text(f"❌ 작품을 불러오는 도중 오류가 발생했습니다: {e}")


async def random_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Delivers a randomly picked artist from the curated catalog."""
    chat_id = update.effective_chat.id
    status_msg = await update.message.reply_text("🎲 큐레이션 아카이브에서 작가를 무작위로 탐색 중입니다...")

    try:
        artist = curator.get_random_artist()
        await send_artist_package(context.bot, chat_id, artist, is_today=False)
        try:
            await status_msg.delete()
        except Exception:
            pass
    except Exception as e:
        logger.error(f"Error in random_command: {e}", exc_info=True)
        await update.message.reply_text(f"❌ 작가를 불러오는 도중 오류가 발생했습니다: {e}")


async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Lists all 20 curated contemporary artists with genres and icons."""
    summaries = curator.get_all_artists_summary()

    lines = ["🏛️ <b>[현대미술 큐레이션 작가 풀 (총 20인)]</b>\n"]
    lines.append("<i>설치·공간·미디어아트 75% + 현대 회화·사진·조각 25% 균형 구성</i>\n")

    for s in summaries:
        genre_badge = "✨ 설치/미디어" if s["is_spatial_media"] else "🎨 회화/사진"
        sent_badge = "✅ 소개완료" if s["is_sent"] else "⏳ 대기중"
        lines.append(
            f"<b>{s['index']:02d}. {s['name_kr']}</b> (<i>{s['name_en']}</i>)\n"
            f"   • [{genre_badge}] | 등록 작품: {s['artworks_count']}점 | {sent_badge}"
        )

    lines.append("\n💡 <i>/today 또는 /random 명령어로 원하는 작가의 전체 도록을 감상하실 수 있습니다.</i>")

    full_text = "\n".join(lines)
    await update.message.reply_text(
        text=full_text,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )


async def subscribe_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Subscribes the current chat to daily 08:00 AM weekday notifications."""
    chat_id = str(update.effective_chat.id)
    if subscriber_mgr.add(chat_id):
        await update.message.reply_text(
            f"✅ 알림 수신 등록이 완료되었습니다!\n"
            f"매주 월~금요일 오전 <b>08:00 (KST)</b>에 오늘의 현대미술 작품을 보내드립니다.",
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
        f"• <b>아카이브 작가 수:</b> {artists_count}명 (총 202점 작품 도록 보유)\n"
        f"• <b>활성 구독자 수:</b> {sub_count}개 채팅방\n"
        f"• <b>봇 시스템:</b> 정상 구동 중 (Online 🟢)"
    )
    await update.message.reply_text(text=text, parse_mode=ParseMode.HTML)


# ---------------------------------------------------------------------------
# Callback Query Handler (Inline Buttons)
# ---------------------------------------------------------------------------

async def more_artworks_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handles inline button clicks for viewing additional batches of 10 artworks.
    Pattern: more_artworks:{artist_id}:{page}
    """
    query = update.callback_query
    await query.answer()

    data = query.data or ""
    parts = data.split(":")
    if len(parts) != 3:
        return

    _, artist_id, page_str = parts
    page = int(page_str)

    artist = curator.get_artist_by_id(artist_id)
    if not artist:
        await query.message.reply_text("❌ 작가 정보를 찾을 수 없습니다.")
        return

    chat_id = update.effective_chat.id

    # Fetch requested batch of 10 artworks
    batch, has_next, start_idx, total = curator.get_artworks_batch(
        artist, page=page, batch_size=10
    )

    if not batch:
        await query.message.reply_text("✨ 더 이상 추가 작품이 없습니다.")
        return

    # Build and send album
    media_group = []
    for idx, artwork in enumerate(batch, start=start_idx):
        caption = curator.format_artwork_caption(artist, artwork, idx)
        media_group.append(
            InputMediaPhoto(
                media=artwork["image_url"],
                caption=caption,
                parse_mode=ParseMode.HTML,
            )
        )

    try:
        await context.bot.send_media_group(chat_id=chat_id, media=media_group)
    except Exception as e:
        logger.warning(f"Callback send_media_group failed: {e}. Sending fallback text.")
        fallback_text = (
            f"🖼️ <b>[{artist['name_kr']} - 추가 작품 목록 ({start_idx}~{start_idx+len(batch)-1}번)]</b>\n\n"
        )
        for idx, artwork in enumerate(batch, start=start_idx):
            fallback_text += f"{curator.format_artwork_caption(artist, artwork, idx)}\n\n"
        await context.bot.send_message(
            chat_id=chat_id,
            text=fallback_text[:4000],
            parse_mode=ParseMode.HTML,
        )

    # Next page button or completion message
    if has_next:
        next_page = page + 1
        next_start = start_idx + len(batch)
        next_end = min(total, next_start + 9)
        keyboard = [
            [
                InlineKeyboardButton(
                    f"🖼️ 추가 작품 10점 더 보기 ({next_start}~{next_end}번)",
                    callback_data=f"more_artworks:{artist['id']}:{next_page}",
                )
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"현재까지 <b>{start_idx + len(batch) - 1}점 / 총 {total}점</b>을 감상하셨습니다.",
            reply_markup=reply_markup,
            parse_mode=ParseMode.HTML,
        )
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                f"✨ <b>{artist['name_kr']}</b> (<i>{artist['name_en']}</i>) 작가의 "
                f"전체 작품 <b>총 {total}점</b>을 모두 감상하셨습니다.\n\n"
                f"💡 내일 주중 아침 08:00에 또 다른 거장의 작품으로 찾아뵙겠습니다!"
            ),
            parse_mode=ParseMode.HTML,
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

    # Double-check weekday
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

    # Broadcast to all subscribed chats
    success_count = 0
    for chat_id in subscribers:
        try:
            logger.info(f"Delivering daily artist to chat_id: {chat_id}")
            await send_artist_package(bot, chat_id, today_artist, is_today=True)
            success_count += 1
            await asyncio.sleep(1.0)  # Gentle rate limit between chats
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
    print(f" • 큐레이션 풀: 20인 거장 (총 202점 고화질 도록 보유)")
    print(" • 상태: 봇 인스턴스 초기화 중...")
    print("=" * 65 + "\n")

    # Build Telegram Application with post_init hook
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
    application.add_handler(CommandHandler("list", list_command))
    application.add_handler(CommandHandler("subscribe", subscribe_command))
    application.add_handler(CommandHandler("unsubscribe", unsubscribe_command))
    application.add_handler(CommandHandler("status", status_command))

    # Register Callback Query Handler
    application.add_handler(
        CallbackQueryHandler(more_artworks_callback, pattern=r"^more_artworks:")
    )

    # Start Polling
    logger.info("Bot polling started. Press Ctrl+C to terminate.")
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
