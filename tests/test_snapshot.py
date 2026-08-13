from datetime import datetime
from pathlib import Path

from venda_de_put.config import AppConfig
from venda_de_put.models import SourceStamp
from venda_de_put.snapshot import is_stale, write_snapshot
from venda_de_put.tz import TZ

from test_scrape import _petr_inputs
from venda_de_put.scrape import run_scrape


def test_is_stale_before_due_scrape():
    cfg = AppConfig()
    now = datetime(2026, 8, 13, 16, 30, tzinfo=TZ)
    stamps = [
        SourceStamp(
            source="yahoo",
            collected_at=datetime(2026, 8, 13, 11, 0, tzinfo=TZ),
            ok=True,
            error=None,
            stale=False,
        )
    ]
    assert is_stale(stamps, now, cfg, holidays=set()) is True


def test_is_stale_false_when_fresh():
    cfg = AppConfig()
    now = datetime(2026, 8, 13, 16, 30, tzinfo=TZ)
    stamps = [
        SourceStamp(
            source="yahoo",
            collected_at=datetime(2026, 8, 13, 16, 0, tzinfo=TZ),
            ok=True,
            error=None,
            stale=False,
        )
    ]
    assert is_stale(stamps, now, cfg, holidays=set()) is False


def test_history_copied_near_1600(tmp_path: Path):
    price, iv, fund, universe, now = _petr_inputs()
    snap = run_scrape(price, iv, fund, AppConfig(), universe, set(), now)
    hist = tmp_path / "history"
    write_snapshot(snap, tmp_path / "current.json", hist, archive_if_1600=True)
    assert (hist / "2026-08-15.json").is_file()
