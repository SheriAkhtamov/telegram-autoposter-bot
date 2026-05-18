import re

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.utils.deep_linking import create_start_link

from app.common import escape_user_name, get_translation


def create_referrals_router(state):
    router = Router()

    @router.message(lambda m: m.text and get_translation(state, str(m.from_user.id), "share_bot") in m.text)
    async def share_bot_info(msg: Message):
        user_id = str(msg.from_user.id)
        invited = state.referrals.get(user_id, [])
        text = get_translation(state, user_id, "share_bot_info").format(len(invited))
        top_referrers_text = re.sub(r"<[^>]+>", "", get_translation(state, user_id, "top_referrers")).split(":")[0]
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=get_translation(state, user_id, "ref_link").split("\n")[0], callback_data="get_ref_link")],
                [InlineKeyboardButton(text=top_referrers_text, callback_data="show_top_referrers")],
            ]
        )
        await msg.answer(text, reply_markup=keyboard)

    @router.callback_query(F.data == "get_ref_link")
    async def send_ref_link(call: CallbackQuery):
        user_id = str(call.from_user.id)
        link = await create_start_link(state.bot, payload=user_id)
        await call.message.answer(get_translation(state, user_id, "ref_link").format(link))
        await call.answer()

    @router.callback_query(F.data == "show_top_referrers")
    async def show_top_referrers(call: CallbackQuery):
        user_id = str(call.from_user.id)
        leaderboard = [(uid, len(invited_list)) for uid, invited_list in state.referrals.items()]
        leaderboard.sort(key=lambda item: item[1], reverse=True)

        top_text = ""
        for position, (uid, count) in enumerate(leaderboard[:10], start=1):
            try:
                user = await state.bot.get_chat(uid)
                name = escape_user_name(user.full_name)
            except Exception:
                if state.users[user_id].get("language", "ru") == "ru":
                    name = escape_user_name(f"Пользователь {uid}")
                elif state.users[user_id].get("language") == "en":
                    name = escape_user_name(f"User {uid}")
                else:
                    name = escape_user_name(f"Foydalanuvchi {uid}")
            suffix = "приглашений" if state.users[user_id].get("language", "ru") == "ru" else "invitations" if state.users[user_id].get("language") == "en" else "takliflar"
            top_text += f"{position}. {name} — {count} {suffix}\n"

        current_user_id = str(call.from_user.id)
        position = next((index for index, (uid, _) in enumerate(leaderboard, start=1) if uid == current_user_id), None)
        if position:
            top_text += f"\n{get_translation(state, user_id, 'your_position').format(position)}"
        else:
            top_text += f"\n{get_translation(state, user_id, 'no_referrals')}"

        await call.message.answer(get_translation(state, user_id, "top_referrers").format(top_text))
        await call.answer()

    return router
