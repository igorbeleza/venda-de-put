"""Snapshot local só para ver os cards. Não é dado de mercado."""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

from venda_de_put.config import AppConfig
from venda_de_put.models import (
    AssetInput,
    Fundamentals,
    PutQuote,
    Snapshot,
    SourceStamp,
    TechnicalInput,
)
from venda_de_put.paths import snapshot_current, snapshot_history
from venda_de_put.scoring import apply_technical, build_lists, score_fundamentals
from venda_de_put.snapshot import write_snapshot
from venda_de_put.tz import TZ

ROOT = Path(__file__).resolve().parents[1]

# ticker: grupo, preco, mm200, ifr, boll, strike, last, symbol, pl, roe, dy, pvp
PACK = [
    ("PETR4", "Petróleo e Gás", 38.40, 36.10, 32.0, 37.80, 36.21, 0.62, "PETRU362", 5.8, 0.24, 0.11, 1.05),
    ("VALE3", "Mineração e Siderurgia", 58.90, 55.20, 28.0, 57.40, 55.18, 0.88, "VALEU551", 6.4, 0.20, 0.09, 1.15),
    ("ITUB4", "Financeiro", 34.20, 32.80, 41.0, 33.70, 32.46, 0.41, "ITUBU324", 8.1, 0.18, 0.07, 1.40),
    ("WEGE3", "Industrial", 42.10, 44.80, 46.0, 41.20, 40.00, 0.22, "WEGEU400", 28.0, 0.21, 0.015, 8.00),
    ("BBAS3", "Financeiro", 27.80, 26.40, 24.0, 27.10, 26.21, 0.38, "BBASU262", 4.9, 0.19, 0.08, 0.90),
    ("EGIE3", "Utilities (Energia/Saneamento)", 39.50, 37.20, 36.0, 38.80, 37.46, 0.51, "EGIEU374", 7.2, 0.22, 0.065, 1.80),
    ("SUZB3", "Papel e Química", 52.30, 54.90, 44.0, 51.10, 49.71, 0.18, None, 9.5, 0.13, 0.04, 1.30),
    ("PRIO3", "Petróleo e Gás", 41.20, 38.60, 29.0, 40.40, 38.97, 0.70, "PRIOU389", 6.1, 0.23, 0.02, 1.60),
    ("SBSP3", "Utilities (Energia/Saneamento)", 96.40, 91.00, 38.0, 94.80, 91.43, 1.15, "SBSPU914", 10.2, 0.17, 0.03, 1.90),
    ("RENT3", "Transporte e Logística", 44.80, 46.20, 48.0, 43.90, 42.50, 0.15, None, 14.0, 0.11, 0.025, 2.40),
    ("ABEV3", "Agro e Alimentos", 12.40, 11.80, 33.0, 12.15, 11.71, 0.19, "ABEVU117", 13.5, 0.16, 0.05, 2.10),
    ("BBSE3", "Financeiro", 33.10, 31.40, 27.0, 32.50, 31.43, 0.47, "BBSEU314", 7.8, 0.25, 0.09, 3.20),
]


def main() -> None:
    now = datetime(2026, 8, 17, 16, 5, tzinfo=TZ)
    venc_ago = date(2026, 8, 21)
    venc = date(2026, 9, 18)
    inputs = []
    fund_rows = []
    techs = {}
    chains = {}
    for t, grupo, preco, mm, ifr, boll, strike, last, sym, pl, roe, dy, pvp in PACK:
        inputs.append(AssetInput(
            ticker=t, grupo=grupo, pl=pl, pvp=pvp, ev_ebitda=5.0,
            mrg_liq=0.14, liq_corr=1.3, roic=roe * 0.8, roe=roe,
            div_pat=0.35, cresc=0.07,
        ))
        fund_rows.append(Fundamentals(
            ticker=t, cotacao=preco, pl=pl, pvp=pvp, psr=None, dy=dy,
            p_ativo=None, p_cap_giro=None, p_ebit=None, p_ativ_circ_liq=None,
            ev_ebit=None, ev_ebitda=5.0, mrg_bruta=None, mrg_ebit=None,
            mrg_liq=0.14, liq_corr=1.3, roic=roe * 0.8, roe=roe, liq_2meses=None,
            patrim_liq=None, div_liq_patrim=0.35, cresc_rec_5a=0.07,
        ))
        techs[t] = TechnicalInput(
            preco=preco, mm200=mm, ifr=ifr, boll_inf=boll,
            iv=0.34, hv=0.28, iv_rank=42, iv_percentile=0.51,
        )
        last_ago = round(last * 0.55, 2)
        chains[t] = [
            PutQuote(venc_ago, strike, last_ago, last_ago + 0.03, -0.22, 0.20, 70.0, last_ago, sym),
            PutQuote(venc, strike, last, last + 0.04, -0.27, 0.25, 110.0, last, sym),
        ]

    funds = score_fundamentals(inputs)
    assets = [apply_technical(f, techs[f.ticker], AppConfig()) for f in funds]
    lists = build_lists(assets)
    snap = Snapshot(
        generated_at=now,
        stamps=[
            SourceStamp("yahoo", now, True, None, False),
            SourceStamp("oplab", now, True, None, False),
            SourceStamp("fundamentus", now, True, None, False),
        ],
        assets=assets,
        lists=lists,
        fundamentus_rows=fund_rows,
        chains=chains,
        fundamentus_unit="fraction",
    )
    dest = snapshot_current(ROOT / "data")
    dest.parent.mkdir(parents=True, exist_ok=True)
    write_snapshot(snap, dest, snapshot_history(ROOT / "data"), archive_if_1600=False)
    print("wrote", dest)
    print("fund", [a.ticker for a in lists.fundamentalista])
    print("tec", [(a.ticker, a.sinal) for a in lists.tecnico])
    print("cmb", [a.ticker for a in lists.combinado])


if __name__ == "__main__":
    main()
