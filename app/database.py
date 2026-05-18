import asyncpg

from .config import DATABASE_URL


async def init_db(state):
    state.pool = await asyncpg.create_pool(dsn=DATABASE_URL)
    async with state.pool.acquire() as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                publish_channel_id BIGINT,
                temp_channel_id BIGINT,
                auto_publish BOOLEAN DEFAULT TRUE,
                publish_channel_invite_link TEXT,
                language TEXT,
                hyperlink_enabled BOOLEAN DEFAULT TRUE,
                last_published_at DOUBLE PRECISION,
                panel_login TEXT,
                panel_password_hash TEXT,
                panel_password_salt TEXT
            );
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS storage (
                message_key TEXT PRIMARY KEY,
                user_id BIGINT NOT NULL,
                text TEXT,
                file_id TEXT,
                file_path TEXT,
                original_file_name TEXT,
                file_type TEXT,
                temp_msg_id BIGINT,
                created_at DOUBLE PRECISION
            );
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS referrals (
                referrer_id BIGINT NOT NULL,
                referred_id BIGINT NOT NULL,
                PRIMARY KEY (referrer_id, referred_id)
            );
            """
        )
        await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_published_at DOUBLE PRECISION;")
        await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS panel_login TEXT;")
        await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS panel_password_hash TEXT;")
        await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS panel_password_salt TEXT;")
        await conn.execute("ALTER TABLE storage ADD COLUMN IF NOT EXISTS file_path TEXT;")
        await conn.execute("ALTER TABLE storage ADD COLUMN IF NOT EXISTS original_file_name TEXT;")
        await conn.execute("ALTER TABLE storage ALTER COLUMN temp_msg_id DROP NOT NULL;")
        await conn.execute("ALTER TABLE storage ADD COLUMN IF NOT EXISTS created_at DOUBLE PRECISION;")


async def load_users(state):
    async with state.pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM users")
    users = {}
    for row in rows:
        users[str(row["user_id"])] = {
            "publish_channel_id": row["publish_channel_id"],
            "temp_channel_id": row["temp_channel_id"],
            "auto_publish": row["auto_publish"],
            "publish_channel_invite_link": row["publish_channel_invite_link"],
            "language": row["language"],
            "hyperlink_enabled": row["hyperlink_enabled"],
            "last_published_at": row["last_published_at"] or 0,
            "panel_login": row["panel_login"],
            "panel_password_hash": row["panel_password_hash"],
            "panel_password_salt": row["panel_password_salt"],
        }
    return users


async def save_users(state):
    async with state.pool.acquire() as conn:
        for user_id, data in state.users.items():
            await conn.execute(
                """
                INSERT INTO users (
                    user_id, publish_channel_id, temp_channel_id, auto_publish,
                    publish_channel_invite_link, language, hyperlink_enabled,
                    last_published_at, panel_login, panel_password_hash, panel_password_salt
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                ON CONFLICT (user_id) DO UPDATE SET
                    publish_channel_id = EXCLUDED.publish_channel_id,
                    temp_channel_id = EXCLUDED.temp_channel_id,
                    auto_publish = EXCLUDED.auto_publish,
                    publish_channel_invite_link = EXCLUDED.publish_channel_invite_link,
                    language = EXCLUDED.language,
                    hyperlink_enabled = EXCLUDED.hyperlink_enabled,
                    last_published_at = EXCLUDED.last_published_at,
                    panel_login = EXCLUDED.panel_login,
                    panel_password_hash = EXCLUDED.panel_password_hash,
                    panel_password_salt = EXCLUDED.panel_password_salt
                """,
                int(user_id),
                data["publish_channel_id"],
                data["temp_channel_id"],
                data["auto_publish"],
                data["publish_channel_invite_link"],
                data["language"],
                data["hyperlink_enabled"],
                data.get("last_published_at"),
                data.get("panel_login"),
                data.get("panel_password_hash"),
                data.get("panel_password_salt"),
            )


async def load_storage(state):
    async with state.pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM storage")
    storage = {}
    for row in rows:
        storage[row["message_key"]] = {
            "user_id": str(row["user_id"]),
            "text": row["text"],
            "file_id": row["file_id"],
            "file_path": row["file_path"],
            "original_file_name": row["original_file_name"],
            "file_type": row["file_type"],
            "temp_msg_id": row["temp_msg_id"],
            "created_at": row["created_at"] or 0,
        }
    return storage


async def save_storage(state):
    async with state.pool.acquire() as conn:
        await conn.execute("DELETE FROM storage")
        for message_key, data in state.storage.items():
            await conn.execute(
                """
                INSERT INTO storage (
                    message_key, user_id, text, file_id, file_path, original_file_name,
                    file_type, temp_msg_id, created_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                """,
                message_key,
                int(data["user_id"]),
                data["text"],
                data.get("file_id"),
                data.get("file_path"),
                data.get("original_file_name"),
                data.get("file_type"),
                data.get("temp_msg_id"),
                data.get("created_at"),
            )


async def load_referrals(state):
    async with state.pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM referrals")
    referrals = {}
    for row in rows:
        referrer_id = str(row["referrer_id"])
        referred_id = str(row["referred_id"])
        referrals.setdefault(referrer_id, []).append(referred_id)
    return referrals


async def save_referrals(state):
    async with state.pool.acquire() as conn:
        await conn.execute("DELETE FROM referrals")
        for referrer_id, referred_ids in state.referrals.items():
            for referred_id in referred_ids:
                await conn.execute(
                    """
                    INSERT INTO referrals (referrer_id, referred_id)
                    VALUES ($1, $2)
                    """,
                    int(referrer_id),
                    int(referred_id),
                )
