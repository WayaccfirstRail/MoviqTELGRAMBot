"""
Telegram Bot for موفيك بوت Platform (Arabic)
-------------------------------------------

This script implements a Telegram bot in Python that mirrors basic
functionality of the موفيك بوت website.  It lists the movies and
series currently available on the site, checks the website status,
and provides a suite of administrative commands for managing users
and invite codes.  All bot responses are written in Arabic to
provide a native experience for users in the Middle East and North
Africa region.

Key Features
============

* **Static catalog of movies and series** – The bot includes
  a pre‑copied list of the titles currently displayed on
  https://captainm.netlify.app/.  When the `/movies` or `/series`
  command is invoked (or via inline buttons), the bot returns
  these titles in a neatly formatted list.
* **Website status check** – The `/status` command performs a
  simple HTTP GET request to the home page to determine whether
  the site is reachable.  If the request succeeds, it replies
  that the site is online; otherwise it reports that the site is
  under maintenance.
* **Invite codes** – Each user sees the current invite code when
  they start interacting with the bot.  An admin can change this
  code on the fly via `/change_invite <code>`.  Users can also
  request the current code at any time using `/invite`.
* **Administrative controls** – A list of admin user IDs is
  defined in the `ADMIN_IDS` constant.  Admins can ban, block or
  flag users by ID using `/ban`, `/block` or `/flag` commands.
  Banned users will be silently ignored by the bot.  Blocked
  users are tracked but still receive a warning when they try
  interacting.  Flagged users are simply noted for later review.

To deploy this bot on Replit or any other Python environment,
install the following dependencies:

```
pip install python-telegram-bot==20.3 requests beautifulsoup4
```

Replace `YOUR_BOT_TOKEN` below with your actual Telegram bot token
and populate `ADMIN_IDS` with your Telegram user ID(s).  You can
find your own user ID by sending a message to
@userinfobot on Telegram.

Note:  The list of movies and series here reflects the
catalogue as of August 2025.  If the website updates, you should
edit the `MOVIES` and `SERIES` lists accordingly.
"""

import os
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import List, Optional, Dict, Any

import requests
import psycopg2
import json
from bs4 import BeautifulSoup
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardRemove,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
)


# -----------------------------------------------------------------------------
# Configuration
#
# Insert your bot token below.  For security, you may prefer to set it as an
# environment variable called BOT_TOKEN on Replit instead of writing it
# directly in code (e.g. TOKEN = os.environ.get('BOT_TOKEN')).
# -----------------------------------------------------------------------------

# TODO: Replace this with your actual bot token, or set BOT_TOKEN in the
# environment and leave TOKEN as None to fetch it automatically.
TOKEN: Optional[str] = os.getenv("BOT_TOKEN", "7820798678:AAEQq-2A9rT3klHNY_ueb1ZTYf2l_1NHtAU")

# Database connection
DATABASE_URL = os.environ.get('DATABASE_URL')

# List of Telegram user IDs who have administrative privileges.  Replace
# the example IDs with actual numeric IDs.  Admins can ban/block/flag users
# and change the invite code.
ADMIN_IDS: List[int] = [123456789, 987654321, 5506657489]


# Invite code shown to regular users.  Admins can change this value at
# runtime via the /change_invite command.
invite_code: str = "ABCDEF"

# In‑memory data structures for tracking user status.  You could persist
# these sets to disk (e.g. JSON file) for a long‑running bot, but for
# simplicity they live in RAM.
banned_users: set[int] = set()
blocked_users: set[int] = set()
flagged_users: set[int] = set()

# Command toggle states - admins can enable/disable commands
command_states = {
    "movies": True,
    "series": True,
    "status": True,
    "invite": True,
    "help": True
}

# Temporary storage for admin commands waiting for user input
waiting_for_input: dict[int, str] = {}
# Store additional context for admin operations
admin_context: dict[int, dict] = {}
# Site status control - affects status command behavior
site_status: bool = True  # True = ON, False = OFF

# ---------------------------------------------------------------------------
# Ticketing System Variables
# ---------------------------------------------------------------------------

# This list will hold all tickets.  Each ticket is a dict with:
# id, user_id, user_link, category, message, timestamp, closed (bool)
tickets: List[Dict[str, Any]] = []

# Map user_id -> category when waiting for the user to type their ticket message
waiting_for_ticket: Dict[int, str] = {}


# Static catalog taken from Captain M website (as of Aug 2025).  Each
# entry is a movie title in Arabic.
MOVIES: List[str] = [
    "أحمد و أحمد",
    "روكي الغلابة",
    "الشاطر",
    "في عز الظهر",
    "المشروع X",
    "ريستارت",
    "الصفا ثانوية بنات",
    "نجوم الساحل",
]

# Static series list.  At the time of writing there was only one series.
SERIES: List[str] = [
    "لعبة الحبار",
]


# -----------------------------------------------------------------------------
# Helper functions
# -----------------------------------------------------------------------------

def user_is_admin(user_id: int) -> bool:
    """Return True if the given user ID belongs to an administrator."""
    return user_id in ADMIN_IDS


def fetch_website_status(url: str = "https://captainm.netlify.app") -> bool:
    """Check whether the target website is reachable.

    Performs a simple GET request and returns True if the HTTP status
    code is 200.  Any exception or non‑200 code is interpreted as the
    site being down or under maintenance.
    """
    try:
        response = requests.get(url, timeout=10)
        return response.status_code == 200
    except requests.RequestException:
        return False


# -----------------------------------------------------------------------------
# Database functions for persistence
# -----------------------------------------------------------------------------

def init_database():
    """Initialize database tables and load initial data."""
    if not DATABASE_URL:
        print("Warning: No DATABASE_URL found. Data will not persist between restarts.")
        return
    
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        
        # Create tables
        cur.execute('''
            CREATE TABLE IF NOT EXISTS bot_data (
                id SERIAL PRIMARY KEY,
                data_type VARCHAR(50) UNIQUE,
                content TEXT
            )
        ''')
        
        conn.commit()
        cur.close()
        conn.close()
        print("Database initialized successfully")
        
    except Exception as e:
        print(f"Database initialization failed: {e}")

def save_to_database(data_type: str, data):
    """Save data to database."""
    if not DATABASE_URL:
        return
    
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        
        json_data = json.dumps(data, ensure_ascii=False)
        cur.execute('''
            INSERT INTO bot_data (data_type, content) VALUES (%s, %s)
            ON CONFLICT (data_type) DO UPDATE SET content = EXCLUDED.content
        ''', (data_type, json_data))
        
        conn.commit()
        cur.close()
        conn.close()
        
    except Exception as e:
        print(f"Failed to save {data_type}: {e}")

def load_from_database(data_type: str, default_value):
    """Load data from database."""
    if not DATABASE_URL:
        return default_value
    
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        
        cur.execute('SELECT content FROM bot_data WHERE data_type = %s', (data_type,))
        result = cur.fetchone()
        
        cur.close()
        conn.close()
        
        if result:
            return json.loads(result[0])
        else:
            # Save default value if not exists
            save_to_database(data_type, default_value)
            return default_value
            
    except Exception as e:
        print(f"Failed to load {data_type}: {e}")
        return default_value

def save_all_data():
    """Save all bot data to database."""
    global MOVIES, SERIES, banned_users, blocked_users, flagged_users
    global invite_code, command_states, site_status, tickets
    
    save_to_database('movies', MOVIES)
    save_to_database('series', SERIES)
    save_to_database('banned_users', list(banned_users))
    save_to_database('blocked_users', list(blocked_users))
    save_to_database('flagged_users', list(flagged_users))
    save_to_database('invite_code', invite_code)
    save_to_database('command_states', command_states)
    save_to_database('site_status', site_status)
    save_to_database('tickets', tickets)

def load_all_data():
    """Load all bot data from database."""
    global MOVIES, SERIES, banned_users, blocked_users, flagged_users
    global invite_code, command_states, site_status, tickets
    
    # Load movies and series with current data as default
    MOVIES = load_from_database('movies', MOVIES)
    SERIES = load_from_database('series', SERIES)
    
    # Load user lists
    banned_users = set(load_from_database('banned_users', []))
    blocked_users = set(load_from_database('blocked_users', []))
    flagged_users = set(load_from_database('flagged_users', []))
    
    # Load settings
    invite_code = load_from_database('invite_code', invite_code)
    command_states = load_from_database('command_states', command_states)
    site_status = load_from_database('site_status', site_status)
    
    # Load tickets
    tickets = load_from_database('tickets', [])


def parse_titles_from_page(url: str, selector: str = "h3") -> List[str]:
    """Attempt to scrape titles from a page on the Captain M site.

    This function is not currently used because the site loads data
    dynamically via JavaScript and the static HTML does not contain
    the lists we need.  It is provided here for completeness should
    the site change its implementation.  You can adjust the `selector`
    parameter to target the correct element for titles.

    Args:
        url:  URL of the page to scrape (e.g. '/movies' or '/series').
        selector: CSS selector for the elements containing titles.

    Returns:
        A list of unique title strings.
    """
    try:
        resp = requests.get(url, timeout=10)
        soup = BeautifulSoup(resp.content, "html.parser")
        titles = [elem.get_text(strip=True) for elem in soup.select(selector)]
        # Remove duplicates while preserving order
        unique: List[str] = []
        for t in titles:
            if t and t not in unique:
                unique.append(t)
        return unique
    except requests.RequestException:
        return []


# -----------------------------------------------------------------------------
# Command and callback handlers
# -----------------------------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a welcome message with quick‑action buttons when the user starts."""
    user_id = update.effective_user.id
    # If the user is banned, ignore the command
    if user_id in banned_users:
        return
    # Craft the welcome message in Arabic
    welcome_text = (
        f"مرحبًا {update.effective_user.first_name}!\n\n"
        "هذا هو موفيك بوت حيث يمكنك معرفة الأفلام والمسلسلات المتاحة "
        "وحالة الموقع الحالية.\n\n"
        f"رمز الدعوة الخاص بك هو: {invite_code}\n\n"
        "استخدم الأزرار أدناه أو الأوامر النصية لاستكشاف المحتوى."
    )
    # Inline keyboard with options
    keyboard = [
        [InlineKeyboardButton("🎬 الأفلام", callback_data="movies")],
        [InlineKeyboardButton("🌐 حالة الموقع", callback_data="status")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(welcome_text, reply_markup=reply_markup)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Provide a list of available commands (admin only)."""
    user_id = update.effective_user.id
    if user_id in banned_users:
        return
    if not user_is_admin(user_id):
        await update.message.reply_text("هذا الأمر مخصص للمسؤولين فقط.")
        return
    
    help_text = (
        "الأوامر المتاحة:\n"
        "/start - بدء المحادثة وعرض الأزرار\n"
        "/movies - عرض قائمة الأفلام المتاحة\n"
        "/series - عرض قائمة المسلسلات المتاحة\n"
        "/status - التحقق من حالة موقع كابتن م\n"
        "/invite - عرض رمز الدعوة الحالي\n"
        "/help - عرض هذه الرسالة\n"
    )
    # Only show admin commands to admins
    if user_is_admin(update.effective_user.id):
        help_text += (
            "\nأوامر الإدارة:\n"
            "/ban <رقم المستخدم> - حظر مستخدم من استخدام البوت\n"
            "/block <رقم المستخدم> - منع مستخدم مؤقتًا وإعلامه\n"
            "/flag <رقم المستخدم> - وضع علامة على مستخدم كمشتبه به\n"
            "/change_invite <رمز> - تغيير رمز الدعوة\n"
            "/toggle <أمر> - تفعيل/تعطيل الأوامر (movies, series, status, invite, help)\n"
            "/add - إضافة فيلم أو مسلسل جديد\n"
            "/remove - حذف فيلم أو مسلسل\n"
            "/move - تحريك فيلم أو مسلسل إلى موضع جديد\n"
            "/site - تحكم في حالة الموقع (ON/OFF)\n"
        )
    await update.message.reply_text(help_text)


async def movies_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send the list of movies."""
    user_id = update.effective_user.id
    if user_id in banned_users:
        return
    if user_id in blocked_users:
        await update.message.reply_text(
            "لقد تم حظرك مؤقتًا من استخدام هذا البوت. يرجى التواصل مع الإدارة."
        )
        return
    # Check if movies command is enabled
    if not command_states.get("movies", True):
        await update.message.reply_text("هذا الأمر معطل حاليًا من قبل الإدارة.")
        return
    # Compose the movie list in modern format
    if MOVIES:
        text = "🎬 ***قائمة الأفلام المتاحة***\n\n"
        for idx, title in enumerate(MOVIES, 1):
            text += f"🎞️ ***{idx}.*** __**{title}**__\n\n"
        text += f"***المجموع: {len(MOVIES)} فيلم***"
    else:
        text = "🚫 ***لا توجد أفلام متاحة حاليًا***"
    await update.message.reply_text(text, parse_mode='Markdown')


async def series_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send the list of series."""
    user_id = update.effective_user.id
    if user_id in banned_users:
        return
    if user_id in blocked_users:
        await update.message.reply_text(
            "لقد تم حظرك مؤقتًا من استخدام هذا البوت. يرجى التواصل مع الإدارة."
        )
        return
    # Check if series command is enabled
    if not command_states.get("series", True):
        await update.message.reply_text("هذا الأمر معطل حاليًا من قبل الإدارة.")
        return
    if SERIES:
        text = "📺 ***قائمة المسلسلات المتاحة***\n\n"
        for idx, title in enumerate(SERIES, 1):
            text += f"📽️ ***{idx}.*** __**{title}**__\n\n"
        text += f"***المجموع: {len(SERIES)} مسلسل***"
    else:
        text = "🚫 ***لا توجد مسلسلات متاحة حاليًا***"
    await update.message.reply_text(text, parse_mode='Markdown')


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Report whether the Captain M website is online or under maintenance."""
    user_id = update.effective_user.id
    if user_id in banned_users:
        return
    if user_id in blocked_users:
        await update.message.reply_text(
            "لقد تم حظرك مؤقتًا من استخدام هذا البوت. يرجى التواصل مع الإدارة."
        )
        return
    # Check if status command is enabled
    if not command_states.get("status", True):
        await update.message.reply_text("هذا الأمر معطل حاليًا من قبل الإدارة.")
        return
    online = fetch_website_status()
    if online:
        text = "الموقع يعمل بشكل طبيعي حاليًا."
    else:
        text = "الموقع تحت الصيانة أو غير متاح في الوقت الحالي."
    await update.message.reply_text(text)


async def invite_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Return the current invite code."""
    user_id = update.effective_user.id
    if user_id in banned_users:
        return
    if user_id in blocked_users:
        await update.message.reply_text(
            "لقد تم حظرك مؤقتًا من استخدام هذا البوت. يرجى التواصل مع الإدارة."
        )
        return
    # Check if invite command is enabled
    if not command_states.get("invite", True):
        await update.message.reply_text("هذا الأمر معطل حاليًا من قبل الإدارة.")
        return
    await update.message.reply_text(f"رمز الدعوة الحالي هو: {invite_code}")


async def admin_ban(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ban a user by their Telegram ID (admin only)."""
    user_id = update.effective_user.id
    if not user_is_admin(user_id):
        await update.message.reply_text("هذا الأمر مخصص للمسؤولين فقط.")
        return
    
    # Check if user provided the ID directly with the command
    if context.args and context.args[0].isdigit():
        target_id = int(context.args[0])
        banned_users.add(target_id)
        blocked_users.discard(target_id)
        flagged_users.discard(target_id)
        await update.message.reply_text(
            f"تم حظر المستخدم برقم {target_id} من استخدام هذا البوت."
        )
    else:
        # Ask for the user ID
        waiting_for_input[user_id] = "ban"
        await update.message.reply_text("اكتب ID المستخدم")


async def admin_block(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Temporarily block a user (admin only)."""
    user_id = update.effective_user.id
    if not user_is_admin(user_id):
        await update.message.reply_text("هذا الأمر مخصص للمسؤولين فقط.")
        return
    
    # Check if user provided the ID directly with the command
    if context.args and context.args[0].isdigit():
        target_id = int(context.args[0])
        if target_id in banned_users:
            await update.message.reply_text("هذا المستخدم محظور بالفعل.")
            return
        blocked_users.add(target_id)
        await update.message.reply_text(
            f"تم منع المستخدم برقم {target_id} مؤقتًا من استخدام هذا البوت."
        )
    else:
        # Ask for the user ID
        waiting_for_input[user_id] = "block"
        await update.message.reply_text("اكتب ID المستخدم")


async def admin_flag(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Flag a user as suspicious (admin only)."""
    user_id = update.effective_user.id
    if not user_is_admin(user_id):
        await update.message.reply_text("هذا الأمر مخصص للمسؤولين فقط.")
        return
    
    # Check if user provided the ID directly with the command
    if context.args and context.args[0].isdigit():
        target_id = int(context.args[0])
        flagged_users.add(target_id)
        await update.message.reply_text(
            f"تم وضع علامة على المستخدم برقم {target_id} كمشتبه به للمراجعة."
        )
    else:
        # Ask for the user ID
        waiting_for_input[user_id] = "flag"
        await update.message.reply_text("اكتب ID المستخدم")


async def admin_change_invite(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Allow admins to change the invite code."""
    global invite_code
    user_id = update.effective_user.id
    if not user_is_admin(user_id):
        await update.message.reply_text("هذا الأمر مخصص للمسؤولين فقط.")
        return
    
    # Check if user provided the code directly with the command
    if context.args:
        new_code = context.args[0]
        invite_code = new_code
        await update.message.reply_text(f"تم تحديث رمز الدعوة إلى: {invite_code}")
    else:
        # Ask for the new invite code
        waiting_for_input[user_id] = "change_invite"
        await update.message.reply_text("اكتب رمز الدعوة الجديد")


async def admin_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Toggle commands on/off (admin only)."""
    user_id = update.effective_user.id
    if not user_is_admin(user_id):
        await update.message.reply_text("هذا الأمر مخصص للمسؤولين فقط.")
        return
    
    if not context.args:
        # Show current status of all commands
        status_text = "حالة الأوامر الحالية:\n\n"
        for cmd, enabled in command_states.items():
            status = "مفعل" if enabled else "معطل"
            status_text += f"/{cmd}: {status}\n"
        status_text += "\nلتفعيل/تعطيل أمر: /toggle <اسم الأمر>"
        await update.message.reply_text(status_text)
        return
    
    command_name = context.args[0].lower()
    if command_name in command_states:
        command_states[command_name] = not command_states[command_name]
        status = "مفعل" if command_states[command_name] else "معطل"
        await update.message.reply_text(f"تم {status} الأمر /{command_name}")
    else:
        await update.message.reply_text("أمر غير صحيح. الأوامر المتاحة: movies, series, status, invite, help")


async def handle_admin_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle admin input when waiting for specific data."""
    user_id = update.effective_user.id
    if not user_is_admin(user_id) or user_id not in waiting_for_input:
        return
    
    command_type = waiting_for_input[user_id]
    user_input = update.message.text.strip()
    
    if command_type == "ban":
        if user_input.isdigit():
            target_id = int(user_input)
            banned_users.add(target_id)
            blocked_users.discard(target_id)
            flagged_users.discard(target_id)
            await update.message.reply_text(
                f"تم حظر المستخدم برقم {target_id} من استخدام هذا البوت."
            )
        else:
            await update.message.reply_text("رقم غير صحيح. يرجى إدخال رقم صحيح.")
    
    elif command_type == "block":
        if user_input.isdigit():
            target_id = int(user_input)
            if target_id in banned_users:
                await update.message.reply_text("هذا المستخدم محظور بالفعل.")
            else:
                blocked_users.add(target_id)
                await update.message.reply_text(
                    f"تم منع المستخدم برقم {target_id} مؤقتًا من استخدام هذا البوت."
                )
        else:
            await update.message.reply_text("رقم غير صحيح. يرجى إدخال رقم صحيح.")
    
    elif command_type == "flag":
        if user_input.isdigit():
            target_id = int(user_input)
            flagged_users.add(target_id)
            await update.message.reply_text(
                f"تم وضع علامة على المستخدم برقم {target_id} كمشتبه به للمراجعة."
            )
        else:
            await update.message.reply_text("رقم غير صحيح. يرجى إدخال رقم صحيح.")
    
    elif command_type == "change_invite":
        global invite_code
        invite_code = user_input
        save_to_database('invite_code', invite_code)  # Save to database
        await update.message.reply_text(f"تم تحديث رمز الدعوة إلى: {invite_code}")
    
    elif command_type == "add_movie_name":
        MOVIES.append(user_input.strip())
        save_to_database('movies', MOVIES)  # Save to database
        await update.message.reply_text(f"✅ تم إضافة الفيلم: {user_input.strip()}")
    
    elif command_type == "add_series_name":
        SERIES.append(user_input.strip())
        save_to_database('series', SERIES)  # Save to database
        await update.message.reply_text(f"✅ تم إضافة المسلسل: {user_input.strip()}")
    
    elif command_type == "move_position":
        if user_id not in admin_context:
            await update.message.reply_text("خطأ: لم يتم العثور على بيانات العملية")
            return
            
        try:
            new_position = int(user_input.strip()) - 1  # Convert to 0-based index
            context = admin_context[user_id]
            
            if context["action"] == "move_movie":
                if 0 <= new_position < len(MOVIES):
                    old_idx = context["item_idx"]
                    movie_name = MOVIES.pop(old_idx)
                    MOVIES.insert(new_position, movie_name)
                    await update.message.reply_text(f"✅ تم نقل الفيلم '{movie_name}' إلى الموضع {new_position + 1}")
                else:
                    await update.message.reply_text(f"موضع غير صحيح. يجب أن يكون بين 1 و {len(MOVIES)}")
            
            elif context["action"] == "move_series":
                if 0 <= new_position < len(SERIES):
                    old_idx = context["item_idx"]
                    series_name = SERIES.pop(old_idx)
                    SERIES.insert(new_position, series_name)
                    await update.message.reply_text(f"✅ تم نقل المسلسل '{series_name}' إلى الموضع {new_position + 1}")
                else:
                    await update.message.reply_text(f"موضع غير صحيح. يجب أن يكون بين 1 و {len(SERIES)}")
                    
        except ValueError:
            await update.message.reply_text("يرجى إدخال رقم صحيح")
    
    # Remove from waiting list
    del waiting_for_input[user_id]
    if user_id in admin_context:
        del admin_context[user_id]


async def admin_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Add a new movie or series (admin only)."""
    user_id = update.effective_user.id
    if not user_is_admin(user_id):
        await update.message.reply_text("هذا الأمر مخصص للمسؤولين فقط.")
        return
    
    keyboard = [
        [
            InlineKeyboardButton("🎬 فيلم", callback_data="add_movie"),
            InlineKeyboardButton("📺 مسلسل", callback_data="add_series")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("ماذا تريد أن تضيف؟", reply_markup=reply_markup)


async def admin_remove(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Remove a movie or series (admin only)."""
    user_id = update.effective_user.id
    if not user_is_admin(user_id):
        await update.message.reply_text("هذا الأمر مخصص للمسؤولين فقط.")
        return
    
    keyboard = [
        [
            InlineKeyboardButton("🎬 أفلام", callback_data="remove_movie"),
            InlineKeyboardButton("📺 مسلسلات", callback_data="remove_series")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("ماذا تريد أن تحذف؟", reply_markup=reply_markup)


async def admin_move(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Move a movie or series to different position (admin only)."""
    user_id = update.effective_user.id
    if not user_is_admin(user_id):
        await update.message.reply_text("هذا الأمر مخصص للمسؤولين فقط.")
        return
    
    keyboard = [
        [
            InlineKeyboardButton("🎬 أفلام", callback_data="move_movie"),
            InlineKeyboardButton("📺 مسلسلات", callback_data="move_series")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("ماذا تريد أن تحرك؟", reply_markup=reply_markup)


async def admin_site(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Control site status with ON/OFF buttons (admin only)."""
    user_id = update.effective_user.id
    if not user_is_admin(user_id):
        await update.message.reply_text("هذا الأمر مخصص للمسؤولين فقط.")
        return
    
    global site_status
    current_status = "تشغيل" if site_status else "إيقاف"
    
    keyboard = [
        [
            InlineKeyboardButton(f"ON {'✅' if site_status else ''}", callback_data="site_on"),
            InlineKeyboardButton(f"OFF {'❌' if not site_status else ''}", callback_data="site_off")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(f"حالة الموقع الحالية: **{current_status}**\n\nاختر الحالة الجديدة:", reply_markup=reply_markup, parse_mode='Markdown')


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle button presses from the inline keyboard."""
    global site_status
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    # Ignore interactions from banned users
    if user_id in banned_users:
        return
    if query.data == "movies":
        if not command_states.get("movies", True):
            await query.message.reply_text("هذا الأمر معطل حاليًا من قبل الإدارة.")
            return
        # Use modern format for inline callback
        if MOVIES:
            text = "🎬 ***قائمة الأفلام المتاحة***\n\n"
            for idx, title in enumerate(MOVIES, 1):
                text += f"🎞️ ***{idx}.*** __**{title}**__\n\n"
            text += f"***المجموع: {len(MOVIES)} فيلم***"
        else:
            text = "🚫 ***لا توجد أفلام متاحة حاليًا***"
        await query.message.reply_text(text, parse_mode='Markdown')
    elif query.data == "series":
        if not command_states.get("series", True):
            await query.message.reply_text("هذا الأمر معطل حاليًا من قبل الإدارة.")
            return
        if SERIES:
            text = "📺 ***قائمة المسلسلات المتاحة***\n\n"
            for idx, title in enumerate(SERIES, 1):
                text += f"📽️ ***{idx}.*** __**{title}**__\n\n"
            text += f"***المجموع: {len(SERIES)} مسلسل***"
        else:
            text = "🚫 ***لا توجد مسلسلات متاحة حاليًا***"
        await query.message.reply_text(text, parse_mode='Markdown')
    elif query.data == "status":
        if not command_states.get("status", True):
            await query.message.reply_text("هذا الأمر معطل حاليًا من قبل الإدارة.")
            return
        
        if site_status:
            # Normal behavior - check actual website
            try:
                response = requests.get("https://captainm.netlify.app", timeout=10)
                if response.status_code == 200:
                    text = "🔴 الموقع يعمل بشكل طبيعي وقابل للوصول."
                else:
                    text = "الموقع يعمل بكفاءه."
            except requests.exceptions.RequestException:
                text = "❌ الموقع تحت الصيانة أو غير متاح في الوقت الحالي."
        else:
            # Site is set to OFF - always show as down
            text = "❌ الموقع تحت الصيانة أو غير متاح في الوقت الحالي."
        
        await query.message.reply_text(text)
    
    # Handle admin operations
    elif query.data == "add_movie":
        if not user_is_admin(user_id):
            return
        waiting_for_input[user_id] = "add_movie_name"
        await query.message.reply_text("اكتب اسم الفيلم الجديد:")
    
    elif query.data == "add_series":
        if not user_is_admin(user_id):
            return
        waiting_for_input[user_id] = "add_series_name"
        await query.message.reply_text("اكتب اسم المسلسل الجديد:")
    
    elif query.data == "remove_movie":
        if not user_is_admin(user_id) or not MOVIES:
            if not MOVIES:
                await query.message.reply_text("لا توجد أفلام لحذفها")
            return
        
        # Create buttons for each movie
        keyboard = []
        for idx, movie in enumerate(MOVIES):
            keyboard.append([InlineKeyboardButton(f"{idx+1}. {movie}", callback_data=f"del_movie_{idx}")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.reply_text("اختر الفيلم الذي تريد حذفه:", reply_markup=reply_markup)
    
    elif query.data == "remove_series":
        if not user_is_admin(user_id) or not SERIES:
            if not SERIES:
                await query.message.reply_text("لا توجد مسلسلات لحذفها")
            return
        
        # Create buttons for each series
        keyboard = []
        for idx, series in enumerate(SERIES):
            keyboard.append([InlineKeyboardButton(f"{idx+1}. {series}", callback_data=f"del_series_{idx}")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.reply_text("اختر المسلسل الذي تريد حذفه:", reply_markup=reply_markup)
    
    elif query.data == "move_movie":
        if not user_is_admin(user_id) or not MOVIES:
            if not MOVIES:
                await query.message.reply_text("لا توجد أفلام لتحريكها")
            return
        
        # Create buttons for each movie
        keyboard = []
        for idx, movie in enumerate(MOVIES):
            keyboard.append([InlineKeyboardButton(f"{idx+1}. {movie}", callback_data=f"move_movie_{idx}")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.reply_text("اختر الفيلم الذي تريد تحريكه:", reply_markup=reply_markup)
    
    elif query.data == "move_series":
        if not user_is_admin(user_id) or not SERIES:
            if not SERIES:
                await query.message.reply_text("لا توجد مسلسلات لتحريكها")
            return
        
        # Create buttons for each series
        keyboard = []
        for idx, series in enumerate(SERIES):
            keyboard.append([InlineKeyboardButton(f"{idx+1}. {series}", callback_data=f"move_series_{idx}")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.reply_text("اختر المسلسل الذي تريد تحريكه:", reply_markup=reply_markup)
    
    # Handle delete operations
    elif query.data.startswith("del_movie_"):
        if not user_is_admin(user_id):
            return
        idx = int(query.data.split("_")[2])
        if 0 <= idx < len(MOVIES):
            deleted_movie = MOVIES.pop(idx)
            await query.message.reply_text(f"تم حذف الفيلم: {deleted_movie}")
    
    elif query.data.startswith("del_series_"):
        if not user_is_admin(user_id):
            return
        idx = int(query.data.split("_")[2])
        if 0 <= idx < len(SERIES):
            deleted_series = SERIES.pop(idx)
            await query.message.reply_text(f"تم حذف المسلسل: {deleted_series}")
    
    # Handle move operations
    elif query.data.startswith("move_movie_"):
        if not user_is_admin(user_id):
            return
        idx = int(query.data.split("_")[2])
        if 0 <= idx < len(MOVIES):
            admin_context[user_id] = {"action": "move_movie", "item_idx": idx, "item_name": MOVIES[idx]}
            waiting_for_input[user_id] = "move_position"
            await query.message.reply_text(f"اكتب الموضع الجديد للفيلم '{MOVIES[idx]}' (من 1 إلى {len(MOVIES)}):")
    
    elif query.data.startswith("move_series_"):
        if not user_is_admin(user_id):
            return
        idx = int(query.data.split("_")[2])
        if 0 <= idx < len(SERIES):
            admin_context[user_id] = {"action": "move_series", "item_idx": idx, "item_name": SERIES[idx]}
            waiting_for_input[user_id] = "move_position"
            await query.message.reply_text(f"اكتب الموضع الجديد للمسلسل '{SERIES[idx]}' (من 1 إلى {len(SERIES)}):")
    
    # Handle site status changes
    elif query.data == "site_on":
        if not user_is_admin(user_id):
            return
        site_status = True
        save_to_database('site_status', site_status)  # Save to database
        await query.message.reply_text("✅ تم تفعيل الموقع - سيظهر كمعتاد عند فحص حالة الموقع")
    
    elif query.data == "site_off":
        if not user_is_admin(user_id):
            return
        site_status = False
        save_to_database('site_status', site_status)  # Save to database
        await query.message.reply_text("❌ تم إيقاف الموقع - سيظهر كمعطل عند فحص حالة الموقع")


async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Respond to unknown commands politely."""
    if update.effective_user.id in banned_users:
        return
    await update.message.reply_text("عذرًا، لم أفهم هذا الأمر. استخدم /help لمعرفة الأوامر المتاحة.")


# ---------------------------------------------------------------------------
# Ticketing System Functions
# ---------------------------------------------------------------------------

async def ticket_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Allow a user to create a ticket by choosing a category."""
    user_id = update.effective_user.id
    # Respect existing ban/block lists
    if user_id in banned_users:
        return
    if user_id in blocked_users:
        await update.message.reply_text(
            "لقد تم حظرك مؤقتًا من استخدام هذا البوت. يرجى التواصل مع الإدارة."
        )
        return
    # Show category options
    keyboard = [
        [InlineKeyboardButton("💡 اقتراح", callback_data="ticket_suggestion")],
        [InlineKeyboardButton("⚠️ بلاغ", callback_data="ticket_report")],
        [InlineKeyboardButton("📩 تحدث مع المالك", callback_data="ticket_owner")],
    ]
    await update.message.reply_text(
        "اختر نوع التذكرة التي تريد إرسالها:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def handle_ticket_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Capture the user's message when they are creating a ticket."""
    user_id = update.effective_user.id
    # Only handle this message if we're expecting a ticket from the user
    if user_id in waiting_for_ticket:
        # Pop the category to avoid processing extra messages
        category = waiting_for_ticket.pop(user_id)
        message_text = update.message.text.strip()
        # Create a unique ticket ID using the current timestamp (milliseconds)
        now = datetime.now(ZoneInfo("Africa/Cairo"))
        ticket_id = str(int(now.timestamp() * 1000))
        # Build a clickable link for the user
        user_link = f"[{update.effective_user.first_name}](tg://user?id={user_id})"
        # Create the ticket record
        ticket = {
            "id": ticket_id,
            "user_id": user_id,
            "user_link": user_link,
            "category": category,
            "message": message_text,
            "timestamp": now.strftime("%Y-%m-%d %H:%M"),
            "closed": False,
        }
        tickets.append(ticket)
        # Persist tickets
        save_to_database('tickets', tickets)
        # Confirm to the user
        await update.message.reply_text(
            "✅ تم إرسال تذكرتك بنجاح! سنتواصل معك قريبًا.",
            parse_mode='Markdown'
        )
        # Forward to admins (owners).  Each admin receives a button to close the ticket.
        text = (
            "🎟️ **تذكرة جديدة**\n\n"
            f"**النوع:** {category}\n"
            f"**المرسل:** {user_link}\n"
            f"**الوقت:** {ticket['timestamp']}\n"
            f"**الرسالة:**\n{message_text}"
        )
        reply_markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔒 إغلاق التذكرة", callback_data=f"close_ticket_{ticket_id}")]
        ])
        for admin_id in ADMIN_IDS:
            try:
                await context.bot.send_message(
                    chat_id=admin_id,
                    text=text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            except Exception:
                # In case sending fails, we ignore the error
                pass
    else:
        # If this message isn't part of a ticket, fall back to existing admin handler
        await handle_admin_input(update, context)


async def admin_view_tickets(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin command: list all tickets with their status."""
    user_id = update.effective_user.id
    if not user_is_admin(user_id):
        await update.message.reply_text("هذا الأمر مخصص للمسؤولين فقط.")
        return
    if not tickets:
        await update.message.reply_text("لا توجد تذاكر حالياً.")
        return
    lines = []
    for idx, t in enumerate(tickets, 1):
        status = "✅ مغلقة" if t.get("closed") else "🕒 مفتوحة"
        lines.append(
            f"{idx}. {t['user_link']} - {t['category']} - {t['timestamp']} - {status}"
        )
    msg = "📄 **قائمة التذاكر**\n\n" + "\n".join(lines)
    keyboard = [
        [InlineKeyboardButton("🧹 حذف التذاكر المغلقة", callback_data="clear_closed_tickets")]
    ]
    await update.message.reply_text(
        msg,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )


async def admin_view_ticket_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin command: show unique users who submitted tickets."""
    user_id = update.effective_user.id
    if not user_is_admin(user_id):
        await update.message.reply_text("هذا الأمر مخصص للمسؤولين فقط.")
        return
    if not tickets:
        await update.message.reply_text("لا توجد تذاكر حالياً.")
        return
    unique_links: List[str] = []
    seen_ids = set()
    for t in tickets:
        if t['user_id'] not in seen_ids:
            seen_ids.add(t['user_id'])
            unique_links.append(t['user_link'])
    msg = "👥 **المستخدمون الذين أرسلوا تذاكر:**\n\n" + "\n".join(
        [f"{idx + 1}. {link}" for idx, link in enumerate(unique_links)]
    )
    await update.message.reply_text(msg, parse_mode='Markdown')


async def admin_pending_tickets(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin command: count how many tickets are still open."""
    user_id = update.effective_user.id
    if not user_is_admin(user_id):
        await update.message.reply_text("هذا الأمر مخصص للمسؤولين فقط.")
        return
    open_count = sum(1 for t in tickets if not t.get("closed"))
    if open_count == 0:
        msg = "✅ لا توجد تذاكر بحاجة إلى رد."
    else:
        msg = f"📬 يوجد {open_count} تذكرة بانتظار الرد."
    await update.message.reply_text(msg)


async def handle_ticket_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle inline button callbacks for ticketing:
    - Choosing ticket category
    - Closing a ticket
    - Clearing all closed tickets
    """
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id
    # User chooses the type of ticket
    if data.startswith("ticket_"):
        category = data.split("_", 1)[1]
        waiting_for_ticket[user_id] = category
        await query.message.reply_text("✉️ يرجى كتابة رسالتك الآن:")
    # Admin clicks "close ticket"
    elif data.startswith("close_ticket_"):
        ticket_id = data[len("close_ticket_"):]
        target_user_id = None
        for t in tickets:
            if t["id"] == ticket_id and not t.get("closed"):
                t["closed"] = True
                target_user_id = t["user_id"]
                break
        save_to_database('tickets', tickets)
        # Edit the original admin message or send a new one confirming closure
        try:
            await query.edit_message_text("🔒 تم إغلاق التذكرة.", parse_mode='Markdown')
        except Exception:
            await query.message.reply_text("🔒 تم إغلاق التذكرة.", parse_mode='Markdown')
        # Notify the original user (if available)
        if target_user_id:
            try:
                await context.bot.send_message(
                    chat_id=target_user_id,
                    text="✅ تم إغلاق تذكرتك من قبل المسؤول.",
                    parse_mode='Markdown'
                )
            except Exception:
                pass
    # Admin clicks "clear closed tickets"
    elif data == "clear_closed_tickets":
        # Filter out closed tickets
        tickets[:] = [t for t in tickets if not t.get("closed")]
        save_to_database('tickets', tickets)
        await query.message.reply_text("🧹 تم حذف التذاكر المغلقة.")


# -----------------------------------------------------------------------------
# Bot initialization
# -----------------------------------------------------------------------------

def main() -> None:
    """Start the bot and register handlers."""
    # Configure logging to standard output for debugging
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=logging.INFO,
    )

    # Initialize database and load saved data
    init_database()
    load_all_data()

    if not TOKEN or TOKEN == "YOUR_BOT_TOKEN":
        raise RuntimeError(
            "Please set your Telegram bot token in the TOKEN variable or as the BOT_TOKEN environment variable."
        )

    # Create the application instance
    application = Application.builder().token(TOKEN).build()

    # Register command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("movies", movies_command))
    application.add_handler(CommandHandler("series", series_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("invite", invite_command))

    # Admin commands
    application.add_handler(CommandHandler("ban", admin_ban))
    application.add_handler(CommandHandler("block", admin_block))
    application.add_handler(CommandHandler("flag", admin_flag))
    application.add_handler(CommandHandler("change_invite", admin_change_invite))

    # Ticketing system commands
    application.add_handler(CommandHandler("ticket", ticket_command))
    application.add_handler(CommandHandler("tickets", admin_view_tickets))
    application.add_handler(CommandHandler("ticket_users", admin_view_ticket_users))
    application.add_handler(CommandHandler("pending_tickets", admin_pending_tickets))

    # Callback query handlers for inline buttons
    application.add_handler(CallbackQueryHandler(handle_ticket_callback, pattern="^(ticket_|close_ticket_|clear_closed_tickets)"))
    application.add_handler(CallbackQueryHandler(handle_callback))

    # Admin management commands
    application.add_handler(CommandHandler("toggle", admin_toggle))
    application.add_handler(CommandHandler("add", admin_add))
    application.add_handler(CommandHandler("remove", admin_remove))
    application.add_handler(CommandHandler("move", admin_move))
    application.add_handler(CommandHandler("site", admin_site))

    # Handle ticket input (higher priority than admin input)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_ticket_input), group=1)

    # Unknown command handler should be last
    application.add_handler(MessageHandler(filters.COMMAND, unknown_command))

    # Start the bot
    application.run_polling()


if __name__ == "__main__":
    main()