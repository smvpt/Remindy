"""
Lightweight natural-language time parser built on regular expressions.

Understands English phrases such as:
    "in 2 hours", "after 30 mins", "in an hour", "in a week",
    "today / tomorrow / day after tomorrow",
    "friday", "on fri", "next monday",
    "25.12.2026", "at 18:30", "at 9am", "14:00".

No third-party date libraries are required.
"""
import re
from datetime import date, datetime, timedelta

import pytz

# ── Vocabulary ────────────────────────────────────────────────────────────────
_WEEKDAYS = {
    "monday": 0, "mon": 0,
    "tuesday": 1, "tue": 1,
    "wednesday": 2, "wed": 2,
    "thursday": 3, "thu": 3,
    "friday": 4, "fri": 4,
    "saturday": 5, "sat": 5,
    "sunday": 6, "sun": 6,
}

# Minutes per unit, keyed by the unit's 3-letter prefix.
_UNITS = {
    "min": 1,
    "hou": 60, "hr": 60,
    "day": 1440,
    "wee": 10080,
    "mon": 43200,
}

_WD_ALL = "monday|mon|tuesday|tue|wednesday|wed|thursday|thu|friday|fri|saturday|sat|sunday|sun"
_WD_FULL = "monday|tuesday|wednesday|thursday|friday|saturday|sunday"

# ── Patterns ──────────────────────────────────────────────────────────────────
# "at 14:00", "at 14.00", "at 9am", "at 9 pm", "at 9:30pm"
_RE_CLOCK = re.compile(
    r"\bat\s+(\d{1,2})(?:[.:](\d{2}))?\s*(am|pm)?\b(?![.:]\d)",
    re.IGNORECASE,
)
# bare "14:00", "9:30pm", "9am"
_RE_CLOCK_BARE = re.compile(
    r"\b(\d{1,2}):(\d{2})\s*(am|pm)?\b|\b(\d{1,2})\s*(am|pm)\b",
    re.IGNORECASE,
)

# "in 5 minutes", "after 2 hours", "in a week", "in an hour"
_RE_DELTA = re.compile(
    r"\b(in|after)\s+(\d+|an?)\s+(min\w*|hour\w*|hr\w*|day\w*|week\w*|month\w*)",
    re.IGNORECASE,
)

_RE_DAY_WORD = re.compile(r"\b(day after tomorrow|tomorrow|today)\b", re.IGNORECASE)

# "next friday" — strictly the following week
_RE_NEXT_WEEKDAY = re.compile(rf"\bnext\s+({_WD_ALL})\b", re.IGNORECASE)

# "on friday", "on fri", or a bare full name: "friday"
_RE_WEEKDAY = re.compile(rf"\b(?:on\s+({_WD_ALL})|({_WD_FULL}))\b", re.IGNORECASE)

# "25.12.2026" or "25/12/2026"
_RE_DATE = re.compile(r"\b(\d{1,2})[./](\d{1,2})[./](\d{4})\b")

_RE_EDGE_FILLER = r"(?:at|on|in|after|and|by)\b|[,.;:-]"


# ── Public API ────────────────────────────────────────────────────────────────

def parse_reminder(user_input: str, timezone: str, now: datetime | None = None) -> dict:
    """
    Splits free text into the reminder text and its time.

    Returns a dict with keys:
        text          — what to remind about (``None`` if only a time was given)
        datetime      — timezone-aware ``datetime`` or ``None``
        raw_time      — the time fragment as written by the user
        ambiguous     — a time was found, but no reminder text
        time_missing  — no time could be recognised
    """
    tz = pytz.timezone(timezone)
    now = now or datetime.now(tz)
    text = user_input.strip()

    parsed_dt = _parse_dt(text, tz, now)

    if parsed_dt:
        reminder_text = _remove_time_parts(text)
        return {
            "text": reminder_text or None,
            "datetime": parsed_dt,
            "raw_time": _find_raw_time(text) or text,
            "ambiguous": not reminder_text,
            "time_missing": False,
        }

    return {
        "text": text,
        "datetime": None,
        "raw_time": None,
        "ambiguous": False,
        "time_missing": True,
    }


def parse_time_only(user_input: str, timezone: str, now: datetime | None = None) -> datetime | None:
    """
    Parses only the time from a short answer such as "in 2 hours".
    Used during the clarification step, when the reminder text is already known.
    """
    tz = pytz.timezone(timezone)
    now = now or datetime.now(tz)
    return _parse_dt(user_input.strip(), tz, now)


# ── Internals ─────────────────────────────────────────────────────────────────

def _to_24h(hour: int, ampm: str | None) -> int:
    if not ampm:
        return hour
    ampm = ampm.lower()
    if not 1 <= hour <= 12:
        return -1  # "13pm" is invalid
    if ampm == "am":
        return 0 if hour == 12 else hour
    return 12 if hour == 12 else hour + 12


def _extract_clock(text: str):
    """Returns ``(hour, minute)`` if a time of day is found, otherwise ``None``."""
    m = _RE_CLOCK.search(text)
    if m:
        hour, minute, ampm = int(m.group(1)), int(m.group(2) or 0), m.group(3)
        return _to_24h(hour, ampm), minute
    m = _RE_CLOCK_BARE.search(text)
    if m:
        if m.group(1):
            return _to_24h(int(m.group(1)), m.group(3)), int(m.group(2))
        return _to_24h(int(m.group(4)), m.group(5)), 0
    return None


def _valid_clock(clock) -> bool:
    h, mi = clock
    return 0 <= h <= 23 and 0 <= mi <= 59


def _localize(tz, d: date, hour: int, minute: int) -> datetime:
    return tz.localize(datetime(d.year, d.month, d.day, hour, minute))


def _remove_time_parts(text: str) -> str:
    """Removes every time-related fragment, leaving only the reminder text."""
    for pattern in (_RE_DELTA, _RE_DAY_WORD, _RE_NEXT_WEEKDAY, _RE_WEEKDAY,
                    _RE_DATE, _RE_CLOCK, _RE_CLOCK_BARE):
        text = pattern.sub(" ", text)

    text = re.sub(r"\s{2,}", " ", text).strip()
    # Strip leftover prepositions / punctuation at the edges (whole words only).
    prev = None
    while prev != text:
        prev = text
        text = re.sub(rf"^(?:{_RE_EDGE_FILLER})\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*\b(?:at|on|in|after|and|by)$|\s*[,.;:-]$", "", text, flags=re.IGNORECASE)
        text = text.strip()
    return text


def _weekday_date(now: datetime, name: str, skip_week: bool = False) -> date | None:
    target = _WEEKDAYS.get(name.lower())
    if target is None:
        return None
    days_ahead = (target - now.weekday()) % 7 or 7  # same weekday → next week
    if skip_week:
        days_ahead += 7
    return (now + timedelta(days=days_ahead)).date()


def _parse_dt(text: str, tz, now: datetime) -> datetime | None:
    """Core logic: determines the date and time from text."""

    # 1. Relative delta: "in X hours", "after 30 mins", "in a week"
    m = _RE_DELTA.search(text)
    if m:
        amount_str = m.group(2).lower()
        amount = 1 if amount_str in ("a", "an") else int(amount_str)
        minutes = _match_unit(m.group(3).lower()) * amount
        if minutes:
            return now + timedelta(minutes=minutes)

    # 2. Base date
    base_date = None

    m = _RE_DAY_WORD.search(text)
    if m:
        offset = {"today": 0, "tomorrow": 1, "day after tomorrow": 2}[m.group(1).lower()]
        base_date = (now + timedelta(days=offset)).date()

    if base_date is None:
        m = _RE_NEXT_WEEKDAY.search(text)
        if m:
            base_date = _weekday_date(now, m.group(1), skip_week=True)

    if base_date is None:
        m = _RE_WEEKDAY.search(text)
        if m:
            base_date = _weekday_date(now, m.group(1) or m.group(2))

    if base_date is None:
        m = _RE_DATE.search(text)
        if m:
            try:
                base_date = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            except ValueError:
                pass

    # 3. Time of day
    clock = _extract_clock(text)
    if clock and not _valid_clock(clock):
        return None

    if base_date and clock:
        dt = _localize(tz, base_date, *clock)
        return dt if dt > now else None

    # 4. Date without a time → 09:00, or 12:00 if the morning has already passed
    if base_date:
        for hour in (9, 12):
            dt = _localize(tz, base_date, hour, 0)
            if dt > now:
                return dt
        return None

    # 5. Time without a date → today, or tomorrow if that time has passed
    if clock:
        local_now = now.astimezone(tz)
        candidate = _localize(tz, local_now.date(), *clock)
        if candidate <= now:
            candidate = _localize(tz, local_now.date() + timedelta(days=1), *clock)
        return candidate

    return None


def _match_unit(unit_str: str) -> int:
    """Returns the number of minutes for a time unit ("hours" → 60)."""
    for prefix, minutes in _UNITS.items():
        if unit_str.startswith(prefix):
            return minutes
    return 0


def _find_raw_time(text: str) -> str | None:
    """Finds the raw time fragment to show back to the user."""
    for pattern in (_RE_DELTA, _RE_DAY_WORD, _RE_NEXT_WEEKDAY, _RE_WEEKDAY, _RE_DATE):
        m = pattern.search(text)
        if m:
            clock = _RE_CLOCK.search(text) or _RE_CLOCK_BARE.search(text)
            if clock and pattern is not _RE_DELTA:
                clock_str = re.sub(r"(?i)^at\s+", "", clock.group(0)).strip()
                return f"{m.group(0).strip()} at {clock_str}"
            return m.group(0).strip()
    clock = _RE_CLOCK.search(text) or _RE_CLOCK_BARE.search(text)
    return clock.group(0).strip() if clock else None
