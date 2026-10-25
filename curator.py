"""
Contemporary Art Curator Engine.
Handles artist rotation, history tracking, weekday scheduling,
and rich docent text cards with interactive links for Telegram.
"""

import json
import random
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
import pytz

from config import ARTISTS_FILE, HISTORY_FILE, TIMEZONE


class ArtCurator:
    def __init__(self):
        self.tz = pytz.timezone(TIMEZONE)
        self.filepath = ARTISTS_FILE
        self.artists = self._load_artists()
        self.history = self._load_history()

    def _load_artists(self) -> List[Dict[str, Any]]:
        if not self.filepath.exists():
            return []
        with open(self.filepath, "r", encoding="utf-8") as f:
            return json.load(f)

    def _load_history(self) -> List[Dict[str, Any]]:
        if not HISTORY_FILE.exists():
            return []
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def _save_history(self) -> None:
        HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(self.history, f, ensure_ascii=False, indent=2)

    def reload(self) -> None:
        self.artists = self._load_artists()
        self.history = self._load_history()

    def get_current_date_str(self) -> str:
        return datetime.now(self.tz).strftime("%Y-%m-%d")

    def get_weekday_korean(self) -> str:
        weekdays = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]
        return weekdays[datetime.now(self.tz).weekday()]

    def is_weekday(self) -> bool:
        # Monday=0 ... Friday=4, Saturday=5, Sunday=6
        return datetime.now(self.tz).weekday() < 5

    def get_today_artist(self, record_history: bool = True) -> Dict[str, Any]:
        """
        Picks today's featured artist from the 200+ pool.
        Ensures diverse, non-repeating daily weekday delivery across all genres.
        """
        self.reload()
        if not self.artists:
            raise ValueError("No artists found in catalog.")

        today_str = self.get_current_date_str()

        # Check if already picked today
        for entry in reversed(self.history):
            if entry.get("date") == today_str:
                artist = self.get_artist_by_id(entry.get("artist_id", ""))
                if artist:
                    return artist

        # Filter out previously sent artists in this cycle
        sent_artist_ids = {entry.get("artist_id") for entry in self.history}
        unsent_artists = [a for a in self.artists if a["id"] not in sent_artist_ids]

        if not unsent_artists:
            # All artists in catalog have been shown once! Reset history to start fresh cycle
            self.history = []
            self._save_history()
            unsent_artists = list(self.artists)

        # Free and unbiased random selection across all contemporary genres
        candidate = random.choice(unsent_artists)

        if record_history:
            self.history.append({
                "date": today_str,
                "weekday": self.get_weekday_korean(),
                "artist_id": candidate["id"],
                "artist_kr": candidate["name_kr"],
                "artist_en": candidate["name_en"],
                "sent_at": datetime.now(self.tz).isoformat()
            })
            self._save_history()

        return candidate

    def get_random_artist(self) -> Dict[str, Any]:
        """Returns a random artist from the entire catalog."""
        self.reload()
        return random.choice(self.artists)

    def get_artist_by_id(self, artist_id: str) -> Optional[Dict[str, Any]]:
        self.reload()
        for a in self.artists:
            if a["id"] == artist_id:
                return a
        return None

    def get_all_artists_summary(self) -> List[Dict[str, Any]]:
        self.reload()
        sent_ids = {entry.get("artist_id") for entry in self.history}
        summaries = []
        for idx, a in enumerate(self.artists, 1):
            summaries.append({
                "index": idx,
                "id": a["id"],
                "name_kr": a["name_kr"],
                "name_en": a["name_en"],
                "category": a.get("category", "현대미술"),
                "is_spatial_media": a.get("is_spatial_media", True),
                "artworks_count": len(a.get("artworks", [])),
                "is_sent": a["id"] in sent_ids
            })
        return summaries

    def format_artist_intro(self, artist: Dict[str, Any], is_today: bool = True) -> str:
        """
        Formats a polite, comprehensive Korean docent card with:
        - Profile (Korean/English name, Nationality, Birth, Genre)
        - Key Biennales & Major Exhibitions
        - Artistic Worldview (작품관)
        - Stylistic Features & Visual Elements (작품 특징)
        - Curated Masterpiece List (대표작 3~6점)
        - Gallery & Archives
        """
        name_kr = artist["name_kr"]
        name_en = artist["name_en"]
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
        today_date = datetime.now(self.tz).strftime("%Y년 %m월 %d일")
        weekday_kr = self.get_weekday_korean()

        awards_text = "\n".join([f"  • {item}" for item in awards[:3]])
        galleries_text = ", ".join(galleries[:3]) if galleries else "글로벌 대표 현대 갤러리"
        sources_text = ", ".join(sources[:2]) if sources else "국제 비엔날레 아카이브"

        # Format representative artworks list
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
        artworks_section = "\n\n".join(artworks_lines) if artworks_lines else "대표작 아카이브 정리 중"

        msg = (
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
        return msg

    def get_artist_keyboard_buttons(self, artist: Dict[str, Any]) -> list:
        """
        Builds the 3-row interactive inline keyboard for Telegram:
        Row 1: [📷 인스타그램] | [🌐 공식 웹사이트]
        Row 2: [🎨 구글 아츠 갤러리 실물 보기]
        Row 3: [🎲 다른 작가 감상하기]
        """
        from telegram import InlineKeyboardButton

        sns = artist.get("sns", {})
        name_en = artist.get("name_en", "")
        encoded_name = urllib.parse.quote(name_en)

        instagram_url = sns.get("instagram") or f"https://www.instagram.com/explore/tags/{artist['id'].replace('-', '')}/"
        website_url = sns.get("official_website") or f"https://en.wikipedia.org/wiki/{encoded_name}"
        arts_culture_url = sns.get("arts_culture") or f"https://artsandculture.google.com/search?q={encoded_name}"

        keyboard = [
            [
                InlineKeyboardButton("📷 인스타그램 바로가기", url=instagram_url),
                InlineKeyboardButton("🌐 공식 웹사이트 / 위키", url=website_url),
            ],
            [
                InlineKeyboardButton("🎨 구글 아츠 갤러리 실물 보기", url=arts_culture_url),
            ],
            [
                InlineKeyboardButton("🎲 다른 비엔날레 작가 감상하기", callback_data="random_artist"),
            ]
        ]
        return keyboard
