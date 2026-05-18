import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, ContentType, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice, Message, PreCheckoutQuery

from translations import TRANSLATIONS

from app.common import check_bot_is_admin, get_channel_link, get_translation, translation_value_exists, user_is_admin
from app.database import save_referrals, save_users
from app.keyboards import get_donate_menu, get_language_menu, get_main_menu, get_persistent_menu
from app.panel_auth import ensure_panel_credentials, send_panel_access_message, update_panel_login, update_panel_password
from app.queue import ensure_user_publish_task


def create_general_router(state):
    router = Router()

    @router.message(Command(commands=["start", "menu"]))
    async def start(msg: Message):
        user_id = str(msg.from_user.id)
        is_new_user = user_id not in state.users
        if is_new_user:
            state.users[user_id] = {
                "publish_channel_id": None,
                "temp_channel_id": None,
                "auto_publish": True,
                "publish_channel_invite_link": None,
                "language": None,
                "hyperlink_enabled": True,
                "last_published_at": 0,
                "panel_login": None,
                "panel_password_hash": None,
                "panel_password_salt": None,
            }
            await save_users(state)

        parts = msg.text.strip().split()
        if len(parts) > 1 and is_new_user:
            referrer_id = parts[1]
            if referrer_id != user_id and user_id not in state.referrals.get(referrer_id, []):
                state.referrals.setdefault(referrer_id, []).append(user_id)
                await save_referrals(state)

        _, generated_password = await ensure_panel_credentials(state, user_id)
        if generated_password:
            await send_panel_access_message(msg, state, user_id, include_password=True, password=generated_password)

        if not state.users[user_id].get("language"):
            await msg.answer("Выберите язык / Select language / Tilni tanlang:", reply_markup=get_language_menu())
            return

        await msg.answer(get_translation(state, user_id, "menu_appeared"), reply_markup=get_persistent_menu(state, user_id))
        await msg.answer(get_translation(state, user_id, "add_channels"), reply_markup=get_main_menu(state, user_id))

    @router.callback_query(F.data.startswith("set_language:"))
    async def set_language(call: CallbackQuery):
        user_id = str(call.from_user.id)
        _, lang = call.data.split(":")
        if lang in TRANSLATIONS:
            state.users[user_id]["language"] = lang
            await save_users(state)
            await call.message.answer(
                get_translation(state, user_id, "language_changed").format(TRANSLATIONS[lang]["select_language"].split(":")[0])
            )
            await call.message.answer(get_translation(state, user_id, "add_channels"), reply_markup=get_main_menu(state, user_id))
            await call.message.answer(get_translation(state, user_id, "menu_appeared"), reply_markup=get_persistent_menu(state, user_id))
        await call.message.edit_text(get_translation(state, user_id, "menu_appeared"))
        await call.answer()

    @router.message(lambda m: m.text and get_translation(state, str(m.from_user.id), "change_language") in m.text)
    async def change_language(msg: Message):
        await msg.answer(get_translation(state, str(msg.from_user.id), "select_language"), reply_markup=get_language_menu())

    @router.message(lambda m: m.text and get_translation(state, str(m.from_user.id), "donate") in m.text)
    async def donate(msg: Message):
        await msg.answer(get_translation(state, str(msg.from_user.id), "donate_message"), reply_markup=get_donate_menu(state, str(msg.from_user.id)))

    @router.message(lambda m: m.text and get_translation(state, str(m.from_user.id), "panel_open_button") in m.text)
    async def open_panel(msg: Message):
        await send_panel_access_message(msg, state, str(msg.from_user.id))

    @router.callback_query(F.data.startswith("donate:"))
    async def donate_amount(call: CallbackQuery):
        user_id = str(call.from_user.id)
        _, amount = call.data.split(":")
        amount = int(amount)
        lang = state.users[user_id].get("language", "ru")
        try:
            await state.bot.send_invoice(
                chat_id=call.from_user.id,
                title="Поддержка бота" if lang == "ru" else "Bot Support" if lang == "en" else "Botni qo'llab-quvvatlash",
                description="Пожертвование для поддержки серверов бота" if lang == "ru" else "Donation to support bot servers" if lang == "en" else "Bot serverlarini qo'llab-quvvatlash uchun xayriya",
                payload=f"donation_{amount}",
                provider_token="",
                currency="XTR",
                prices=[LabeledPrice(
                    label="Пожертвование" if lang == "ru" else "Donation" if lang == "en" else "Xayriya",
                    amount=amount,
                )],
                need_name=False,
                need_phone_number=False,
                need_email=False,
                need_shipping_address=False,
            )
            await call.answer()
        except Exception as exc:
            logging.error(f"Ошибка при отправке инвойса: {exc}")
            await call.message.answer(get_translation(state, user_id, "donation_error"))
            await call.answer()

    @router.pre_checkout_query()
    async def pre_checkout_query(pre_checkout: PreCheckoutQuery):
        await state.bot.answer_pre_checkout_query(pre_checkout.id, ok=True)

    @router.message(F.content_type == ContentType.SUCCESSFUL_PAYMENT)
    async def successful_payment(msg: Message):
        await msg.answer(get_translation(state, str(msg.from_user.id), "donation_success"))

    @router.callback_query(F.data == "settings")
    async def settings(call: CallbackQuery):
        user_id = str(call.from_user.id)
        user = state.users[user_id]
        publish_channel_id = user.get("publish_channel_id")
        auto = get_translation(state, user_id, "auto_publish_on") if user.get("auto_publish", True) else get_translation(state, user_id, "auto_publish_off")
        hyperlink_state = get_translation(state, user_id, "hyperlink_on") if user.get("hyperlink_enabled", True) else get_translation(state, user_id, "hyperlink_off")

        async def channel_title(channel_id):
            if not channel_id:
                return get_translation(state, user_id, "channel_not_set")
            chat = await state.bot.get_chat(channel_id)
            invite_link = user.get("publish_channel_invite_link")
            if invite_link:
                link = invite_link
            elif chat.username:
                link = f"https://t.me/{chat.username}"
            else:
                link = f"https://t.me/c/{str(chat.id)[4:]}"
            return f"<a href='{link}'>{chat.title}</a>"

        publish = await channel_title(publish_channel_id)
        local_storage = get_translation(state, user_id, "local_storage_status")
        text = get_translation(state, user_id, "settings").format(publish, local_storage, auto, hyperlink_state)
        await call.message.edit_text(text, reply_markup=get_main_menu(state, user_id))

    @router.callback_query(F.data == "add_publish_channel")
    async def add_pub_channel(call: CallbackQuery):
        await call.message.answer(get_translation(state, str(call.from_user.id), "add_publish_channel_prompt"))
        await call.answer()

    @router.callback_query(F.data == "add_temp_channel")
    async def add_temp_channel(call: CallbackQuery):
        await call.message.answer(get_translation(state, str(call.from_user.id), "drafts_local_info"))
        await call.answer()

    @router.callback_query(F.data == "reset_channels")
    async def confirm_reset_channels(call: CallbackQuery):
        user_id = str(call.from_user.id)
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text=get_translation(state, user_id, "yes"), callback_data="confirm_reset_channels"),
                    InlineKeyboardButton(text=get_translation(state, user_id, "no"), callback_data="cancel_reset_channels"),
                ]
            ]
        )
        await call.message.edit_text(get_translation(state, user_id, "confirm_reset_channels"), reply_markup=keyboard)
        await call.answer()

    @router.callback_query(F.data == "toggle_auto")
    async def toggle_auto(call: CallbackQuery):
        user_id = str(call.from_user.id)
        user = state.users[user_id]
        user["auto_publish"] = not user.get("auto_publish", True)
        await save_users(state)
        ensure_user_publish_task(state, user_id)
        await call.message.edit_reply_markup(reply_markup=get_main_menu(state, user_id))
        await call.answer(get_translation(state, user_id, "auto_publish_toggled"))

    @router.message(lambda m: m.text and get_translation(state, str(m.from_user.id), "menu") in m.text)
    async def menu_button_handler(msg: Message):
        await start(msg)

    @router.callback_query(F.data == "panel_change_login")
    async def panel_change_login(call: CallbackQuery):
        user_id = str(call.from_user.id)
        state.panel_credentials_state[call.from_user.id] = {"field": "login"}
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=get_translation(state, user_id, "panel_cancel_change_button"), callback_data="panel_cancel_change")]
            ]
        )
        await call.message.answer(get_translation(state, user_id, "panel_login_prompt"), reply_markup=keyboard)
        await call.answer()

    @router.callback_query(F.data == "panel_change_password")
    async def panel_change_password(call: CallbackQuery):
        user_id = str(call.from_user.id)
        state.panel_credentials_state[call.from_user.id] = {"field": "password"}
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=get_translation(state, user_id, "panel_cancel_change_button"), callback_data="panel_cancel_change")]
            ]
        )
        await call.message.answer(get_translation(state, user_id, "panel_password_prompt"), reply_markup=keyboard)
        await call.answer()

    @router.callback_query(F.data == "panel_cancel_change")
    async def panel_cancel_change(call: CallbackQuery):
        state.panel_credentials_state.pop(call.from_user.id, None)
        await call.message.answer(get_translation(state, str(call.from_user.id), "panel_change_cancelled"))
        await call.answer()

    @router.message(lambda msg: state.panel_credentials_state.get(msg.from_user.id, {}).get("field") == "login")
    async def receive_new_panel_login(msg: Message):
        user_id = str(msg.from_user.id)
        if not msg.text:
            await msg.answer(get_translation(state, user_id, "panel_login_invalid"))
            return
        try:
            await update_panel_login(state, user_id, msg.text)
        except ValueError as exc:
            if str(exc) == "login_taken":
                await msg.answer(get_translation(state, user_id, "panel_login_taken"))
            else:
                await msg.answer(get_translation(state, user_id, "panel_login_invalid"))
            return
        state.panel_credentials_state.pop(msg.from_user.id, None)
        await msg.answer(get_translation(state, user_id, "panel_login_changed"))
        await send_panel_access_message(msg, state, user_id)

    @router.message(lambda msg: state.panel_credentials_state.get(msg.from_user.id, {}).get("field") == "password")
    async def receive_new_panel_password(msg: Message):
        user_id = str(msg.from_user.id)
        if not msg.text:
            await msg.answer(get_translation(state, user_id, "panel_password_invalid"))
            return
        try:
            new_password = await update_panel_password(state, user_id, msg.text)
        except ValueError:
            await msg.answer(get_translation(state, user_id, "panel_password_invalid"))
            return
        state.panel_credentials_state.pop(msg.from_user.id, None)
        await msg.answer(get_translation(state, user_id, "panel_password_changed"))
        await send_panel_access_message(msg, state, user_id, include_password=True, password=new_password)

    @router.message(lambda m: m.text and (m.text.startswith("@") or m.text.startswith("-100")))
    async def add_channel(msg: Message):
        user_id = str(msg.from_user.id)
        text = msg.text.strip()
        user = state.users[user_id]

        try:
            chat = await state.bot.get_chat(text)
            channel_id = chat.id
        except Exception:
            await msg.answer(get_translation(state, user_id, "channel_not_found"))
            return

        if not await user_is_admin(state, user_id, channel_id):
            await msg.answer(get_translation(state, user_id, "not_admin"))
            return

        if user.get("publish_channel_id"):
            await msg.answer(get_translation(state, user_id, "channels_already_set"))
            return

        if not await check_bot_is_admin(state, channel_id):
            await msg.answer(get_translation(state, user_id, "bot_not_admin_publish"))
            return

        try:
            invite_link = await state.bot.create_chat_invite_link(
                chat_id=channel_id,
                name=f"Invite for {chat.title}",
                member_limit=None,
                expire_date=None,
            )
            state.users[user_id]["publish_channel_id"] = channel_id
            state.users[user_id]["publish_channel_invite_link"] = invite_link.invite_link
            await save_users(state)
            await msg.answer(get_translation(state, user_id, "publish_channel_added"), reply_markup=get_main_menu(state, user_id))
        except Exception as exc:
            logging.error(f"Failed to create invite link: {exc}")
            state.users[user_id]["publish_channel_id"] = channel_id
            state.users[user_id]["publish_channel_invite_link"] = None
            await save_users(state)
            await msg.answer(get_translation(state, user_id, "publish_channel_added_no_link"), reply_markup=get_main_menu(state, user_id))

    @router.callback_query(F.data == "confirm_reset_channels")
    async def perform_reset_channels(call: CallbackQuery):
        user_id = str(call.from_user.id)
        state.users[user_id]["publish_channel_id"] = None
        state.users[user_id]["temp_channel_id"] = None
        state.users[user_id]["publish_channel_invite_link"] = None
        await save_users(state)
        await call.message.edit_text(get_translation(state, user_id, "channels_reset"), reply_markup=get_main_menu(state, user_id))
        await call.answer(get_translation(state, user_id, "channels_reset"))

    @router.callback_query(F.data == "cancel_reset_channels")
    async def cancel_reset_channels(call: CallbackQuery):
        user_id = str(call.from_user.id)
        await call.message.edit_text(get_translation(state, user_id, "reset_cancelled"), reply_markup=get_main_menu(state, user_id))
        await call.answer()

    @router.callback_query(F.data == "toggle_hyperlink")
    async def toggle_hyperlink(call: CallbackQuery):
        user_id = str(call.from_user.id)
        user = state.users[user_id]
        user["hyperlink_enabled"] = not user.get("hyperlink_enabled", True)
        await save_users(state)
        await call.message.edit_reply_markup(reply_markup=get_main_menu(state, user_id))
        hyperlink_state = get_translation(state, user_id, "hyperlink_on") if user["hyperlink_enabled"] else get_translation(state, user_id, "hyperlink_off")
        await call.answer(get_translation(state, user_id, "hyperlink_toggled").format(hyperlink_state))

    return router
