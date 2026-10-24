"""
AI Contemporary Art Enricher
Uses Google Gemini API to automatically discover, structure, and append
new contemporary artists to the catalog following the exact schema.
"""

import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any

from config import ARTISTS_FILE, GEMINI_API_KEY

logger = logging.getLogger("ArtEnricher")


def add_artist_with_gemini(artist_name: str) -> Optional[Dict[str, Any]]:
    """
    Queries Gemini API to generate structured docent data and artwork catalogue
    for a given contemporary artist, and appends it to data/artists.json.
    """
    if not GEMINI_API_KEY:
        print("[!] GEMINI_API_KEY is not set in .env. Please set it to use the AI enricher.")
        return None

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=GEMINI_API_KEY)

        prompt = f"""
당신은 세계적인 현대미술 큐레이터이자 수석 도슨트입니다.
작가 '{artist_name}'에 대한 전문적이고 신뢰도 높은 도슨트 정보를 JSON 형식으로 작성해 주세요.

[요구사항]
1. 해설은 100% 매끄럽고 친절한 한국어 도슨트 톤으로 작성하되, 작가명, 작품명, 갤러리명은 영문 원문을 반드시 병기해 주세요.
2. 세계적인 비엔날레(베니스 비엔날레 등) 및 주요 미술상(터너상, 휴고보스상 등) 수상 및 참여 이력을 명시해 주세요.
3. 실제 대표작품 10~20점의 목록을 포함하고, 각 작품마다 한국어/영문 작품명, 제작연도, 기법/재료(한국어/영문), 소장/전시처, 실제 고화질 이미지 URL(위키미디어, 미술관 오픈 CDN 등), 한 줄 해설을 작성해 주세요.
4. 아래 JSON 스키마를 엄격히 준수해 주세요:

{{
  "id": "slug-name",
  "name_kr": "한국어 작가명",
  "name_en": "English Name",
  "nationality": "국적",
  "birth_year": 1970,
  "category": "설치미술 / 미디어아트 / 공간 예술 등",
  "is_spatial_media": true,
  "awards_and_biennales": ["이력 1", "이력 2"],
  "philosophy": "작품관 (한국어 상세 도슨트 설명)",
  "style_features": "작품 특징 및 시각적 요소",
  "sns": {{
    "instagram": "https://www.instagram.com/...",
    "official_website": "https://..."
  }},
  "galleries": ["갤러리명 (도시)"],
  "sources": ["소장 미술관 / 아카이브"],
  "artworks": [
    {{
      "title_kr": "한국어 제목",
      "title_en": "English Title",
      "year": 2020,
      "medium_kr": "재료 및 기법",
      "medium_en": "Medium in English",
      "gallery_or_location": "소장처 또는 전시 장소",
      "image_url": "https://...",
      "caption": "한 줄 도슨트 해설"
    }}
  ]
}}
반드시 순수 JSON 마크다운 코드블록(```json ... ```) 또는 JSON 문자열만 출력해 주세요.
"""

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )

        data = json.loads(response.text)

        # Load existing artists
        if ARTISTS_FILE.exists():
            with open(ARTISTS_FILE, "r", encoding="utf-8") as f:
                artists = json.load(f)
        else:
            artists = []

        # Check for duplicates
        existing_ids = {a["id"] for a in artists}
        if data["id"] in existing_ids:
            print(f"[!] Artist {data['name_kr']} ({data['id']}) already exists in catalog.")
            return data

        artists.append(data)
        with open(ARTISTS_FILE, "w", encoding="utf-8") as f:
            json.dump(artists, f, ensure_ascii=False, indent=2)

        print(f"[SUCCESS] Successfully appended {data['name_kr']} ({data['name_en']}) with {len(data.get('artworks', []))} artworks!")
        return data

    except Exception as e:
        logger.error(f"Enrichment error: {e}", exc_info=True)
        print(f"[ERROR] Failed to enrich artist {artist_name}: {e}")
        return None


if __name__ == "__main__":
    import sys
    name = sys.argv[1] if len(sys.argv) > 1 else "Hito Steyerl"
    print(f"Running AI enricher for: {name}...")
    add_artist_with_gemini(name)
