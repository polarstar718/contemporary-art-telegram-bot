import os
from pathlib import Path
from dotenv import load_dotenv

# Base directory
BASE_DIR = Path(__file__).resolve().parent

# Load .env file
load_dotenv(BASE_DIR / ".env")

# Telegram Configuration
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

# Delivery Schedule
# Default: Monday to Friday at 08:00 KST
DELIVERY_HOUR = int(os.getenv("DELIVERY_HOUR", "8"))
DELIVERY_MINUTE = int(os.getenv("DELIVERY_MINUTE", "0"))
TIMEZONE = os.getenv("TIMEZONE", "Asia/Seoul")

# Data File Paths
DATA_DIR = BASE_DIR / "data"
ARTISTS_FILE = DATA_DIR / "artists.json"
HISTORY_FILE = DATA_DIR / "history.json"
SUBSCRIBERS_FILE = DATA_DIR / "subscribers.json"

# Gemini API Key (optional for AI enrichment)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
