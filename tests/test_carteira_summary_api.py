from datetime import date, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from venda_de_put.models import FundScore, Lists, PutQuote, ScoredAsset, Snapshot, TechnicalInput
from venda_de_put.snapshot import write_snapshot
from venda_de_put.tz import TZ
from venda_de_put.web.app import create_app


def _make_summary_snapshot(
    generated_at: datetime,
    ticker: str,
    spot: float,
    option: str,
    option_last: float,
) -> Snapshot:
    fund = FundScore(
        ticker=ticker, n_roe=None, n_roic=None, n_mrgl=None, n_div=None,
        n_liqc=None, n_pl=None, n_pvp=None, n_eveb=None, n_crsc=None,
        qualid=None, saude=None, valuat=None, consist=None,
        score_f=None, pct_f=None,
    )
    asset = ScoredAsset(
        ticker=ticker, fund=fund, tendencia=None, timing=None, sinal=None,
        score_t=None, score_c=None, iv_hv=None,
        technicals=TechnicalInput(
            preco=spot, mm200=None, ifr=None, boll_inf=None, iv=None, hv=None,
        ),
    )
    quote = PutQuote(
        due_date=date(2026, 9, 18), strike=40.0, bid=None, ask=None,
        delta=None, poe=None, volume=1, last=option_last, symbol=option,
    )
    return Snapshot(
        generated_at=generated_at, stamps=[], assets=[asset],
        lists=Lists(fundamentalista=[], tecnico=[], combinado=[]),
        fundamentus_rows=[], chains={ticker: [quote]},
    )


def _seed_user_and_put(client: TestClient):
    reg = client.post(
        "/api/carteira/auth/register",
        json={"username": "summary", "password": "senha-pessoal-123"},
    )
    csrf = reg.json()["csrf_token"]
    body = {
        "sale_date": "2026-08-01", "underlying_ticker": "PETR4",
        "option_ticker": "PETRU400", "option_kind": "put", "quantity": 100,
        "strike_cents": 4000, "expiry_date": "2026-09-18",
        "premium_per_share_cents": 80, "status": "open",
        "close_cost_per_share_cents": None, "repurchase_date": None,
    }
    assert client.post(
        "/api/carteira/operations", json=body,
        headers={"X-CSRF-Token": csrf},
    ).status_code == 201


def test_summary_keeps_risk_but_marks_missing_market_data(tmp_path: Path):
    client = TestClient(create_app(data_dir=tmp_path))
    _seed_user_and_put(client)
    summary = client.get("/api/carteira/summary?year=2026").json()
    assert summary["put_capital_at_risk_cents"] == 400_000
    assert summary["open_operations"][0]["option_price_cents"] is None
    assert summary["open_operations"][0]["open_profit_cents"] is None
    assert set(summary["missing_quotes"]) == {"PETR4", "PETRU400"}


def test_summary_reads_existing_snapshot_without_scraping(tmp_path: Path):
    snap = _make_summary_snapshot(
        generated_at=datetime(2026, 8, 30, 16, tzinfo=TZ),
        ticker="PETR4", spot=41.75, option="PETRU400", option_last=0.30,
    )
    write_snapshot(snap, tmp_path / "snapshots/current.json", tmp_path / "history", False)
    client = TestClient(create_app(data_dir=tmp_path))
    _seed_user_and_put(client)
    summary = client.get("/api/carteira/summary?year=2026").json()
    opened = summary["open_operations"][0]
    assert opened["underlying_price_cents"] == 4175
    assert opened["option_price_cents"] == 30
    assert opened["open_profit_cents"] == 5000
    assert summary["market_generated_at"].startswith("2026-08-30")
