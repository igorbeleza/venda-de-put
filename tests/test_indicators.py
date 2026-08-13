import math

from venda_de_put.indicators import (
    bollinger_lower,
    hv_log,
    posicao_52s,
    rsi_wilder,
    sma,
)


def test_sma_needs_full_window():
    assert sma([1, 2, 3], 4) is None
    assert sma([1.0, 2.0, 3.0], 3) == 2.0


def test_rsi_wilder_flat_series_is_none_or_edge():
    # 20 fechamentos iguais: ganhos=perdas=0 → sem dado, não 50 inventado
    assert rsi_wilder([10.0] * 20, 14) is None


def test_rsi_wilder_known_climb():
    # 15 dias: 1,2,...,15. Só ganhos. RSI deve ir a 100.
    closes = [float(i) for i in range(1, 16)]
    assert rsi_wilder(closes, 14) == 100.0


def test_auau3_cannot_have_mm200():
    assert sma([1.0] * 153, 200) is None


def test_hv_log_n_lt_2_is_none():
    assert hv_log([100.0, 101.0], 1) is None
    assert hv_log([100.0], 0) is None


def test_hv_and_range():
    closes = [100.0, 101.0, 100.0, 102.0] + [100.0] * 20
    hv = hv_log(closes, 21)
    assert hv is not None and hv > 0
    assert posicao_52s(15.0, 10.0, 20.0) == 0.5
    assert posicao_52s(15.0, 15.0, 15.0) is None


def test_bollinger_lower_below_sma():
    closes = [float(i % 5) for i in range(20)]
    mid = sma(closes, 20)
    low = bollinger_lower(closes, 20, 2.0)
    assert mid is not None and low is not None
    assert low < mid
