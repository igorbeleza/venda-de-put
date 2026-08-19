from venda_de_put.models import AssetInput
from venda_de_put.scoring import score_fundamentals


def _fin(ticker, roe, mrg, pl, pvp, cresc):
    return AssetInput(
        ticker=ticker, grupo="Financeiro",
        pl=pl, pvp=pvp, ev_ebitda=None, mrg_liq=mrg, liq_corr=None,
        roic=None, roe=roe, div_pat=None, cresc=cresc,
    )


def test_financeiro_computes_nmrgl_and_skips_nroic():
    assets = [
        _fin("AAA", roe=0.30, mrg=0.20, pl=8, pvp=1.0, cresc=0.10),
        _fin("BBB", roe=0.10, mrg=0.05, pl=20, pvp=3.0, cresc=0.01),
    ]
    out = {a.ticker: a for a in score_fundamentals(assets)}
    assert out["AAA"].n_roic is None
    assert out["BBB"].n_roic is None
    assert out["AAA"].n_mrgl == 1
    assert out["BBB"].n_mrgl == 2
    assert out["AAA"].n_div is None
    assert out["AAA"].score_f is not None
    assert out["AAA"].score_f < out["BBB"].score_f


def test_menor_e_melhor_no_topo():
    """ROE alto, dívida baixa, P/L baixo → PctF menor."""
    grupo = "Varejo"
    bom = AssetInput("BOM3", grupo, pl=5, pvp=1, ev_ebitda=4, mrg_liq=0.2,
                     liq_corr=2, roic=0.2, roe=0.3, div_pat=0.1, cresc=0.2)
    ruim = AssetInput("RUI3", grupo, pl=40, pvp=8, ev_ebitda=20, mrg_liq=0.02,
                      liq_corr=0.8, roic=0.02, roe=0.03, div_pat=2.0, cresc=-0.1)
    out = {a.ticker: a for a in score_fundamentals([bom, ruim])}
    assert out["BOM3"].pct_f < out["RUI3"].pct_f


def test_pl_negativo_vai_para_o_fim():
    grupo = "Saúde"
    a = AssetInput("NEG3", grupo, pl=-10, pvp=1, ev_ebitda=5, mrg_liq=0.1,
                   liq_corr=1.5, roic=0.1, roe=0.1, div_pat=0.2, cresc=0.1)
    b = AssetInput("POS3", grupo, pl=8, pvp=1, ev_ebitda=5, mrg_liq=0.1,
                   liq_corr=1.5, roic=0.1, roe=0.1, div_pat=0.2, cresc=0.1)
    out = {x.ticker: x for x in score_fundamentals([a, b])}
    assert out["NEG3"].n_pl == 3  # tamanho 2 + 1
    assert out["POS3"].n_pl == 1


def _varejo(ticker, **kw):
    defaults = dict(
        grupo="Varejo", pl=5, pvp=1, ev_ebitda=4, mrg_liq=0.2,
        liq_corr=2, roic=0.2, roe=0.3, div_pat=0.1, cresc=0.2,
    )
    defaults.update(kw)
    return AssetInput(ticker=ticker, **defaults)


def test_bloco_consist_ausente_anula_score_f():
    # Consist é um campo só. Sem Cresc. Rec.5a o Excel anula o ScoreF inteiro.
    incompleto = _varejo("INC3", cresc=None)
    completo = _varejo("COM3", roe=0.10)
    out = {a.ticker: a for a in score_fundamentals([incompleto, completo])}
    assert out["INC3"].consist is None
    assert out["INC3"].qualid is not None
    assert out["INC3"].score_f is None
    assert out["INC3"].pct_f is None
    assert out["COM3"].score_f is not None
    assert out["COM3"].pct_f == 1.0


def test_campo_isolado_na_saude_nao_anula_score_f():
    # AVERAGE ignora vazio: falta um campo do bloco, o bloco ainda existe.
    so_div = _varejo("DIV3", liq_corr=None)
    out = score_fundamentals([so_div, _varejo("PAR3")])[0]
    assert out.saude is not None
    assert out.score_f is not None


def test_financeiro_saude_ausente_nao_anula_score_f():
    # Saúde é None por construção no ramo; não é bloco faltante.
    out = score_fundamentals([
        _fin("AAA", roe=0.30, mrg=0.20, pl=8, pvp=1.0, cresc=0.10),
    ])[0]
    assert out.saude is None
    assert out.score_f is not None


def test_financeiro_consist_ausente_anula_score_f():
    out = score_fundamentals([
        _fin("AAA", roe=0.30, mrg=0.20, pl=8, pvp=1.0, cresc=None),
        _fin("BBB", roe=0.10, mrg=0.05, pl=20, pvp=3.0, cresc=0.01),
    ])
    by = {a.ticker: a for a in out}
    assert by["AAA"].score_f is None
    assert by["AAA"].pct_f is None
    assert by["BBB"].score_f is not None


def test_paridade_brsr6_itub4_contra_excel():
    import json
    from pathlib import Path
    raw = json.loads(Path("tests/fixtures/excel_ativos.json").read_text(encoding="utf-8"))
    assets = [
        AssetInput(
            ticker=r["ticker"], grupo=r["grupo"],
            pl=r["pl"], pvp=r["pvp"], ev_ebitda=r["ev_ebitda"],
            mrg_liq=r["mrg_liq"], liq_corr=r["liq_corr"], roic=r["roic"],
            roe=r["roe"], div_pat=r["div_pat"], cresc=r["cresc"],
        )
        for r in raw
    ]
    out = {a.ticker: a for a in score_fundamentals(assets)}
    expect = {r["ticker"]: r for r in raw}
    for t in ("BRSR6", "ITUB4", "PSSA3", "IRBR3"):
        assert out[t].n_mrgl == expect[t]["nmrgl"]
        assert abs(out[t].score_f - expect[t]["scoref"]) < 1e-6
        assert abs(out[t].pct_f - expect[t]["pctf"]) < 1e-9
