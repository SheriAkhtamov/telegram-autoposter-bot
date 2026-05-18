import html
import logging
import secrets
import time
from pathlib import Path

from aiohttp import web

from .common import format_storage_time
from .config import PANEL_BASE_PATH, PANEL_HOST, PANEL_PORT, PANEL_SESSION_COOKIE, PANEL_SESSION_TTL
from .database import save_storage
from .media_storage import store_uploaded_file_locally
from .panel_auth import build_panel_url, clear_panel_session, create_panel_session, get_panel_session_user, verify_panel_password
from .queue import cleanup_stored_message, get_user_storage_items, send_to_channel, touch_last_published, ensure_user_publish_task


def get_state(request):
    return request.app["state"]


def render_panel_login_page(error_code=None):
    error_html = ""
    if error_code == "invalid":
        error_html = "<div class='notice error'>Неверный логин или пароль.</div>"

    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Панель управления</title>
  <style>
    :root {{
      --bg: #f5efe6;
      --paper: #fffaf2;
      --ink: #1f1a16;
      --muted: #705d4d;
      --line: #d9c7b7;
      --accent: #b85c38;
      --accent-dark: #8f4326;
      --danger: #b3261e;
      --shadow: 0 24px 70px rgba(58, 38, 24, 0.12);
      font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(184, 92, 56, 0.16), transparent 30%),
        linear-gradient(180deg, #f7f1e9 0%, #efe2d4 100%);
      display: grid;
      place-items: center;
      padding: 24px;
    }}
    .card {{
      width: min(100%, 440px);
      background: rgba(255, 250, 242, 0.96);
      border: 1px solid rgba(217, 199, 183, 0.9);
      border-radius: 28px;
      padding: 32px;
      box-shadow: var(--shadow);
      backdrop-filter: blur(10px);
    }}
    h1 {{ margin: 0 0 10px; font-size: 32px; }}
    p {{ margin: 0 0 20px; color: var(--muted); line-height: 1.55; }}
    label {{ display: block; margin: 16px 0 8px; font-size: 14px; color: var(--muted); }}
    input {{
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 14px 16px;
      background: #fff;
      font-size: 15px;
    }}
    button {{
      width: 100%;
      margin-top: 20px;
      border: 0;
      border-radius: 16px;
      padding: 14px 18px;
      background: var(--accent);
      color: #fff;
      font-size: 15px;
      font-weight: 600;
      cursor: pointer;
    }}
    button:hover {{ background: var(--accent-dark); }}
    .notice {{
      border-radius: 16px;
      padding: 12px 14px;
      margin-bottom: 18px;
      font-size: 14px;
    }}
    .error {{
      background: rgba(179, 38, 30, 0.10);
      border: 1px solid rgba(179, 38, 30, 0.20);
      color: var(--danger);
    }}
  </style>
</head>
<body>
  <main class="card">
    <h1>Панель управления</h1>
    <p>Войдите под логином и паролем, которые бот сгенерировал лично для вас.</p>
    {error_html}
    <form method="post" action="{PANEL_BASE_PATH}/login">
      <label for="login">Логин</label>
      <input id="login" name="login" type="text" autocomplete="username" required>
      <label for="password">Пароль</label>
      <input id="password" name="password" type="password" autocomplete="current-password" required>
      <button type="submit">Войти</button>
    </form>
  </main>
</body>
</html>"""


def render_panel_dashboard(state, user_id, status_code=None, error_code=None):
    panel_login = html.escape(state.users[user_id].get("panel_login") or "—")
    publish_channel_ready = "Подключен" if state.users[user_id].get("publish_channel_id") else "Не подключен"
    posts = get_user_storage_items(state, user_id)

    notices = {
        "created": "<div class='notice success'>Пост добавлен в очередь.</div>",
        "published": "<div class='notice success'>Пост отправлен сразу.</div>",
        "deleted": "<div class='notice success'>Пост удален из очереди.</div>",
    }
    errors = {
        "empty": "<div class='notice error'>Добавьте текст или файл.</div>",
        "upload": "<div class='notice error'>Не удалось сохранить загруженный файл.</div>",
        "missing": "<div class='notice error'>Пост не найден.</div>",
        "publish": "<div class='notice error'>Не удалось отправить пост. Проверьте канал публикации и наличие файла.</div>",
    }
    flash_html = notices.get(status_code, "") + errors.get(error_code, "")

    cards = []
    for message_key, data in posts:
        text_preview = html.escape(data.get("text") or "Без текста").replace("\n", "<br>")
        media_name = html.escape(data.get("original_file_name") or (Path(data["file_path"]).name if data.get("file_path") else "Нет файла"))
        media_label = html.escape(data.get("file_type") or "text")
        cards.append(
            f"""
        <article class="post-card">
          <div class="post-head">
            <div>
              <strong>Пост в очереди</strong>
              <div class="meta">Добавлен: {format_storage_time(data.get("created_at"))}</div>
            </div>
            <span class="badge">{media_label}</span>
          </div>
          <div class="post-body">{text_preview}</div>
          <div class="meta">Файл: {media_name}</div>
          <div class="actions">
            <form method="post" action="{PANEL_BASE_PATH}/posts/{message_key}/publish">
              <button class="ghost" type="submit">Отправить сразу</button>
            </form>
            <form method="post" action="{PANEL_BASE_PATH}/posts/{message_key}/delete">
              <button class="danger" type="submit">Удалить</button>
            </form>
          </div>
        </article>
        """
        )

    posts_html = "\n".join(cards) if cards else """
      <div class="empty">
        <strong>Очередь пока пустая.</strong>
        <p>Добавьте пост через эту панель или прямо в Telegram-боте — список общий.</p>
      </div>
    """

    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Панель управления</title>
  <style>
    :root {{
      --bg: #f5efe6;
      --paper: #fffaf2;
      --ink: #1f1a16;
      --muted: #705d4d;
      --line: #d9c7b7;
      --accent: #b85c38;
      --accent-dark: #8f4326;
      --danger: #b3261e;
      --success: #2f7d4a;
      --shadow: 0 24px 70px rgba(58, 38, 24, 0.12);
      font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(184, 92, 56, 0.12), transparent 24%),
        linear-gradient(180deg, #f7f1e9 0%, #efe2d4 100%);
      min-height: 100vh;
    }}
    .shell {{
      width: min(1180px, calc(100% - 32px));
      margin: 24px auto;
      display: grid;
      gap: 20px;
    }}
    .hero, .panel, .post-card, .empty {{
      background: rgba(255, 250, 242, 0.96);
      border: 1px solid rgba(217, 199, 183, 0.9);
      border-radius: 28px;
      box-shadow: var(--shadow);
      backdrop-filter: blur(10px);
    }}
    .hero {{
      padding: 28px;
      display: grid;
      grid-template-columns: 1.7fr 1fr;
      gap: 18px;
      align-items: start;
    }}
    .hero h1 {{ margin: 0 0 8px; font-size: 34px; }}
    .hero p {{ margin: 0; color: var(--muted); line-height: 1.6; }}
    .meta-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }}
    .meta-card {{
      background: #fff;
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 14px 16px;
    }}
    .meta-card span {{
      display: block;
      color: var(--muted);
      font-size: 13px;
      margin-bottom: 6px;
    }}
    .meta-card strong {{ font-size: 16px; }}
    .topbar {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
    }}
    .logout {{
      width: auto;
      padding: 12px 16px;
      border-radius: 14px;
      border: 1px solid var(--line);
      background: #fff;
      color: var(--ink);
      cursor: pointer;
    }}
    .grid {{
      display: grid;
      grid-template-columns: 360px 1fr;
      gap: 20px;
      align-items: start;
    }}
    .panel {{
      padding: 24px;
    }}
    .panel h2, .list h2 {{
      margin: 0 0 16px;
      font-size: 24px;
    }}
    label {{
      display: block;
      margin: 14px 0 8px;
      font-size: 14px;
      color: var(--muted);
    }}
    textarea, input[type="file"] {{
      width: 100%;
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 14px 16px;
      background: #fff;
      font-size: 15px;
    }}
    textarea {{
      min-height: 180px;
      resize: vertical;
      line-height: 1.5;
    }}
    .panel button, .actions button {{
      border: 0;
      border-radius: 16px;
      padding: 12px 16px;
      font-size: 14px;
      font-weight: 600;
      cursor: pointer;
    }}
    .panel button {{
      width: 100%;
      margin-top: 18px;
      background: var(--accent);
      color: #fff;
    }}
    .list {{
      display: grid;
      gap: 16px;
    }}
    .post-card {{
      padding: 20px;
    }}
    .post-head {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: start;
      margin-bottom: 14px;
    }}
    .post-body {{
      margin-bottom: 14px;
      line-height: 1.6;
      word-break: break-word;
    }}
    .meta {{
      color: var(--muted);
      font-size: 13px;
    }}
    .badge {{
      background: rgba(184, 92, 56, 0.12);
      color: var(--accent-dark);
      border-radius: 999px;
      padding: 8px 12px;
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }}
    .actions {{
      display: flex;
      gap: 10px;
      margin-top: 18px;
    }}
    .actions form {{ flex: 1; }}
    .ghost {{
      width: 100%;
      background: #fff;
      border: 1px solid var(--line);
      color: var(--ink);
    }}
    .danger {{
      width: 100%;
      background: rgba(179, 38, 30, 0.10);
      color: var(--danger);
    }}
    .notice {{
      border-radius: 18px;
      padding: 14px 16px;
      font-size: 14px;
      margin-bottom: 18px;
    }}
    .success {{
      background: rgba(47, 125, 74, 0.12);
      color: var(--success);
      border: 1px solid rgba(47, 125, 74, 0.18);
    }}
    .error {{
      background: rgba(179, 38, 30, 0.10);
      color: var(--danger);
      border: 1px solid rgba(179, 38, 30, 0.18);
    }}
    .empty {{
      padding: 28px;
    }}
    .empty p {{
      margin: 8px 0 0;
      color: var(--muted);
      line-height: 1.6;
    }}
    @media (max-width: 900px) {{
      .hero, .grid {{
        grid-template-columns: 1fr;
      }}
      .meta-grid {{
        grid-template-columns: 1fr;
      }}
      .actions {{
        flex-direction: column;
      }}
    }}
  </style>
</head>
<body>
  <div class="shell">
    <section class="hero">
      <div>
        <div class="topbar">
          <div>
            <h1>Панель управления</h1>
            <p>Все отложенные посты пользователя собраны здесь. Посты можно добавлять как через панель, так и прямо в Telegram-боте.</p>
          </div>
          <form method="post" action="{PANEL_BASE_PATH}/logout">
            <button class="logout" type="submit">Выйти</button>
          </form>
        </div>
      </div>
      <div class="meta-grid">
        <div class="meta-card"><span>Логин панели</span><strong>{panel_login}</strong></div>
        <div class="meta-card"><span>Канал публикации</span><strong>{publish_channel_ready}</strong></div>
        <div class="meta-card"><span>Постов в очереди</span><strong>{len(posts)}</strong></div>
        <div class="meta-card"><span>Хранение медиа</span><strong>Локально на сервере</strong></div>
      </div>
    </section>
    <section class="grid">
      <aside class="panel">
        <h2>Добавить пост</h2>
        {flash_html}
        <form method="post" action="{PANEL_BASE_PATH}/posts" enctype="multipart/form-data">
          <label for="text">Текст поста</label>
          <textarea id="text" name="text" placeholder="Напишите подпись или сам текст поста..."></textarea>
          <label for="media">Медиафайл</label>
          <input id="media" name="media" type="file">
          <button type="submit">Добавить в очередь</button>
        </form>
      </aside>
      <section class="list">
        <h2>Отложенные посты</h2>
        {posts_html}
      </section>
    </section>
  </div>
</body>
</html>"""


async def require_panel_user(request):
    state = get_state(request)
    user_id = get_panel_session_user(state, request)
    if not user_id:
        raise web.HTTPFound(f"{PANEL_BASE_PATH}/login")
    return user_id


async def panel_login_page(request):
    state = get_state(request)
    if get_panel_session_user(state, request):
        raise web.HTTPFound(PANEL_BASE_PATH)
    return web.Response(text=render_panel_login_page(request.query.get("error")), content_type="text/html")


async def panel_login_submit(request):
    state = get_state(request)
    form = await request.post()
    login = (form.get("login") or "").strip()
    password = form.get("password") or ""

    matched_user_id = None
    matched_user = None
    for user_id, user_data in state.users.items():
        if (user_data.get("panel_login") or "").lower() == login.lower():
            matched_user_id = user_id
            matched_user = user_data
            break

    if not matched_user or not matched_user.get("panel_password_hash") or not matched_user.get("panel_password_salt"):
        raise web.HTTPFound(f"{PANEL_BASE_PATH}/login?error=invalid")

    if not verify_panel_password(password, matched_user["panel_password_salt"], matched_user["panel_password_hash"]):
        raise web.HTTPFound(f"{PANEL_BASE_PATH}/login?error=invalid")

    session_id = create_panel_session(state, matched_user_id)
    response = web.HTTPFound(PANEL_BASE_PATH)
    response.set_cookie(
        PANEL_SESSION_COOKIE,
        session_id,
        max_age=PANEL_SESSION_TTL,
        httponly=True,
        samesite="Lax",
        path="/",
    )
    return response


async def panel_logout(request):
    state = get_state(request)
    clear_panel_session(state, request)
    response = web.HTTPFound(f"{PANEL_BASE_PATH}/login")
    response.del_cookie(PANEL_SESSION_COOKIE, path="/")
    return response


async def panel_dashboard(request):
    state = get_state(request)
    user_id = await require_panel_user(request)
    return web.Response(
        text=render_panel_dashboard(state, user_id, request.query.get("status"), request.query.get("error")),
        content_type="text/html",
    )


async def panel_add_post(request):
    state = get_state(request)
    user_id = await require_panel_user(request)
    form = await request.post()
    text = (form.get("text") or "").strip()
    uploaded_file = form.get("media")

    has_upload = bool(uploaded_file and getattr(uploaded_file, "filename", ""))
    if not text and not has_upload:
        raise web.HTTPFound(f"{PANEL_BASE_PATH}?error=empty")

    message_key = f"{user_id}:panel:{int(time.time() * 1000)}:{secrets.token_hex(4)}"
    file_path = None
    original_file_name = None
    file_type = None

    if has_upload:
        try:
            file_path, original_file_name, file_type = store_uploaded_file_locally(user_id, message_key, uploaded_file)
        except Exception as exc:
            logging.error(f"Ошибка сохранения загруженного файла в панели: {exc}")
            raise web.HTTPFound(f"{PANEL_BASE_PATH}?error=upload")

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
    raise web.HTTPFound(f"{PANEL_BASE_PATH}?status=created")


async def panel_publish_post(request):
    state = get_state(request)
    user_id = await require_panel_user(request)
    message_key = request.match_info["message_key"]
    data = state.storage.get(message_key)
    if not data or data["user_id"] != user_id:
        raise web.HTTPFound(f"{PANEL_BASE_PATH}?error=missing")

    try:
        await send_to_channel(
            state,
            user_id,
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
        return web.HTTPFound(f"{PANEL_BASE_PATH}?status=published")
    except Exception as exc:
        logging.error(f"Ошибка публикации из панели: {exc}")
        raise web.HTTPFound(f"{PANEL_BASE_PATH}?error=publish")


async def panel_delete_post(request):
    state = get_state(request)
    user_id = await require_panel_user(request)
    message_key = request.match_info["message_key"]
    data = state.storage.get(message_key)
    if not data or data["user_id"] != user_id:
        raise web.HTTPFound(f"{PANEL_BASE_PATH}?error=missing")

    await cleanup_stored_message(state, data)
    del state.storage[message_key]
    await save_storage(state)
    raise web.HTTPFound(f"{PANEL_BASE_PATH}?status=deleted")


async def start_panel_server(state):
    app = web.Application(client_max_size=200 * 1024 ** 2)
    app["state"] = state
    app.add_routes(
        [
            web.get(PANEL_BASE_PATH, panel_dashboard),
            web.get(f"{PANEL_BASE_PATH}/login", panel_login_page),
            web.post(f"{PANEL_BASE_PATH}/login", panel_login_submit),
            web.post(f"{PANEL_BASE_PATH}/logout", panel_logout),
            web.post(f"{PANEL_BASE_PATH}/posts", panel_add_post),
            web.post(f"{PANEL_BASE_PATH}/posts/{{message_key}}/publish", panel_publish_post),
            web.post(f"{PANEL_BASE_PATH}/posts/{{message_key}}/delete", panel_delete_post),
        ]
    )

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, PANEL_HOST, PANEL_PORT)
    await site.start()
    logging.info(f"Панель управления запущена на {build_panel_url(PANEL_BASE_PATH)}")
    return runner
