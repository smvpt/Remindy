import pytest

pytest.importorskip("telebot")

from bot import parse_nbk_rates  # noqa: E402

SAMPLE_FEED = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0"><channel>
  <item><title>USD</title><description>480.50</description><quant>1</quant></item>
  <item><title>RUB</title><description>5.20</description><quant>1</quant></item>
  <item><title>JPY</title><description>310.00</description><quant>100</quant></item>
  <item><title>CNY</title><description>bad</description><quant>1</quant></item>
</channel></rss>"""


def test_parse_nbk_rates_keeps_supported_currencies_only():
    assert parse_nbk_rates(SAMPLE_FEED) == {"USD": 480.50, "RUB": 5.20}


def test_parse_nbk_rates_empty_feed():
    assert parse_nbk_rates("<rss><channel></channel></rss>") == {}
