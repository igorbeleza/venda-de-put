# Task 8 report

**Status:** done  
**Commit:** `11aee4d` feat: snapshot em disco e CLI de scrape com degradação por fonte

## Tests

- `tests/test_scrape.py` + `tests/test_snapshot.py`: 6 passed
- Full suite: 34 passed, 1 failed (`test_fundamentus_iso8859_and_position`) — fixture encoding, pre-existing, not this task

## What landed

- `Snapshot` / `SourceStamp` on `models.py`; `ScoredAsset.technicals`
- `run_scrape` only `.fetch()` site; previous block on source failure
- JSON UTC; history at 16:00±10 SP if stamps ok
- CLI `python -m venda_de_put scrape`; `serve` → `NotImplementedError`
- `YahooHttp`: 2 attempts per ticker, then skip that ticker

## Concerns

- Extra files vs brief add list: `models.py`, `scoring.py`, `yahoo.py`, `web/app.py` stub (needed)
- `web.app` must not import `run_scrape` (Task 10)

---

## Review fix: Yahoo empty fetch stamp

**Issue:** `YahooHttp.fetch` never raises after two failed attempts; it returns `{}`. `run_scrape` stamped Yahoo `ok=True`, so a total outage was not marked failed/stale.

**Fix (in `run_scrape`):** After `price.fetch(tickers)`, if no requested ticker is present in the result (empty dict or zero matches), stamp:

`SourceStamp(source="yahoo", ok=False, stale=True, error="no series for requested tickers")`

and keep `series` empty so previous technicals/candles reuse via existing per-ticker logic. Partial success (some tickers present) still stamps `ok=True`.

**Test:** `test_empty_yahoo_fetch_stamps_failed_and_reuses_previous` — `FakePrice.fetch` returns `{}`; previous snapshot has PETR4 IV/price; after `run_scrape`, yahoo stamp `ok` is False and PETR4 technicals from previous remain.

**Evidence:**

```
python -m pytest tests/test_scrape.py tests/test_snapshot.py -v
7 passed in 0.46s
```
