"""Remindy — Telegram reminder bot. Entry point: `python bot.py`."""
import logging
import re
import threading
from datetime import datetime
from html import escape

import pytz
import requests
import telebot
from bs4 import BeautifulSoup
from telebot import types

from config import BOT_TOKEN, DEFAULT_TIMEZONE, WEATHER_API
from database import Database
from nlp_parser import parse_reminder, parse_time_only
from reminders import make_reminder, merge_sort_reminders, shorten
from scheduler import start_scheduler, to_utc

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")
db = Database()

# Dialog state storage: {user_id: {"step": ..., ...}}
user_state: dict[int, dict] = {}

TIMEZONES = [
    ("🇬🇧 London",      "Europe/London"),
    ("🇩🇪 Berlin",      "Europe/Berlin"),
    ("🇺🇸 New York",    "America/New_York"),
    ("🇷🇺 Moscow",      "Europe/Moscow"),
    ("🇰🇿 Almaty",      "Asia/Almaty"),
    ("🇺🇦 Kyiv",        "Europe/Kyiv"),
    ("🇧🇾 Minsk",       "Europe/Minsk"),
    ("🇷🇺 Novosibirsk", "Asia/Novosibirsk"),
    ("🇷🇺 Vladivostok", "Asia/Vladivostok"),
]

CURRENCIES = {"USD": "🇺🇸", "EUR": "🇪🇺", "RUB": "🇷🇺", "CNY": "🇨🇳"}

BTN_LIST, BTN_FIND, BTN_WEATHER = "📋 List", "🔍 Find", "🌤 Weather"
BTN_RATES, BTN_TIMEZONE, BTN_HELP = "💱 Rates", "🌍 Timezone", "ℹ️ Help"

TIME_HINT = "<i>in 2 hours, tomorrow at 10:00, friday at 18:00</i>"


# ─── Helpers ──────────────────────────────────────────────────────────────────

def display_name(user) -> str:
    return user.username or user.first_name


def log_query(user, text: str):
    """Stores every user request so it shows up in the Django admin."""
    try:
        db.save_user_query(user.id, display_name(user), text)
    except Exception as e:
        logger.warning("Could not save user query (did you run `manage.py migrate`?): %s", e)


def local_time(dt_iso: str, tz_name: str) -> datetime:
    return to_utc(dt_iso).astimezone(pytz.timezone(tz_name))


def save_and_confirm(message, text: str, dt: datetime, tz_name: str):
    """Saves the reminder (in UTC) and sends a confirmation to the user."""
    dt_utc = dt.astimezone(pytz.utc).replace(microsecond=0)
    reminder_id = db.add_reminder(message.from_user.id, text, dt_utc.isoformat())
    logger.info("Created %s", make_reminder(text, dt_utc.isoformat()))

    formatted = dt.astimezone(pytz.timezone(tz_name)).strftime("%B %d, %Y at %H:%M")
    bot.send_message(
        message.chat.id,
        f"✅ <b>Reminder created!</b>\n\n"
        f"📝 {escape(text)}\n"
        f"🗓 {formatted} ({tz_name})\n"
        f"🆔 ID: <code>{reminder_id}</code>",
    )


def render_list(reminders: list[dict], tz_name: str) -> str:
    lines = [f"📋 <b>Your Reminders</b> ({len(reminders)}):\n"]
    for r in reminders:
        dt = local_time(r["datetime"], tz_name)
        lines.append(
            f"🔔 <b>{escape(shorten(r['text'], 40))}</b>\n"
            f"   🗓 {dt.strftime('%d.%m.%Y %H:%M')}\n"
            f"   🆔 <code>{r['id']}</code>\n"
        )
    return "\n".join(lines)


# ─── Keyboards ────────────────────────────────────────────────────────────────

def main_menu_keyboard():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(*(types.KeyboardButton(b) for b in
             (BTN_LIST, BTN_FIND, BTN_WEATHER, BTN_RATES, BTN_TIMEZONE, BTN_HELP)))
    return kb


def delete_keyboard(reminders):
    """Inline keyboard to delete a single reminder or all of them."""
    kb = types.InlineKeyboardMarkup()
    for r in reminders:
        kb.add(types.InlineKeyboardButton(f"❌ #{r['id']} {shorten(r['text'], 35)}",
                                          callback_data=f"del_{r['id']}"))
    if len(reminders) > 1:
        kb.add(types.InlineKeyboardButton("🗑️ Clear All Reminders", callback_data="clear_all_reminders"))
    return kb


def timezone_keyboard():
    kb = types.InlineKeyboardMarkup(row_width=1)
    for label, tz in TIMEZONES:
        kb.add(types.InlineKeyboardButton(label, callback_data=f"tz_{tz}"))
    return kb


# ─── Screens ──────────────────────────────────────────────────────────────────

def show_start(message):
    user = message.from_user
    db.add_user(user.id, user.first_name)
    tz = db.get_timezone(user.id)
    bot.send_message(
        message.chat.id,
        f"👋 Hello, <b>{escape(user.first_name)}</b>!\n\n"
        "Just type what and when you want to be reminded of, and I'll handle it:\n\n"
        "• <i>stream in 2 hours</i>\n"
        "• <i>meeting tomorrow at 15:00</i>\n"
        "• <i>call mom on Friday at 18:30</i>\n\n"
        "Use the menu buttons below to manage your reminders and tools.\n\n"
        f"🕐 Your current timezone: <b>{tz}</b>",
        reply_markup=main_menu_keyboard(),
    )


def show_help(message):
    bot.send_message(
        message.chat.id,
        "📖 <b>How to create a reminder</b>\n\n"
        "Type your reminder in plain English:\n\n"
        "⏱ <b>Relative time:</b>\n"
        "  • <code>call in 30 minutes</code>\n"
        "  • <code>coffee in an hour</code>\n\n"
        "📅 <b>Date and time:</b>\n"
        "  • <code>workout tomorrow at 9:00</code>\n"
        "  • <code>meeting friday at 6pm</code>\n"
        "  • <code>dentist 25.12.2026 at 10:30</code>\n\n"
        "💡 Add <i>urgent</i> or <i>important</i> to get a highlighted notification.\n"
        "If the time is unclear, I will ask you to clarify.\n\n"
        "<b>Commands:</b> /list, /find, /weather, /rates, /timezone, /cancel",
    )


def show_list(message):
    user_id = message.from_user.id
    reminders = merge_sort_reminders(db.get_reminders(user_id))
    if not reminders:
        bot.send_message(message.chat.id, "📭 You have no active reminders.")
        return
    bot.send_message(message.chat.id, render_list(reminders, db.get_timezone(user_id)),
                     reply_markup=delete_keyboard(reminders))


def show_timezone(message):
    bot.send_message(message.chat.id, "🌍 Select your timezone:", reply_markup=timezone_keyboard())


def initiate_find(message):
    bot.send_message(
        message.chat.id,
        "🔍 Type <code>/find &lt;keyword or regex&gt;</code> to search.\n\n"
        "Examples:\n"
        "• <code>/find meeting</code> — everything containing 'meeting'\n"
        "• <code>/find \\d{2}:\\d{2}</code> — reminders with a time like 12:30",
    )


def initiate_weather(message):
    bot.send_message(
        message.chat.id,
        "🌤 Type <code>/weather &lt;city&gt;</code> to check the weather.\n"
        "Example: <code>/weather London</code> or <code>/weather Almaty</code>",
    )


# ─── Command handlers ─────────────────────────────────────────────────────────

@bot.message_handler(commands=["start"])
def cmd_start(message):
    log_query(message.from_user, "/start")
    show_start(message)


@bot.message_handler(commands=["help"])
def cmd_help(message):
    log_query(message.from_user, "/help")
    show_help(message)


@bot.message_handler(commands=["list"])
def cmd_list(message):
    log_query(message.from_user, "/list")
    show_list(message)


@bot.message_handler(commands=["timezone"])
def cmd_timezone(message):
    log_query(message.from_user, "/timezone")
    show_timezone(message)


@bot.message_handler(commands=["cancel"])
def cmd_cancel(message):
    user_state.pop(message.from_user.id, None)
    bot.send_message(message.chat.id, "❌ Action canceled.", reply_markup=main_menu_keyboard())


@bot.message_handler(commands=["find"])
def cmd_find(message):
    user_id = message.from_user.id
    log_query(message.from_user, message.text)

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        initiate_find(message)
        return

    query = parts[1].strip()
    try:
        pattern = re.compile(query, re.IGNORECASE)
    except re.error:
        bot.send_message(message.chat.id, "❌ Invalid regular expression.")
        return

    tz_name = db.get_timezone(user_id)
    found = []
    for r in merge_sort_reminders(db.get_reminders(user_id)):
        dt_str = local_time(r["datetime"], tz_name).strftime("%d.%m.%Y %H:%M")
        searchable = f"{r['text']} {dt_str}"
        matches = sum(1 for _ in pattern.finditer(searchable))
        if matches:
            found.append((r, dt_str, matches))

    if not found:
        bot.send_message(message.chat.id, f"🔍 No reminders found for <code>{escape(query)}</code>.")
        return

    count = len(found)
    lines = [f"🔍 Found <b>{count}</b> reminder{'s' if count > 1 else ''} for <code>{escape(query)}</code>:"]
    for r, dt_str, matches in found:
        lines.append(
            f"🔔 <b>{escape(shorten(r['text'], 50))}</b>\n"
            f"   🗓 {dt_str} | 🆔 <code>{r['id']}</code>\n"
            f"   🎯 Matches: {matches}"
        )
    bot.send_message(message.chat.id, "\n\n".join(lines),
                     reply_markup=delete_keyboard([r for r, _, _ in found]))


@bot.message_handler(commands=["weather"])
def cmd_weather(message):
    log_query(message.from_user, message.text)

    parts = message.text.split(maxsplit=1)
    city = parts[1].strip() if len(parts) > 1 else "Almaty"

    try:
        response = requests.get(
            "https://api.openweathermap.org/data/2.5/weather",
            params={"q": city, "appid": WEATHER_API, "units": "metric", "lang": "en"},
            timeout=10,
        )
        if response.status_code == 401:
            bot.reply_to(message, "🔑 Invalid OpenWeather API key (error 401).")
            return
        if response.status_code == 404:
            bot.reply_to(message, f"🌍 City <b>{escape(city)}</b> not found.")
            return
        response.raise_for_status()

        data = response.json()
        temp = data["main"]["temp"]
        feels_like = data["main"]["feels_like"]
        comfort = "😌 Comfortable" if abs(temp - feels_like) < 3 else "🧥 Feels different"

        bot.reply_to(
            message,
            f"🌤 <b>Weather in {escape(data.get('name', city))}, {data['sys']['country']}</b>\n\n"
            f"🌡 Temperature: <b>{temp:.1f}°C</b> (feels like {feels_like:.1f}°C)\n"
            f"🌥 {escape(data['weather'][0]['description'].capitalize())}\n"
            f"💧 Humidity: {data['main']['humidity']}%\n"
            f"💨 Wind: {data['wind']['speed']} m/s\n"
            f"☁️ Cloudiness: {data['clouds']['all']}%\n\n"
            f"{comfort}",
        )
    except requests.exceptions.ConnectionError:
        bot.reply_to(message, "❌ Connection to OpenWeather failed.")
    except requests.exceptions.Timeout:
        bot.reply_to(message, "⏱ Weather server timed out.")
    except Exception:
        logger.exception("Weather request failed")
        bot.reply_to(message, "❌ Could not get the weather. Please try again later.")


def fetch_nbk_rates(date_str: str) -> dict[str, float]:
    """Fetches KZT exchange rates from the National Bank of Kazakhstan RSS feed."""
    response = requests.get(f"https://nationalbank.kz/rss/get_rates.cfm?fdate={date_str}", timeout=15)
    response.raise_for_status()
    return parse_nbk_rates(response.content)


def parse_nbk_rates(xml: bytes | str) -> dict[str, float]:
    """Parses the NBK RSS feed into {currency: rate in KZT per 1 unit}."""
    rates = {}
    for item in BeautifulSoup(xml, "xml").find_all("item"):
        title, desc, quant = item.find("title"), item.find("description"), item.find("quant")
        if not (title and desc):
            continue
        code = title.get_text(strip=True)
        if code in CURRENCIES:
            try:
                qty = int(quant.get_text(strip=True)) if quant else 1
                rates[code] = float(desc.get_text(strip=True)) / qty
            except (ValueError, ZeroDivisionError):
                continue
    return rates


@bot.message_handler(commands=["rates"])
def cmd_rates(message):
    log_query(message.from_user, "/rates")
    today = datetime.now(pytz.timezone("Asia/Almaty")).strftime("%d.%m.%Y")

    try:
        rates = fetch_nbk_rates(today)
    except requests.exceptions.ConnectionError:
        bot.send_message(message.chat.id, "❌ Connection to nationalbank.kz failed.")
        return
    except requests.exceptions.Timeout:
        bot.send_message(message.chat.id, "⏱ National Bank server timed out.")
        return
    except Exception:
        logger.exception("Rates request failed")
        bot.send_message(message.chat.id, "❌ Could not get exchange rates. Please try again later.")
        return

    if not rates:
        bot.send_message(message.chat.id, "⚠️ National Bank returned no data. Please try again later.")
        return

    lines = [f"💱 <b>NBK exchange rates for {today}</b>\n"]
    lines += [f"{flag} <b>{code}</b> → <code>{rates[code]:.2f}</code> ₸"
              for code, flag in CURRENCIES.items() if code in rates]
    bot.send_message(message.chat.id, "\n".join(lines))


# ─── Inline callbacks ─────────────────────────────────────────────────────────

@bot.callback_query_handler(func=lambda call: call.data.startswith("del_"))
def cb_delete(call):
    user_id = call.from_user.id
    if not db.delete_reminder(int(call.data[4:]), user_id):
        bot.answer_callback_query(call.id, text="❌ Reminder not found.", show_alert=True)
        return

    bot.answer_callback_query(call.id, text="Deleted successfully!")
    reminders = merge_sort_reminders(db.get_reminders(user_id))
    if reminders:
        bot.edit_message_text(render_list(reminders, db.get_timezone(user_id)),
                              call.message.chat.id, call.message.message_id,
                              reply_markup=delete_keyboard(reminders))
    else:
        bot.edit_message_text("📭 You have no active reminders.",
                              call.message.chat.id, call.message.message_id)


@bot.callback_query_handler(func=lambda call: call.data == "clear_all_reminders")
def cb_clear_all(call):
    try:
        db.delete_all_reminders(call.from_user.id)
        bot.answer_callback_query(call.id, text="All reminders cleared!")
        bot.edit_message_text("📭 You have no active reminders.",
                              call.message.chat.id, call.message.message_id)
    except Exception:
        logger.exception("Error while clearing reminders for user %s", call.from_user.id)
        bot.answer_callback_query(call.id, text="❌ Failed to clear the list.", show_alert=True)


@bot.callback_query_handler(func=lambda call: call.data.startswith("tz_"))
def cb_timezone(call):
    tz_name = call.data[3:]
    if tz_name not in pytz.all_timezones_set:
        bot.answer_callback_query(call.id, text="Unknown timezone.", show_alert=True)
        return
    db.set_timezone(call.from_user.id, tz_name)
    bot.answer_callback_query(call.id)
    bot.edit_message_text(f"✅ Timezone set to: <b>{tz_name}</b>",
                          call.message.chat.id, call.message.message_id)


# ─── Free text: menu buttons, dialog steps and natural-language reminders ─────

MENU_ACTIONS = {
    BTN_LIST: show_list,
    BTN_FIND: initiate_find,
    BTN_WEATHER: initiate_weather,
    BTN_RATES: cmd_rates,
    BTN_TIMEZONE: show_timezone,
    BTN_HELP: show_help,
}


@bot.message_handler(content_types=["text"])
def handle_text(message):
    user_id = message.from_user.id
    text = message.text.strip()

    if text in MENU_ACTIONS:
        if text != BTN_RATES:  # cmd_rates logs the query itself
            log_query(message.from_user, text)
        MENU_ACTIONS[text](message)
        return

    log_query(message.from_user, text)
    tz_name = db.get_timezone(user_id)
    state = user_state.get(user_id)

    # Dialog step: we know the text, waiting for the time
    if state and state["step"] == "waiting_time":
        dt = parse_time_only(text, tz_name)
        if dt:
            user_state.pop(user_id, None)
            save_and_confirm(message, state["reminder_text"], dt, tz_name)
        else:
            bot.send_message(
                message.chat.id,
                f"❌ Could not understand the time. Try:\n{TIME_HINT}\n\n/cancel to stop.",
            )
        return

    # Dialog step: we know the time, waiting for the text
    if state and state["step"] == "waiting_text":
        user_state.pop(user_id, None)
        save_and_confirm(message, text, datetime.fromisoformat(state["datetime"]), tz_name)
        return

    result = parse_reminder(text, tz_name)

    if result["datetime"] and result["text"]:
        save_and_confirm(message, result["text"], result["datetime"], tz_name)
    elif result["datetime"]:
        user_state[user_id] = {"step": "waiting_text", "datetime": result["datetime"].isoformat()}
        bot.send_message(message.chat.id, "🕐 Time understood.\n\nWhat should I remind you about?")
    else:
        user_state[user_id] = {"step": "waiting_time", "reminder_text": result["text"]}
        bot.send_message(
            message.chat.id,
            f"📝 Remind you to: <b>{escape(result['text'])}</b>\n\n⏰ When?\n{TIME_HINT}",
        )


# ─── Startup ──────────────────────────────────────────────────────────────────

def main():
    threading.Thread(target=start_scheduler, args=(bot, db), daemon=True).start()
    logger.info("Remindy started (default timezone: %s).", DEFAULT_TIMEZONE)
    bot.infinity_polling()


if __name__ == "__main__":
    main()
