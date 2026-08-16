from datetime import date

from venda_de_put.models import PutQuote, ScoredAsset, Lists, FundScore
from venda_de_put.strike import recommended_tickers, select_strike


def _put(due, strike, bid, delta=-0.25, poe=0.25, ask=None, volume=10.0, last=None, symbol=None):
    return PutQuote(
        due_date=due,
        strike=strike,
        bid=bid,
        ask=ask,
        delta=delta,
        poe=poe,
        volume=volume,
        last=bid if last is None else last,
        symbol=symbol,
    )


DUE = date(2026, 8, 21)
ALVO = 0.0115 * (8 / 30) ** 0.5  # ~0.59%


def test_brav3_primeiro_strike_cujo_ultimo_bate_a_meta():
    """Meta 1,21%: BRAVU162 (0,19/16,13 = 1,17%) não basta; BRAVU165 (0,22/16,38 = 1,34%) é o primeiro."""
    due = date(2026, 9, 18)
    alvo = 0.0121
    puts = [
        _put(due, 16.13, bid=0.25, last=0.19, delta=-0.22, symbol="BRAVU162"),
        _put(due, 16.38, bid=0.20, last=0.22, delta=-0.25, symbol="BRAVU165"),
        _put(due, 16.63, bid=0.28, last=0.28, delta=-0.28, symbol="BRAVU168"),
    ]
    pick = select_strike(puts, due, spot=17.20, premio_alvo=alvo)
    assert pick.status == "ok"
    assert pick.strike == 16.38
    assert pick.last == 0.22
    assert pick.symbol == "BRAVU165"
    assert abs(pick.last_pct - (0.22 / 16.38)) < 1e-9


def test_ignora_ultimo_sem_negocio_no_dia():
    """Último velho em strike fundo (volume 0) não pode 'bater a meta' antes do 16,38."""
    due = date(2026, 9, 18)
    alvo = 0.0121
    puts = [
        _put(due, 12.13, bid=0.0, last=0.27, volume=0, delta=-0.05, symbol="BRAVU122"),
        _put(due, 16.13, bid=0.0, last=0.19, volume=19300, delta=-0.14, symbol="BRAVU162"),
        _put(due, 16.38, bid=0.0, last=0.22, volume=96700, delta=-0.16, symbol="BRAVU165"),
    ]
    pick = select_strike(puts, due, spot=18.38, premio_alvo=alvo)
    assert pick.status == "ok"
    assert pick.strike == 16.38
    assert pick.symbol == "BRAVU165"


def test_petr4_escolhe_strike_mais_longe_que_ainda_bate_o_alvo():
    puts = [
        _put(DUE, 39.50, 0.10, delta=-0.14),   # 0,25% — abaixo
        _put(DUE, 40.00, 0.20, delta=-0.20),   # 0,50% — abaixo
        _put(DUE, 40.86, 0.28, delta=-0.266, poe=0.279),  # 0,69% — bate, mais longe
        _put(DUE, 41.11, 0.40, delta=-0.32),   # 0,97% — bate, mais perto
        _put(DUE, 42.00, 1.10, delta=-0.55),   # ITM
        _put(DUE, 40.50, 0.80, delta=-0.50),   # % alto, delta pior que -0,45
        _put(date(2026, 9, 18), 39.86, 0.54, delta=-0.24),
    ]
    pick = select_strike(puts, DUE, spot=41.75, premio_alvo=ALVO)
    assert pick.status == "ok"
    assert pick.strike == 40.86
    assert pick.bid == 0.28
    assert abs(pick.bid_pct - (0.28 / 40.86)) < 1e-9
    assert abs(pick.delta - (-0.266)) < 1e-9
    assert abs(pick.poe - 0.279) < 1e-9
    assert pick.distancia_pct == (41.75 - 40.86) / 41.75


def test_sem_serie_no_vencimento():
    pick = select_strike(
        [_put(date(2026, 9, 18), 10.0, 0.2)],
        DUE,
        spot=12.0,
        premio_alvo=ALVO,
    )
    assert pick.status == "sem_serie"
    assert pick.strike is None
    assert pick.bid is None


def test_serie_sem_liquidez():
    puts = [_put(DUE, 10.0, 0.0), _put(DUE, 9.5, None)]
    pick = select_strike(puts, DUE, spot=12.0, premio_alvo=ALVO)
    assert pick.status == "sem_liquidez"
    assert pick.strike is None


def test_abaixo_da_meta_mostra_melhor_pct():
    puts = [
        _put(DUE, 23.00, 0.10, delta=-0.19),  # 0,43%
        _put(DUE, 22.50, 0.08, delta=-0.16),  # 0,36%
    ]
    pick = select_strike(puts, DUE, spot=24.34, premio_alvo=ALVO)
    assert pick.status == "abaixo_da_meta"
    assert pick.strike == 23.00
    assert pick.bid == 0.10


def test_recommended_tickers_union_combinado_primeiro():
    def scored(t):
        return ScoredAsset(
            ticker=t,
            fund=FundScore(
                ticker=t, n_roe=None, n_roic=None, n_mrgl=None, n_div=None,
                n_liqc=None, n_pl=None, n_pvp=None, n_eveb=None, n_crsc=None,
                qualid=None, saude=None, valuat=None, consist=None,
                score_f=1.0, pct_f=0.1,
            ),
            tendencia=None, timing=None, sinal=None,
            score_t=None, score_c=None, iv_hv=None,
        )

    lists = Lists(
        fundamentalista=[scored("AAA3"), scored("BBB3"), scored("CCC3")],
        tecnico=[scored("BBB3"), scored("DDD3")],
        combinado=[scored("BBB3")],
    )
    assert recommended_tickers(lists) == ["BBB3", "DDD3", "AAA3", "CCC3"]
