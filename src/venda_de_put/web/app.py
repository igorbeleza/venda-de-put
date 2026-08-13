from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Query, Request

from venda_de_put.calendar_b3 import (
    build_calendar,
    default_vencimento,
    load_holidays,
    weekday_pt,
)
from venda_de_put.config import load_config, save_config
from venda_de_put.models import (
    AppConfig,
    AssetInput,
    Fundamentals,
    ScoredAsset,
    Snapshot,
    TechnicalInput,
    Vencimento,
)
from venda_de_put.premium import premio_alvo
from venda_de_put.scoring import apply_technical, build_lists, score_fundamentals
from venda_de_put.snapshot import is_stale, read_snapshot, snapshot_to_dict, write_snapshot
from venda_de_put.tz import TZ

_INSTRUCOES = (
    "Ferramenta de seleção para venda de put coberta por critério próprio.\n"
    "Timing de entrada: IFR (RSI Wilder) entre 10 e 50, com preço na ou abaixo "
    "da banda inferior de Bollinger (com folga configurável).\n"
    "Tendência: preço acima da média móvel de 200 períodos.\n"
    "Prêmio-alvo escala a meta de 30 dias pela raiz do prazo até o vencimento.\n"
    "Os dados vêm do snapshot em disco (Yahoo, OpLab, Fundamentus), "
    "relido no botão Atualizar — sem terminal de corretora.\n"
)


def label_vencimento(v: Vencimento) -> str:
    dia = v.efetivo.strftime("%d/%m/%Y")
    wd = weekday_pt(v.efetivo, curto=True)
    return (
        f"{dia} · {wd} · {v.dias_corridos} dias corridos · "
        f"{v.dias_uteis} úteis · {v.tipo}"
    )


def _jsonable(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, date):
        return obj.isoformat()
    if is_dataclass(obj):
        return {k: _jsonable(v) for k, v in asdict(obj).items()}
    if isinstance(obj, list):
        return [_jsonable(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, tuple):
        return [_jsonable(x) for x in obj]
    return obj


def _load_universe(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _load_feriados_raw(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def _calendar(app: FastAPI, today: Optional[date] = None) -> list[Vencimento]:
    today = today or datetime.now(TZ).date()
    holidays = load_holidays(app.state.feriados_path) if app.state.feriados_path.is_file() else set()
    return build_calendar(today, holidays, today + timedelta(days=400))


def _pick_vencimento(
    rows: list[Vencimento],
    vencimento: Optional[str],
    so_mensais: bool,
) -> Vencimento:
    if vencimento:
        target = date.fromisoformat(vencimento)
        for row in rows:
            if row.efetivo == target or row.nominal == target:
                return row
    return default_vencimento(rows, so_mensais=so_mensais)


def _enrich_asset(a: ScoredAsset, universe: dict[str, str], by_fund: dict[str, Fundamentals]) -> dict:
    row = by_fund.get(a.ticker)
    fund = _jsonable(a.fund)
    tech = _jsonable(a.technicals) if a.technicals else {}
    return {
        "ticker": a.ticker,
        "grupo": universe.get(a.ticker, ""),
        "fund": fund,
        "score_f": a.fund.score_f,
        "pct_f": a.fund.pct_f,
        "roe": a.fund.n_roe,  # ranks live under fund; raw roe from fundamentus
        "pl": None if row is None else row.pl,
        "pvp": None if row is None else row.pvp,
        "dy": None if row is None else row.dy,
        "tendencia": a.tendencia,
        "timing": a.timing,
        "sinal": a.sinal,
        "score_t": a.score_t,
        "score_c": a.score_c,
        "iv_hv": a.iv_hv,
        "technicals": tech,
        "preco": None if a.technicals is None else a.technicals.preco,
        "ifr": None if a.technicals is None else a.technicals.ifr,
        "boll_inf": None if a.technicals is None else a.technicals.boll_inf,
        "mm200": None if a.technicals is None else a.technicals.mm200,
        **fund,
    }


def _stamp_out(s) -> dict:
    return {
        "source": s.source,
        "collected_at": s.collected_at.isoformat(),
        "ok": s.ok,
        "error": s.error,
        "stale": s.stale,
    }


def _recalc(snap: Snapshot, cfg: AppConfig, universe: dict[str, str]) -> Snapshot:
    by_fund = {r.ticker: r for r in snap.fundamentus_rows}
    inputs: list[AssetInput] = []
    tech_by = {a.ticker: a.technicals for a in snap.assets}
    tickers = list(universe.keys()) if universe else [a.ticker for a in snap.assets]
    grupos = universe or {a.ticker: "" for a in snap.assets}
    for ticker in tickers:
        row = by_fund.get(ticker)
        inputs.append(
            AssetInput(
                ticker=ticker,
                grupo=grupos.get(ticker, ""),
                pl=None if row is None else row.pl,
                pvp=None if row is None else row.pvp,
                ev_ebitda=None if row is None else row.ev_ebitda,
                mrg_liq=None if row is None else row.mrg_liq,
                liq_corr=None if row is None else row.liq_corr,
                roic=None if row is None else row.roic,
                roe=None if row is None else row.roe,
                div_pat=None if row is None else row.div_liq_patrim,
                cresc=None if row is None else row.cresc_rec_5a,
            )
        )
    funds = score_fundamentals(inputs)
    assets = []
    for fund in funds:
        tech = tech_by.get(fund.ticker)
        if tech is None:
            tech = TechnicalInput(None, None, None, None, None, None)
        assets.append(apply_technical(fund, tech, cfg))
    lists = build_lists(assets)
    return Snapshot(
        generated_at=snap.generated_at,
        stamps=snap.stamps,
        assets=assets,
        lists=lists,
        fundamentus_rows=snap.fundamentus_rows,
    )


def create_app(data_dir: Path) -> FastAPI:
    data_dir = Path(data_dir)
    app = FastAPI()
    app.state.data_dir = data_dir
    app.state.snapshot_path = data_dir / "current.json"
    if not app.state.snapshot_path.is_file() and (data_dir / "snapshots" / "current.json").is_file():
        app.state.snapshot_path = data_dir / "snapshots" / "current.json"
    app.state.config_path = data_dir / "config.json"
    app.state.feriados_path = data_dir / "feriados.json"
    app.state.universe_path = data_dir / "universe.json"
    app.state.history_dir = data_dir / "history"
    app.state.snapshot: Optional[Snapshot] = None

    def get_snap() -> Snapshot:
        if app.state.snapshot is None:
            if not app.state.snapshot_path.is_file():
                raise HTTPException(404, "snapshot ausente")
            app.state.snapshot = read_snapshot(app.state.snapshot_path)
        return app.state.snapshot

    def persist_snap(snap: Snapshot) -> None:
        app.state.snapshot = snap
        write_snapshot(snap, app.state.snapshot_path, app.state.history_dir, archive_if_1600=False)

    @app.get("/api/dashboard")
    def dashboard(
        vencimento: Optional[str] = None,
        so_mensais: int = Query(default=1),
    ):
        snap = get_snap()
        cfg = load_config(app.state.config_path) if app.state.config_path.is_file() else AppConfig()
        universe = _load_universe(app.state.universe_path)
        by_fund = {r.ticker: r for r in snap.fundamentus_rows}
        holidays = load_holidays(app.state.feriados_path) if app.state.feriados_path.is_file() else set()
        rows = _calendar(app)
        v = _pick_vencimento(rows, vencimento, bool(so_mensais))
        premio = premio_alvo(cfg.meta_premio_30d, v.dias_corridos)
        stale = is_stale(snap.stamps, datetime.now(TZ), cfg, holidays)
        listas = {
            "fundamentalista": [_enrich_asset(a, universe, by_fund) for a in snap.lists.fundamentalista],
            "tecnico": [_enrich_asset(a, universe, by_fund) for a in snap.lists.tecnico],
            "combinado": [_enrich_asset(a, universe, by_fund) for a in snap.lists.combinado],
        }
        return {
            "listas": listas,
            "premio_alvo": premio,
            "vencimento": {
                "efetivo": v.efetivo.isoformat(),
                "nominal": v.nominal.isoformat(),
                "label": label_vencimento(v),
                "tipo": v.tipo,
                "dias_corridos": v.dias_corridos,
                "dias_uteis": v.dias_uteis,
            },
            "stamps": [_stamp_out(s) for s in snap.stamps],
            "stale": stale,
            "generated_at": snap.generated_at.isoformat(),
        }

    @app.get("/api/ativos")
    def ativos(calculo: int = 0):
        snap = get_snap()
        universe = _load_universe(app.state.universe_path)
        by_fund = {r.ticker: r for r in snap.fundamentus_rows}
        items = [_enrich_asset(a, universe, by_fund) for a in snap.assets]
        if not calculo:
            for it in items:
                for k in list(it.get("fund", {})):
                    if k.startswith("n_"):
                        it["fund"].pop(k, None)
        return {"ativos": items, "total": len(items)}

    @app.get("/api/dados")
    def dados():
        snap = get_snap()
        stamp = next((s for s in snap.stamps if s.source == "fundamentus"), None)
        return {
            "rows": [_jsonable(r) for r in snap.fundamentus_rows],
            "carimbo": None if stamp is None else _stamp_out(stamp),
            "generated_at": snap.generated_at.isoformat(),
        }

    @app.get("/api/setores")
    def setores():
        snap = get_snap()
        universe = _load_universe(app.state.universe_path)
        by_grupo: dict[str, list[float]] = {}
        counts: dict[str, int] = {}
        for a in snap.assets:
            g = universe.get(a.ticker, "")
            counts[g] = counts.get(g, 0) + 1
            if a.fund.score_f is not None:
                by_grupo.setdefault(g, []).append(a.fund.score_f)
        grupos = sorted(set(universe.values()) | set(counts))
        out = []
        for g in grupos:
            vals = by_grupo.get(g, [])
            out.append({
                "grupo": g,
                "contagem": counts.get(g, 0),
                "score_f_medio": (sum(vals) / len(vals)) if vals else None,
            })
        return {"setores": out}

    @app.get("/api/config")
    def get_config():
        cfg = load_config(app.state.config_path) if app.state.config_path.is_file() else AppConfig()
        return _jsonable(cfg)

    @app.put("/api/config")
    def put_config(body: dict):
        cfg = AppConfig(
            ifr_min=body.get("ifr_min", 10),
            ifr_max=body.get("ifr_max", 50),
            folga=body.get("folga", 0.05),
            meta_premio_30d=body.get("meta_premio_30d", 0.0115),
            mm_periodos=body.get("mm_periodos", 200),
            mm_tipo=body.get("mm_tipo", "sma"),
            ifr_periodos=body.get("ifr_periodos", 14),
            boll_periodos=body.get("boll_periodos", 20),
            boll_desvios=body.get("boll_desvios", 2.0),
            hv_periodos=body.get("hv_periodos", 21),
            scrape_times=tuple(body.get("scrape_times", ("11:00", "13:00", "16:00"))),
            fundamentus_days=tuple(body.get("fundamentus_days", (1, 15))),
            fundamentus_time=body.get("fundamentus_time", "07:00"),
        )
        save_config(cfg, app.state.config_path)
        snap = get_snap()
        universe = _load_universe(app.state.universe_path)
        persist_snap(_recalc(snap, cfg, universe))
        return _jsonable(cfg)

    @app.get("/api/vencimentos")
    def vencimentos(so_mensais: int = 0):
        rows = _calendar(app)
        if so_mensais:
            rows = [r for r in rows if r.tipo == "MENSAL"]
        return {
            "vencimentos": [
                {
                    **_jsonable(r),
                    "label": label_vencimento(r),
                }
                for r in rows
            ]
        }

    @app.get("/api/feriados")
    def get_feriados():
        return _load_feriados_raw(app.state.feriados_path)

    @app.put("/api/feriados")
    async def put_feriados(request: Request):
        body = await request.json()
        items = body.get("feriados") if isinstance(body, dict) and "feriados" in body else body
        if not isinstance(items, list):
            raise HTTPException(400, "lista de feriados esperada")
        app.state.feriados_path.write_text(
            json.dumps(items, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return items

    @app.get("/api/instrucoes")
    def instrucoes():
        md = Path(__file__).with_name("instrucoes.md")
        if md.is_file():
            texto = md.read_text(encoding="utf-8")
        else:
            texto = _INSTRUCOES
        return {"texto": texto}

    @app.post("/api/refresh")
    def refresh():
        if not app.state.snapshot_path.is_file():
            raise HTTPException(404, "snapshot ausente")
        app.state.snapshot = read_snapshot(app.state.snapshot_path)
        snap = app.state.snapshot
        return {
            "generated_at": snap.generated_at.isoformat(),
            "stamps": [_stamp_out(s) for s in snap.stamps],
            "coletado": snap.generated_at.isoformat(),
        }

    return app


def cli_serve(host: str = "127.0.0.1", port: int = 8765) -> int:
    import argparse

    default_data = Path(__file__).resolve().parents[3] / "data"

    p = argparse.ArgumentParser(prog="venda_de_put serve")
    p.add_argument("--host", default=host)
    p.add_argument("--port", type=int, default=port)
    p.add_argument("--data-dir", type=Path, default=default_data)
    args, _ = p.parse_known_args()
    import uvicorn

    data_dir = Path(args.data_dir)
    app = create_app(data_dir)
    uvicorn.run(app, host=args.host, port=args.port)
    return 0
