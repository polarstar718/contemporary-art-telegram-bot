"""
GitHub Actions Automated Dispatcher for Contemporary Art Telegram Bot.
Invoked by .github/workflows/daily_dispatch.yml every weekday at 08:00 KST (23:00 UTC).
Triggers the Vercel 24/7 cloud serverless API endpoint, which runs full Gemini AI commentary
and delivers to all subscribers with built-in deduplication.
"""

import logging
import sys
import requests

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("DailyDispatcher")

VERCEL_CRON_URL = "https://contemporary-art-telegram-bot.vercel.app/api?cron=daily"

def main():
    logger.info("=" * 60)
    logger.info("Initiating weekday 08:00 KST contemporary art docent dispatch...")
    logger.info(f"Calling cloud endpoint: {VERCEL_CRON_URL}")
    
    try:
        # Give up to 60s for Gemini AI analysis and multi-subscriber delivery
        response = requests.get(VERCEL_CRON_URL, timeout=60)
        logger.info(f"Response HTTP Status: {response.status_code}")
        
        try:
            result = response.json()
            logger.info(f"Response Payload: {result}")
        except Exception:
            logger.info(f"Raw Response: {response.text}")
            result = {}

        if response.status_code == 200:
            status = result.get("status")
            if status == "success":
                artist = result.get("artist")
                delivered = result.get("delivered")
                total = result.get("total_subscribers")
                logger.info(f"[SUCCESS] Today's docent card ({artist}) delivered to {delivered}/{total} subscribers.")
            elif status == "already_sent":
                logger.info(f"[INFO] {result.get('message')}")
            else:
                logger.info(f"[DONE] Dispatch result: {result}")
            sys.exit(0)
        else:
            logger.error(f"[ERROR] Endpoint returned non-200 code: {response.status_code}")
            sys.exit(1)

    except requests.exceptions.Timeout:
        logger.error("[TIMEOUT] Request timed out after 60s.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"[EXCEPTION] Failed to dispatch: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
