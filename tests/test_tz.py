from datetime import date, datetime
from zoneinfo import ZoneInfo

from venda_de_put.tz import TZ, format_date, format_datetime, format_number, format_percent


def test_timezone_is_sao_paulo():
    assert TZ.key == "America/Sao_Paulo"


def test_format_date_br():
    assert format_date(date(2026, 8, 13)) == "13/08/2026"


def test_format_datetime_converts_from_utc():
    utc = datetime(2026, 8, 13, 15, 5, 29, tzinfo=ZoneInfo("UTC"))
    assert format_datetime(utc) == "13/08/2026 12:05:29"


def test_format_number_and_percent_br():
    assert format_number(1234.56) == "1.234,56"
    assert format_percent(0.123) == "12,3%"
