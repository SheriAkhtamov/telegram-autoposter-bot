import hashlib
import hmac
import secrets
import string
import time

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from .common import get_translation
from .config import PANEL_BASE_PATH, PANEL_BASE_URL, PANEL_SESSION_COOKIE, PANEL_SESSION_TTL
from .database import save_users


def build_panel_url(path=""):
    suffix = path or PANEL_BASE_PATH
    return f"{PANEL_BASE_URL.rstrip('/')}{suffix}"


def normalize_panel_login(login):
    return login.strip()


def is_valid_panel_login(login):
    import re

    return bool(re.fullmatch(r"[A-Za-z0-9_.-]{4,32}", login))


def is_valid_panel_password(password):
    return 8 <= len(password.strip()) <= 64


def is_panel_login_available(state, login, exclude_user_id=None):
    normalized = login.lower()
    for user_id, data in state.users.items():
        existing_login = (data.get("panel_login") or "").lower()
        if user_id != exclude_user_id and existing_login == normalized:
            return False
    return True


def generate_panel_login(user_id):
    return f"user{user_id}_{secrets.token_hex(2)}"


def generate_panel_password(length=12):
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def hash_panel_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        120_000,
    ).hex()
    return salt, password_hash


def verify_panel_password(password, salt, password_hash):
    candidate_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        120_000,
    ).hex()
    return hmac.compare_digest(candidate_hash, password_hash)


async def ensure_panel_credentials(state, user_id, reset_password=False):
    user = state.users[user_id]
    credentials_changed = False

    if not user.get("panel_login"):
        panel_login = generate_panel_login(user_id)
        while not is_panel_login_available(state, panel_login, exclude_user_id=user_id):
            panel_login = generate_panel_login(user_id)
        user["panel_login"] = panel_login
        credentials_changed = True

    plain_password = None
    if reset_password or not user.get("panel_password_hash") or not user.get("panel_password_salt"):
        plain_password = generate_panel_password()
        salt, password_hash = hash_panel_password(plain_password)
        user["panel_password_salt"] = salt
        user["panel_password_hash"] = password_hash
        credentials_changed = True

    if credentials_changed:
        await save_users(state)

    return user["panel_login"], plain_password


async def update_panel_login(state, user_id, new_login):
    normalized_login = normalize_panel_login(new_login)
    if not is_valid_panel_login(normalized_login):
        raise ValueError("invalid_login")
    if not is_panel_login_available(state, normalized_login, exclude_user_id=user_id):
        raise ValueError("login_taken")

    state.users[user_id]["panel_login"] = normalized_login
    await save_users(state)
    return normalized_login


async def update_panel_password(state, user_id, new_password):
    normalized_password = new_password.strip()
    if not is_valid_panel_password(normalized_password):
        raise ValueError("invalid_password")

    salt, password_hash = hash_panel_password(normalized_password)
    state.users[user_id]["panel_password_salt"] = salt
    state.users[user_id]["panel_password_hash"] = password_hash
    await save_users(state)
    return normalized_password


def create_panel_session(state, user_id):
    session_id = secrets.token_urlsafe(32)
    state.panel_sessions[session_id] = {
        "user_id": user_id,
        "expires_at": time.time() + PANEL_SESSION_TTL,
    }
    return session_id


def get_panel_session_user(state, request):
    session_id = request.cookies.get(PANEL_SESSION_COOKIE)
    if not session_id:
        return None

    session = state.panel_sessions.get(session_id)
    if not session:
        return None

    if session["expires_at"] <= time.time():
        state.panel_sessions.pop(session_id, None)
        return None

    session["expires_at"] = time.time() + PANEL_SESSION_TTL
    return session["user_id"]


def clear_panel_session(state, request):
    session_id = request.cookies.get(PANEL_SESSION_COOKIE)
    if session_id:
        state.panel_sessions.pop(session_id, None)


def build_panel_access_keyboard(state, user_id):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=get_translation(state, user_id, "panel_open_button"), url=build_panel_url(PANEL_BASE_PATH))],
            [
                InlineKeyboardButton(text=get_translation(state, user_id, "panel_change_login_button"), callback_data="panel_change_login"),
                InlineKeyboardButton(text=get_translation(state, user_id, "panel_change_password_button"), callback_data="panel_change_password"),
            ],
        ]
    )


def build_panel_access_text(state, user_id, include_password=False, password=None):
    panel_login = state.users[user_id].get("panel_login")
    panel_url = build_panel_url(PANEL_BASE_PATH)
    if include_password and password:
        return get_translation(state, user_id, "panel_access_with_password").format(panel_url, panel_login, password)
    return get_translation(state, user_id, "panel_access_without_password").format(panel_url, panel_login)


async def send_panel_access_message(message_target, state, user_id, include_password=False, password=None):
    panel_login, generated_password = await ensure_panel_credentials(state, user_id)
    password_to_show = password or generated_password
    state.users[user_id]["panel_login"] = panel_login
    await message_target.answer(
        build_panel_access_text(state, user_id, include_password=include_password and bool(password_to_show), password=password_to_show),
        reply_markup=build_panel_access_keyboard(state, user_id),
        disable_web_page_preview=True,
    )
