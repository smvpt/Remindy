"""SQLite storage for users, reminders and the user-query log."""
import sqlite3
from contextlib import closing
from pathlib import Path

from config import DB_PATH, DEFAULT_TIMEZONE

BASE_DIR = Path(__file__).resolve().parent


def resolve_db_path(path: str) -> Path:
    """Relative paths are resolved against the project folder, so the bot and
    the Django admin always open the same file regardless of the working dir."""
    p = Path(path)
    return p if p.is_absolute() else BASE_DIR / p


class Database:
    def __init__(self, db_path: str | None = None, default_timezone: str = DEFAULT_TIMEZONE):
        self.db_path = resolve_db_path(db_path or DB_PATH)
        self.default_timezone = default_timezone
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        """Runs a write query in its own transaction and closes the connection."""
        with closing(self._get_conn()) as conn, conn:
            return conn.execute(sql, params)

    def _fetchall(self, sql: str, params: tuple = ()) -> list[dict]:
        with closing(self._get_conn()) as conn:
            return [dict(r) for r in conn.execute(sql, params).fetchall()]

    def _init_db(self):
        with closing(self._get_conn()) as conn, conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id    INTEGER PRIMARY KEY,
                    name       TEXT,
                    timezone   TEXT DEFAULT 'UTC',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS reminders (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id    INTEGER NOT NULL,
                    text       TEXT NOT NULL,
                    datetime   TEXT NOT NULL,
                    is_sent    INTEGER DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                );
            """)

    # ── User queries (table is created by Django: `python manage.py migrate`) ──
    def save_user_query(self, user_id: int, username: str | None, text: str):
        self._execute(
            "INSERT INTO support_userquery (user_id, username, question, is_answered, created_at) "
            "VALUES (?, ?, ?, 0, datetime('now'))",
            (user_id, username, text),
        )

    # ── Users ──────────────────────────────────────────────────────────────────
    def add_user(self, user_id: int, name: str):
        self._execute(
            "INSERT OR IGNORE INTO users (user_id, name, timezone) VALUES (?, ?, ?)",
            (user_id, name, self.default_timezone),
        )

    def get_timezone(self, user_id: int) -> str:
        rows = self._fetchall("SELECT timezone FROM users WHERE user_id = ?", (user_id,))
        return rows[0]["timezone"] if rows and rows[0]["timezone"] else self.default_timezone

    def set_timezone(self, user_id: int, timezone: str):
        self._execute(
            "INSERT INTO users (user_id, timezone) VALUES (?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET timezone = excluded.timezone",
            (user_id, timezone),
        )

    # ── Reminders ──────────────────────────────────────────────────────────────
    def add_reminder(self, user_id: int, text: str, dt_iso: str) -> int:
        return self._execute(
            "INSERT INTO reminders (user_id, text, datetime) VALUES (?, ?, ?)",
            (user_id, text, dt_iso),
        ).lastrowid

    def get_reminders(self, user_id: int) -> list[dict]:
        return self._fetchall(
            "SELECT id, text, datetime FROM reminders "
            "WHERE user_id = ? AND is_sent = 0 ORDER BY datetime",
            (user_id,),
        )

    def get_all_pending(self) -> list[dict]:
        """All unsent reminders (also restores the queue after a restart)."""
        return self._fetchall("SELECT id, user_id, text, datetime FROM reminders WHERE is_sent = 0")

    def mark_sent(self, reminder_id: int):
        self._execute("UPDATE reminders SET is_sent = 1 WHERE id = ?", (reminder_id,))

    def delete_reminder(self, reminder_id: int, user_id: int) -> bool:
        cur = self._execute(
            "DELETE FROM reminders WHERE id = ? AND user_id = ?",
            (reminder_id, user_id),
        )
        return cur.rowcount > 0

    def delete_all_reminders(self, user_id: int) -> int:
        """Deletes all pending reminders of a user. Returns how many were removed."""
        cur = self._execute(
            "DELETE FROM reminders WHERE user_id = ? AND is_sent = 0",
            (user_id,),
        )
        return cur.rowcount
