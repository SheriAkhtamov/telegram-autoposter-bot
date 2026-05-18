from pathlib import Path

ADMIN_IDS = set()
TOKEN = "123456:CHANGE_ME"
DATABASE_URL = "DATABASE_URL"

PANEL_HOST = "0.0.0.0"
PANEL_PORT = 8080
PANEL_BASE_URL = "http://127.0.0.1:8080"
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
