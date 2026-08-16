from datetime import date
from typing import Optional

from venda_de_put.models import Lists, PutQuote, StrikePick

DELTA_FLOOR = -0.45
MAX_CHAIN_DAYS = 120


def recommended_tickers(lists: Lists) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for row in (*lists.combinado, *lists.tecnico, *lists.fundamentalista):
        if row.ticker in seen:
            continue
        seen.add(row.ticker)
        out.append(row.ticker)
    return out


def _empty(status: str, due_date: date) -> StrikePick:
    return StrikePick(
        status=status,
        due_date=due_date,
        strike=None,
        bid=None,
        bid_pct=None,
        ask=None,
        distancia_pct=None,
        delta=None,
        poe=None,
        volume=None,
        last=None,
        last_pct=None,
        symbol=None,
    )


def _premio_pct(put: PutQuote) -> Optional[float]:
    if put.last is None or put.last <= 0 or put.strike <= 0:
        return None
    if put.volume is None or put.volume <= 0:
        return None
    return put.last / put.strike


def _pick(put: PutQuote, status: str, spot: float) -> StrikePick:
    last_pct = _premio_pct(put)
    dist = None if spot <= 0 else (spot - put.strike) / spot
    return StrikePick(
        status=status,
        due_date=put.due_date,
        strike=put.strike,
        bid=put.bid,
        bid_pct=last_pct,
        ask=put.ask,
        distancia_pct=dist,
        delta=put.delta,
        poe=put.poe,
        volume=put.volume,
        last=put.last,
        last_pct=last_pct,
        symbol=put.symbol,
    )


def select_strike(
    puts: list[PutQuote],
    due_date: date,
    spot: Optional[float],
    premio_alvo: float,
) -> StrikePick:
    series = [p for p in puts if p.due_date == due_date]
    if not series or spot is None or spot <= 0:
        return _empty("sem_serie", due_date)

    with_last = [p for p in series if _premio_pct(p) is not None]
    if not with_last:
        return _empty("sem_liquidez", due_date)

    def otm_ok_delta(p: PutQuote) -> bool:
        if p.strike >= spot:
            return False
        if p.delta is not None and p.delta < DELTA_FLOOR:
            return False
        return True

    candidates = [p for p in with_last if otm_ok_delta(p)]
    if not candidates:
        return _empty("sem_liquidez", due_date)

    meeting = [p for p in candidates if _premio_pct(p) >= premio_alvo]
    if meeting:
        chosen = min(meeting, key=lambda p: p.strike)
        return _pick(chosen, "ok", spot)

    best = max(candidates, key=lambda p: _premio_pct(p) or -1.0)
    return _pick(best, "abaixo_da_meta", spot)
