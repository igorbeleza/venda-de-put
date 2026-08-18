from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from venda_de_put.auth import (
    SESSION_MAX_AGE_SECONDS,
    check_password,
    create_session_token,
    verify_session_token,
)

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
from venda_de_put.paths import data_dir as resolve_data_dir
from venda_de_put.paths import snapshot_current, snapshot_history
from venda_de_put.premium import premio_alvo
from venda_de_put.scoring import apply_technical, build_lists, score_fundamentals
from venda_de_put.strike import select_strike
from venda_de_put.scrape_progress import (
    STEPS,
    begin_progress,
    fail_running,
    passos_from_stamps,
    progress_path,
    read_progress,
    retry_from,
    retry_is_full,
    start_retry,
)
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


_CALENDAR_THROUGH_DEFAULT = date(2027, 12, 31)  # usado se calendario_ate no config estiver ilegivel


def _calendar(app: FastAPI, today: Optional[date] = None) -> list[Vencimento]:
    today = today or datetime.now(TZ).date()
    holidays = load_holidays(app.state.feriados_path) if app.state.feriados_path.is_file() else set()
    cfg = load_config(app.state.config_path) if app.state.config_path.is_file() else AppConfig()
    try:
        through = date.fromisoformat(cfg.calendario_ate)
    except (TypeError, ValueError):
        through = _CALENDAR_THROUGH_DEFAULT
    return build_calendar(today, holidays, through)


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
        "roe": None if row is None else row.roe,
        "pl": None if row is None else row.pl,
        "pvp": None if row is None else row.pvp,
        "dy": None if row is None else row.dy,
        "tendencia": a.tendencia,
        "timing": a.timing,
        "sinal": a.sinal,
        "score_t": a.score_t,
        "score_c": a.score_c,
        "iv_hv": a.iv_hv,
        "iv": None if a.technicals is None else a.technicals.iv,
        "hv": None if a.technicals is None else a.technicals.hv,
        "iv_rank": None if a.technicals is None else a.technicals.iv_rank,
        "iv_percentile": None if a.technicals is None else a.technicals.iv_percentile,
        "technicals": tech,
        "preco": None if a.technicals is None else a.technicals.preco,
        "ifr": None if a.technicals is None else a.technicals.ifr,
        "boll_inf": None if a.technicals is None else a.technicals.boll_inf,
        "mm200": None if a.technicals is None else a.technicals.mm200,
        **fund,
    }


def _strike_fields(pick) -> dict:
    return {
        "strike": pick.strike,
        "premio_bid": pick.last,
        "premio_bid_pct": pick.last_pct,
        "premio_ask": pick.ask,
        "option_symbol": pick.symbol,
        "distancia_pct": pick.distancia_pct,
        "delta": pick.delta,
        "poe": pick.poe,
        "strike_status": pick.status,
    }


def _empty_passos() -> list[dict]:
    return [{"id": sid, "label": label, "status": "pendente", "erro": None} for sid, label in STEPS]


def _scrape_passos(app: FastAPI) -> list[dict]:
    progress = read_progress(app.state.progress_path)
    if progress and progress.get("passos"):
        return progress["passos"]
    snap = app.state.snapshot
    if snap is None and app.state.snapshot_path.is_file():
        try:
            snap = read_snapshot(app.state.snapshot_path)
        except Exception:
            snap = None
    if snap is not None:
        return passos_from_stamps(snap.stamps)
    return _empty_passos()


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
        chains=snap.chains,
    )


def require_admin(request: Request) -> None:
    token = request.cookies.get("session")
    if not token or not verify_session_token(token):
        raise HTTPException(401, "não autorizado")


def create_app(data_dir: Path) -> FastAPI:
    data_dir = Path(data_dir)
    app = FastAPI()
    app.state.data_dir = data_dir
    app.state.snapshot_path = snapshot_current(data_dir)
    app.state.config_path = data_dir / "config.json"
    app.state.feriados_path = data_dir / "feriados.json"
    app.state.universe_path = data_dir / "universe.json"
    app.state.history_dir = snapshot_history(data_dir)
    app.state.snapshot: Optional[Snapshot] = None
    app.state.snapshot_mtime: Optional[float] = None
    app.state.scrape_process: Optional[subprocess.Popen] = None
    app.state.scrape_error: Optional[str] = None
    app.state.progress_path = progress_path(data_dir)

    def _is_scrape_running() -> bool:
        proc = app.state.scrape_process
        return proc is not None and proc.poll() is None

    def _wait_for_scrape(process: subprocess.Popen) -> None:
        try:
            stdout, stderr = process.communicate()
            if process.returncode != 0:
                app.state.scrape_error = (stderr or "").strip() or f"processo saiu com código {process.returncode}"
                fail_running(app.state.progress_path, app.state.scrape_error)
            else:
                app.state.scrape_error = None
                if app.state.snapshot_path.is_file():
                    app.state.snapshot = read_snapshot(app.state.snapshot_path)
                    app.state.snapshot_mtime = app.state.snapshot_path.stat().st_mtime
        except Exception as e:
            app.state.scrape_error = str(e)

    legacy = data_dir / "current.json"
    if not app.state.snapshot_path.is_file() and legacy.is_file():
        write_snapshot(
            read_snapshot(legacy),
            app.state.snapshot_path,
            app.state.history_dir,
            archive_if_1600=False,
        )

    def get_snap() -> Snapshot:
        path = app.state.snapshot_path
        if not path.is_file():
            raise HTTPException(404, "snapshot ausente")
        mtime = path.stat().st_mtime
        if app.state.snapshot is None or app.state.snapshot_mtime != mtime:
            app.state.snapshot = read_snapshot(path)
            app.state.snapshot_mtime = mtime
        return app.state.snapshot

    def persist_snap(snap: Snapshot) -> None:
        write_snapshot(snap, app.state.snapshot_path, app.state.history_dir, archive_if_1600=False)
        app.state.snapshot = snap
        if app.state.snapshot_path.is_file():
            app.state.snapshot_mtime = app.state.snapshot_path.stat().st_mtime

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
        def with_strike(a):
            row = _enrich_asset(a, universe, by_fund)
            pick = select_strike(
                snap.chains.get(a.ticker, []),
                v.efetivo,
                row.get("preco"),
                premio,
            )
            row.update(_strike_fields(pick))
            return row

        listas = {
            "fundamentalista": [with_strike(a) for a in snap.lists.fundamentalista],
            "tecnico": [with_strike(a) for a in snap.lists.tecnico],
            "combinado": [with_strike(a) for a in snap.lists.combinado],
        }
        return {
            "listas": listas,
            "premio_alvo": premio,
            "meta_premio_30d": cfg.meta_premio_30d,
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
                for k in list(it):
                    if k.startswith("n_"):
                        it.pop(k, None)
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
    def put_config(body: dict, request: Request):
        require_admin(request)
        if not isinstance(body, dict):
            raise HTTPException(400, "objeto de config esperado")
        required_num = {
            "ifr_min": float,
            "ifr_max": float,
            "folga": float,
            "meta_premio_30d": float,
            "mm_periodos": int,
            "ifr_periodos": int,
            "boll_periodos": int,
            "boll_desvios": float,
            "hv_periodos": int,
        }
        parsed: dict[str, Any] = {}
        for key, caster in required_num.items():
            if key not in body:
                raise HTTPException(400, f"campo obrigatório ausente: {key}")
            try:
                parsed[key] = caster(body[key])
            except (TypeError, ValueError):
                raise HTTPException(400, f"campo não numérico: {key}") from None
        calendario_ate_raw = body.get("calendario_ate", "2027-12-31")
        try:
            calendario_ate_date = date.fromisoformat(str(calendario_ate_raw)[:10])
        except (TypeError, ValueError):
            raise HTTPException(400, "campo calendario_ate sem data parseável") from None
        if calendario_ate_date < datetime.now(TZ).date():
            raise HTTPException(400, "calendario_ate não pode ser no passado")
        cfg = AppConfig(
            ifr_min=parsed["ifr_min"],
            ifr_max=parsed["ifr_max"],
            folga=parsed["folga"],
            meta_premio_30d=parsed["meta_premio_30d"],
            mm_periodos=parsed["mm_periodos"],
            mm_tipo=body.get("mm_tipo", "sma"),
            ifr_periodos=parsed["ifr_periodos"],
            boll_periodos=parsed["boll_periodos"],
            boll_desvios=parsed["boll_desvios"],
            hv_periodos=parsed["hv_periodos"],
            scrape_times=tuple(body.get("scrape_times", ("11:00", "13:00", "16:00"))),
            fundamentus_days=tuple(body.get("fundamentus_days", (1, 15))),
            fundamentus_time=body.get("fundamentus_time", "07:00"),
            calendario_ate=calendario_ate_date.isoformat(),
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
        require_admin(request)
        body = await request.json()
        items = body.get("feriados") if isinstance(body, dict) and "feriados" in body else body
        if not isinstance(items, list):
            raise HTTPException(400, "lista de feriados esperada")
        for item in items:
            raw = item.get("date") if isinstance(item, dict) else item
            try:
                date.fromisoformat(str(raw)[:10])
            except (TypeError, ValueError):
                raise HTTPException(400, "feriado sem date parseável") from None
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

    web_dir = Path(__file__).resolve().parent
    static_dir = web_dir / "static"
    templates_dir = web_dir / "templates"
    if static_dir.is_dir():
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.middleware("http")
    async def no_cache_frontend(request: Request, call_next):
        response = await call_next(request)
        if request.url.path == "/" or request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-cache"
        return response

    @app.get("/")
    def home():
        return FileResponse(templates_dir / "index.html")

    @app.post("/api/login")
    def login(body: dict, request: Request, response: Response):
        if not isinstance(body, dict) or not isinstance(body.get("password"), str):
            raise HTTPException(400, "campo 'password' esperado")
        if not check_password(body["password"]):
            raise HTTPException(401, "senha incorreta")
        token = create_session_token()
        response.set_cookie(
            key="session",
            value=token,
            httponly=True,
            samesite="lax",
            secure=(request.url.scheme == "https"),
            max_age=SESSION_MAX_AGE_SECONDS,
        )
        return {"admin": True}

    @app.post("/api/logout")
    def logout(request: Request, response: Response):
        response.delete_cookie(
            key="session",
            httponly=True,
            samesite="lax",
            secure=(request.url.scheme == "https"),
        )
        return {"admin": False}

    @app.get("/api/me")
    def me(request: Request):
        token = request.cookies.get("session")
        return {"admin": bool(token and verify_session_token(token))}

    @app.post("/api/scrape")
    async def post_scrape(
        request: Request,
        background_tasks: BackgroundTasks,
    ):
        require_admin(request)

        incluir_fundamentus = None
        passo = None
        try:
            body = await request.json()
            if isinstance(body, dict):
                if "incluir_fundamentus" in body:
                    incluir_fundamentus = body["incluir_fundamentus"]
                if isinstance(body.get("passo"), str) and body["passo"].strip():
                    passo = body["passo"].strip()
        except Exception:
            pass

        if passo is not None:
            try:
                retry_from(passo)
            except ValueError:
                raise HTTPException(400, "passo desconhecido")

        if _is_scrape_running():
            raise HTTPException(409, "raspagem já em andamento")

        gen_at = None
        if app.state.snapshot_path.is_file():
            try:
                gen_at = get_snap().generated_at
            except Exception:
                gen_at = None
        if passo is not None and retry_is_full(gen_at, datetime.now(TZ)):
            passo = None

        cmd = [
            sys.executable,
            "-m",
            "venda_de_put",
            "scrape",
            "--data-dir",
            str(app.state.data_dir),
        ]
        if passo is not None:
            cmd.extend(["--from-step", passo])
        if incluir_fundamentus is True:
            cmd.extend(["--force-fundamentus", "true"])
        elif incluir_fundamentus is False:
            cmd.extend(["--force-fundamentus", "false"])

        app.state.scrape_error = None
        if passo is not None:
            start_retry(app.state.progress_path, retry_from(passo))
        else:
            begin_progress(app.state.progress_path)
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        app.state.scrape_process = proc
        background_tasks.add_task(_wait_for_scrape, proc)
        return {"status": "running"}

    @app.get("/api/scrape/status")
    def scrape_status(request: Request):
        require_admin(request)
        running = _is_scrape_running()
        status = "running" if running else "idle"
        gen_at = None
        snap_at = None
        if app.state.snapshot_path.is_file():
            try:
                snap = get_snap()
                snap_at = snap.generated_at
                gen_at = snap.generated_at.isoformat()
            except Exception:
                pass
        return {
            "status": status,
            "generated_at": gen_at,
            "erro": app.state.scrape_error,
            "passos": _scrape_passos(app),
            "retry_completo": retry_is_full(snap_at, datetime.now(TZ)),
        }

    @app.post("/api/refresh")
    def refresh():
        if not app.state.snapshot_path.is_file():
            raise HTTPException(404, "snapshot ausente")
        app.state.snapshot = read_snapshot(app.state.snapshot_path)
        if app.state.snapshot_path.is_file():
            app.state.snapshot_mtime = app.state.snapshot_path.stat().st_mtime
        snap = app.state.snapshot
        return {
            "generated_at": snap.generated_at.isoformat(),
            "stamps": [_stamp_out(s) for s in snap.stamps],
            "coletado": snap.generated_at.isoformat(),
        }

    return app


def cli_serve(
    host: str = "127.0.0.1",
    port: int = 8765,
    data_dir: Path | str | None = None,
) -> int:
    import uvicorn

    app = create_app(resolve_data_dir(data_dir))
    uvicorn.run(app, host=host, port=port)
    return 0
