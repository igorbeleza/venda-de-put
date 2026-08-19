from venda_de_put.config import AppConfig
from venda_de_put.models import AssetInput, TechnicalInput
from venda_de_put.scoring import apply_technical, build_lists, score_fundamentals


def test_itub4_cached_excel_is_fora_not_sinal():
    # preço 38.54 < MM200 40.95 → fora; ScoreT = 100 + 23.23/1000
    fund = score_fundamentals([
        AssetInput("ITUB4", "Financeiro", 10.15, 2.36, None, 0, None, None, 0.2324, None, 0.7155)
    ])[0]
    asset = apply_technical(fund, TechnicalInput(38.54, 40.95, 23.23, 38.81, None, None), AppConfig())
    assert asset.tendencia == "fora"
    assert asset.timing == "ENTRADA"
    assert asset.sinal == "—"
    assert abs(asset.score_t - 100.02323) < 1e-9
    assert asset.score_c is None


def test_sinal_aceso_entra_lista_combinada():
    fund = score_fundamentals([
        AssetInput("BOM3", "Varejo", 5, 1, 4, 0.2, 2, 0.2, 0.3, 0.1, 0.2)
    ])[0]
    cfg = AppConfig()
    # preço > MM200 e colado na banda, IFR 40
    asset = apply_technical(fund, TechnicalInput(20.0, 18.0, 40.0, 19.5, 0.4, 0.3), cfg)
    assert asset.sinal == "► VENDER PUT"
    lists = build_lists([asset])
    assert [a.ticker for a in lists.combinado] == ["BOM3"]
    assert asset.score_t == (20.0 - 19.5) / 19.5


def test_score_t_vazio_quando_sinal_ausente():
    # Sem MM200 o SINAL some. A planilha exige X2 preenchido nos dois ramos
    # do ScoreT; IFR sozinho não entra na ②.
    fund = score_fundamentals([
        AssetInput("AUAU3", "Varejo", 5, 1, 4, 0.2, 2, 0.2, 0.3, 0.1, 0.2)
    ])[0]
    asset = apply_technical(
        fund, TechnicalInput(3.16, None, 41.81, 3.02, None, None), AppConfig()
    )
    assert asset.sinal is None
    assert asset.technicals.ifr == 41.81
    assert asset.score_t is None
    lists = build_lists([asset])
    assert lists.tecnico == []


def test_timing_aguardar_when_entrada_fails_with_inputs_present():
    # IFR, preço e boll_inf presentes; IFR fora da banda → aguardar; SINAL "—"
    fund = score_fundamentals([
        AssetInput("REC3", "Varejo", 5, 1, 4, 0.2, 2, 0.2, 0.3, 0.1, 0.2)
    ])[0]
    # preço > MM200 (alta), IFR 70 fora de [10, 50]
    asset = apply_technical(
        fund, TechnicalInput(20.0, 18.0, 70.0, 19.5, None, None), AppConfig()
    )
    assert asset.tendencia == "alta"
    assert asset.timing == "aguardar"
    assert asset.sinal == "—"


def test_lista1_top_equals_excel_fixture():
    import json
    from pathlib import Path
    from venda_de_put.models import AssetInput
    from venda_de_put.scoring import apply_technical, build_lists, score_fundamentals
    raw = json.loads(Path("tests/fixtures/excel_ativos.json").read_text(encoding="utf-8"))
    funds = score_fundamentals([
        AssetInput(r["ticker"], r["grupo"], r["pl"], r["pvp"], r["ev_ebitda"],
                   r["mrg_liq"], r["liq_corr"], r["roic"], r["roe"], r["div_pat"], r["cresc"])
        for r in raw
    ])
    scored = []
    for f, r in zip(funds, raw, strict=True):
        scored.append(apply_technical(
            f,
            TechnicalInput(r["preco"], r["mm200"], r["ifr"], r["boll_inf"], None, None),
            AppConfig(),
        ))
    lists = build_lists(scored)
    expect = ["BRSR6", "SBSP3", "RECV3", "CMIN3", "PSSA3", "VIVA3", "ISAE4", "CURY3", "ECOR3", "BEEF3"]
    # CMIN3 e PSSA3 e VIVA3 empatam em 0.142857 — desempate alfabético
    # CMIN3, PSSA3, VIVA3. O Excel usou ROW(); nós usamos ticker.
    # Aceite da spec: desempate alfabético. A ORDEM dos empatados pode
    # divergir do Excel. Os 10 CONJUNTOS devem bater; a ordem só é rígida
    # quando PctF é distinto.
    got = [a.ticker for a in lists.fundamentalista]
    assert set(got) == set(expect)
    assert got[0] == "BRSR6"
    assert got[1] == "SBSP3"
    assert got[2] == "RECV3"
