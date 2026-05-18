import asyncio
from dataclasses import dataclass, field
from typing import Any

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties

from .config import MEDIA_ROOT, TOKEN


@dataclass
class AppState:
    bot: Bot
    dp: Dispatcher
    pool: Any = None
    users: dict = field(default_factory=dict)
    storage: dict = field(default_factory=dict)
    referrals: dict = field(default_factory=dict)
    user_active_tasks: dict[str, asyncio.Task] = field(default_factory=dict)
    user_publish_events: dict[str, asyncio.Event] = field(default_factory=dict)
    admin_broadcast_state: dict = field(default_factory=dict)
    panel_credentials_state: dict = field(default_factory=dict)
    panel_sessions: dict = field(default_factory=dict)


def create_app_state() -> AppState:
    MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
    bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher()
    return AppState(bot=bot, dp=dp)
