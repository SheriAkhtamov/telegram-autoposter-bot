from pathlib import Path
import os

ADMIN_IDS = set(map(int, filter(None, os.getenv("ADMIN_IDS", "").split(","))))
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "123456:CHANGE_ME")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@localhost/dbname")

PANEL_HOST = os.getenv("PANEL_HOST", "0.0.0.0")
PANEL_PORT = int(os.getenv("PANEL_PORT", "8080"))
PANEL_BASE_URL = os.getenv("PANEL_BASE_URL", "http://127.0.0.1:8080")
PANEL_BASE_PATH = "/panel"
PANEL_SESSION_COOKIE = "panel_session"
PANEL_SESSION_TTL = 7 * 24 * 60 * 60

ROOT_DIR = Path(__file__).resolve().parent.parent
MEDIA_ROOT = ROOT_DIR / "media_storage"
DEFAULT_EXTENSIONS = {
    "photo": ".jpg",
    "video": ".mp4",
    "audio": ".mp3",
    "voice": ".ogg",
    "document": "",
}

AUTO_PUBLISH_DELAY_MIN = int(os.getenv("AUTO_PUBLISH_DELAY_MIN", "1800"))
AUTO_PUBLISH_DELAY_MAX = int(os.getenv("AUTO_PUBLISH_DELAY_MAX", "3600"))

# Ограничения
MAX_QUEUE_SIZE_PER_USER = int(os.getenv("MAX_QUEUE_SIZE_PER_USER", "50"))
MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "50"))
ENABLE_PUBLISH_NOTIFICATION = os.getenv("ENABLE_PUBLISH_NOTIFICATION", "true").lower() == "true"
