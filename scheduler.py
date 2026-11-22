"""Background loop that delivers due reminders."""
import logging
import threading
from datetime import datetime

import pytz

from reminders import make_reminder

logger = logging.getLogger(__name__)

CHECK_INTERVAL_SECONDS = 10


def to_utc(value: str) -> datetime:
    """Parses an ISO timestamp from the DB; naive values are treated as UTC."""
    dt = datetime.fromisoformat(value)
    return pytz.utc.localize(dt) if dt.tzinfo is None else dt.astimezone(pytz.utc)


class ReminderScheduler:
    def __init__(self, bot, db):
        self.bot = bot
        self.db = db

    def check_and_send(self, now: datetime | None = None) -> int:
        """Sends every reminder that is due. Returns the number sent."""
        now = now or datetime.now(pytz.utc)
        sent = 0

        for r in self.db.get_all_pending():
            if to_utc(r["datetime"]) > now:
                continue
            try:
                reminder = make_reminder(r["text"], r["datetime"])
                self.bot.send_message(r["user_id"], reminder.format_message(), parse_mode="HTML")
                self.db.mark_sent(r["id"])
                sent += 1
                logger.info("Sent reminder %s to user %s", r["id"], r["user_id"])
            except Exception:
                logger.exception("Error sending reminder %s", r["id"])
        return sent


def start_scheduler(bot, db, interval: float = CHECK_INTERVAL_SECONDS,
                    stop_event: threading.Event | None = None):
    """Runs the scheduler loop. Called by bot.py in a daemon thread."""
    scheduler = ReminderScheduler(bot, db)
    stop_event = stop_event or threading.Event()
    logger.info("Scheduler started (checking every %ss).", interval)

    while not stop_event.is_set():
        try:
            scheduler.check_and_send()
        except Exception:
            logger.exception("Critical error in scheduler loop")
        stop_event.wait(interval)

