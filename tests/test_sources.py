from pathlib import Path

import pytest

from venda_de_put.sources.fundamentus import parse_fundamentus_html
from venda_de_put.sources.oplab import parse_oplab_chain, parse_oplab_next_data
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
    assert series.closes == [40.0, None, 41.0, 41.75]
    assert series.preco == 41.75
    assert series.closes[-1] == series.preco


def test_yahoo_replaces_todays_bar_with_spot():
    from datetime import datetime

    from venda_de_put.tz import TZ

    now = datetime(2026, 8, 17, 11, 0, tzinfo=TZ)
    ts_yday = int(datetime(2026, 8, 14, 18, 0, tzinfo=TZ).timestamp())
    ts_today = int(now.timestamp())
    payload = {
        "chart": {"result": [{
            "meta": {"regularMarketPrice": 39.2, "fiftyTwoWeekHigh": 42.0, "fiftyTwoWeekLow": 30.0},
            "timestamp": [ts_yday, ts_today],
            "indicators": {"quote": [{"close": [41.0, 40.5]}]},
        }]}
    }
    series = parse_yahoo_chart(payload, "PETR4", now=now)
    assert series.closes == [41.0, 39.2]
    assert series.preco == 39.2


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


def test_oplab_chain_usa_put_bid_nunca_bs_bid():
    from datetime import date

    html = Path("tests/fixtures/oplab_chain_petr4.html").read_text(encoding="utf-8")
    puts = parse_oplab_chain(html, today=date(2026, 8, 13))
    first = next(p for p in puts if p.strike == 40.86)
    assert first.bid == 0.28
    assert first.bid != 0.92
    assert first.last == 0.28
    assert first.symbol == "PETRX406"
    assert first.delta == -0.266
    assert first.poe == 0.279
    assert first.due_date == date(2026, 8, 21)
    assert all(p.due_date.year != 2027 for p in puts)


def test_oplab_chain_poe_em_percentual_vira_fracao():
    from datetime import date

    html = (
        '<script id="__NEXT_DATA__">{"props":{"pageProps":{"series":['
        '{"due_date":"2026-08-21","strikes":[{"strike":10,'
        '"put":{"bid":0.2,"ask":0.3,"volume":1,"bs":{"delta":-0.2,"poe":27.9}}}]}'
        ']}}}</script>'
    )
    puts = parse_oplab_chain(html, today=date(2026, 8, 13))
    assert puts[0].poe == pytest.approx(0.279)


def test_fundamentus_iso8859_and_position():
    raw = Path("tests/fixtures/fundamentus.html").read_bytes()
    # Fixture is iso-8859-1 on disk (or UTF-8 that we re-encode); parser always gets iso-8859-1.
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError:
        # Already iso-8859-1 bytes (e.g. 0xe7); pass through.
        raw.decode("iso-8859-1")
    else:
        raw = raw.decode("utf-8").encode("iso-8859-1")
    rows = parse_fundamentus_html(raw)
    petr = next(r for r in rows if r.ticker == "PETR4")
    assert petr.pl is not None
    assert petr.cresc_rec_5a is not None
    # "10,00%" no HTML → fração 0.10 (convenção do app). Sem isso a UI
    # faz ×100 e o pt-BR mostra 1.000% em vez de 10,00%.
    assert petr.dy == pytest.approx(0.10)
    assert petr.roe == pytest.approx(0.22)
    assert petr.roic == pytest.approx(0.15)
    assert petr.mrg_liq == pytest.approx(0.20)
    assert petr.cresc_rec_5a == pytest.approx(-2.0815)
    assert petr.pl == pytest.approx(6.0)
