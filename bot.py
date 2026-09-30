import logging
import sqlite3
import random
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# ============================================================
# CONFIG
# ============================================================
BOT_TOKEN = "8853239467:AAEGTvd8O8H7wHhyGML6Q4VQbZYqUPMJ-oY"   # <-- Replace this
DB_PATH = "planner.db"
DEFAULT_TZ = "Africa/Lagos"               # Change if you want a different default

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ============================================================
# DAILY TIPS (No external API — all built-in)
# ============================================================
MORNING_TIPS = [
    "🌅 *Start with your #1 task.* Do the hardest thing first — everything else feels easier.",
    "☀️ *3-task rule:* Pick only 3 must-do tasks today. Ignore the rest until these are done.",
    "🧠 *Brain warm-up:* Spend 5 minutes writing what you want to achieve before checking messages.",
    "💧 *Hydrate first.* A glass of water before coffee boosts focus and energy.",
    "🎯 *Set one clear win* for today. What single thing, if done, makes today a success?",
    "📵 *Phone-free first hour.* Protect your morning focus — it sets the tone for the day.",
    "🚶 *Move your body* for 5 minutes. Stretch, walk, or dance — it wakes up your brain.",
    "📝 *Plan tomorrow tonight.* 5 minutes of planning saves 1 hour of chaos.",
    "🍎 *Eat a real breakfast.* Fuel beats caffeine for steady focus.",
    "🙏 *Name 3 things you're grateful for.* It shifts your mindset before work begins.",
]

MIDDAY_TIPS = [
    "🍽️ *Take a real lunch break.* Step away from the screen — your brain needs the reset.",
    "🚶 *5-minute walk* after eating boosts energy and digestion.",
    "💧 *Drink water now.* Most afternoon slumps are mild dehydration.",
    "✅ *Check your progress.* How many of your 3 tasks are done? Adjust if needed.",
    "🧘 *60-second breathing break.* Inhale 4s, hold 4s, exhale 6s. Repeat.",
    "📵 *Mute notifications* for 25 minutes and do one focused sprint.",
    "🍵 *Avoid heavy sugar* — it causes an afternoon crash.",
    "👀 *20-20-20 rule:* Every 20 min, look 20 feet away for 20 seconds.",
    "📋 *Re-prioritize.* Anything urgent that appeared? Slot it, don't panic.",
    "💬 *Send one kind message* to someone. It lifts your mood and theirs.",
]

EVENING_TIPS = [
    "🌙 *Close the day.* Write down 3 things you accomplished — even small wins count.",
    "📝 *Plan tomorrow's top 3* before bed. Future-you will thank present-you.",
    "📵 *Screens off 30 minutes* before sleep. Better rest = better tomorrow.",
    "🙏 *Gratitude check:* What went well today? What will you do differently?",
    "🛁 *Wind down ritual:* tea, shower, or reading — signal your brain it's rest time.",
    "🧹 *2-minute tidy.* Clear your desk so tomorrow starts clean.",
    "💤 *Aim for 7–8 hours.* Sleep is the ultimate productivity hack.",
    "📖 *Read 5 pages* of a book instead of scrolling.",
    "🎯 *Review your goals.* Are you moving toward them or just staying busy?",
    "❤️ *Forgive today's mistakes.* Tomorrow is a fresh start.",
]

WEEKLY_TIPS = [
    "📊 *Weekly review:* What worked? What didn't? What will you change next week?",
    "🎯 *Set 1 big goal* for the week — everything else supports it.",
    "🧹 *Digital cleanup:* Unsubscribe, delete, organize. A clear inbox = a clear mind.",
    "📅 *Block time* for deep work this week. Protect it like a meeting.",
    "🌱 *Learn one new thing* this week. Small growth compounds.",
]

def get_tip(period: str) -> str:
    if period == "morning":
        return random.choice(MORNING_TIPS)
    if period == "midday":
        return random.choice(MIDDAY_TIPS)
    if period == "evening":
        return random.choice(EVENING_TIPS)
    return random.choice(WEEKLY_TIPS)

# ============================================================
# DATABASE
# ============================================================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            timezone TEXT DEFAULT 'Africa/Lagos',
            morning_time TEXT DEFAULT '08:00',
            midday_time TEXT DEFAULT '13:00',
            evening_time TEXT DEFAULT '21:00',
            joined_at TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            title TEXT,
            status TEXT DEFAULT 'pending',
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()

def db():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def register_user(user):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT user_id FROM users WHERE user_id=?", (user.id,))
    if not cur.fetchone():
        cur.execute(
            "INSERT INTO users (user_id, username, first_name, joined_at) VALUES (?,?,?,?)",
            (user.id, user.username or "", user.first_name or "", datetime.utcnow().isoformat()),
        )
        conn.commit()
    conn.close()

def get_user(user_id):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT timezone, morning_time, midday_time, evening_time FROM users WHERE user_id=?",
                (user_id,))
    row = cur.fetchone()
    conn.close()
    return row

def update_user_time(user_id, field, value):
    if field not in ("timezone", "morning_time", "midday_time", "evening_time"):
        return
    conn = db()
    cur = conn.cursor()
    cur.execute(f"UPDATE users SET {field}=? WHERE user_id=?", (value, user_id))
    conn.commit()
    conn.close()

def add_task(user_id, title):
    conn = db()
    cur = conn.cursor()
    cur.execute("INSERT INTO tasks (user_id, title, created_at) VALUES (?,?,?)",
                (user_id, title, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()

def get_tasks(user_id):
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT id, title, status FROM tasks WHERE user_id=? ORDER BY id", (user_id,))
    rows = cur.fetchall()
    conn.close()
    return rows

def mark_done(user_id, task_id):
    conn = db()
    cur = conn.cursor()
    cur.execute("UPDATE tasks SET status='done' WHERE id=? AND user_id=?", (task_id, user_id))
    conn.commit()
    conn.close()

def delete_task(user_id, task_id):
    conn = db()
    cur = conn.cursor()
    cur.execute("DELETE FROM tasks WHERE id=? AND user_id=?", (task_id, user_id))
    conn.commit()
    conn.close()

def clear_done(user_id):
    conn = db()
    cur = conn.cursor()
    cur.execute("DELETE FROM tasks WHERE user_id=? AND status='done'", (user_id,))
    conn.commit()
    conn.close()

def all_users():
    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT user_id, timezone, morning_time, midday_time, evening_time FROM users")
    rows = cur.fetchall()
    conn.close()
    return rows

# ============================================================
# COMMANDS
# ============================================================
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    register_user(user)

    welcome = (
        f"👋 *Welcome, {user.first_name}!*\n\n"
        "I'm *PlanDayBot* — your personal daily planner.\n\n"
        "Here's what I can do:\n"
        "• 📝 Add and track your daily tasks\n"
        "• ⏰ Send you motivational tips 3x a day\n"
        "• 📊 Show your daily progress\n"
        "• 🌅 Give you a morning plan and evening recap\n\n"
        "*Commands:*\n"
        "/add <task> — Add a task\n"
        "/today — See today's tasks\n"
        "/done <id> — Mark task complete\n"
        "/delete <id> — Remove a task\n"
        "/clear — Remove all completed tasks\n"
        "/tip — Get a random tip now\n"
        "/settings — Set your timezone & tip times\n"
        "/help — Show this menu\n\n"
        "Let's make today productive! 🚀"
    )
    await update.message.reply_text(welcome, parse_mode=ParseMode.MARKDOWN)


async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await start(update, ctx)


async def add_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text("Usage: `/add Finish report`", parse_mode=ParseMode.MARKDOWN)
        return
    title = " ".join(ctx.args)
    add_task(update.effective_user.id, title)
    await update.message.reply_text(f"✅ Added: *{title}*", parse_mode=ParseMode.MARKDOWN)


async def today_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    rows = get_tasks(update.effective_user.id)
    if not rows:
        await update.message.reply_text(
            "📭 You have no tasks yet.\nUse `/add <task>` to get started.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    msg = "📅 *Your Tasks Today*\n\n"
    for tid, title, status in rows:
        icon = "✅" if status == "done" else "⬜"
        msg += f"`{tid}`. {icon} {title}\n"

    done = sum(1 for r in rows if r[2] == "done")
    msg += f"\n📊 Progress: *{done}/{len(rows)}* completed"
    await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)


async def done_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args or not ctx.args[0].isdigit():
        await update.message.reply_text("Usage: `/done 2`", parse_mode=ParseMode.MARKDOWN)
        return
    mark_done(update.effective_user.id, int(ctx.args[0]))
    await update.message.reply_text("🎉 Marked as done! Great work.")


async def delete_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args or not ctx.args[0].isdigit():
        await update.message.reply_text("Usage: `/delete 2`", parse_mode=ParseMode.MARKDOWN)
        return
    delete_task(update.effective_user.id, int(ctx.args[0]))
    await update.message.reply_text("🗑️ Task deleted.")


async def clear_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    clear_done(update.effective_user.id)
    await update.message.reply_text("🧹 All completed tasks removed.")


async def tip_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    hour = datetime.now().hour
    if hour < 12:
        period = "morning"
    elif hour < 18:
        period = "midday"
    else:
        period = "evening"
    await update.message.reply_text(get_tip(period), parse_mode=ParseMode.MARKDOWN)


async def settings_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🌍 Timezone", callback_data="set_tz")],
        [InlineKeyboardButton("🌅 Morning tip time", callback_data="set_morning")],
        [InlineKeyboardButton("🍽️ Midday tip time", callback_data="set_midday")],
        [InlineKeyboardButton("🌙 Evening tip time", callback_data="set_evening")],
    ]
    await update.message.reply_text(
        "⚙️ *Settings*\n\nChoose what to update:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode=ParseMode.MARKDOWN,
    )


async def settings_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    hints = {
        "set_tz": "Send your timezone like:\n`Africa/Lagos`\n`Europe/London`\n`America/New_York`",
        "set_morning": "Send morning tip time (24h) like:\n`07:30`",
        "set_midday": "Send midday tip time (24h) like:\n`13:00`",
        "set_evening": "Send evening tip time (24h) like:\n`21:00`",
    }
    ctx.user_data["awaiting"] = data
    await query.message.reply_text(hints[data], parse_mode=ParseMode.MARKDOWN)


async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    awaiting = ctx.user_data.get("awaiting")
    if not awaiting:
        return
    text = update.message.text.strip()
    user_id = update.effective_user.id

    if awaiting == "set_tz":
        try:
            ZoneInfo(text)
        except Exception:
            await update.message.reply_text("❌ Invalid timezone. Try `Africa/Lagos`.", parse_mode=ParseMode.MARKDOWN)
            return
        update_user_time(user_id, "timezone", text)
        await update.message.reply_text(f"✅ Timezone set to *{text}*", parse_mode=ParseMode.MARKDOWN)

    elif awaiting in ("set_morning", "set_midday", "set_evening"):
        try:
            datetime.strptime(text, "%H:%M")
        except ValueError:
            await update.message.reply_text("❌ Use 24-hour format like `07:30`.", parse_mode=ParseMode.MARKDOWN)
            return
        field = {"set_morning": "morning_time", "set_midday": "midday_time", "set_evening": "evening_time"}[awaiting]
        update_user_time(user_id, field, text)
        await update.message.reply_text(f"✅ Updated to *{text}*", parse_mode=ParseMode.MARKDOWN)

    ctx.user_data["awaiting"] = None
    # Reschedule jobs
    schedule_user_jobs(ctx.application, user_id)


# ============================================================
# DAILY MESSAGE SENDER
# ============================================================
async def send_daily(app: Application, user_id: int, period: str):
    try:
        if period == "morning":
            rows = get_tasks(user_id)
            pending = [t for t in rows if t[2] == "pending"]
            header = "🌅 *Good morning!*\n\nHere's your day ahead:\n"
            if pending:
                for tid, title, _ in pending:
                    header += f"⬜ {title}\n"
            else:
                header += "_No tasks yet. Add some with /add!_\n"
            header += "\n"
            header += get_tip("morning")
            await app.bot.send_message(user_id, header, parse_mode=ParseMode.MARKDOWN)

        elif period == "midday":
            rows = get_tasks(user_id)
            done = sum(1 for r in rows if r[2] == "done")
            total = len(rows)
            msg = f"🍽️ *Midday Check-in*\n\nProgress: *{done}/{total}* tasks done.\n\n"
            msg += get_tip("midday")
            await app.bot.send_message(user_id, msg, parse_mode=ParseMode.MARKDOWN)

        elif period == "evening":
            rows = get_tasks(user_id)
            done = sum(1 for r in rows if r[2] == "done")
            total = len(rows)
            msg = f"🌙 *Evening Recap*\n\n✅ Done: *{done}*\n⬜ Pending: *{total - done}*\n\n"
            msg += get_tip("evening")
            await app.bot.send_message(user_id, msg, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.warning(f"Failed to send {period} to {user_id}: {e}")


def schedule_user_jobs(app: Application, user_id: int):
    data = get_user(user_id)
    if not data:
        return
    tz_name, m, mid, e = data
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo(DEFAULT_TZ)

    scheduler: AsyncIOScheduler = app.bot_data["scheduler"]

    # Remove existing jobs for this user
    for period in ("morning", "midday", "evening"):
        jid = f"{user_id}_{period}"
        if scheduler.get_job(jid):
            scheduler.remove_job(jid)

    def make_time(hhmm):
        h, mnt = map(int, hhmm.split(":"))
        return dtime(hour=h, minute=mnt, tzinfo=tz)

    scheduler.add_job(
        send_daily, "cron", hour=make_time(m).hour, minute=make_time(m).minute,
        args=[app, user_id, "morning"], id=f"{user_id}_morning", replace_existing=True,
    )
    scheduler.add_job(
        send_daily, "cron", hour=make_time(mid).hour, minute=make_time(mid).minute,
        args=[app, user_id, "midday"], id=f"{user_id}_midday", replace_existing=True,
    )
    scheduler.add_job(
        send_daily, "cron", hour=make_time(e).hour, minute=make_time(e).minute,
        args=[app, user_id, "evening"], id=f"{user_id}_evening", replace_existing=True,
    )


async def post_init(app: Application):
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.start()
    app.bot_data["scheduler"] = scheduler
    for (uid, *_rest) in all_users():
        schedule_user_jobs(app, uid)
    logger.info("Scheduler started and jobs loaded.")


# ============================================================
# MAIN
# ============================================================
def main():
    init_db()

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("add", add_cmd))
    app.add_handler(CommandHandler("today", today_cmd))
    app.add_handler(CommandHandler("done", done_cmd))
    app.add_handler(CommandHandler("delete", delete_cmd))
    app.add_handler(CommandHandler("clear", clear_cmd))
    app.add_handler(CommandHandler("tip", tip_cmd))
    app.add_handler(CommandHandler("settings", settings_cmd))
    app.add_handler(CallbackQueryHandler(settings_callback, pattern="^set_"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    logger.info("Bot is running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
