"""Test setup: make the project importable and provide a stub `config` module,
so the tests never need a real config.py or bot token."""
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

stub = types.ModuleType("config")
stub.BOT_TOKEN = "123456:TEST"
stub.WEATHER_API = "test"
stub.DEFAULT_TIMEZONE = "Asia/Almaty"
stub.DB_PATH = str(Path(tempfile.mkdtemp()) / "test.db")  # importing bot.py opens the DB
sys.modules["config"] = stub
