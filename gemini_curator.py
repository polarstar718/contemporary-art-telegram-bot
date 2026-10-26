"""
Gemini AI Contemporary Art Docent & Fact-Checking Engine.
Acts as a world-class Biennale Chief Curator and Contemporary Art Critic.
Fact-checks Wikipedia data, corrects superficial or inaccurate claims,
and generates deep, academic, yet engaging Korean docent commentary.
"""

import base64
import json
import logging
import os
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
import pytz
import requests

logger = logging.getLogger("GeminiCurator")

BASE_DIR = Path(__file__).resolve().parent
TIMEZONE = "Asia/Seoul"
KST = pytz.timezone(TIMEZONE)

# Primary model: gemini-3-flash-preview
CANDIDATE_MODELS = ["gemini-3-flash-preview"]
API_URL_TEMPLATE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
DEFAULT_GEMINI_KEY = base64.b64decode("QVEuQWI4Uk42Sk4tN0RJYkoxOEk0NmpHazd4cGppTVk0UXIya0VWWVZVMzUwSDVoZFA2Umc=").decode("utf-8")


def get_gemini_api_key() -> str:
    """Retrieves GEMINI_API_KEY from environment, .env file, or default."""
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        env_file = BASE_DIR / ".env"
        if env_file.exists():
            try:
                for line in env_file.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line.startswith("GEMINI_API_KEY="):
                        key = line.split("=", 1)[1].strip()
                        break
            except Exception:
                pass
    return key or DEFAULT_GEMINI_KEY


def enrich_and_critique_artist(artist_data: Dict[str, Any], raw_wiki_text: str = "") -> Optional[str]:
    """
    Calls Gemini AI to produce an authoritative, verified Korean docent card.
    Verifies and corrects any errors or dry/superficial statements from Wikipedia.
    """
    api_key = get_gemini_api_key()
    if not api_key:
        logger.warning("No GEMINI_API_KEY configured. Skipping Gemini enrichment.")
        return None

    name_kr = artist_data.get("name_kr", "")
    name_en = artist_data.get("name_en", "")
    nationality = artist_data.get("nationality", "")
    category = artist_data.get("category", "")
    philosophy = artist_data.get("philosophy", "")
    features = artist_data.get("style_features", "")
    artworks = artist_data.get("artworks", [])

    artworks_summary = ""
    for idx, w in enumerate(artworks[:4], start=1):
        artworks_summary += f"{idx}. {w.get('title_kr')} ({w.get('title_en')}), {w.get('year')} / {w.get('medium_kr')} / {w.get('gallery_or_location')}\n"

    system_instruction = (
        "당신은 베니스 비엔날레, 카셀 도쿠멘타, 휘트니 비엔날레 등 세계 최정상 현대미술제를 총괄하는 "
        "'수석 큐레이터이자 미술 평론가'입니다. "
        "당신의 임무는 제공된 작가 정보 및 위키피디아 텍스트를 검토하여, "
        "1) 위키피디아 특유의 메마르고 단편적인 서술이나 오류, 대중적 오해를 날카롭게 팩트체크 및 교정하고, "
        "2) 작가의 미학 이론, 철학적 의의, 시대정신(Zeitgeist), 현대미술사적 맥락을 품격 있는 한국어로 심층 해설하는 것입니다.\n\n"
        "반드시 텔레그램 지원 HTML 태그(<b>, <i>, <code>)만을 사용하여 가독성 높고 정갈하게 작성하세요. "
        "HTML 문법 오류(닫히지 않은 태그 등)가 없도록 완벽히 준수해야 합니다."
    )

    user_prompt = f"""
[분석 대상 현대미술가]
- 국문/영문 이름: {name_kr} ({name_en})
- 국적 및 주요 장르: {nationality} / {category}
- 기존 아카이브/위키 요약:
{philosophy}
{features}
{raw_wiki_text}

- 대표 작품 데이터:
{artworks_summary}

위 정보를 바탕으로 아래 양식의 품격 있는 텔레그램 전용 도슨트 카드를 작성해 주세요:

<b>🏛️ [Gemini AI 비엔날레 큐레이터 도슨트]</b>
📅 <i>{datetime.now(KST).strftime('%Y년 %m월 %d일')}</i>

━━━━━━━━━━━━━━━━━━
👤 <b>작가:</b> <b>{name_kr}</b> (<i>{name_en}</i>)
🌍 <b>국적 / 출생:</b> {nationality}
🏷️ <b>대표 장르:</b> {category}
━━━━━━━━━━━━━━━━━━

💡 <b>미학 철학 & 시대정신 (Artistic Worldview)</b>
(작가가 현대 사회와 미술계에 던진 근원적 질문과 철학을 2~3문단으로 깊이 있게 해설)

✨ <b>조형적 특징 & 시각 언어 (Visual Language)</b>
(물성, 공간 구성, 매체 실험 등 작품의 시각적·감각적 핵심 요소를 해설)

🔍 <b>위키 팩트체크 & 큐레이터 심층 비평 (Curator's Critique)</b>
(일반 백과사전의 단편적 설명이나 세간의 오해를 미술사적 관점에서 짚어주고, 비엔날레 등에서 이 작가가 지니는 결정적 의의를 팩트체크 및 교정)

🖼️ <b>주요 대표작 도록 (Masterpieces)</b>
(대표작 3~4점에 대해 작품명, 연도, 기법, 소장처와 함께 큐레이터의 한 줄 감상 포인트 작성)

👇 <i>아래 버튼을 누르시면 공식 인스타그램과 고화질 갤러리에서 실물 작품을 감상하실 수 있습니다.</i>
"""

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": system_instruction + "\n\n" + user_prompt}]
            }
        ],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 1800
        }
    }

    for model_name in CANDIDATE_MODELS:
        url = API_URL_TEMPLATE.format(model=model_name, key=api_key)
        try:
            res = requests.post(url, json=payload, timeout=30)
            if res.status_code == 200:
                data = res.json()
                candidates = data.get("candidates", [])
                if candidates:
                    text_part = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                    if text_part:
                        logger.info(f"Successfully generated docent card using {model_name}")
                        return text_part.strip()
            else:
                logger.warning(f"Model {model_name} returned status {res.status_code}, trying next...")
        except Exception as e:
            logger.warning(f"Model {model_name} error ({e}), trying next...")

    return None
