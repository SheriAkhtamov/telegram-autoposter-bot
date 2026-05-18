from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from .common import get_translation


def get_main_menu(state, user_id):
    user = state.users.get(str(user_id), {})
    hyperlink_text = get_translation(state, user_id, "toggle_hyperlink").format(
        get_translation(state, user_id, "hyperlink_on") if user.get("hyperlink_enabled", True) else get_translation(state, user_id, "hyperlink_off")
    )
    keyboard = [
        [InlineKeyboardButton(text=get_translation(state, user_id, "add_publish_channel"), callback_data="add_publish_channel")],
        [InlineKeyboardButton(text=get_translation(state, user_id, "view_settings"), callback_data="settings")],
        [InlineKeyboardButton(text=get_translation(state, user_id, "reset_channels"), callback_data="reset_channels")],
        [InlineKeyboardButton(
            text=get_translation(state, user_id, "toggle_auto_publish").format(
                get_translation(state, user_id, "auto_publish_on") if user.get("auto_publish", True) else get_translation(state, user_id, "auto_publish_off")
            ),
            callback_data="toggle_auto",
        )],
        [InlineKeyboardButton(text=hyperlink_text, callback_data="toggle_hyperlink")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def get_persistent_menu(state, user_id):
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=get_translation(state, user_id, "menu")),
                KeyboardButton(text=get_translation(state, user_id, "share_bot")),
                KeyboardButton(text=get_translation(state, user_id, "panel_open_button")),
            ],
            [
                KeyboardButton(text=get_translation(state, user_id, "change_language")),
                KeyboardButton(text=get_translation(state, user_id, "donate")),
            ],
        ],
        resize_keyboard=True,
        is_persistent=True,
    )


def get_language_menu():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Русский", callback_data="set_language:ru"),
                InlineKeyboardButton(text="English", callback_data="set_language:en"),
                InlineKeyboardButton(text="O'zbek", callback_data="set_language:uz"),
            ]
        ]
    )


def get_donate_menu(state, user_id):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=get_translation(state, user_id, "donate_10"), callback_data="donate:10"),
                InlineKeyboardButton(text=get_translation(state, user_id, "donate_50"), callback_data="donate:50"),
                InlineKeyboardButton(text=get_translation(state, user_id, "donate_100"), callback_data="donate:100"),
            ],
            [
                InlineKeyboardButton(text=get_translation(state, user_id, "donate_500"), callback_data="donate:500"),
                InlineKeyboardButton(text=get_translation(state, user_id, "donate_1000"), callback_data="donate:1000"),
                InlineKeyboardButton(text=get_translation(state, user_id, "donate_5000"), callback_data="donate:5000"),
            ],
        ]
    )
