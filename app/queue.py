import asyncio
import logging
import random
import time

from .common import get_channel_link
from .config import AUTO_PUBLISH_DELAY_MIN, AUTO_PUBLISH_DELAY_MAX
from .database import save_storage, save_users
from .media_storage import build_local_input_file, delete_local_file


async def delete_temp_draft_message(state, data):
    temp_msg_id = data.get("temp_msg_id")
    temp_channel_id = state.users.get(data["user_id"], {}).get("temp_channel_id")
    if not temp_msg_id or not temp_channel_id:
        return
    try:
        await state.bot.delete_message(temp_channel_id, temp_msg_id)
    except Exception:
        pass


async def cleanup_stored_message(state, data):
    await delete_temp_draft_message(state, data)
    try:
        delete_local_file(data.get("file_path"))
    except Exception as exc:
        logging.warning(f"Не удалось удалить локальный файл {data.get('file_path')}: {exc}")


def get_user_storage_items(state, user_id):
    return sorted(
        ((message_key, data) for message_key, data in state.storage.items() if data["user_id"] == user_id),
        key=lambda item: ((item[1].get("created_at") or 0), item[0]),
    )


async def send_to_channel(state, user_id, text, file_id=None, file_type=None, file_path=None, original_file_name=None):
    user = state.users[user_id]
    publish_channel_id = user.get("publish_channel_id")
    if not publish_channel_id:
        raise ValueError("Publish channel is not configured")

    if user.get("hyperlink_enabled", True):
        channel_link = await get_channel_link(state, publish_channel_id, user_id)
        text = f"{text}\n\n{channel_link}"

    caption = text or None
    media_source = build_local_input_file(file_path, original_file_name) or file_id
    if file_type:
        if not media_source:
            raise FileNotFoundError(f"Media source for task is missing: {file_path}")
        if file_type == "photo":
            await state.bot.send_photo(publish_channel_id, media_source, caption=caption)
        elif file_type == "video":
            await state.bot.send_video(publish_channel_id, media_source, caption=caption)
        elif file_type == "audio":
            await state.bot.send_audio(publish_channel_id, media_source, caption=caption)
        elif file_type == "voice":
            await state.bot.send_voice(publish_channel_id, media_source, caption=caption)
        elif file_type == "document":
            await state.bot.send_document(publish_channel_id, media_source, caption=caption)
        else:
            raise ValueError(f"Unsupported file type: {file_type}")
        return

    if text:
        await state.bot.send_message(publish_channel_id, text)
        return

    raise ValueError("Nothing to publish")


async def touch_last_published(state, user_id):
    state.users[user_id]["last_published_at"] = time.time()
    await save_users(state)


def ensure_user_publish_task(state, user_id):
    event = state.user_publish_events.get(user_id)
    if not event:
        event = asyncio.Event()
        state.user_publish_events[user_id] = event

    if state.users.get(user_id, {}).get("auto_publish", True):
        event.set()
    else:
        event.clear()

    task = state.user_active_tasks.get(user_id)
    if not task or task.done():
        state.user_active_tasks[user_id] = asyncio.create_task(publish_queue_for_user(state, user_id, event))
    return event


async def publish_queue_for_user(state, user_id, publish_event):
    while True:
        await publish_event.wait()
        tasks = [message_key for message_key, _ in get_user_storage_items(state, user_id)]
        if not tasks:
            state.user_active_tasks.pop(user_id, None)
            return

        last_published = state.users[user_id].get("last_published_at", 0)
        current_time = time.time()
        time_since_last = current_time - last_published
        if time_since_last < AUTO_PUBLISH_DELAY_MIN:
            await asyncio.sleep(AUTO_PUBLISH_DELAY_MIN - time_since_last)

        message_key = tasks[0]
        data = state.storage[message_key]
        try:
            await send_to_channel(
                state,
                data["user_id"],
                data["text"],
                data.get("file_id"),
                data.get("file_type"),
                data.get("file_path"),
                data.get("original_file_name"),
            )
            await cleanup_stored_message(state, data)
            del state.storage[message_key]
            await save_storage(state)
            await touch_last_published(state, user_id)
            await asyncio.sleep(random.randint(AUTO_PUBLISH_DELAY_MIN, AUTO_PUBLISH_DELAY_MAX))
        except Exception as exc:
            logging.error(f"Ошибка публикации: {exc}")
