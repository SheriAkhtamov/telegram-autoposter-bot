import logging
import time

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from app.common import get_translation, translation_value_exists
from app.config import MAX_QUEUE_SIZE_PER_USER
from app.database import save_storage
from app.media_storage import get_message_media_payload, store_media_locally
from app.queue import cleanup_stored_message, ensure_user_publish_task, send_to_channel, touch_last_published


def create_posts_router(state):
    router = Router()

    @router.message(lambda msg: not msg.text or not msg.text.startswith("/"))
    async def handle_message(msg: Message):
        user_id = str(msg.from_user.id)
        if msg.text and any(
            translation_value_exists(msg.text.lower().strip(), key)
            for key in ("menu", "share_bot", "change_language", "donate", "panel_open_button")
        ):
            return
        if state.admin_broadcast_state.get(msg.from_user.id, {}).get("stage") == "awaiting_message":
            return
        if state.panel_credentials_state.get(msg.from_user.id):
            return

        user = state.users.get(user_id)
        if not user or not user.get("publish_channel_id"):
            await msg.answer(get_translation(state, user_id, "add_channels"))
            return

        # Проверка размера очереди
        user_posts_count = sum(1 for key, data in state.storage.items() if data["user_id"] == user_id)
        if user_posts_count >= MAX_QUEUE_SIZE_PER_USER:
            await msg.answer(get_translation(state, user_id, "queue_full").format(MAX_QUEUE_SIZE_PER_USER))
            return

        text = msg.caption if msg.caption else (msg.text or "")
        file_id, file_type, original_file_name, mime_type = get_message_media_payload(msg)
        if not text and not file_id:
            await msg.answer(get_translation(state, user_id, "draft_error"))
            return

        message_key = f"{user_id}:{msg.message_id}"
        file_path = None
        if file_id and file_type:
            try:
                file_path, original_file_name = await store_media_locally(
                    state,
                    user_id,
                    message_key,
                    file_id,
                    file_type,
                    original_file_name,
                    mime_type,
                )
            except Exception as exc:
                logging.error(f"Ошибка локального сохранения медиа: {exc}")
                await msg.answer(get_translation(state, user_id, "draft_error"))
                return

        state.storage[message_key] = {
            "user_id": user_id,
            "text": text,
            "file_id": None,
            "file_path": file_path,
            "original_file_name": original_file_name,
            "file_type": file_type,
            "temp_msg_id": None,
            "created_at": time.time(),
        }
        await save_storage(state)
        ensure_user_publish_task(state, user_id)
        await msg.answer(get_translation(state, user_id, "post_scheduled"))

        try:
            await state.bot.delete_message(msg.chat.id, msg.message_id)
        except Exception as exc:
            logging.warning(f"Не удалось удалить сообщение: {exc}")

    @router.callback_query(F.data.startswith("publish:"))
    async def publish_now(call: CallbackQuery):
        user_id = str(call.from_user.id)
        _, target_user_id, message_key = call.data.split(":", 2)
        if message_key not in state.storage or state.storage[message_key]["user_id"] != target_user_id:
            await call.answer(get_translation(state, user_id, "task_not_found"))
            return

        data = state.storage[message_key]
        try:
            await send_to_channel(
                state,
                target_user_id,
                data["text"],
                data.get("file_id"),
                data.get("file_type"),
                data.get("file_path"),
                data.get("original_file_name"),
            )
            await cleanup_stored_message(state, data)
            del state.storage[message_key]
            await save_storage(state)
            await touch_last_published(state, target_user_id)
            await call.answer(get_translation(state, user_id, "publish_now"))
        except Exception as exc:
            logging.error(f"Ошибка ручной публикации: {exc}")
            await call.answer(get_translation(state, user_id, "publish_failed"), show_alert=True)

    @router.callback_query(F.data.startswith("remove:"))
    async def remove_task(call: CallbackQuery):
        user_id = str(call.from_user.id)
        _, target_user_id, message_key = call.data.split(":", 2)
        if message_key not in state.storage or state.storage[message_key]["user_id"] != target_user_id:
            await call.answer(get_translation(state, user_id, "task_already_removed"), show_alert=True)
            return
        try:
            await cleanup_stored_message(state, state.storage[message_key])
            del state.storage[message_key]
            await save_storage(state)
            await call.answer(get_translation(state, user_id, "task_removed"), show_alert=True)
        except Exception as exc:
            await call.answer(get_translation(state, user_id, "task_remove_error").format(exc), show_alert=True)

    return router
