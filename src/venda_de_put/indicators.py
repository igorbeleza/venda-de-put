import math
from datetime import datetime
from typing import Optional, Sequence

from venda_de_put.tz import TZ


def _last_valid(values: Sequence[Optional[float]], n: int) -> Optional[list[float]]:
    """Last n non-None values in order; None if fewer than n valid points."""
    if n <= 0:
        return None
    valid = [v for v in values if v is not None]
    if len(valid) < n:
        return None
    return valid[-n:]


def apply_spot_as_last_period(
    closes: Sequence[Optional[float]],
    preco: Optional[float],
    timestamps: Sequence[Optional[int]] | None = None,
    now: datetime | None = None,
) -> list[Optional[float]]:
    """Último período da janela = à vista do instante. Não duplica o último close."""
    out: list[Optional[float]] = list(closes)
    if preco is None:
        return out
    spot = float(preco)
    now = now or datetime.now(TZ)
    today = now.astimezone(TZ).date() if now.tzinfo else now.replace(tzinfo=TZ).date()
    last_is_today = False
    if timestamps:
        ts = timestamps[-1]
        if ts is not None:
            last_is_today = datetime.fromtimestamp(int(ts), TZ).date() == today
    if last_is_today and out:
        out[-1] = spot
        return out
    last_valid = next((v for v in reversed(out) if v is not None), None)
    if last_valid is not None and last_valid == spot:
        return out
    out.append(spot)
    return out


def sma(values: Sequence[Optional[float]], n: int) -> Optional[float]:
    window = _last_valid(values, n)
    if window is None:
        return None
    return sum(window) / n


def rsi_wilder(closes: Sequence[Optional[float]], n: int = 14) -> Optional[float]:
    """RSI de Wilder: seed = SMA dos primeiros n deltas; depois suavização Wilder."""
    if n <= 0:
        return None
    valid = [c for c in closes if c is not None]
    if len(valid) < n + 1:
        return None

    deltas = [valid[i] - valid[i - 1] for i in range(1, len(valid))]
    gains = [d if d > 0 else 0.0 for d in deltas]
    losses = [-d if d < 0 else 0.0 for d in deltas]

    avg_gain = sum(gains[:n]) / n
    avg_loss = sum(losses[:n]) / n
    for i in range(n, len(gains)):
        avg_gain = (avg_gain * (n - 1) + gains[i]) / n
        avg_loss = (avg_loss * (n - 1) + losses[i]) / n

    if avg_gain == 0.0 and avg_loss == 0.0:
        return None
    if avg_loss == 0.0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def bollinger_lower(
    closes: Sequence[Optional[float]], n: int = 20, k: float = 2.0
) -> Optional[float]:
    """Banda inferior de Bollinger: SMA − k·σ com desvio populacional (divisão por n)."""
    window = _last_valid(closes, n)
    if window is None:
        return None
    mid = sum(window) / n
    var = sum((x - mid) ** 2 for x in window) / n
    return mid - k * math.sqrt(var)


def hv_log(closes: Sequence[Optional[float]], n: int = 21) -> Optional[float]:
    """Volatilidade histórica: σ amostral dos n log-retornos × √252."""
    if n <= 0:
        return None
    valid = [c for c in closes if c is not None and c > 0]
    if len(valid) < n + 1:
        return None
    prices = valid[-(n + 1) :]
    log_rets = [math.log(prices[i] / prices[i - 1]) for i in range(1, len(prices))]
    if n < 2:
        return None
    mean = sum(log_rets) / n
    var = sum((r - mean) ** 2 for r in log_rets) / (n - 1)
    return math.sqrt(var) * math.sqrt(252.0)


def posicao_52s(preco: float, low: float, high: float) -> Optional[float]:
    if high == low:
        return None
    return (preco - low) / (high - low)
