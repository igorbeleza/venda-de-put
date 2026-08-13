from datetime import date, datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Sao_Paulo")


def format_date(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def format_datetime(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TZ)
    return dt.astimezone(TZ).strftime("%d/%m/%Y %H:%M:%S")


def format_number(x: float, nd: int = 2) -> str:
    formatted = f"{x:,.{nd}f}"
    return formatted.replace(",", "X").replace(".", ",").replace("X", ".")


def format_percent(x: float, nd: int = 1) -> str:
    return format_number(x * 100.0, nd) + "%"
