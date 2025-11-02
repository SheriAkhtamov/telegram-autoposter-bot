import asyncio
import random
import logging
import time
import re
import html
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import (
    InlineKeyboardButton, InlineKeyboardMarkup, Message, CallbackQuery,
    LabeledPrice, PreCheckoutQuery, ContentType
)
from aiogram.client.default import DefaultBotProperties
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.deep_linking import create_start_link
import asyncpg
from translations import TRANSLATIONS

ADMIN_IDS = {ADMIN_IDS, ADMIN_IDS, ADMIN_IDS}
TOKEN = "TOKEN"
DATABASE_URL = "DATABASE_URL"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()

pool = None
users = {}
storage = {}
referrals = {}

user_active_tasks = {}  # user_id -> asyncio.Task
user_publish_events = {}  # user_id -> asyncio.Event()
admin_broadcast_state = {}

# --- Database Initialization ---
async def init_db():
    global pool
    pool = await asyncpg.create_pool(dsn=DATABASE_URL)
    async with pool.acquire() as conn:
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                publish_channel_id BIGINT,
                temp_channel_id BIGINT,
                auto_publish BOOLEAN DEFAULT TRUE,
                publish_channel_invite_link TEXT,
                language TEXT,
                hyperlink_enabled BOOLEAN DEFAULT TRUE,
                last_published_at DOUBLE PRECISION
            );
        ''')
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS storage (
                message_key TEXT PRIMARY KEY,
                user_id BIGINT NOT NULL,
                text TEXT,
                file_id TEXT,
                file_type TEXT,
                temp_msg_id BIGINT NOT NULL
            );
        ''')
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS referrals (
                referrer_id BIGINT NOT NULL,
                referred_id BIGINT NOT NULL,
                PRIMARY KEY (referrer_id, referred_id)
            );
        ''')
        await conn.execute('''
            ALTER TABLE users
            ADD COLUMN IF NOT EXISTS last_published_at DOUBLE PRECISION;
        ''')

# --- Database Load/Save Functions ---
async def load_users():
    async with pool.acquire() as conn:
        rows = await conn.fetch('SELECT * FROM users')
        users_dict = {}
        for row in rows:
            users_dict[str(row['user_id'])] = {
                'publish_channel_id': row['publish_channel_id'],
                'temp_channel_id': row['temp_channel_id'],
                'auto_publish': row['auto_publish'],
                'publish_channel_invite_link': row['publish_channel_invite_link'],
                'language': row['language'],
                'hyperlink_enabled': row['hyperlink_enabled'],
                'last_published_at': row['last_published_at'] or 0
            }
        return users_dict

async def save_users(users):
    async with pool.acquire() as conn:
        for user_id, data in users.items():
            await conn.execute('''
                INSERT INTO users (user_id, publish_channel_id, temp_channel_id, auto_publish, publish_channel_invite_link, language, hyperlink_enabled, last_published_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (user_id) DO UPDATE SET
                    publish_channel_id = EXCLUDED.publish_channel_id,
                    temp_channel_id = EXCLUDED.temp_channel_id,
                    auto_publish = EXCLUDED.auto_publish,
                    publish_channel_invite_link = EXCLUDED.publish_channel_invite_link,
                    language = EXCLUDED.language,
                    hyperlink_enabled = EXCLUDED.hyperlink_enabled,
                    last_published_at = EXCLUDED.last_published_at
            ''', int(user_id), data['publish_channel_id'], data['temp_channel_id'], data['auto_publish'], data['publish_channel_invite_link'], data['language'], data['hyperlink_enabled'], data.get('last_published_at'))

async def load_storage():
    async with pool.acquire() as conn:
        rows = await conn.fetch('SELECT * FROM storage')
        storage_dict = {}
        for row in rows:
            storage_dict[row['message_key']] = {
                'user_id': str(row['user_id']),
                'text': row['text'],
                'file_id': row['file_id'],
                'file_type': row['file_type'],
                'temp_msg_id': row['temp_msg_id']
            }
        return storage_dict

async def save_storage(storage):
    async with pool.acquire() as conn:
        await conn.execute('DELETE FROM storage')
        for message_key, data in storage.items():
            await conn.execute('''
                INSERT INTO storage (message_key, user_id, text, file_id, file_type, temp_msg_id)
                VALUES ($1, $2, $3, $4, $5, $6)
            ''', message_key, int(data['user_id']), data['text'], data['file_id'], data['file_type'], data['temp_msg_id'])

async def load_referrals():
    async with pool.acquire() as conn:
        rows = await conn.fetch('SELECT * FROM referrals')
        referrals_dict = {}
        for row in rows:
            referrer_id = str(row['referrer_id'])
            referred_id = str(row['referred_id'])
            if referrer_id not in referrals_dict:
                referrals_dict[referrer_id] = []
            referrals_dict[referrer_id].append(referred_id)
        return referrals_dict

async def save_referrals(referrals):
    async with pool.acquire() as conn:
        await conn.execute('DELETE FROM referrals')
        for referrer_id, referred_list in referrals.items():
            for referred_id in referred_list:
                await conn.execute('''
                    INSERT INTO referrals (referrer_id, referred_id)
                    VALUES ($1, $2)
                ''', int(referrer_id), int(referred_id))

# --- Utility Functions ---
def get_translation(user_id, key):
    lang = users.get(str(user_id), {}).get("language", "ru")
    return TRANSLATIONS.get(lang, TRANSLATIONS["ru"]).get(key, key)

async def get_channel_link(channel_id, user_id):
    u = users.get(str(user_id), {})
    invite_link = u.get("publish_channel_invite_link")
    if invite_link:
        chat = await bot.get_chat(channel_id)
        return f"<a href='{invite_link}'>{chat.title}</a>"
    else:
        chat = await bot.get_chat(channel_id)
        if chat.username:
            link = f"https://t.me/{chat.username}"
        else:
            link = f"https://t.me/c/{str(chat.id)[4:]}"
        return f"<a href='{link}'>{chat.title}</a>"

# --- Menu Functions ---
def get_main_menu(user_id):
    u = users.get(str(user_id), {})
    lang = u.get("language", "ru")
    hyperlink_text = "Гиперссылка: ВКЛ" if u.get("hyperlink_enabled", True) else "Гиперссылка: ВЫКЛ"
    kb = [
        [InlineKeyboardButton(text=get_translation(user_id, "add_publish_channel"), callback_data="add_publish_channel")],
        [InlineKeyboardButton(text=get_translation(user_id, "add_temp_channel"), callback_data="add_temp_channel")],
        [InlineKeyboardButton(text=get_translation(user_id, "view_settings"), callback_data="settings")],
        [InlineKeyboardButton(text=get_translation(user_id, "reset_channels"), callback_data="reset_channels")],
        [InlineKeyboardButton(text=get_translation(user_id, "toggle_auto_publish").format(
            get_translation(user_id, "auto_publish_on") if u.get("auto_publish", True) else get_translation(user_id, "auto_publish_off")
        ), callback_data="toggle_auto")],
        [InlineKeyboardButton(text=hyperlink_text, callback_data="toggle_hyperlink")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def get_persistent_menu(user_id):
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text=get_translation(user_id, "menu")),
                KeyboardButton(text=get_translation(user_id, "share_bot")),
                KeyboardButton(text=get_translation(user_id, "change_language")),
                KeyboardButton(text=get_translation(user_id, "donate"))
            ],
        ],
        resize_keyboard=True,
        is_persistent=True
    )

def get_language_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Русский", callback_data="set_language:ru"),
            InlineKeyboardButton(text="English", callback_data="set_language:en"),
            InlineKeyboardButton(text="O'zbek", callback_data="set_language:uz")
        ]
    ])

def get_donate_menu(user_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=get_translation(user_id, "donate_10"), callback_data="donate:10"),
            InlineKeyboardButton(text=get_translation(user_id, "donate_50"), callback_data="donate:50"),
            InlineKeyboardButton(text=get_translation(user_id, "donate_100"), callback_data="donate:100")
        ],
        [
            InlineKeyboardButton(text=get_translation(user_id, "donate_500"), callback_data="donate:500"),
            InlineKeyboardButton(text=get_translation(user_id, "donate_1000"), callback_data="donate:1000"),
            InlineKeyboardButton(text=get_translation(user_id, "donate_5000"), callback_data="donate:5000")
        ]
    ])

# --- Bot Admin Check Functions ---
async def check_bot_is_admin(chat_id):
    try:
        me = await bot.get_chat_member(chat_id, (await bot.me()).id)
        return me.can_post_messages or me.status == 'administrator'
    except Exception:
        return False

async def user_is_admin(user_id, channel_id):
    try:
        admins = await bot.get_chat_administrators(channel_id)
        for admin in admins:
            if admin.user.id == int(user_id):
                return True
        return False
    except Exception:
        return False

# --- Handlers ---
@dp.message(Command(commands=["start", "menu"]))
async def start(msg: Message):
    user_id = str(msg.from_user.id)
    is_new_user = user_id not in users
    if is_new_user:
        users[user_id] = {
            "publish_channel_id": None,
            "temp_channel_id": None,
            "auto_publish": True,
            "publish_channel_invite_link": None,
            "language": None,
            "hyperlink_enabled": True
        }
        await save_users(users)
    parts = msg.text.strip().split()
    if len(parts) > 1 and is_new_user:  # Добавляем реферала только для новых пользователей
        referrer_id = parts[1]
        if referrer_id != user_id and user_id not in referrals.get(referrer_id, []):
            referrals.setdefault(referrer_id, []).append(user_id)
            await save_referrals(referrals)
    if not users[user_id].get("language"):
        await msg.answer("Выберите язык / Select language / Tilni tanlang:", reply_markup=get_language_menu())
    else:
        await msg.answer(get_translation(user_id, "menu_appeared"), reply_markup=get_persistent_menu(user_id))
        await msg.answer(get_translation(user_id, "add_channels"), reply_markup=get_main_menu(user_id))

@dp.callback_query(F.data.startswith("set_language:"))
async def set_language(call: CallbackQuery):
    user_id = str(call.from_user.id)
    _, lang = call.data.split(":")
    if lang in TRANSLATIONS:
        users[user_id]["language"] = lang
        await save_users(users)
        # Подтверждение смены языка
        await call.message.answer(get_translation(user_id, "language_changed").format(TRANSLATIONS[lang]["select_language"].split(":")[0]))
        # Отправка меню с инлайн-кнопками
        await call.message.answer(get_translation(user_id, "add_channels"), reply_markup=get_main_menu(user_id))
        await call.message.answer(get_translation(user_id, "menu_appeared"), reply_markup=get_persistent_menu(user_id))
    await call.message.edit_text(get_translation(user_id, "menu_appeared"))
    await call.answer()

@dp.message(lambda m: m.text and get_translation(str(m.from_user.id), "change_language") in m.text)
async def change_language(msg: Message):
    user_id = str(msg.from_user.id)
    await msg.answer(get_translation(user_id, "select_language"), reply_markup=get_language_menu())

@dp.message(lambda m: m.text and get_translation(str(m.from_user.id), "donate") in m.text)
async def donate(msg: Message):
    user_id = str(msg.from_user.id)
    await msg.answer(get_translation(user_id, "donate_message"), reply_markup=get_donate_menu(user_id))

@dp.callback_query(F.data.startswith("donate:"))
async def donate_amount(call: CallbackQuery):
    user_id = str(call.from_user.id)
    _, amount = call.data.split(":")
    amount = int(amount)
    lang = users[user_id].get("language", "ru")
    try:
        await bot.send_invoice(
            chat_id=call.from_user.id,
            title="Поддержка бота" if lang == "ru" else "Bot Support" if lang == "en" else "Botni qo'llab-quvvatlash",
            description="Пожертвование для поддержки серверов бота" if lang == "ru" else "Donation to support bot servers" if lang == "en" else "Bot serverlarini qo'llab-quvvatlash uchun xayriya",
            payload=f"donation_{amount}",
            provider_token="",
            currency="XTR",
            prices=[LabeledPrice(
                label="Пожертвование" if lang == "ru" else "Donation" if lang == "en" else "Xayriya",
                amount=amount
            )],
            need_name=False,
            need_phone_number=False,
            need_email=False,
            need_shipping_address=False
        )
        await call.answer()
    except Exception as e:
        logging.error(f"Ошибка при отправке инвойса: {e}")
        await call.message.answer(get_translation(user_id, "donation_error"))
        await call.answer()

@dp.pre_checkout_query()
async def pre_checkout_query(pre_checkout: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout.id, ok=True)

@dp.message(F.content_type == ContentType.SUCCESSFUL_PAYMENT)
async def successful_payment(msg: Message):
    user_id = str(msg.from_user.id)
    await msg.answer(get_translation(user_id, "donation_success"))

@dp.callback_query(F.data == "settings")
async def settings(call: CallbackQuery):
    user_id = str(call.from_user.id)
    u = users[user_id]
    publish_channel_id = u.get("publish_channel_id")
    temp_channel_id = u.get("temp_channel_id")
    auto = get_translation(user_id, "auto_publish_on") if u.get("auto_publish", True) else get_translation(user_id, "auto_publish_off")
    hyperlink_state = get_translation(user_id, "hyperlink_on") if u.get("hyperlink_enabled", True) else get_translation(user_id, "hyperlink_off")

    async def channel_title(cid):
        if not cid:
            return get_translation(user_id, "channel_not_set")
        chat = await bot.get_chat(cid)
        invite_link = u.get("publish_channel_invite_link") if cid == publish_channel_id else None
        if invite_link and cid == publish_channel_id:
            link = invite_link
        elif chat.username:
            link = f"https://t.me/{chat.username}"
        else:
            link = f"https://t.me/c/{str(chat.id)[4:]}"
        return f"<a href='{link}'>{chat.title}</a>"

    publish = await channel_title(publish_channel_id)
    temp = await channel_title(temp_channel_id)

    text = get_translation(user_id, "settings").format(publish, temp, auto, hyperlink_state)
    await call.message.edit_text(text, reply_markup=get_main_menu(user_id))

@dp.callback_query(F.data == "add_publish_channel")
async def add_pub_channel(call: CallbackQuery):
    user_id = str(call.from_user.id)
    await call.message.answer(get_translation(user_id, "add_publish_channel_prompt"))
    await call.answer()

@dp.callback_query(F.data == "add_temp_channel")
async def add_temp_channel(call: CallbackQuery):
    user_id = str(call.from_user.id)
    await call.message.answer(get_translation(user_id, "add_temp_channel_prompt"))
    await call.answer()

@dp.callback_query(F.data == "reset_channels")
async def confirm_reset_channels(call: CallbackQuery):
    user_id = str(call.from_user.id)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=get_translation(user_id, "yes"), callback_data="confirm_reset_channels"),
            InlineKeyboardButton(text=get_translation(user_id, "no"), callback_data="cancel_reset_channels")
        ]
    ])
    await call.message.edit_text(get_translation(user_id, "confirm_reset_channels"), reply_markup=kb)
    await call.answer()

@dp.callback_query(F.data == "toggle_auto")
async def toggle_auto(call: CallbackQuery):
    user_id = str(call.from_user.id)
    user = users[user_id]
    current_state = user.get("auto_publish", True)
    user["auto_publish"] = not current_state
    await save_users(users)

    event = user_publish_events.get(user_id)
    if not event:
        event = asyncio.Event()
        user_publish_events[user_id] = event
        if user["auto_publish"]:
            event.set()

        if user_id not in user_active_tasks:
            task = asyncio.create_task(publish_queue_for_user(user_id, event))
            user_active_tasks[user_id] = task
    else:
        if user["auto_publish"]:
            event.set()
        else:
            event.clear()

    await call.message.edit_reply_markup(reply_markup=get_main_menu(user_id))
    await call.answer(get_translation(user_id, "auto_publish_toggled"))

@dp.message(lambda m: m.text and get_translation(str(m.from_user.id), "menu") in m.text)
async def menu_button_handler(msg: Message):
    await start(msg)

@dp.message(lambda m: m.text and (m.text.startswith("@") or m.text.startswith("-100")))
async def add_channel(msg: Message):
    user_id = str(msg.from_user.id)
    text = msg.text.strip()
    u = users[user_id]

    try:
        chat = await bot.get_chat(text)
        channel_id = chat.id
    except Exception:
        await msg.answer(get_translation(user_id, "channel_not_found"))
        return

    if not await user_is_admin(user_id, channel_id):
        await msg.answer(get_translation(user_id, "not_admin"))
        return

    if not u.get("publish_channel_id"):
        if await check_bot_is_admin(channel_id):
            try:
                invite_link = await bot.create_chat_invite_link(
                    chat_id=channel_id,
                    name=f"Invite for {chat.title}",
                    member_limit=None,
                    expire_date=None
                )
                users[user_id]["publish_channel_id"] = channel_id
                users[user_id]["publish_channel_invite_link"] = invite_link.invite_link
                await save_users(users)
                await msg.answer(get_translation(user_id, "publish_channel_added"), reply_markup=get_main_menu(user_id))
            except Exception as e:
                logging.error(f"Failed to create invite link: {e}")
                users[user_id]["publish_channel_id"] = channel_id
                users[user_id]["publish_channel_invite_link"] = None
                await save_users(users)
                await msg.answer(get_translation(user_id, "publish_channel_added_no_link"), reply_markup=get_main_menu(user_id))
        else:
            await msg.answer(get_translation(user_id, "bot_not_admin_publish"))
    elif not u.get("temp_channel_id"):
        if await check_bot_is_admin(channel_id):
            users[user_id]["temp_channel_id"] = channel_id
            await save_users(users)
            await msg.answer(get_translation(user_id, "temp_channel_added"), reply_markup=get_main_menu(user_id))
        else:
            await msg.answer(get_translation(user_id, "bot_not_admin_temp"))
    else:
        await msg.answer(get_translation(user_id, "channels_already_set"))

async def send_to_channel(user_id, text, file_id=None, file_type=None):
    u = users[user_id]
    publish_channel_id = u.get("publish_channel_id")
    if not publish_channel_id:
        return
    if u.get("hyperlink_enabled", True):
        channel_link = await get_channel_link(publish_channel_id, user_id)
        text = f"{text}\n\n{channel_link}"
    if file_id and file_type:
        if file_type == "photo":
            await bot.send_photo(publish_channel_id, file_id, caption=text)
        elif file_type == "video":
            await bot.send_video(publish_channel_id, file_id, caption=text)
        elif file_type == "audio":
            await bot.send_audio(publish_channel_id, file_id, caption=text)
        elif file_type == "voice":
            await bot.send_voice(publish_channel_id, file_id, caption=text)
        elif file_type == "document":
            await bot.send_document(publish_channel_id, file_id, caption=text)
    else:
        await bot.send_message(publish_channel_id, text)

async def save_to_temp_channel(user_id, text, file_id=None, file_type=None, message_key=None):
    u = users[user_id]
    temp_channel_id = u.get("temp_channel_id")
    publish_channel_id = u.get("publish_channel_id")
    if not temp_channel_id or not publish_channel_id:
        return None
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=get_translation(user_id, "publish_now"), callback_data=f"publish:{user_id}:{message_key}"),
            InlineKeyboardButton(text=get_translation(user_id, "task_removed"), callback_data=f"remove:{user_id}:{message_key}")
        ]
    ])
    if u.get("hyperlink_enabled", True):
        channel_link = await get_channel_link(publish_channel_id, user_id)
        text = f"{text}\n\n{channel_link}"
    if file_id and file_type:
        if file_type == "photo":
            temp_msg = await bot.send_photo(temp_channel_id, file_id, caption=text, reply_markup=kb)
        elif file_type == "video":
            temp_msg = await bot.send_video(temp_channel_id, file_id, caption=text, reply_markup=kb)
        elif file_type == "audio":
            temp_msg = await bot.send_audio(temp_channel_id, file_id, caption=text, reply_markup=kb)
        elif file_type == "voice":
            temp_msg = await bot.send_voice(temp_channel_id, file_id, caption=text, reply_markup=kb)
        elif file_type == "document":
            temp_msg = await bot.send_document(temp_channel_id, file_id, caption=text, reply_markup=kb)
        else:
            return None
    else:
        temp_msg = await bot.send_message(temp_channel_id, text, reply_markup=kb)
    return temp_msg.message_id

async def publish_queue_for_user(user_id, publish_event: asyncio.Event):
    delay_min = 30 * 60  # 30 минут в секундах
    delay_max = 60 * 60  # 60 минут в секундах

    while True:
        await publish_event.wait()

        tasks = [k for k, v in storage.items() if v["user_id"] == user_id]
        if not tasks:
            user_active_tasks.pop(user_id, None)
            return

        # Получите время последней публикации
        last_published = users[user_id].get("last_published_at", 0)
        current_time = time.time()
        time_since_last = current_time - last_published

        # Если с последней публикации прошло меньше 30 минут, ждем
        if time_since_last < delay_min:
            await asyncio.sleep(delay_min - time_since_last)

        # Берем первый доступный пост
        message_key = tasks[0]
        data = storage[message_key]
        try:
            await send_to_channel(
                data["user_id"],
                data["text"],
                data.get("file_id"),
                data.get("file_type")
            )
            try:
                await bot.delete_message(users[data["user_id"]]['temp_channel_id'], data['temp_msg_id'])
            except Exception:
                pass
            del storage[message_key]
            await save_storage(storage)

            # Обновите время последней публикации
            users[user_id]["last_published_at"] = time.time()
            await save_users(users)

            # Случайная задержка перед следующей публикацией
            delay = random.randint(delay_min, delay_max)
            await asyncio.sleep(delay)
        except Exception as e:
            logging.error(f"Ошибка публикации: {e}")
            # Можете добавить обработку ошибок, например, пропустить пост


@dp.message(lambda msg: admin_broadcast_state.get(msg.from_user.id, {}).get("stage") == "awaiting_message")
async def receive_broadcast_message(msg: Message):
    user_id = str(msg.from_user.id)
    content = {}

    if msg.photo:
        content['file_id'] = msg.photo[-1].file_id
        content['file_type'] = 'photo'
        content['caption'] = msg.caption
    elif msg.video:
        content['file_id'] = msg.video.file_id
        content['file_type'] = 'video'
        content['caption'] = msg.caption
    elif msg.audio:
        content['file_id'] = msg.audio.file_id
        content['file_type'] = 'audio'
        content['caption'] = msg.caption
    elif msg.voice:
        content['file_id'] = msg.voice.file_id
        content['file_type'] = 'voice'
        content['caption'] = None
    elif msg.document:
        content['file_id'] = msg.document.file_id
        content['file_type'] = 'document'
        content['caption'] = msg.caption
    elif msg.text:
        content['text'] = msg.text
    else:
        content['text'] = '[Пустое сообщение]' if users[user_id].get("language", "ru") == "ru" else '[Empty message]' if users[user_id].get("language") == "en" else '[Bo\'sh xabar]'

    admin_broadcast_state[msg.from_user.id]["content"] = content
    admin_broadcast_state[msg.from_user.id]["stage"] = "confirm"
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=get_translation(user_id, "yes"), callback_data="admin_broadcast_confirm"),
                InlineKeyboardButton(text=get_translation(user_id, "no"), callback_data="admin_broadcast_cancel")
            ]
        ]
    )
    await msg.answer(get_translation(user_id, "broadcast_ready"), reply_markup=kb)

@dp.callback_query(F.data == "admin_broadcast_confirm")
async def confirm_broadcast(call: CallbackQuery):
    user_id = str(call.from_user.id)
    state = admin_broadcast_state.get(call.from_user.id)
    if not state or "content" not in state:
        await call.message.answer(get_translation(user_id, "broadcast_error"))
        return
    content = state["content"]
    count = 0
    errors = 0
    for uid in users:
        try:
            if content.get('file_type') == 'photo':
                await bot.send_photo(uid, content['file_id'], caption=content.get('caption', ''))
            elif content.get('file_type') == 'video':
                await bot.send_video(uid, content['file_id'], caption=content.get('caption', ''))
            elif content.get('file_type') == 'audio':
                await bot.send_audio(uid, content['file_id'], caption=content.get('caption', ''))
            elif content.get('file_type') == 'voice':
                await bot.send_voice(uid, content['file_id'])
            elif content.get('file_type') == 'document':
                await bot.send_document(uid, content['file_id'], caption=content.get('caption', ''))
            elif 'text' in content:
                await bot.send_message(uid, content['text'])
            else:
                await bot.send_message(uid, '[Пустое сообщение]' if users[uid].get("language", "ru") == "ru" else '[Empty message]' if users[uid].get("language") == "en" else '[Bo\'sh xabar]')
            count += 1
            await asyncio.sleep(0.04)
        except Exception:
            errors += 1
            continue
    del admin_broadcast_state[call.from_user.id]
    await call.message.answer(get_translation(user_id, "broadcast_complete").format(count, errors))

@dp.callback_query(F.data == "admin_broadcast_cancel")
async def cancel_broadcast(call: CallbackQuery):
    user_id = str(call.from_user.id)
    admin_broadcast_state.pop(call.from_user.id, None)
    await call.message.answer(get_translation(user_id, "broadcast_cancelled"))

@dp.message(lambda m: m.text and get_translation(str(m.from_user.id), "share_bot") in m.text)
async def share_bot_info(msg: Message):
    user_id = str(msg.from_user.id)
    invited = referrals.get(user_id, [])
    text = get_translation(user_id, "share_bot_info").format(len(invited))
    top_referrers_text = re.sub(r'<[^>]+>', '', get_translation(user_id, "top_referrers")).split(':')[0]
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=get_translation(user_id, "ref_link").split('\n')[0], callback_data="get_ref_link")],
        [InlineKeyboardButton(text=top_referrers_text, callback_data="show_top_referrers")]
    ])
    await msg.answer(text, reply_markup=keyboard)

@dp.message(lambda msg: not msg.text or not msg.text.startswith('/'))
async def handle_message(msg: Message):
    user_id = str(msg.from_user.id)
    if msg.text and msg.text.lower().strip() in [TRANSLATIONS["ru"]["menu"], TRANSLATIONS["ru"]["share_bot"], TRANSLATIONS["ru"]["change_language"], TRANSLATIONS["ru"]["donate"]]:
        return
    if admin_broadcast_state.get(msg.from_user.id, {}).get("stage") == "awaiting_message":
        return
    u = users.get(user_id)
    if not u or not u.get("publish_channel_id") or not u.get("temp_channel_id"):
        await msg.answer(get_translation(user_id, "add_channels"))
        return

    file_id = None
    file_type = None
    text = msg.caption if msg.caption else (msg.text or "")

    if msg.photo:
        file_id = msg.photo[-1].file_id
        file_type = "photo"
    elif msg.video:
        file_id = msg.video.file_id
        file_type = "video"
    elif msg.audio:
        file_id = msg.audio.file_id
        file_type = "audio"
    elif msg.voice:
        file_id = msg.voice.file_id
        file_type = "voice"
    elif msg.document:
        file_id = msg.document.file_id
        file_type = "document"

    message_key = f"{user_id}:{msg.message_id}"

    temp_msg_id = await save_to_temp_channel(user_id, text, file_id, file_type, message_key)
    if temp_msg_id is None:
        await msg.answer(get_translation(user_id, "draft_error"))
        return

    storage[message_key] = {
        "user_id": user_id,
        "text": text,
        "file_id": file_id,
        "file_type": file_type,
        "temp_msg_id": temp_msg_id
    }
    await save_storage(storage)
    await msg.answer(get_translation(user_id, "post_scheduled"))

    try:
        await bot.delete_message(msg.chat.id, msg.message_id)
    except Exception as e:
        logging.warning(f"Не удалось удалить сообщение: {e}")

@dp.callback_query(F.data.startswith("publish:"))
async def publish_now(call: CallbackQuery):
    user_id = str(call.from_user.id)
    _, user_id, message_key = call.data.split(":", 2)
    try:
        if message_key in storage and storage[message_key]["user_id"] == user_id:
            data = storage[message_key]
            await send_to_channel(user_id, data["text"], data["file_id"], data["file_type"])
            try:
                await bot.delete_message(users[user_id]['temp_channel_id'], data['temp_msg_id'])
            except Exception:
                pass
            await call.answer(get_translation(user_id, "publish_now"))
        else:
            await call.answer(get_translation(user_id, "task_not_found"))
    finally:
        if message_key in storage:
            del storage[message_key]
            await save_storage(storage)
        await call.answer(get_translation(user_id, "publish_now"))

@dp.callback_query(F.data.startswith("remove:"))
async def remove_task(call: CallbackQuery):
    user_id = str(call.from_user.id)
    _, user_id, message_key = call.data.split(":", 2)
    if message_key in storage and storage[message_key]["user_id"] == user_id:
        try:
            try:
                await bot.delete_message(users[user_id]['temp_channel_id'], storage[message_key]['temp_msg_id'])
            except Exception:
                pass
            del storage[message_key]
            await save_storage(storage)
            await call.answer(get_translation(user_id, "task_removed"), show_alert=True)
        except Exception as e:
            await call.answer(get_translation(user_id, "task_remove_error").format(e), show_alert=True)
    else:
        await call.answer(get_translation(user_id, "task_already_removed"), show_alert=True)

@dp.message(Command("sheri"))
async def handle_sheri_command(msg: Message):
    user_id = msg.from_user.id
    if user_id not in ADMIN_IDS:
        await msg.answer(get_translation(str(user_id), "not_wizard"))
        return
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=get_translation(str(user_id), "send_broadcast").split(':')[0], callback_data="admin_broadcast")],
            [InlineKeyboardButton(text=get_translation(str(user_id), "report_ready").split('!')[0], callback_data="admin_report")]
        ]
    )
    await msg.answer(get_translation(str(user_id), "admin_menu"), reply_markup=kb)

@dp.callback_query(F.data == "admin_broadcast")
async def start_broadcast(call: CallbackQuery):
    user_id = str(call.from_user.id)
    admin_broadcast_state[call.from_user.id] = {"stage": "awaiting_message"}
    await call.message.answer(get_translation(user_id, "send_broadcast"))
    await call.answer()

@dp.callback_query(F.data == "get_ref_link")
async def send_ref_link(call: CallbackQuery):
    user_id = str(call.from_user.id)
    link = await create_start_link(bot, payload=user_id)
    await call.message.answer(get_translation(user_id, "ref_link").format(link))
    await call.answer()

@dp.callback_query(F.data == "show_top_referrers")
async def show_top_referrers(call: CallbackQuery):
    user_id = str(call.from_user.id)
    leaderboard = []

    for uid, invited_list in referrals.items():
        leaderboard.append((uid, len(invited_list)))

    leaderboard.sort(key=lambda x: x[1], reverse=True)

    top_text = ""
    for i, (uid, count) in enumerate(leaderboard[:10], start=1):
        try:
            user = await bot.get_chat(uid)
            name = html.escape(user.full_name)  # Экранируем специальные символы
        except Exception:
            name = html.escape(f"Пользователь {uid}" if users[user_id].get("language", "ru") == "ru" else f"User {uid}" if users[user_id].get("language") == "en" else f"Foydalanuvchi {uid}")
        top_text += f"{i}. {name} — {count} {'приглашений' if users[user_id].get('language', 'ru') == 'ru' else 'invitations' if users[user_id].get('language') == 'en' else 'takliflar'}\n"

    current_user_id = str(call.from_user.id)
    position = next((i for i, (uid, _) in enumerate(leaderboard, start=1) if uid == current_user_id), None)
    if position:
        top_text += f"\n{get_translation(user_id, 'your_position').format(position)}"
    else:
        top_text += f"\n{get_translation(user_id, 'no_referrals')}"

    await call.message.answer(get_translation(user_id, "top_referrers").format(top_text))
    await call.answer()

@dp.callback_query(F.data == "confirm_reset_channels")
async def perform_reset_channels(call: CallbackQuery):
    user_id = str(call.from_user.id)
    users[user_id]["publish_channel_id"] = None
    users[user_id]["temp_channel_id"] = None
    users[user_id]["publish_channel_invite_link"] = None
    await save_users(users)
    await call.message.edit_text(
        get_translation(user_id, "channels_reset"), reply_markup=get_main_menu(user_id)
    )
    await call.answer(get_translation(user_id, "channels_reset"))

@dp.callback_query(F.data == "cancel_reset_channels")
async def cancel_reset_channels(call: CallbackQuery):
    user_id = str(call.from_user.id)
    await call.message.edit_text(
        get_translation(user_id, "reset_cancelled"), reply_markup=get_main_menu(user_id)
    )
    await call.answer()

@dp.callback_query(F.data == "toggle_hyperlink")
async def toggle_hyperlink(call: CallbackQuery):
    user_id = str(call.from_user.id)
    user = users[user_id]
    current_state = user.get("hyperlink_enabled", True)
    user["hyperlink_enabled"] = not current_state
    await save_users(users)
    await call.message.edit_reply_markup(reply_markup=get_main_menu(user_id))
    await call.answer("Гиперссылка " + ("включена" if user["hyperlink_enabled"] else "выключена"))


@dp.callback_query(F.data == "admin_report")
async def admin_report(call: CallbackQuery):
    user_id = str(call.from_user.id)
    total = len(users)
    active = 0
    blocked = 0
    unknown = 0
    checked = 0
    for uid in users:
        try:
            await bot.send_chat_action(uid, "typing")
            active += 1
        except Exception:
            blocked += 1
        checked += 1
        await asyncio.sleep(0.04)

    text = get_translation(user_id, "admin_report").format(total, active, blocked, unknown)
    await call.message.answer(text)
    await call.answer(get_translation(user_id, "report_ready"))

async def main():
    await init_db()
    global users, storage, referrals
    users = await load_users()
    storage = await load_storage()
    referrals = await load_referrals()

    for user_id in set(v["user_id"] for v in storage.values()):
        event = asyncio.Event()
        u = users.get(user_id, {})
        if u.get("auto_publish", True):
            event.set()
        user_publish_events[user_id] = event

        if user_id not in user_active_tasks:
            task = asyncio.create_task(publish_queue_for_user(user_id, event))
            user_active_tasks[user_id] = task
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())