from datetime import datetime
from pathlib import Path

import pytest

from venda_de_put.config import AppConfig
from venda_de_put.models import SourceStamp
from venda_de_put.snapshot import is_stale, snapshot_from_dict, write_snapshot
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


def test_snapshot_dy_em_pontos_percentuais_vira_fracao():
    snap = snapshot_from_dict({
        "generated_at": "2026-08-13T16:00:00-03:00",
        "stamps": [],
        "assets": [],
        "lists": {"fundamentalista": [], "tecnico": [], "combinado": []},
        "fundamentus_rows": [{
            "ticker": "BBSE3",
            "cotacao": 37.56,
            "pl": 7.94,
            "pvp": 6.7,
            "psr": 0.0,
            "dy": 17.72,
            "p_ativo": 3.326,
            "p_cap_giro": 0.0,
            "p_ebit": 7.31,
            "p_ativ_circ_liq": 0.0,
            "ev_ebit": 0.0,
            "ev_ebitda": 0.0,
            "mrg_bruta": 0.0,
            "mrg_ebit": 0.0,
            "mrg_liq": 0.0,
            "liq_corr": 0.0,
            "roic": 0.0,
            "roe": 84.38,
            "liq_2meses": 242580000.0,
            "patrim_liq": 10890300000.0,
            "div_liq_patrim": 0.0,
            "cresc_rec_5a": -208.15,
        }, {
            "ticker": "BBAS3",
            "cotacao": 19.0, "pl": 7.52, "pvp": 0.6, "psr": 0.0,
            "dy": 2.89, "p_ativo": 0.0, "p_cap_giro": 0.0, "p_ebit": 0.0,
            "p_ativ_circ_liq": 0.0, "ev_ebit": 0.0, "ev_ebitda": 0.0,
            "mrg_bruta": 0.0, "mrg_ebit": 0.0, "mrg_liq": 0.0, "liq_corr": 0.0,
            "roic": 0.0, "roe": 7.99, "liq_2meses": 1.0, "patrim_liq": 1.0,
            "div_liq_patrim": 0.0, "cresc_rec_5a": -9.61,
        }],
    })
    bbse = next(r for r in snap.fundamentus_rows if r.ticker == "BBSE3")
    bbas = next(r for r in snap.fundamentus_rows if r.ticker == "BBAS3")
    assert bbse.dy == pytest.approx(0.1772)
    assert bbse.roe == pytest.approx(0.8438)
    assert bbse.cresc_rec_5a == pytest.approx(-2.0815)
    assert bbas.dy == pytest.approx(0.0289)
    assert bbas.roe == pytest.approx(0.0799)
    again = snapshot_from_dict({
        "generated_at": "2026-08-13T16:00:00-03:00",
        "stamps": [],
        "assets": [],
        "lists": {"fundamentalista": [], "tecnico": [], "combinado": []},
        "fundamentus_unit": "fraction",
        "fundamentus_rows": [{
            "ticker": "BBSE3",
            "cotacao": 37.56, "pl": 7.94, "pvp": 6.7, "psr": 0.0,
            "dy": 0.1772, "p_ativo": 3.326, "p_cap_giro": 0.0, "p_ebit": 7.31,
            "p_ativ_circ_liq": 0.0, "ev_ebit": 0.0, "ev_ebitda": 0.0,
            "mrg_bruta": 0.0, "mrg_ebit": 0.0, "mrg_liq": 0.0, "liq_corr": 0.0,
            "roic": 0.0, "roe": 1.457, "liq_2meses": 1.0, "patrim_liq": 1.0,
            "div_liq_patrim": 0.0, "cresc_rec_5a": -2.0815,
        }],
    })
    kept = again.fundamentus_rows[0]
    assert kept.dy == pytest.approx(0.1772)
    assert kept.roe == pytest.approx(1.457)
    assert kept.cresc_rec_5a == pytest.approx(-2.0815)
