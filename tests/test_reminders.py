import random

import pytest

from reminders import (
    ReminderBase,
    SimpleReminder,
    UrgentReminder,
    make_reminder,
    merge_sort_reminders,
    shorten,
)


def test_merge_sort_orders_by_datetime():
    items = [{"id": i, "datetime": f"2026-11-{d:02d}T10:00:00+00:00"} for i, d in enumerate([5, 1, 3, 2, 4])]
    result = merge_sort_reminders(items)
    assert [r["datetime"][8:10] for r in result] == ["01", "02", "03", "04", "05"]


def test_merge_sort_matches_builtin_sort_and_keeps_input():
    items = [{"datetime": random.randint(0, 1000)} for _ in range(200)]
    snapshot = list(items)
    assert merge_sort_reminders(items) == sorted(items, key=lambda r: r["datetime"])
    assert items == snapshot


def test_merge_sort_is_stable():
    items = [{"datetime": 1, "id": "a"}, {"datetime": 0, "id": "b"}, {"datetime": 1, "id": "c"}]
    assert [r["id"] for r in merge_sort_reminders(items)] == ["b", "a", "c"]


@pytest.mark.parametrize("items", [[], [{"datetime": 1}]])
def test_merge_sort_trivial(items):
    assert merge_sort_reminders(items) == items


@pytest.mark.parametrize("text, cls", [
    ("buy milk", SimpleReminder),
    ("URGENT: call the bank", UrgentReminder),
    ("important meeting", UrgentReminder),
    ("срочно позвонить", UrgentReminder),
])
def test_factory_picks_subclass(text, cls):
    assert type(make_reminder(text, "2026-11-25T10:00:00+00:00")) is cls


def test_format_message_escapes_html():
    msg = SimpleReminder("compare <a> & <b>", "x").format_message()
    assert "&lt;a&gt; &amp; &lt;b&gt;" in msg


def test_urgent_message_is_highlighted():
    assert "URGENT" in UrgentReminder("call", "x").format_message()


def test_base_class_is_abstract():
    with pytest.raises(TypeError):
        ReminderBase("x", "y")


def test_remind_at_is_read_only():
    r = SimpleReminder("x", "2026-11-25")
    assert r.remind_at == "2026-11-25"
    with pytest.raises(AttributeError):
        r.remind_at = "other"


def test_shorten():
    assert shorten("abc", 5) == "abc"
    assert shorten("abcdef", 3) == "abc…"
