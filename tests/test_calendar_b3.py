from datetime import date
from pathlib import Path

from venda_de_put.calendar_b3 import (
    adjust_friday,
    build_calendar,
    default_vencimento,
    is_monthly,
    load_holidays,
    weekday_pt,
)


def test_novembro_2026_mensal_e_quinta_19():
    holidays = load_holidays(Path("data/feriados.json"))
    assert date(2026, 11, 20) in holidays  # Consciência Negra
    nominal = date(2026, 11, 20)  # 3ª sexta — feriado
    assert is_monthly(nominal) is True
    efetivo = adjust_friday(nominal, holidays)
    assert efetivo == date(2026, 11, 19)
    assert weekday_pt(efetivo) == "quinta"


def test_abril_2028_mensal_e_quinta_20():
    holidays = {date(2028, 4, 21)}  # Tiradentes
    nominal = date(2028, 4, 21)
    assert is_monthly(nominal) is True
    assert adjust_friday(nominal, holidays) == date(2028, 4, 20)


def test_terceira_sexta_nao_e_a_regra():
    """16/10/2026 é sexta e mensal; 23/10 não é mensal mesmo sendo sexta."""
    assert is_monthly(date(2026, 10, 16)) is True
    assert is_monthly(date(2026, 10, 23)) is False


def test_default_e_proximo_mensal():
    holidays = load_holidays(Path("data/feriados.json"))
    rows = build_calendar(date(2026, 8, 13), holidays, through=date(2026, 12, 31))
    escolhido = default_vencimento(rows, so_mensais=True)
    assert escolhido.tipo == "MENSAL"
    assert escolhido.efetivo >= date(2026, 8, 13)
    assert 15 <= escolhido.nominal.day <= 21
