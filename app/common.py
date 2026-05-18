import html
import time

from translations import TRANSLATIONS


def get_translation(state, user_id, key):
    lang = state.users.get(str(user_id), {}).get("language", "ru")
    return TRANSLATIONS.get(lang, TRANSLATIONS["ru"]).get(key, key)


async def get_channel_link(state, channel_id, user_id):
    user = state.users.get(str(user_id), {})
    invite_link = user.get("publish_channel_invite_link")
    chat = await state.bot.get_chat(channel_id)
    if invite_link:
        return f"<a href='{invite_link}'>{chat.title}</a>"
    if chat.username:
        link = f"https://t.me/{chat.username}"
    else:
        link = f"https://t.me/c/{str(chat.id)[4:]}"
    return f"<a href='{link}'>{chat.title}</a>"


async def check_bot_is_admin(state, chat_id):
    try:
        me = await state.bot.get_chat_member(chat_id, (await state.bot.me()).id)
        return me.can_post_messages or me.status == "administrator"
    except Exception:
        return False


async def user_is_admin(state, user_id, channel_id):
    try:
        admins = await state.bot.get_chat_administrators(channel_id)
        return any(admin.user.id == int(user_id) for admin in admins)
    except Exception:
        return False


def format_storage_time(timestamp):
    if not timestamp:
        return "Неизвестно"
    return time.strftime("%d.%m.%Y %H:%M", time.localtime(timestamp))


def translation_value_exists(text, key):
    normalized = (text or "").strip().lower()
    return any(normalized == (lang_map.get(key, "") or "").strip().lower() for lang_map in TRANSLATIONS.values())


def escape_user_name(name):
    return html.escape(name)
