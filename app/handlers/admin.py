import asyncio
import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app.common import get_translation
from app.config import ADMIN_IDS


def create_admin_router(state):
    router = Router()

    @router.message(lambda msg: state.admin_broadcast_state.get(msg.from_user.id, {}).get("stage") == "awaiting_message")
    async def receive_broadcast_message(msg: Message):
        user_id = str(msg.from_user.id)
        content = {}

        if msg.photo:
            content["file_id"] = msg.photo[-1].file_id
            content["file_type"] = "photo"
            content["caption"] = msg.caption
        elif msg.video:
            content["file_id"] = msg.video.file_id
            content["file_type"] = "video"
            content["caption"] = msg.caption
        elif msg.audio:
            content["file_id"] = msg.audio.file_id
            content["file_type"] = "audio"
            content["caption"] = msg.caption
        elif msg.voice:
            content["file_id"] = msg.voice.file_id
            content["file_type"] = "voice"
            content["caption"] = None
        elif msg.document:
            content["file_id"] = msg.document.file_id
            content["file_type"] = "document"
            content["caption"] = msg.caption
        elif msg.text:
            content["text"] = msg.text
        else:
            content["text"] = "[Пустое сообщение]" if state.users[user_id].get("language", "ru") == "ru" else "[Empty message]" if state.users[user_id].get("language") == "en" else "[Bo'sh xabar]"

        state.admin_broadcast_state[msg.from_user.id]["content"] = content
        state.admin_broadcast_state[msg.from_user.id]["stage"] = "confirm"
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text=get_translation(state, user_id, "yes"), callback_data="admin_broadcast_confirm"),
                    InlineKeyboardButton(text=get_translation(state, user_id, "no"), callback_data="admin_broadcast_cancel"),
                ]
            ]
        )
        await msg.answer(get_translation(state, user_id, "broadcast_ready"), reply_markup=keyboard)

    @router.callback_query(F.data == "admin_broadcast_confirm")
    async def confirm_broadcast(call: CallbackQuery):
        user_id = str(call.from_user.id)
        state_data = state.admin_broadcast_state.get(call.from_user.id)
        if not state_data or "content" not in state_data:
            await call.message.answer(get_translation(state, user_id, "broadcast_error"))
            return

        content = state_data["content"]
        count = 0
        errors = 0
        for target_user_id in state.users:
            try:
                if content.get("file_type") == "photo":
                    await state.bot.send_photo(target_user_id, content["file_id"], caption=content.get("caption", ""))
                elif content.get("file_type") == "video":
                    await state.bot.send_video(target_user_id, content["file_id"], caption=content.get("caption", ""))
                elif content.get("file_type") == "audio":
                    await state.bot.send_audio(target_user_id, content["file_id"], caption=content.get("caption", ""))
                elif content.get("file_type") == "voice":
                    await state.bot.send_voice(target_user_id, content["file_id"])
                elif content.get("file_type") == "document":
                    await state.bot.send_document(target_user_id, content["file_id"], caption=content.get("caption", ""))
                elif "text" in content:
                    await state.bot.send_message(target_user_id, content["text"])
                else:
                    await state.bot.send_message(
                        target_user_id,
                        "[Пустое сообщение]" if state.users[target_user_id].get("language", "ru") == "ru" else "[Empty message]" if state.users[target_user_id].get("language") == "en" else "[Bo'sh xabar]",
                    )
                count += 1
                await asyncio.sleep(0.04)
            except Exception:
                errors += 1

        del state.admin_broadcast_state[call.from_user.id]
        await call.message.answer(get_translation(state, user_id, "broadcast_complete").format(count, errors))

    @router.callback_query(F.data == "admin_broadcast_cancel")
    async def cancel_broadcast(call: CallbackQuery):
        state.admin_broadcast_state.pop(call.from_user.id, None)
        await call.message.answer(get_translation(state, str(call.from_user.id), "broadcast_cancelled"))

    @router.message(Command("sheri"))
    async def handle_sheri_command(msg: Message):
        if msg.from_user.id not in ADMIN_IDS:
            await msg.answer(get_translation(state, str(msg.from_user.id), "not_wizard"))
            return

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=get_translation(state, str(msg.from_user.id), "send_broadcast").split(":")[0], callback_data="admin_broadcast")],
                [InlineKeyboardButton(text=get_translation(state, str(msg.from_user.id), "report_ready").split("!")[0], callback_data="admin_report")],
            ]
        )
        await msg.answer(get_translation(state, str(msg.from_user.id), "admin_menu"), reply_markup=keyboard)

    @router.callback_query(F.data == "admin_broadcast")
    async def start_broadcast(call: CallbackQuery):
        state.admin_broadcast_state[call.from_user.id] = {"stage": "awaiting_message"}
        await call.message.answer(get_translation(state, str(call.from_user.id), "send_broadcast"))
        await call.answer()

    @router.callback_query(F.data == "admin_report")
    async def admin_report(call: CallbackQuery):
        user_id = str(call.from_user.id)
        total = len(state.users)
        active = 0
        blocked = 0
        unknown = 0

        for target_user_id in state.users:
            try:
                await state.bot.send_chat_action(target_user_id, "typing")
                active += 1
            except Exception:
                blocked += 1
            await asyncio.sleep(0.04)

        text = get_translation(state, user_id, "admin_report").format(total, active, blocked, unknown)
        await call.message.answer(text)
        await call.answer(get_translation(state, user_id, "report_ready"))

    return router
