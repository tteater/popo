# wisherbot_mvp.py
import logging
from datetime import datetime, timedelta, date
import sqlite3
import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# =================== CONFIG ===================
BOT_TOKEN = "8438325284:AAEoWJ1vFwzbTavRu-94EyiZwixo2nVkebs"
DB_FILE = "wisherbot.db"
scheduler = AsyncIOScheduler()
# ==============================================

# Logging
logging.basicConfig(level=logging.INFO)

# --------------- Database Setup ---------------
conn = sqlite3.connect(DB_FILE, check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS birthdays (
    user_id INTEGER,
    name TEXT,
    dob TEXT,
    timezone TEXT,
    reminder_type TEXT,
    reminder_days INTEGER
)
""")
conn.commit()

# --------------- Helper Functions ---------------
def calculate_age(dob_str):
    try:
        dob = datetime.strptime(dob_str, "%Y-%m-%d").date()
        today = date.today()
        age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        return age
    except:
        return None

def days_until(dob_str):
    dob = datetime.strptime(dob_str, "%Y-%m-%d").date()
    today = date.today()
    next_bday = dob.replace(year=today.year)
    if next_bday < today:
        next_bday = next_bday.replace(year=today.year + 1)
    delta = (next_bday - today).days
    return delta

def days_since(dob_str):
    dob = datetime.strptime(dob_str, "%Y-%m-%d").date()
    today = date.today()
    last_bday = dob.replace(year=today.year)
    if last_bday > today:
        last_bday = last_bday.replace(year=today.year - 1)
    delta = (today - last_bday).days
    return delta

# --------------- Scheduler Job ---------------
async def send_reminder(context: ContextTypes.DEFAULT_TYPE):
    cursor.execute("SELECT * FROM birthdays")
    rows = cursor.fetchall()
    for row in rows:
        user_id, name, dob, tz_str, reminder_type, reminder_days = row
        user_tz = pytz.timezone(tz_str)
        today = datetime.now(user_tz).date()
        next_bday = datetime.strptime(dob, "%Y-%m-%d").date().replace(year=today.year)
        if next_bday < today:
            next_bday = next_bday.replace(year=today.year + 1)
        send = False
        if reminder_type == "daily":
            send = True
        elif reminder_type == "before" and reminder_days is not None:
            if (next_bday - today).days == reminder_days:
                send = True
        if send:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"🎂 Reminder: {name}'s birthday is in {(next_bday - today).days} day(s)! 🎉"
            )

# --------------- Telegram Handlers ---------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("➕ Add Birthday", callback_data="add_birthday")],
        [InlineKeyboardButton("📅 My Birthdays", callback_data="list_birthdays")]
    ]
    await update.message.reply_text(
        "🎉 Welcome to WisherBot!\nI help you remember birthdays with inline reminders.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# Step storage
user_steps = {}

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text.strip()
    step = user_steps.get(user_id, {}).get("step")
    if step == "name":
        user_steps[user_id]["name"] = text
        keyboard = [
            [InlineKeyboardButton("✅ Confirm", callback_data="confirm_name")],
            [InlineKeyboardButton("✏️ Edit Name", callback_data="edit_name")]
        ]
        await update.message.reply_text(f"Confirm name: *{text}*", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    elif step == "dob":
        try:
            datetime.strptime(text, "%Y-%m-%d")
            user_steps[user_id]["dob"] = text
            keyboard = [
                [InlineKeyboardButton("✅ Confirm Date", callback_data="confirm_date")],
                [InlineKeyboardButton("✏️ Edit Date", callback_data="edit_date")]
            ]
            await update.message.reply_text(f"Confirm DOB: *{text}*", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        except:
            await update.message.reply_text("❌ Invalid format. Please type date as YYYY-MM-DD")

# Callback handler
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    # Start adding birthday
    if data == "add_birthday":
        user_steps[user_id] = {"step": "name"}
        await query.message.reply_text("Enter the person's name:")

    # Confirm name
    elif data == "confirm_name":
        user_steps[user_id]["step"] = "dob"
        await query.message.reply_text("Enter birthday (YYYY-MM-DD):")

    # Confirm date
    elif data == "confirm_date":
        # Ask timezone
        user_steps[user_id]["step"] = "timezone"
        await query.message.reply_text("Enter timezone (e.g., Asia/Kolkata):")

    elif data == "list_birthdays":
        cursor.execute("SELECT name, dob, timezone FROM birthdays WHERE user_id=?", (user_id,))
        rows = cursor.fetchall()
        if not rows:
            await query.message.reply_text("No birthdays added yet.")
            return
        msg = "📅 Your Birthdays:\n"
        for row in rows:
            name, dob, tz = row
            age = calculate_age(dob)
            delta = days_until(dob)
            msg += f"{name} - {dob} ({age} years old) - in {delta} days\n"
        await query.message.reply_text(msg)

# --------------- Main Application ---------------
if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Handlers
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.COMMAND, start))  # For /start

    # Scheduler
    scheduler.add_job(send_reminder, "interval", minutes=60, args=[app.bot])
    scheduler.start()

    print("Bot started...")
    app.run_polling()
