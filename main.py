import asyncio
import logging

from app import create_app_state
from app.database import init_db, load_referrals, load_storage, load_users
from app.handlers import setup_routers
from app.panel_web import start_panel_server
from app.queue import ensure_user_publish_task


logging.basicConfig(level=logging.INFO)


async def main():
    state = create_app_state()
    await init_db(state)
    state.users = await load_users(state)
    state.storage = await load_storage(state)
    state.referrals = await load_referrals(state)

    setup_routers(state)
    panel_runner = await start_panel_server(state)
    for user_id in {data["user_id"] for data in state.storage.values()}:
        ensure_user_publish_task(state, user_id)

    try:
        await state.dp.start_polling(state.bot)
    finally:
        await panel_runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
