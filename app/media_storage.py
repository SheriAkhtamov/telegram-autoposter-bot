import mimetypes
import re
from pathlib import Path

from aiogram.types import FSInputFile

from .config import DEFAULT_EXTENSIONS, MEDIA_ROOT


def sanitize_filename(file_name):
    base_name = Path(file_name).name.strip()
    sanitized = re.sub(r'[<>:"/\\|?*\s]+', "_", base_name)
    return sanitized.strip("._") or "file"


def build_storage_filename(message_key, file_type, original_file_name=None, mime_type=None):
    safe_key = message_key.replace(":", "_")
    if original_file_name:
        return f"{safe_key}_{sanitize_filename(original_file_name)}"
    suffix = mimetypes.guess_extension(mime_type or "") or DEFAULT_EXTENSIONS.get(file_type, "")
    return f"{safe_key}_{file_type or 'file'}{suffix}"


def get_message_media_payload(msg):
    if msg.photo:
        return msg.photo[-1].file_id, "photo", f"photo_{msg.message_id}.jpg", "image/jpeg"
    if msg.video:
        return msg.video.file_id, "video", msg.video.file_name or f"video_{msg.message_id}.mp4", msg.video.mime_type
    if msg.audio:
        return msg.audio.file_id, "audio", msg.audio.file_name or f"audio_{msg.message_id}.mp3", msg.audio.mime_type
    if msg.voice:
        return msg.voice.file_id, "voice", f"voice_{msg.message_id}.ogg", msg.voice.mime_type
    if msg.document:
        return msg.document.file_id, "document", msg.document.file_name or f"document_{msg.message_id}", msg.document.mime_type
    return None, None, None, None


async def store_media_locally(state, user_id, message_key, file_id, file_type, original_file_name=None, mime_type=None):
    user_dir = MEDIA_ROOT / user_id
    user_dir.mkdir(parents=True, exist_ok=True)
    storage_file_name = build_storage_filename(message_key, file_type, original_file_name, mime_type)
    file_path = user_dir / storage_file_name
    await state.bot.download(file_id, destination=file_path)
    return str(file_path), original_file_name or storage_file_name


def build_local_input_file(file_path, original_file_name=None):
    if not file_path:
        return None
    path = Path(file_path)
    if not path.exists():
        return None
    return FSInputFile(path, filename=original_file_name or path.name)


def delete_local_file(file_path):
    if not file_path:
        return
    path = Path(file_path)
    if path.exists():
        path.unlink()


def guess_uploaded_file_type(file_name=None, mime_type=None):
    guessed_mime = mime_type or mimetypes.guess_type(file_name or "")[0] or ""
    if guessed_mime.startswith("image/"):
        return "photo"
    if guessed_mime.startswith("video/"):
        return "video"
    if guessed_mime.startswith("audio/"):
        return "audio"
    return "document"


def store_uploaded_file_locally(user_id, message_key, uploaded_file):
    original_file_name = uploaded_file.filename or "upload.bin"
    file_type = guess_uploaded_file_type(original_file_name, uploaded_file.content_type)
    user_dir = MEDIA_ROOT / user_id
    user_dir.mkdir(parents=True, exist_ok=True)
    storage_file_name = build_storage_filename(message_key, file_type, original_file_name, uploaded_file.content_type)
    file_path = user_dir / storage_file_name

    uploaded_file.file.seek(0)
    with open(file_path, "wb") as destination:
        while True:
            chunk = uploaded_file.file.read(65536)
            if not chunk:
                break
            destination.write(chunk)

    return str(file_path), original_file_name, file_type
