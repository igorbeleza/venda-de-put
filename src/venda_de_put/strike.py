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
    )


def _pick(put: PutQuote, status: str, spot: float) -> StrikePick:
    bid_pct = None if put.bid is None or put.strike <= 0 else put.bid / put.strike
    dist = None if spot <= 0 else (spot - put.strike) / spot
    return StrikePick(
        status=status,
        due_date=put.due_date,
        strike=put.strike,
        bid=put.bid,
        bid_pct=bid_pct,
        ask=put.ask,
        distancia_pct=dist,
        delta=put.delta,
        poe=put.poe,
        volume=put.volume,
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

    with_bid = [p for p in series if p.bid is not None and p.bid > 0]
    if not with_bid:
        return _empty("sem_liquidez", due_date)

    def otm_ok_delta(p: PutQuote) -> bool:
        if p.strike >= spot:
            return False
        if p.delta is not None and p.delta < DELTA_FLOOR:
            return False
        return True

    candidates = [p for p in with_bid if otm_ok_delta(p)]
    if not candidates:
        return _empty("sem_liquidez", due_date)

    meeting = [p for p in candidates if p.strike > 0 and (p.bid / p.strike) >= premio_alvo]
    if meeting:
        chosen = min(meeting, key=lambda p: p.strike)
        return _pick(chosen, "ok", spot)

    best = max(candidates, key=lambda p: p.bid / p.strike if p.strike > 0 else -1.0)
    return _pick(best, "abaixo_da_meta", spot)
