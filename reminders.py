"""
Domain logic for reminders: the reminder class hierarchy and sorting.

Kept free of Telegram / config imports so it can be unit-tested in isolation.
"""
from abc import ABC, abstractmethod
from html import escape

URGENT_KEYWORDS = (
    "urgent", "important", "asap", "immediately",
    "срочно", "важно", "немедленно",
)


class ReminderBase(ABC):
    """Abstract base class for reminders."""

    def __init__(self, text: str, remind_at: str):
        self._text = text               # protected
        self.__remind_at = remind_at    # private (name-mangled) — encapsulation

    @property
    def text(self) -> str:
        return self._text

    @property
    def remind_at(self) -> str:
        return self.__remind_at

    @abstractmethod
    def format_message(self) -> str:
        """Builds the HTML notification text. Each subclass formats it differently."""

    def __str__(self):
        return f"[{self.__class__.__name__}] {self._text} @ {self.__remind_at}"


class SimpleReminder(ReminderBase):
    """Regular reminder."""

    def format_message(self) -> str:
        return f"🔔 <b>Reminder!</b>\n\n{escape(self._text)}"


class UrgentReminder(ReminderBase):
    """Urgent reminder — visually highlighted."""

    def format_message(self) -> str:
        return f"🚨 <b>URGENT REMINDER</b> 🚨\n\n❗ {escape(self._text)}"


def make_reminder(text: str, remind_at: str) -> ReminderBase:
    """Factory: picks the reminder subclass based on keywords in the text."""
    lowered = text.lower()
    if any(kw in lowered for kw in URGENT_KEYWORDS):
        return UrgentReminder(text, remind_at)
    return SimpleReminder(text, remind_at)


def merge_sort_reminders(reminders: list[dict], key: str = "datetime") -> list[dict]:
    """
    Sorts reminder dicts by ``key`` using merge sort.
    Stable, O(n log n). Returns a new list; the input is not modified.
    """
    if len(reminders) <= 1:
        return list(reminders)

    mid = len(reminders) // 2
    left = merge_sort_reminders(reminders[:mid], key)
    right = merge_sort_reminders(reminders[mid:], key)
    return _merge(left, right, key)


def _merge(left: list[dict], right: list[dict], key: str) -> list[dict]:
    result, i, j = [], 0, 0
    while i < len(left) and j < len(right):
        if left[i][key] <= right[j][key]:
            result.append(left[i])
            i += 1
        else:
            result.append(right[j])
            j += 1
    result.extend(left[i:])
    result.extend(right[j:])
    return result


def shorten(text: str, limit: int) -> str:
    """Truncates text to ``limit`` characters, adding an ellipsis."""
    return text if len(text) <= limit else text[:limit] + "…"
