from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from venda_de_put.sources.fundamentus import FundamentusHttp
from venda_de_put.sources.oplab import OplabHttp
from venda_de_put.sources.yahoo import YahooHttp
from venda_de_put.tz import format_datetime, format_number


@dataclass(frozen=True)
class SmokeResult:
    ok: bool
    yahoo_preco: Optional[float] = None
    yahoo_collected: Optional[str] = None
    oplab_n: Optional[int] = None
    petr4_iv: Optional[float] = None
    fund_n: Optional[int] = None
    errors: tuple[str, ...] = ()


def run_smoke() -> SmokeResult:
    errors: list[str] = []
    yahoo_preco: Optional[float] = None
    yahoo_collected: Optional[str] = None
    oplab_n: Optional[int] = None
    petr4_iv: Optional[float] = None
    fund_n: Optional[int] = None

    try:
        series = YahooHttp().fetch(["PETR4"]).get("PETR4")
        if series is None:
            errors.append("Yahoo: PETR4 ausente")
        else:
            yahoo_preco = series.preco
            yahoo_collected = format_datetime(series.collected_at)
    except Exception as exc:
        errors.append(f"Yahoo: {exc}")

    try:
        ivs = OplabHttp().fetch()
        oplab_n = len(ivs)
        petr = ivs.get("PETR4")
        petr4_iv = None if petr is None else petr.iv
    except Exception as exc:
        errors.append(f"OpLab: {exc}")

    try:
        rows = FundamentusHttp().fetch()
        fund_n = len(rows)
    except Exception as exc:
        errors.append(f"Fundamentus: {exc}")

    return SmokeResult(
        ok=not errors,
        yahoo_preco=yahoo_preco,
        yahoo_collected=yahoo_collected,
        oplab_n=oplab_n,
        petr4_iv=petr4_iv,
        fund_n=fund_n,
        errors=tuple(errors),
    )


def _fmt_opt(val: Optional[float]) -> str:
    if val is None:
        return "—"
    return format_number(val)


def cli_smoke() -> int:
    result = run_smoke()
    collected = result.yahoo_collected or "—"
    print(f"PETR4 preço={_fmt_opt(result.yahoo_preco)} coletado em {collected}")
    print(f"OpLab stocks={result.oplab_n if result.oplab_n is not None else '—'} PETR4 iv={_fmt_opt(result.petr4_iv)}")
    print(
        f"Fundamentus linhas={result.fund_n if result.fund_n is not None else '—'} encoding=iso-8859-1"
    )
    for err in result.errors:
        print(f"ERRO: {err}")
    return 0 if result.ok else 1
