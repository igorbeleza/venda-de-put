from pathlib import Path

import pytest

from venda_de_put.sources.fundamentus import parse_fundamentus_html
from venda_de_put.sources.oplab import parse_oplab_next_data
from venda_de_put.sources.yahoo import parse_yahoo_chart

FIXTURES = Path("tests/fixtures")


def test_yahoo_keeps_null_and_refuses_to_need_max_range():
    payload = {
        "chart": {"result": [{
            "meta": {"regularMarketPrice": 41.75, "fiftyTwoWeekHigh": 42.0, "fiftyTwoWeekLow": 30.0},
            "timestamp": [1, 2, 3],
            "indicators": {"quote": [{"close": [40.0, None, 41.0]}]},
        }]}
    }
    series = parse_yahoo_chart(payload, "PETR4")
    assert series.closes == [40.0, None, 41.0]
    assert series.preco == 41.75


def test_yahoo_fixture_file():
    import json
    payload = json.loads((FIXTURES / "yahoo_petr4.json").read_text(encoding="utf-8"))
    series = parse_yahoo_chart(payload, "PETR4")
    assert None in series.closes
    assert series.max_52 == 42.0
    assert series.min_52 == 30.0


def test_oplab_raiz4_sem_iv_e_petr4_com_iv():
    html = Path("tests/fixtures/oplab_next_data.html").read_text(encoding="utf-8")
    pts = parse_oplab_next_data(html)
    assert pts["PETR4"].iv is not None
    assert pts["RAIZ4"].iv is None


def test_oplab_sem_next_data_falha_alto():
    with pytest.raises(ValueError):
        parse_oplab_next_data("<html></html>")


def test_fundamentus_iso8859_and_position():
    raw = Path("tests/fixtures/fundamentus.html").read_bytes()
    # Fixture may be UTF-8 on disk; decoder under test is always iso-8859-1.
    try:
        raw.decode("iso-8859-1")
        if "cotações".encode("iso-8859-1") not in raw:
            raw = raw.decode("utf-8").encode("iso-8859-1")
    except UnicodeDecodeError:
        raw = raw.decode("utf-8").encode("iso-8859-1")
    rows = parse_fundamentus_html(raw)
    petr = next(r for r in rows if r.ticker == "PETR4")
    assert petr.pl is not None
    assert petr.cresc_rec_5a is not None
