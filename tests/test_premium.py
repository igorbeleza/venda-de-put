from math import isclose, sqrt

from venda_de_put.premium import premio_alvo


def test_excel_example_40_days():
    # Config texto: 1,15% e 40 dias → ~1,33%
    got = premio_alvo(0.0115, 40)
    assert isclose(got, 0.0115 * sqrt(40 / 30), rel_tol=1e-12)
    assert isclose(got, 0.013279, rel_tol=1e-3)


def test_zero_or_negative_days():
    assert premio_alvo(0.0115, 0) == 0.0
    assert premio_alvo(0.0115, -3) == 0.0
