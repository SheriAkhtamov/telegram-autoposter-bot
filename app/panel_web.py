import html
import json
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
        error_html = "<div class='notice error'><svg class='icon' viewBox='0 0 24 24'><path fill='currentColor' d='M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z'/></svg>Неверный логин или пароль</div>"

    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Панель управления | Вход</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <style>
    :root {{
      --primary: #6366f1;
      --primary-dark: #4f46e5;
      --primary-light: #e0e7ff;
      --secondary: #ec4899;
      --accent: #8b5cf6;
      --bg: #f8fafc;
      --bg-card: #ffffff;
      --text: #1e293b;
      --text-muted: #64748b;
      --border: #e2e8f0;
      --danger: #ef4444;
      --danger-bg: #fef2f2;
      --success: #10b981;
      --success-bg: #ecfdf5;
      --shadow-sm: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
      --shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -2px rgba(0, 0, 0, 0.1);
      --shadow-lg: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 8px 10px -6px rgba(0, 0, 0, 0.1);
      --shadow-xl: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
      --radius: 20px;
      --radius-sm: 12px;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: 'Inter', system-ui, -apple-system, sans-serif;
      background: var(--bg);
      min-height: 100vh;
      display: grid;
      place-items: center;
      padding: 24px;
      position: relative;
      overflow-x: hidden;
    }}
    body::before {{
      content: '';
      position: absolute;
      top: -50%;
      left: -50%;
      width: 200%;
      height: 200%;
      background: 
        radial-gradient(circle at 20% 30%, rgba(99, 102, 241, 0.08) 0%, transparent 40%),
        radial-gradient(circle at 80% 70%, rgba(236, 72, 153, 0.08) 0%, transparent 40%),
        radial-gradient(circle at 50% 50%, rgba(139, 92, 246, 0.06) 0%, transparent 50%);
      animation: gradientMove 20s ease infinite;
      z-index: -1;
    }}
    @keyframes gradientMove {{
      0%, 100% {{ transform: translate(0, 0) rotate(0deg); }}
      33% {{ transform: translate(2%, 2%) rotate(1deg); }}
      66% {{ transform: translate(-1%, 1%) rotate(-1deg); }}
    }}
    .card {{
      width: 100%;
      max-width: 440px;
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 48px;
      box-shadow: var(--shadow-xl);
      position: relative;
      overflow: hidden;
    }}
    .card::before {{
      content: '';
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      height: 4px;
      background: linear-gradient(90deg, var(--primary), var(--secondary), var(--accent));
    }}
    .logo {{
      width: 72px;
      height: 72px;
      background: linear-gradient(135deg, var(--primary), var(--secondary));
      border-radius: var(--radius-sm);
      display: grid;
      place-items: center;
      margin-bottom: 28px;
      box-shadow: var(--shadow-lg);
      transition: transform 0.3s ease;
    }}
    .logo:hover {{
      transform: scale(1.05) rotate(2deg);
    }}
    .logo svg {{
      width: 40px;
      height: 40px;
      color: white;
    }}
    h1 {{
      font-size: 30px;
      font-weight: 800;
      color: var(--text);
      margin-bottom: 10px;
      letter-spacing: -0.02em;
    }}
    .subtitle {{
      color: var(--text-muted);
      font-size: 15px;
      line-height: 1.6;
      margin-bottom: 36px;
    }}
    .form-group {{
      margin-bottom: 22px;
    }}
    label {{
      display: block;
      font-size: 14px;
      font-weight: 600;
      color: var(--text);
      margin-bottom: 10px;
      letter-spacing: 0.01em;
    }}
    input {{
      width: 100%;
      border: 2px solid var(--border);
      border-radius: var(--radius-sm);
      padding: 16px 18px;
      background: var(--bg);
      color: var(--text);
      font-size: 15px;
      transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
      font-weight: 500;
    }}
    input:focus {{
      outline: none;
      border-color: var(--primary);
      box-shadow: 0 0 0 4px var(--primary-light);
      background: white;
      transform: translateY(-1px);
    }}
    input::placeholder {{
      color: var(--text-muted);
      font-weight: 400;
    }}
    button {{
      width: 100%;
      border: none;
      border-radius: var(--radius-sm);
      padding: 16px;
      background: linear-gradient(135deg, var(--primary), var(--secondary));
      color: white;
      font-size: 16px;
      font-weight: 700;
      cursor: pointer;
      transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
      margin-top: 8px;
      position: relative;
      overflow: hidden;
      letter-spacing: 0.01em;
    }}
    button::before {{
      content: '';
      position: absolute;
      top: 0;
      left: -100%;
      width: 100%;
      height: 100%;
      background: linear-gradient(90deg, transparent, rgba(255,255,255,0.2), transparent);
      transition: left 0.5s;
    }}
    button:hover::before {{
      left: 100%;
    }}
    button:hover {{
      transform: translateY(-2px);
      box-shadow: 0 15px 35px -5px rgba(99, 102, 241, 0.4);
    }}
    button:active {{
      transform: translateY(0);
    }}
    .notice {{
      border-radius: var(--radius-sm);
      padding: 16px 18px;
      margin-bottom: 28px;
      font-size: 14px;
      display: flex;
      align-items: center;
      gap: 12px;
      font-weight: 500;
      animation: slideIn 0.3s ease;
    }}
    @keyframes slideIn {{
      from {{ opacity: 0; transform: translateY(-10px); }}
      to {{ opacity: 1; transform: translateY(0); }}
    }}
    .error {{
      background: var(--danger-bg);
      color: var(--danger);
      border: 1px solid rgba(239, 68, 68, 0.15);
    }}
    .icon {{
      width: 22px;
      height: 22px;
      flex-shrink: 0;
    }}
    .footer {{
      margin-top: 36px;
      text-align: center;
      font-size: 13px;
      color: var(--text-muted);
      padding-top: 24px;
      border-top: 1px solid var(--border);
    }}
  </style>
</head>
<body>
  <main class="card">
    <div class="logo">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
        <line x1="3" y1="9" x2="21" y2="9"/>
        <line x1="9" y1="21" x2="9" y2="9"/>
      </svg>
    </div>
    <h1>Панель управления</h1>
    <p class="subtitle">Войдите под логином и паролем, которые бот сгенерировал лично для вас</p>
    {error_html}
    <form method="post" action="{PANEL_BASE_PATH}/login">
      <div class="form-group">
        <label for="login">Логин</label>
        <input id="login" name="login" type="text" autocomplete="username" placeholder="Введите ваш логин" required>
      </div>
      <div class="form-group">
        <label for="password">Пароль</label>
        <input id="password" name="password" type="password" autocomplete="current-password" placeholder="Введите ваш пароль" required>
      </div>
      <button type="submit">Войти в панель</button>
    </form>
    <div class="footer">
      Система управления отложенными публикациями
    </div>
  </main>
</body>
</html>"""


def render_panel_dashboard(state, user_id, status_code=None, error_code=None):
    panel_login = html.escape(state.users[user_id].get("panel_login") or "—")
    publish_channel_ready = "Подключен" if state.users[user_id].get("publish_channel_id") else "Не подключен"
    posts = get_user_storage_items(state, user_id)

    notices = {
        "created": "<div class='notice success'><svg class='icon' viewBox='0 0 24 24'><path fill='currentColor' d='M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z'/></svg>Пост добавлен в очередь.</div>",
        "published": "<div class='notice success'><svg class='icon' viewBox='0 0 24 24'><path fill='currentColor' d='M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z'/></svg>Пост отправлен сразу.</div>",
        "deleted": "<div class='notice success'><svg class='icon' viewBox='0 0 24 24'><path fill='currentColor' d='M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z'/></svg>Пост удален из очереди.</div>",
    }
    errors = {
        "empty": "<div class='notice error'><svg class='icon' viewBox='0 0 24 24'><path fill='currentColor' d='M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z'/></svg>Добавьте текст или файл.</div>",
        "upload": "<div class='notice error'><svg class='icon' viewBox='0 0 24 24'><path fill='currentColor' d='M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z'/></svg>Не удалось сохранить загруженный файл.</div>",
        "missing": "<div class='notice error'><svg class='icon' viewBox='0 0 24 24'><path fill='currentColor' d='M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z'/></svg>Пост не найден.</div>",
        "publish": "<div class='notice error'><svg class='icon' viewBox='0 0 24 24'><path fill='currentColor' d='M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z'/></svg>Не удалось отправить пост. Проверьте канал публикации и наличие файла.</div>",
    }
    flash_html = notices.get(status_code, "") + errors.get(error_code, "")

    cards = []
    for message_key, data in posts:
        text_preview = html.escape(data.get("text") or "Без текста").replace("\n", "<br>")
        media_name = html.escape(data.get("original_file_name") or (Path(data["file_path"]).name if data.get("file_path") else "Нет файла"))
        media_label = html.escape(data.get("file_type") or "text")
        
        # File type icon
        file_icons = {
            "photo": "📷",
            "video": "🎬",
            "audio": "🎵",
            "voice": "🎙️",
            "document": "📄",
            "text": "📝"
        }
        file_icon = file_icons.get(media_label, "📎")
        
        cards.append(
            f"""
        <article class="post-card" data-key="{message_key}">
          <div class="post-head">
            <div class="post-info">
              <div class="post-meta">
                <span class="badge">{file_icon} {media_label}</span>
                <span class="time">{format_storage_time(data.get("created_at"))}</span>
              </div>
              <div class="post-body">{text_preview}</div>
              <div class="file-name">📎 {media_name}</div>
            </div>
            <div class="post-actions">
              <form method="post" action="{PANEL_BASE_PATH}/posts/{message_key}/publish">
                <button class="btn-publish" type="submit" title="Отправить сейчас">
                  <svg viewBox="0 0 24 24" width="18" height="18"><path fill="currentColor" d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>
                </button>
              </form>
              <form method="post" action="{PANEL_BASE_PATH}/posts/{message_key}/delete">
                <button class="btn-delete" type="submit" title="Удалить">
                  <svg viewBox="0 0 24 24" width="18" height="18"><path fill="currentColor" d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/></svg>
                </button>
              </form>
            </div>
          </div>
        </article>
        """
        )

    posts_html = "\n".join(cards) if cards else """
      <div class="empty-state">
        <div class="empty-icon">📭</div>
        <strong>Очередь пуста</strong>
        <p>Добавьте пост через эту панель или прямо в Telegram-боте</p>
      </div>
    """

    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Панель управления | Дашборд</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <style>
    :root {{
      --primary: #6366f1;
      --primary-dark: #4f46e5;
      --primary-light: #e0e7ff;
      --secondary: #ec4899;
      --accent: #8b5cf6;
      --bg: #f8fafc;
      --bg-card: #ffffff;
      --text: #1e293b;
      --text-muted: #64748b;
      --border: #e2e8f0;
      --danger: #ef4444;
      --danger-bg: #fef2f2;
      --success: #10b981;
      --success-bg: #ecfdf5;
      --shadow-sm: 0 1px 2px 0 rgba(0, 0, 0, 0.05);
      --shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -2px rgba(0, 0, 0, 0.1);
      --shadow-lg: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 8px 10px -6px rgba(0, 0, 0, 0.1);
      --shadow-xl: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
      --radius: 20px;
      --radius-sm: 12px;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: 'Inter', system-ui, -apple-system, sans-serif;
      background: var(--bg);
      color: var(--text);
      min-height: 100vh;
      position: relative;
      overflow-x: hidden;
    }}
    body::before {{
      content: '';
      position: absolute;
      top: -50%;
      left: -50%;
      width: 200%;
      height: 200%;
      background: 
        radial-gradient(circle at 20% 30%, rgba(99, 102, 241, 0.06) 0%, transparent 40%),
        radial-gradient(circle at 80% 70%, rgba(236, 72, 153, 0.06) 0%, transparent 40%),
        radial-gradient(circle at 50% 50%, rgba(139, 92, 246, 0.04) 0%, transparent 50%);
      animation: gradientMove 20s ease infinite;
      z-index: -1;
    }}
    @keyframes gradientMove {{
      0%, 100% {{ transform: translate(0, 0) rotate(0deg); }}
      33% {{ transform: translate(2%, 2%) rotate(1deg); }}
      66% {{ transform: translate(-1%, 1%) rotate(-1deg); }}
    }}
    .container {{
      max-width: 1280px;
      margin: 0 auto;
      padding: 32px;
    }}
    /* Header */
    .header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 40px;
      gap: 24px;
      flex-wrap: wrap;
      background: var(--bg-card);
      padding: 24px 32px;
      border-radius: var(--radius);
      border: 1px solid var(--border);
      box-shadow: var(--shadow-lg);
    }}
    .header-left h1 {{
      font-size: 32px;
      font-weight: 800;
      margin-bottom: 8px;
      background: linear-gradient(135deg, var(--primary), var(--secondary));
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
      letter-spacing: -0.02em;
    }}
    .header-left p {{
      color: var(--text-muted);
      font-size: 15px;
      font-weight: 500;
    }}
    .btn-logout {{
      display: inline-flex;
      align-items: center;
      gap: 10px;
      padding: 12px 24px;
      background: var(--bg);
      border: 2px solid var(--border);
      border-radius: var(--radius-sm);
      color: var(--text);
      font-size: 14px;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
    }}
    .btn-logout:hover {{
      background: var(--danger-bg);
      border-color: var(--danger);
      color: var(--danger);
      transform: translateY(-2px);
      box-shadow: var(--shadow-lg);
    }}
    /* Stats Grid */
    .stats-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 20px;
      margin-bottom: 40px;
    }}
    .stat-card {{
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 24px;
      display: flex;
      flex-direction: column;
      gap: 10px;
      transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
      position: relative;
      overflow: hidden;
    }}
    .stat-card::before {{
      content: '';
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      height: 3px;
      background: linear-gradient(90deg, var(--primary), var(--secondary));
      opacity: 0;
      transition: opacity 0.3s;
    }}
    .stat-card:hover {{
      transform: translateY(-4px);
      box-shadow: var(--shadow-xl);
      border-color: var(--primary-light);
    }}
    .stat-card:hover::before {{
      opacity: 1;
    }}
    .stat-label {{
      font-size: 13px;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.08em;
      font-weight: 600;
    }}
    .stat-value {{
      font-size: 28px;
      font-weight: 800;
      color: var(--text);
      letter-spacing: -0.02em;
    }}
    .stat-value.success {{ 
      color: var(--success);
      background: linear-gradient(135deg, var(--success), #059669);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
    }}
    .stat-value.warning {{ 
      color: #f59e0b;
      background: linear-gradient(135deg, #f59e0b, #d97706);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
    }}
    /* Main Grid */
    .main-grid {{
      display: grid;
      grid-template-columns: 400px 1fr;
      gap: 32px;
    }}
    @media (max-width: 1024px) {{
      .main-grid {{
        grid-template-columns: 1fr;
      }}
    }}
    /* Create Post Panel */
    .create-panel {{
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 32px;
      position: sticky;
      top: 32px;
      height: fit-content;
      box-shadow: var(--shadow-lg);
    }}
    .create-panel h2 {{
      font-size: 22px;
      margin-bottom: 24px;
      display: flex;
      align-items: center;
      gap: 12px;
      font-weight: 700;
      letter-spacing: -0.01em;
    }}
    .form-group {{
      margin-bottom: 24px;
    }}
    label {{
      display: block;
      font-size: 14px;
      font-weight: 600;
      color: var(--text);
      margin-bottom: 12px;
      letter-spacing: 0.01em;
    }}
    textarea {{
      width: 100%;
      min-height: 180px;
      border: 2px solid var(--border);
      border-radius: var(--radius-sm);
      padding: 18px 20px;
      background: var(--bg);
      color: var(--text);
      font-size: 15px;
      font-family: inherit;
      resize: vertical;
      transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
      font-weight: 500;
      line-height: 1.6;
    }}
    textarea:focus {{
      outline: none;
      border-color: var(--primary);
      box-shadow: 0 0 0 4px var(--primary-light);
      background: white;
      transform: translateY(-1px);
    }}
    textarea::placeholder {{
      color: var(--text-muted);
      font-weight: 400;
    }}
    .file-input-wrapper {{
      position: relative;
      overflow: hidden;
      display: inline-block;
      width: 100%;
    }}
    .file-input-wrapper input[type=file] {{
      position: absolute;
      left: -9999px;
    }}
    .file-input-label {{
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 12px;
      width: 100%;
      padding: 24px;
      border: 2px dashed var(--border);
      border-radius: var(--radius-sm);
      background: var(--bg);
      color: var(--text-muted);
      cursor: pointer;
      transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
      text-align: center;
      font-weight: 500;
    }}
    .file-input-label:hover {{
      border-color: var(--primary);
      color: var(--primary);
      background: var(--primary-light);
      transform: translateY(-2px);
    }}
    .file-name-display {{
      margin-top: 10px;
      font-size: 13px;
      color: var(--text-muted);
      word-break: break-all;
      font-weight: 500;
    }}
    .btn-submit {{
      width: 100%;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 12px;
      padding: 16px;
      background: linear-gradient(135deg, var(--primary), var(--secondary));
      border: none;
      border-radius: var(--radius-sm);
      color: white;
      font-size: 16px;
      font-weight: 700;
      cursor: pointer;
      transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
      position: relative;
      overflow: hidden;
      letter-spacing: 0.01em;
    }}
    .btn-submit::before {{
      content: '';
      position: absolute;
      top: 0;
      left: -100%;
      width: 100%;
      height: 100%;
      background: linear-gradient(90deg, transparent, rgba(255,255,255,0.2), transparent);
      transition: left 0.5s;
    }}
    .btn-submit:hover::before {{
      left: 100%;
    }}
    .btn-submit:hover {{
      transform: translateY(-2px);
      box-shadow: 0 15px 35px -5px rgba(99, 102, 241, 0.4);
    }}
    /* Posts List */
    .posts-section h2 {{
      font-size: 22px;
      margin-bottom: 24px;
      display: flex;
      align-items: center;
      gap: 12px;
      font-weight: 700;
      letter-spacing: -0.01em;
    }}
    .posts-list {{
      display: flex;
      flex-direction: column;
      gap: 20px;
    }}
    .post-card {{
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 24px;
      transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
      position: relative;
      overflow: hidden;
    }}
    .post-card::before {{
      content: '';
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      height: 3px;
      background: linear-gradient(90deg, var(--primary), var(--secondary));
      opacity: 0;
      transition: opacity 0.3s;
    }}
    .post-card:hover {{
      transform: translateY(-4px);
      box-shadow: var(--shadow-xl);
      border-color: var(--primary-light);
    }}
    .post-card:hover::before {{
      opacity: 1;
    }}
    .post-head {{
      display: flex;
      justify-content: space-between;
      gap: 20px;
    }}
    .post-info {{
      flex: 1;
      min-width: 0;
    }}
    .post-meta {{
      display: flex;
      align-items: center;
      gap: 14px;
      margin-bottom: 14px;
      flex-wrap: wrap;
    }}
    .badge {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 8px 14px;
      background: var(--primary-light);
      color: var(--primary);
      border-radius: 999px;
      font-size: 12px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }}
    .time {{
      font-size: 13px;
      color: var(--text-muted);
      font-weight: 500;
    }}
    .post-body {{
      font-size: 15px;
      line-height: 1.7;
      color: var(--text);
      margin-bottom: 14px;
      word-break: break-word;
      font-weight: 500;
    }}
    .file-name {{
      font-size: 13px;
      color: var(--text-muted);
      font-weight: 500;
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }}
    .post-actions {{
      display: flex;
      flex-direction: column;
      gap: 10px;
      flex-shrink: 0;
    }}
    .btn-publish, .btn-delete {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      padding: 12px;
      border: none;
      border-radius: var(--radius-sm);
      cursor: pointer;
      transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
    }}
    .btn-publish {{
      background: var(--success-bg);
      color: var(--success);
    }}
    .btn-publish:hover {{
      background: var(--success);
      color: white;
      transform: translateY(-2px);
      box-shadow: var(--shadow-lg);
    }}
    .btn-delete {{
      background: var(--danger-bg);
      color: var(--danger);
    }}
    .btn-delete:hover {{
      background: var(--danger);
      color: white;
      transform: translateY(-2px);
      box-shadow: var(--shadow-lg);
    }}
    /* Empty State */
    .empty-state {{
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 80px 40px;
      text-align: center;
    }}
    .empty-icon {{
      font-size: 72px;
      margin-bottom: 20px;
      opacity: 0.6;
      display: inline-block;
      animation: float 3s ease-in-out infinite;
    }}
    @keyframes float {{
      0%, 100% {{ transform: translateY(0); }}
      50% {{ transform: translateY(-10px); }}
    }}
    .empty-state strong {{
      display: block;
      font-size: 22px;
      margin-bottom: 10px;
      color: var(--text);
      font-weight: 700;
    }}
    .empty-state p {{
      color: var(--text-muted);
      font-size: 15px;
      font-weight: 500;
    }}
    /* Notices */
    .notice {{
      border-radius: var(--radius-sm);
      padding: 16px 18px;
      margin-bottom: 24px;
      font-size: 14px;
      display: flex;
      align-items: center;
      gap: 12px;
      font-weight: 600;
      animation: slideIn 0.3s ease;
    }}
    @keyframes slideIn {{
      from {{ opacity: 0; transform: translateY(-10px); }}
      to {{ opacity: 1; transform: translateY(0); }}
    }}
    .success {{
      background: var(--success-bg);
      color: var(--success);
      border: 1px solid rgba(16, 185, 129, 0.2);
    }}
    .error {{
      background: var(--danger-bg);
      color: var(--danger);
      border: 1px solid rgba(239, 68, 68, 0.15);
    }}
    .icon {{
      width: 22px;
      height: 22px;
      flex-shrink: 0;
    }}
    /* Responsive */
    @media (max-width: 768px) {{
      .container {{
        padding: 20px;
      }}
      .header {{
        flex-direction: column;
        align-items: flex-start;
        padding: 20px;
      }}
      .header-left h1 {{
        font-size: 26px;
      }}
      .stats-grid {{
        grid-template-columns: 1fr;
      }}
      .post-head {{
        flex-direction: column;
      }}
      .post-actions {{
        flex-direction: row;
      }}
      .post-actions form {{
        flex: 1;
      }}
    }}
  </style>
</head>
<body>
  <div class="container">
    <header class="header">
      <div class="header-left">
        <h1>📊 Панель управления</h1>
        <p>Управляйте отложенными публикациями легко и удобно</p>
      </div>
      <form method="post" action="{PANEL_BASE_PATH}/logout">
        <button class="btn-logout" type="submit">
          <svg viewBox="0 0 24 24" width="18" height="18"><path fill="currentColor" d="M17 7l-1.41 1.41L18.17 11H8v2h10.17l-2.58 2.58L17 17l5-5zM4 5h8V3H4c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h8v-2H4V5z"/></svg>
          Выйти
        </button>
      </form>
    </header>

    <section class="stats-grid">
      <div class="stat-card">
        <span class="stat-label">Логин панели</span>
        <span class="stat-value">{panel_login}</span>
      </div>
      <div class="stat-card">
        <span class="stat-label">Канал публикации</span>
        <span class="stat-value {'success' if publish_channel_ready == 'Подключен' else 'warning'}">{publish_channel_ready}</span>
      </div>
      <div class="stat-card">
        <span class="stat-label">Постов в очереди</span>
        <span class="stat-value">{len(posts)}</span>
      </div>
      <div class="stat-card">
        <span class="stat-label">Хранение</span>
        <span class="stat-value">Локально</span>
      </div>
    </section>

    <main class="main-grid">
      <aside class="create-panel">
        <h2>✨ Создать пост</h2>
        {flash_html}
        <form method="post" action="{PANEL_BASE_PATH}/posts" enctype="multipart/form-data" id="createForm">
          <div class="form-group">
            <label for="text">Текст поста</label>
            <textarea id="text" name="text" placeholder="Напишите текст вашего поста..."></textarea>
          </div>
          <div class="form-group">
            <label>Медиафайл</label>
            <div class="file-input-wrapper">
              <input type="file" id="media" name="media" onchange="updateFileName(this)">
              <label for="media" class="file-input-label">
                <svg viewBox="0 0 24 24" width="28" height="28"><path fill="currentColor" d="M9 16h6v-6h4l-7-7-7 7h4zm-4 2h14v2H5z"/></svg>
                <span>Выберите файл или перетащите</span>
              </label>
            </div>
            <div class="file-name-display" id="fileName"></div>
          </div>
          <button type="submit" class="btn-submit">
            <svg viewBox="0 0 24 24" width="22" height="22"><path fill="currentColor" d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z"/></svg>
            Добавить в очередь
          </button>
        </form>
      </aside>

      <section class="posts-section">
        <h2>📋 Отложенные посты</h2>
        <div class="posts-list">
          {posts_html}
        </div>
      </section>
    </main>
  </div>

  <script>
    function updateFileName(input) {{
      const fileName = input.files[0] ? input.files[0].name : '';
      document.getElementById('fileName').textContent = fileName;
    }}
    
    // Add confirmation before publishing
    document.querySelectorAll('.btn-publish').forEach(btn => {{
      btn.addEventListener('click', (e) => {{
        if (!confirm('Отправить этот пост прямо сейчас?')) {{
          e.preventDefault();
        }}
      }});
    }});
    
    // Add confirmation before deleting
    document.querySelectorAll('.btn-delete').forEach(btn => {{
      btn.addEventListener('click', (e) => {{
        if (!confirm('Вы уверены, что хотите удалить этот пост?')) {{
          e.preventDefault();
        }}
      }});
    }});
  </script>
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
