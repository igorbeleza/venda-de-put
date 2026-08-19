from typing import Optional

from venda_de_put.models import (
    AppConfig,
    AssetInput,
    FundScore,
    Lists,
    ScoredAsset,
    TechnicalInput,
)


def _mean(vals: list[Optional[float]]) -> Optional[float]:
    present = [v for v in vals if v is not None]
    if not present:
        return None
    return sum(present) / len(present)


def _rank_higher_better(
    mine: Optional[float], peers: list[Optional[float]]
) -> Optional[int]:
    if mine is None:
        return None
    return sum(1 for p in peers if p is not None and p > mine) + 1


def _rank_lower_better(
    mine: Optional[float], peers: list[Optional[float]]
) -> Optional[int]:
    if mine is None:
        return None
    return sum(1 for p in peers if p is not None and p < mine) + 1


def _rank_valuation(mine: Optional[float], peers: list[Optional[float]], group_size: int) -> Optional[int]:
    if mine is None:
        return None
    if mine <= 0:
        return group_size + 1
    return sum(1 for p in peers if p is not None and 0 < p < mine) + 1


def score_fundamentals(assets: list[AssetInput]) -> list[FundScore]:
    by_group: dict[str, list[AssetInput]] = {}
    for a in assets:
        by_group.setdefault(a.grupo, []).append(a)

    prelim: list[tuple[AssetInput, dict]] = []
    for a in assets:
        peers = by_group[a.grupo]
        n = len(peers)
        financeiro = a.grupo == "Financeiro"

        n_roe = _rank_higher_better(a.roe, [p.roe for p in peers])
        n_roic = None if financeiro else _rank_higher_better(a.roic, [p.roic for p in peers])
        n_mrgl = _rank_higher_better(a.mrg_liq, [p.mrg_liq for p in peers])
        n_div = None if financeiro else _rank_lower_better(a.div_pat, [p.div_pat for p in peers])
        n_liqc = None if financeiro else _rank_higher_better(a.liq_corr, [p.liq_corr for p in peers])
        n_pl = _rank_valuation(a.pl, [p.pl for p in peers], n)
        n_pvp = _rank_valuation(a.pvp, [p.pvp for p in peers], n)
        n_eveb = None if financeiro else _rank_valuation(a.ev_ebitda, [p.ev_ebitda for p in peers], n)
        n_crsc = _rank_higher_better(a.cresc, [p.cresc for p in peers])

        qualid = _mean([n_roe, n_roic, n_mrgl])
        saude = _mean([n_div, n_liqc])
        valuat = _mean([n_pl, n_pvp, n_eveb])
        consist = n_crsc

        if financeiro:
            if None in (qualid, valuat, consist):
                score_f = None
            else:
                score_f = 0.50 * qualid + 0.30 * valuat + 0.20 * consist
        else:
            if None in (qualid, saude, valuat, consist):
                score_f = None
            else:
                score_f = 0.40 * qualid + 0.25 * saude + 0.20 * valuat + 0.15 * consist

        prelim.append((a, {
            "n_roe": n_roe, "n_roic": n_roic, "n_mrgl": n_mrgl,
            "n_div": n_div, "n_liqc": n_liqc, "n_pl": n_pl,
            "n_pvp": n_pvp, "n_eveb": n_eveb, "n_crsc": n_crsc,
            "qualid": qualid, "saude": saude, "valuat": valuat,
            "consist": consist, "score_f": score_f,
        }))

    scores_by_group: dict[str, list[Optional[float]]] = {}
    for a, d in prelim:
        scores_by_group.setdefault(a.grupo, []).append(d["score_f"])

    out: list[FundScore] = []
    for a, d in prelim:
        sf = d["score_f"]
        group_scores = scores_by_group[a.grupo]
        denom = sum(1 for s in group_scores if s is not None and s > 0)
        if sf is None or denom == 0:
            pct_f = None
        else:
            better = sum(1 for s in group_scores if s is not None and s < sf)
            pct_f = (better + 1) / denom
        out.append(FundScore(ticker=a.ticker, pct_f=pct_f, **d))
    return out


SINAL_VENDER = "► VENDER PUT"
SINAL_DASH = "—"


def apply_technical(fund: FundScore, tech: TechnicalInput, cfg: AppConfig) -> ScoredAsset:
    if tech.preco is None or tech.mm200 is None:
        tendencia = None
    elif tech.preco > tech.mm200:
        tendencia = "alta"
    else:
        tendencia = "fora"

    timing_inputs_ok = (
        tech.ifr is not None and tech.preco is not None and tech.boll_inf is not None
    )
    if not timing_inputs_ok:
        timing = None
    elif cfg.ifr_min <= tech.ifr <= cfg.ifr_max and tech.preco <= tech.boll_inf * (1 + cfg.folga):
        timing = "ENTRADA"
    else:
        timing = "aguardar"

    if tendencia is None or not timing_inputs_ok:
        sinal = None
    elif tendencia == "alta" and timing == "ENTRADA":
        sinal = SINAL_VENDER
    else:
        sinal = SINAL_DASH

    if sinal == SINAL_VENDER and tech.preco is not None and tech.boll_inf is not None:
        score_t = (tech.preco - tech.boll_inf) / tech.boll_inf
    elif sinal is not None and tech.ifr is not None:
        score_t = 100 + tech.ifr / 1000
    else:
        score_t = None

    if sinal == SINAL_VENDER:
        score_c = fund.pct_f
    else:
        score_c = None

    if tech.iv is not None and tech.hv is not None and tech.hv != 0:
        iv_hv = tech.iv / tech.hv
    else:
        iv_hv = None

    return ScoredAsset(
        ticker=fund.ticker,
        fund=fund,
        tendencia=tendencia,
        timing=timing,
        sinal=sinal,
        score_t=score_t,
        score_c=score_c,
        iv_hv=iv_hv,
        technicals=tech,
    )


def build_lists(assets: list[ScoredAsset], n: int = 10) -> Lists:
    with_pct = [a for a in assets if a.fund.pct_f is not None]
    fundamentalista = sorted(with_pct, key=lambda a: (a.fund.pct_f, a.ticker))[:n]

    with_t = [a for a in assets if a.score_t is not None]
    tecnico = sorted(with_t, key=lambda a: (a.score_t, a.ticker))[:n]

    with_c = [a for a in assets if a.score_c is not None]
    combinado = sorted(with_c, key=lambda a: (a.score_c, a.ticker))[:n]

    return Lists(
        fundamentalista=fundamentalista,
        tecnico=tecnico,
        combinado=combinado,
    )
