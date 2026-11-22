# Copy this file to config.py and fill in your own values:
#     cp config.example.py config.py
# config.py is listed in .gitignore and must never be committed.

# Telegram bot token from @BotFather
BOT_TOKEN = "YOUR_BOT_TOKEN"

# OpenWeather API key: https://home.openweathermap.org/api_keys
WEATHER_API = "YOUR_API_KEY"

# Timezone assigned to new users (any IANA name, e.g. "Europe/London")
DEFAULT_TIMEZONE = "Asia/Almaty"

# SQLite file shared by the bot and the Django admin.
# Relative paths are resolved against the project folder.
DB_PATH = "reminders.db"
