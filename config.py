"""
DramaNova Bot - Configuration (LOCKED)
All encoding & subtitle settings are FINAL and must not be changed.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ─── DramaNova API (sansekai) ────────────────────────────────
BASE_URL = "https://api.sansekai.my.id/api/dramanova"

# ─── Telegram ────────────────────────────────────────────────
API_ID = int(os.getenv("API_ID", "0"))
API_HASH = os.getenv("API_HASH", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
CHANNEL_ID = int(os.getenv("AUTO_CHANNEL", "0"))
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_ID", "0").split(",") if x.strip()]

# ─── Paths ───────────────────────────────────────────────────
DOWNLOAD_DIR = os.path.join(os.path.dirname(__file__), "downloads")
MERGE_DIR = os.path.join(os.path.dirname(__file__), "merged")
TEMP_DIR = os.path.join(os.path.dirname(__file__), "temp")

for d in [DOWNLOAD_DIR, MERGE_DIR, TEMP_DIR]:
    os.makedirs(d, exist_ok=True)

# ─── FFmpeg Encoding (LOCKED 🔒) ────────────────────────────
CRF = 23
PRESET = "ultrafast"
VIDEO_CODEC = "libx264"
AUDIO_CODEC = "copy"

# ─── Subtitle Style (LOCKED 🔒) ─────────────────────────────
SUB_FONT = "Standard Symbols PS"
SUB_SIZE = 10
SUB_COLOR = "&H00FFFFFF"  # Putih
SUB_BOLD = 1
SUB_OUTLINE = 1
SUB_OUTLINE_COLOR = "&H00000000"  # Hitam
SUB_MARGIN_V = 90

# ─── Download Settings ───────────────────────────────────────
MAX_CONCURRENT_DOWNLOADS = 3
DOWNLOAD_TIMEOUT = 120  # seconds
MAX_RETRIES = 3

# ─── Auto Mode ───────────────────────────────────────────────
AUTO_CHECK_INTERVAL = 300  # seconds (5 min)
AUTO_MODE_ENABLED = os.getenv("AUTO_MODE", "false").lower() == "true"
