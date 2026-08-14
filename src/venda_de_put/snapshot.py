from __future__ import annotations

import json
import shutil
from dataclasses import asdict, fields, is_dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

from venda_de_put.calendar_b3 import is_business_day
from venda_de_put.models import (
    AppConfig,
    FundScore,
    Fundamentals,
    Lists,
    PutQuote,
    ScoredAsset,
    Snapshot,
    SourceStamp,
    TechnicalInput,
)
from venda_de_put.sources.fundamentus import PCT_FIELDS
from venda_de_put.tz import TZ


def _to_utc_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TZ)
    return dt.astimezone(timezone.utc).isoformat()


def _parse_dt(value: str | None) -> datetime:
    if value is None:
        return datetime.now(TZ)
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TZ)
    return dt.astimezone(TZ)


def _encode(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return _to_utc_iso(obj)
    if isinstance(obj, date):
        return obj.isoformat()
    if is_dataclass(obj):
        return {k: _encode(v) for k, v in asdict(obj).items()}
    if isinstance(obj, list):
        return [_encode(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _encode(v) for k, v in obj.items()}
    return obj


def _fund_score(d: dict) -> FundScore:
    return FundScore(**d)


def _technicals(d: dict | None) -> TechnicalInput | None:
    if d is None:
        return None
    allowed = {f.name for f in fields(TechnicalInput)}
    return TechnicalInput(**{k: d[k] for k in allowed if k in d})


def _scored(d: dict) -> ScoredAsset:
    return ScoredAsset(
        ticker=d["ticker"],
        fund=_fund_score(d["fund"]),
        tendencia=d.get("tendencia"),
        timing=d.get("timing"),
        sinal=d.get("sinal"),
        score_t=d.get("score_t"),
        score_c=d.get("score_c"),
        iv_hv=d.get("iv_hv"),
        technicals=_technicals(d.get("technicals")),
    )


def _stamp(d: dict) -> SourceStamp:
    return SourceStamp(
        source=d["source"],
        collected_at=_parse_dt(d["collected_at"]),
        ok=d["ok"],
        error=d.get("error"),
        stale=d["stale"],
    )


def _fundamentals(d: dict, *, as_points: bool) -> Fundamentals:
    data = dict(d)
    if as_points:
        for k in PCT_FIELDS:
            if data.get(k) is not None:
                data[k] = data[k] / 100.0
    return Fundamentals(**data)


def _put_quote(d: dict) -> PutQuote:
    due = d["due_date"]
    if isinstance(due, str):
        due = date.fromisoformat(due[:10])
    poe = d.get("poe")
    if poe is not None and poe > 1:
        poe = poe / 100.0
    return PutQuote(
        due_date=due,
        strike=float(d["strike"]),
        bid=d.get("bid"),
        ask=d.get("ask"),
        delta=d.get("delta"),
        poe=poe,
        volume=d.get("volume"),
    )


def snapshot_to_dict(snap: Snapshot) -> dict:
    return _encode(snap)


def snapshot_from_dict(data: dict) -> Snapshot:
    lists = data["lists"]
    raw_chains = data.get("chains") or {}
    chains = {
        ticker: [_put_quote(p) for p in (puts or [])]
        for ticker, puts in raw_chains.items()
    }
    return Snapshot(
        generated_at=_parse_dt(data["generated_at"]),
        stamps=[_stamp(s) for s in data.get("stamps", [])],
        assets=[_scored(a) for a in data.get("assets", [])],
        lists=Lists(
            fundamentalista=[_scored(a) for a in lists.get("fundamentalista", [])],
            tecnico=[_scored(a) for a in lists.get("tecnico", [])],
            combinado=[_scored(a) for a in lists.get("combinado", [])],
        ),
        fundamentus_rows=[
            _fundamentals(r, as_points=data.get("fundamentus_unit") != "fraction")
            for r in data.get("fundamentus_rows", [])
        ],
        chains=chains,
        fundamentus_unit="fraction",
    )


def write_snapshot(
    snap: Snapshot,
    current: Path,
    history_dir: Path,
    archive_if_1600: bool,
) -> None:
    current.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(snapshot_to_dict(snap), ensure_ascii=False, indent=2)
    current.write_text(payload + "\n", encoding="utf-8")
    if not archive_if_1600:
        return
    if not _should_archive(snap):
        return
    history_dir.mkdir(parents=True, exist_ok=True)
    day = snap.generated_at.astimezone(TZ).date().isoformat()
    dest = history_dir / f"{day}.json"
    shutil.copyfile(current, dest)


def _should_archive(snap: Snapshot) -> bool:
    if not all(s.ok for s in snap.stamps) and snap.stamps:
        return False
    local = snap.generated_at.astimezone(TZ)
    target = local.replace(hour=16, minute=0, second=0, microsecond=0)
    return abs((local - target).total_seconds()) <= 10 * 60


def read_snapshot(path: Path) -> Snapshot:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return snapshot_from_dict(data)


def _parse_hhmm(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


def _last_due_scrape(now: datetime, cfg: AppConfig, holidays: set[date]) -> datetime | None:
    now = now.astimezone(TZ) if now.tzinfo else now.replace(tzinfo=TZ)
    times = sorted(_parse_hhmm(t) for t in cfg.scrape_times)
    d = now.date()
    for _ in range(14):
        if is_business_day(d, holidays):
            candidates = []
            for t in times:
                dt = datetime.combine(d, t, tzinfo=TZ)
                if dt <= now:
                    candidates.append(dt)
            if candidates:
                return max(candidates)
        d = d - timedelta(days=1)
    return None


def is_stale(
    stamps: list[SourceStamp],
    now: datetime,
    cfg: AppConfig,
    holidays: set[date],
) -> bool:
    if not stamps:
        return True
    latest = max(s.collected_at for s in stamps)
    due = _last_due_scrape(now, cfg, holidays)
    if due is None:
        return False
    latest = latest.astimezone(TZ) if latest.tzinfo else latest.replace(tzinfo=TZ)
    return latest < due
