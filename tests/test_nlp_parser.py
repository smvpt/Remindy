from datetime import datetime, timedelta

import pytest
import pytz

from nlp_parser import parse_reminder, parse_time_only

TZ_NAME = "Asia/Almaty"
TZ = pytz.timezone(TZ_NAME)
# Wednesday, 25 November 2026, 12:00 local time
NOW = TZ.localize(datetime(2026, 11, 25, 12, 0))


def at(year, month, day, hour, minute=0):
    return TZ.localize(datetime(year, month, day, hour, minute))


def parse(text):
    return parse_reminder(text, TZ_NAME, now=NOW)


# ── Relative time ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("phrase, text, delta", [
    ("call mom in 2 hours",        "call mom",    timedelta(hours=2)),
    ("stream in 45 minutes",       "stream",      timedelta(minutes=45)),
    ("coffee in an hour",          "coffee",      timedelta(hours=1)),
    ("pay rent in a week",         "pay rent",    timedelta(weeks=1)),
    ("after 30 mins check oven",   "check oven",  timedelta(minutes=30)),
    ("renew passport in 3 days",   "renew passport", timedelta(days=3)),
])
def test_relative_time(phrase, text, delta):
    result = parse(phrase)
    assert result["text"] == text
    assert result["datetime"] == NOW + delta
    assert result["time_missing"] is False


# ── Day words, weekdays and dates ─────────────────────────────────────────────

@pytest.mark.parametrize("phrase, text, expected", [
    ("meeting tomorrow at 15:00",          "meeting",  at(2026, 11, 26, 15)),
    ("today at 18:30 gym",                 "gym",      at(2026, 11, 25, 18, 30)),
    ("report day after tomorrow at 9:00",  "report",   at(2026, 11, 27, 9)),
    ("workout friday at 18:30",            "workout",  at(2026, 11, 27, 18, 30)),
    ("call mom on fri at 18:00",           "call mom", at(2026, 11, 27, 18)),
    ("dentist 25.12.2026 at 10:30",        "dentist",  at(2026, 12, 25, 10, 30)),
    ("meeting friday at 6pm",              "meeting",  at(2026, 11, 27, 18)),
    ("breakfast tomorrow at 9am",          "breakfast", at(2026, 11, 26, 9)),
])
def test_absolute_time(phrase, text, expected):
    result = parse(phrase)
    assert result["text"] == text
    assert result["datetime"] == expected


def test_same_weekday_means_next_week():
    # Today is Wednesday, so "on wednesday" is the one in 7 days.
    assert parse("standup on wednesday at 10:00")["datetime"] == at(2026, 12, 2, 10)


def test_next_weekday_skips_a_week():
    assert parse("review next friday at 11:00")["datetime"] == at(2026, 12, 4, 11)


def test_date_without_time_defaults_to_morning():
    assert parse("buy gifts tomorrow")["datetime"] == at(2026, 11, 26, 9)


def test_clock_in_the_past_moves_to_tomorrow():
    assert parse("take pills at 08:00")["datetime"] == at(2026, 11, 26, 8)


def test_clock_later_today_stays_today():
    assert parse("take pills at 20:00")["datetime"] == at(2026, 11, 25, 20)


# ── Text cleanup ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("phrase, text", [
    ("insurance tomorrow at 10:00", "insurance"),   # leading "in" is part of the word
    ("feed the cat tomorrow",       "feed the cat"),  # trailing "at" is part of the word
    ("send invoice, tomorrow at 10:00", "send invoice"),
])
def test_words_are_not_mangled(phrase, text):
    assert parse(phrase)["text"] == text


# ── Ambiguous / missing input ─────────────────────────────────────────────────

def test_time_without_text_is_ambiguous():
    result = parse("tomorrow at 10:00")
    assert result["ambiguous"] is True
    assert result["text"] is None
    assert result["datetime"] == at(2026, 11, 26, 10)


def test_text_without_time():
    result = parse("buy milk")
    assert result["time_missing"] is True
    assert result["datetime"] is None
    assert result["text"] == "buy milk"


@pytest.mark.parametrize("phrase", [
    "meeting at 25:00",           # invalid hour
    "meeting 31.02.2027 at 10:00",  # invalid date → no date, but clock is valid
])
def test_invalid_values_do_not_crash(phrase):
    parse(phrase)


def test_invalid_hour_is_rejected():
    assert parse("meeting at 25:00")["datetime"] is None


def test_past_date_is_rejected():
    assert parse("meeting 01.01.2020 at 10:00")["datetime"] is None


def test_parse_time_only():
    assert parse_time_only("in 2 hours", TZ_NAME, now=NOW) == NOW + timedelta(hours=2)
    assert parse_time_only("no idea", TZ_NAME, now=NOW) is None


def test_raw_time_is_reported():
    assert parse("meeting tomorrow at 15:00")["raw_time"] == "tomorrow at 15:00"
