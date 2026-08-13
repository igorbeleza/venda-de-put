from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from venda_de_put.models import Vencimento

_WEEKDAYS_FULL = (
    "segunda",
    "terça",
    "quarta",
    "quinta",
    "sexta",
    "sábado",
    "domingo",
)
_WEEKDAYS_SHORT = ("seg", "ter", "qua", "qui", "sex", "sáb", "dom")


def load_holidays(path: Path) -> set[date]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {date.fromisoformat(item["date"]) for item in raw}


def is_business_day(d: date, holidays: set[date]) -> bool:
    return d.weekday() < 5 and d not in holidays


def adjust_friday(nominal: date, holidays: set[date]) -> date:
    if nominal not in holidays:
        return nominal
    for delta in (1, 2, 3):
        candidate = nominal - timedelta(days=delta)
        if candidate not in holidays:
            return candidate
    return nominal - timedelta(days=3)


def is_monthly(nominal: date) -> bool:
    return 15 <= nominal.day <= 21


def weekday_pt(d: date, curto: bool = False) -> str:
    names = _WEEKDAYS_SHORT if curto else _WEEKDAYS_FULL
    return names[d.weekday()]


def business_days_inclusive(start: date, end: date, holidays: set[date]) -> int:
    if end < start:
        return 0
    count = 0
    current = start
    one = timedelta(days=1)
    while current <= end:
        if is_business_day(current, holidays):
            count += 1
        current += one
    return count


def _status(dias_corridos: int) -> str:
    if dias_corridos < 0:
        return "Vencido"
    if dias_corridos == 0:
        return "VENCE HOJE"
    if dias_corridos <= 7:
        return "Esta semana"
    return ""


def build_calendar(
    today: date,
    holidays: set[date],
    through: date,
) -> list[Vencimento]:
    # First Friday on or after today
    days_until_friday = (4 - today.weekday()) % 7
    friday = today + timedelta(days=days_until_friday)
    rows: list[Vencimento] = []
    while friday <= through:
        feriado = friday in holidays
        efetivo = adjust_friday(friday, holidays)
        dias_corridos = (efetivo - today).days
        if dias_corridos < 0:
            dias_uteis = 0
        else:
            dias_uteis = business_days_inclusive(today, efetivo, holidays)
        rows.append(
            Vencimento(
                nominal=friday,
                efetivo=efetivo,
                tipo="MENSAL" if is_monthly(friday) else "Semanal",
                feriado_na_sexta=feriado,
                dia_semana=weekday_pt(efetivo),
                dias_corridos=dias_corridos,
                dias_uteis=dias_uteis,
                status=_status(dias_corridos),
            )
        )
        friday += timedelta(days=7)
    return rows


def default_vencimento(
    rows: list[Vencimento],
    so_mensais: bool = True,
) -> Vencimento:
    for row in rows:
        if row.dias_corridos < 0:
            continue
        if so_mensais and row.tipo != "MENSAL":
            continue
        return row
    raise ValueError("nenhum vencimento elegível")
