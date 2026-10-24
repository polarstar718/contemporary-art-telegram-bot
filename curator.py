"""
Contemporary Art Curator Engine
Handles artist rotation, history tracking, weekday scheduling,
and formatted docent messages for Telegram.
"""

import json
import random
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

import pytz

from config import ARTISTS_FILE, HISTORY_FILE, TIMEZONE


class ArtCurator:
    def __init__(self):
        self.tz = pytz.timezone(TIMEZONE)
        self.artists = self._load_artists()
        self.history = self._load_history()

    def _load_artists(self) -> List[Dict[str, Any]]:
        if not ARTISTS_FILE.exists():
            return []
        with open(ARTISTS_FILE, "r", encoding="utf-8") as f:
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

    def get_current_date_str(self) -> str:
        return datetime.now(self.tz).strftime("%Y-%m-%d")

    def is_weekday(self) -> bool:
        """Returns True if today is Monday (0) through Friday (4) in Korea Time."""
        now = datetime.now(self.tz)
        return now.weekday() < 5

    def get_weekday_korean(self) -> str:
        weekdays = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]
        return weekdays[datetime.now(self.tz).weekday()]

    def get_today_artist(self, record_history: bool = True) -> Dict[str, Any]:
        """
        Retrieves today's featured artist.
        If already assigned for today's date, returns that artist.
        Otherwise, selects the next unsent artist in sequence, prioritizing the weekly genre balance.
        """
        today_str = self.get_current_date_str()

        # Check if already sent today
        for entry in reversed(self.history):
            if entry.get("date") == today_str:
                artist_id = entry.get("artist_id")
                artist = self.get_artist_by_id(artist_id)
                if artist:
                    return artist

        # Find unsent artists in current cycle
        sent_ids = {entry.get("artist_id") for entry in self.history}
        unsent_artists = [a for a in self.artists if a["id"] not in sent_ids]

        if not unsent_artists:
            # All artists have been featured once! Start a fresh cycle
            unsent_artists = list(self.artists)

        # Decide whether today should be installation/spatial/media or painting/photo/sculpture
        # Weekday 0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri
        current_weekday = datetime.now(self.tz).weekday()
        # Wednesdays (2) and Fridays (4) are great for balanced painting/photography/sculpture
        prefer_balanced_painting = current_weekday in (2, 4)

        candidate = None
        if prefer_balanced_painting:
            # Look for non-spatial/media artist first
            for a in unsent_artists:
                if not a.get("is_spatial_media", True):
                    candidate = a
                    break

        if not candidate:
            # Default or fallback: pick first available installation/spatial/media artist
            candidate = unsent_artists[0]

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
        return random.choice(self.artists)

    def get_artist_by_id(self, artist_id: str) -> Optional[Dict[str, Any]]:
        for a in self.artists:
            if a["id"] == artist_id:
                return a
        return None

    def get_all_artists_summary(self) -> List[Dict[str, Any]]:
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
        Formats a friendly, smooth Korean docent introductory text with English original names.
        Complies with user request:
        - 100% natural, polite Korean docent commentary
        - English original names for Artist Name, Artwork Titles, and Gallery Names
        - Worldview (작품관), Characteristics (작품 특징), Awards/Biennales, SNS, Sources
        """
        name_kr = artist["name_kr"]
        name_en = artist["name_en"]
        nationality = artist.get("nationality", "")
        birth_year = artist.get("birth_year", "")
        category = artist.get("category", "")
        philosophy = artist.get("philosophy", "")
        features = artist.get("style_features", "")
        awards = artist.get("awards_and_biennales", [])
        sns = artist.get("sns", {})
        galleries = artist.get("galleries", [])
        sources = artist.get("sources", [])
        total_works = len(artist.get("artworks", []))

        header = "🏛️ [오늘의 현대미술 도슨트]" if is_today else "🎨 [현대미술 작가 아카이브]"
        today_date = datetime.now(self.tz).strftime("%Y년 %m월 %d일")
        weekday_kr = self.get_weekday_korean()

        awards_text = "\n".join([f"  • {item}" for item in awards[:4]])
        galleries_text = ", ".join(galleries) if galleries else "글로벌 유수 갤러리"
        sources_text = ", ".join(sources[:3]) if sources else "공식 아카이브"

        instagram_url = sns.get("instagram", "")
        website_url = sns.get("official_website", "")

        links = []
        if instagram_url:
            links.append(f"<a href='{instagram_url}'>📸 인스타그램 공식 계정</a>")
        if website_url:
            links.append(f"<a href='{website_url}'>🌐 공식 웹사이트</a>")
        links_text = " | ".join(links) if links else "공식 SNS 준비 중"

        msg = (
            f"<b>{header}</b>\n"
            f"📅 <i>{today_date} ({weekday_kr})</i>\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👤 <b>작가:</b> <b>{name_kr}</b> (<i>{name_en}</i>)\n"
            f"🌍 <b>국적 / 출생:</b> {nationality} (b. {birth_year})\n"
            f"🏷️ <b>주요 매체:</b> {category}\n"
            f"🖼️ <b>등록 작품 수:</b> 총 {total_works}점 (대표작 10점 우선 감상)\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"💡 <b>작품관 (Artistic Worldview)</b>\n"
            f"{philosophy}\n\n"
            f"✨ <b>작품 특징 및 시각적 요소</b>\n"
            f"{features}\n\n"
            f"🏆 <b>주요 비엔날레 & 수상 이력</b>\n"
            f"{awards_text}\n\n"
            f"🏛️ <b>소속 갤러리 (Gallery):</b> {galleries_text}\n"
            f"📚 <b>출처 및 소장처:</b> {sources_text}\n"
            f"🔗 <b>공식 채널:</b> {links_text}\n\n"
            f"👇 <i>아래로 대표작 10점의 실제 작품 도록이 이어집니다.</i>"
        )
        return msg

    def get_artworks_batch(
        self, artist: Dict[str, Any], page: int = 1, batch_size: int = 10
    ) -> Tuple[List[Dict[str, Any]], bool, int, int]:
        """
        Returns (batch_artworks, has_next_page, current_start_index, total_artworks)
        page 1 -> items 0..9 (start=1, end=10)
        page 2 -> items 10..19 (start=11, end=20)
        """
        artworks = artist.get("artworks", [])
        total = len(artworks)
        start_idx = (page - 1) * batch_size
        end_idx = start_idx + batch_size

        batch = artworks[start_idx:end_idx]
        has_next = end_idx < total
        return batch, has_next, start_idx + 1, total

    def format_artwork_caption(
        self, artist: Dict[str, Any], artwork: Dict[str, Any], item_number: int
    ) -> str:
        """
        Formats a clean, informative caption for an individual artwork photo.
        Max Telegram caption length is 1024 characters.
        """
        title_kr = artwork.get("title_kr", "무제")
        title_en = artwork.get("title_en", "Untitled")
        year = artwork.get("year", "연도 미상")
        medium_kr = artwork.get("medium_kr", "")
        gallery = artwork.get("gallery_or_location", "")
        caption = artwork.get("caption", "")

        text = (
            f"[{item_number}] <b>{title_kr}</b> (<i>{title_en}</i>), {year}\n"
            f"• <b>재료/기법:</b> {medium_kr}\n"
            f"• <b>소장/위치:</b> {gallery}\n"
            f"📝 <i>{caption}</i>"
        )
        # Safe truncate if overly long
        if len(text) > 1000:
            text = text[:990] + "..."
        return text
