from datetime import datetime

import pytest
import pytz

from database import Database
from scheduler import ReminderScheduler, to_utc


@pytest.fixture
def db(tmp_path):
    return Database(db_path=str(tmp_path / "test.db"), default_timezone="Asia/Almaty")


def test_user_timezone(db):
    db.add_user(1, "Alice")
    assert db.get_timezone(1) == "Asia/Almaty"
    db.set_timezone(1, "Europe/London")
    assert db.get_timezone(1) == "Europe/London"


def test_set_timezone_for_unknown_user_creates_it(db):
    db.set_timezone(42, "Europe/Berlin")
    assert db.get_timezone(42) == "Europe/Berlin"


def test_unknown_user_gets_default_timezone(db):
    assert db.get_timezone(999) == "Asia/Almaty"


def test_reminder_crud(db):
    rid = db.add_reminder(1, "buy milk", "2026-11-25T10:00:00+00:00")
    assert db.get_reminders(1) == [{"id": rid, "text": "buy milk", "datetime": "2026-11-25T10:00:00+00:00"}]
    assert db.get_reminders(2) == []

    assert db.delete_reminder(rid, user_id=2) is False   # other users can't delete it
    assert db.delete_reminder(rid, user_id=1) is True
    assert db.get_reminders(1) == []


def test_delete_all_reminders(db):
    for i in range(3):
        db.add_reminder(1, f"task {i}", "2026-11-25T10:00:00+00:00")
    db.add_reminder(2, "someone else's", "2026-11-25T10:00:00+00:00")

    assert db.delete_all_reminders(1) == 3
    assert db.get_reminders(1) == []
    assert len(db.get_reminders(2)) == 1


class FakeBot:
    def __init__(self):
        self.sent = []

    def send_message(self, chat_id, text, **kwargs):
        self.sent.append((chat_id, text))


def test_scheduler_sends_only_due_reminders(db):
    db.add_reminder(1, "past", "2026-11-25T09:00:00+00:00")
    db.add_reminder(1, "URGENT call", "2026-11-25T14:59:00+05:00")  # 09:59 UTC
    db.add_reminder(1, "future", "2026-11-25T11:00:00+00:00")
    bot = FakeBot()

    now = pytz.utc.localize(datetime(2026, 11, 25, 10, 0))
    assert ReminderScheduler(bot, db).check_and_send(now=now) == 2

    texts = [t for _, t in bot.sent]
    assert "past" in texts[0]
    assert "URGENT" in texts[1]
    assert [r["text"] for r in db.get_all_pending()] == ["future"]


def test_scheduler_does_not_resend(db):
    db.add_reminder(1, "once", "2026-11-25T09:00:00+00:00")
    bot = FakeBot()
    scheduler = ReminderScheduler(bot, db)
    now = pytz.utc.localize(datetime(2026, 11, 25, 10, 0))
    scheduler.check_and_send(now=now)
    scheduler.check_and_send(now=now)
    assert len(bot.sent) == 1


def test_to_utc_handles_naive_and_aware_values():
    assert to_utc("2026-11-25 10:00:00") == pytz.utc.localize(datetime(2026, 11, 25, 10))
    assert to_utc("2026-11-25T15:00:00+05:00") == pytz.utc.localize(datetime(2026, 11, 25, 10))
