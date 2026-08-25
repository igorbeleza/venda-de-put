from __future__ import annotations

import io
import time
import zipfile
from datetime import date, datetime
from pathlib import Path

import httpx

from venda_de_put.models import CandleSeries
from venda_de_put.sources.types import USER_AGENT
from venda_de_put.tz import TZ

COTAHIST_URL = "https://bvmf.bmfbovespa.com.br/InstDados/SerHist/COTAHIST_A{year}.ZIP"
CURRENT_YEAR_MAX_AGE = 86400.0


def parse_cotahist_line(line: str) -> tuple[date, str, float] | None:
    if len(line) < 121:
        return None
    if line[0:2] != "01" or line[10:12] != "02" or line[24:27] != "010":
        return None
    raw_date = line[2:10]
    ticker = line[12:24].strip()
    raw_px = line[108:121]
    try:
        d = date(int(raw_date[0:4]), int(raw_date[4:6]), int(raw_date[6:8]))
        px = int(raw_px) / 100.0
    except (TypeError, ValueError):
        return None
    if not ticker:
        return None
    return d, ticker, px


def parse_cotahist_text(text: str, tickers: list[str]) -> dict[str, list[tuple[date, float]]]:
    wanted = set(tickers)
    out: dict[str, list[tuple[date, float]]] = {t: [] for t in tickers}
    for line in text.splitlines():
        row = parse_cotahist_line(line)
        if row is None:
            continue
        d, ticker, px = row
        if ticker in wanted:
            out[ticker].append((d, px))
    for ticker in list(out):
        if not out[ticker]:
            del out[ticker]
        else:
            out[ticker].sort(key=lambda x: x[0])
    return out


def _ts(d: date) -> int:
    return int(datetime(d.year, d.month, d.day, 18, 0, tzinfo=TZ).timestamp())


class CotahistBootstrap:
    def __init__(self, cache_dir: Path, client: httpx.Client | None = None, now: datetime | None = None) -> None:
        self._cache = Path(cache_dir)
        self._client = client
        self._owns = client is None
        self._now = now or datetime.now(TZ)

    def fetch_history(self, tickers: list[str]) -> dict[str, CandleSeries]:
        if not tickers:
            return {}
        year = self._now.astimezone(TZ).year
        texts: list[str] = []
        for current_year in (year - 1, year):
            raw = self._zip_bytes(current_year)
            if not raw:
                continue
            try:
                texts.append(self._read_zip(raw))
            except Exception:
                continue
        merged: dict[str, list[tuple[date, float]]] = {}
        for text in texts:
            for ticker, rows in parse_cotahist_text(text, tickers).items():
                merged.setdefault(ticker, []).extend(rows)
        out: dict[str, CandleSeries] = {}
        for ticker, rows in merged.items():
            rows.sort(key=lambda x: x[0])
            closes = [price for _, price in rows]
            if not closes:
                continue
            out[ticker] = CandleSeries(
                ticker=ticker,
                closes=closes,
                preco=closes[-1],
                max_52=max(closes),
                min_52=min(closes),
                collected_at=self._now,
                timestamps=[_ts(d) for d, _ in rows],
            )
        return out

    def _zip_bytes(self, year: int) -> bytes | None:
        path = self._cache / f"COTAHIST_A{year}.ZIP"
        current = self._now.astimezone(TZ).year
        if path.is_file():
            age = time.time() - path.stat().st_mtime
            if year != current or age <= CURRENT_YEAR_MAX_AGE:
                return path.read_bytes()
        url = COTAHIST_URL.format(year=year)
        client = self._client or httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=60.0)
        try:
            response = client.get(url, headers={"User-Agent": USER_AGENT}, timeout=60.0)
            response.raise_for_status()
            if not zipfile.is_zipfile(io.BytesIO(response.content)):
                if path.is_file():
                    return path.read_bytes()
                return None
            self._cache.mkdir(parents=True, exist_ok=True)
            path.write_bytes(response.content)
            return response.content
        except Exception:
            if path.is_file():
                return path.read_bytes()
            return None
        finally:
            if self._owns and self._client is None:
                client.close()

    def _read_zip(self, raw: bytes) -> str:
        if not zipfile.is_zipfile(io.BytesIO(raw)):
            raise zipfile.BadZipFile("not a zip")
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            names = zf.namelist()
            if not names:
                raise zipfile.BadZipFile("empty zip")
            data = zf.read(names[0])
        try:
            return data.decode("latin-1")
        except Exception:
            return data.decode("utf-8", errors="replace")
