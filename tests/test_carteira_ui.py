from pathlib import Path

from fastapi.testclient import TestClient

from venda_de_put.web.app import create_app


def test_personal_page_is_separate_and_assets_are_relative(tmp_path: Path):
    client = TestClient(create_app(data_dir=tmp_path))
    response = client.get("/carteira")
    assert response.status_code == 200
    html = response.text
    assert 'id="carteira-auth"' in html
    assert 'id="carteira-app"' in html
    assert 'href="static/carteira.css' in html
    assert 'src="static/carteira.js' in html
    assert 'href="/static/' not in html
    assert 'src="/static/' not in html
    assert 'href="./"' in html


def test_public_page_keeps_exactly_eight_tabs_and_links_to_wallet(tmp_path: Path):
    html = TestClient(create_app(data_dir=tmp_path)).get("/").text
    assert html.count('role="tab"') == 8
    assert 'href="carteira"' in html
    assert 'data-tab="carteira"' not in html


def test_personal_js_uses_only_relative_api_paths(tmp_path: Path):
    client = TestClient(create_app(data_dir=tmp_path))
    js = client.get("/static/carteira.js").text
    assert 'api/carteira/me' in js
    assert 'fetch("/api/' not in js
    assert "fetch(`/api/" not in js
    assert "X-CSRF-Token" in js


def test_personal_page_contains_every_yellow_workbook_input(tmp_path: Path):
    client = TestClient(create_app(data_dir=tmp_path))
    html = client.get("/carteira").text
    for field_id in (
        "cash-cents", "portfolio-date", "portfolio-ticker", "portfolio-class",
        "portfolio-side", "portfolio-quantity", "portfolio-price",
        "portfolio-note", "operation-sale-date", "operation-underlying",
        "operation-option-ticker", "operation-kind", "operation-quantity",
        "operation-strike", "operation-expiry", "operation-premium",
        "operation-status", "operation-close-cost", "operation-repurchase-date",
        "custody-date", "custody-total", "flow-date", "flow-kind",
        "flow-amount", "flow-note",
    ):
        assert f'id="{field_id}"' in html
    js = client.get("/static/carteira.js").text
    for function in (
        "saveAccount", "savePortfolioEntry", "editPortfolioEntry",
        "deletePortfolioEntry", "saveOperation", "editOperation",
        "deleteOperation", "saveCustody", "deleteCustody",
        "saveCashFlow", "deleteCashFlow",
    ):
        assert f"function {function}" in js or f"async function {function}" in js
    assert "innerHTML" not in js
    assert "window.confirm" in js or "confirm(" in js
    assert "sem dado" in js
    assert 'fetch("/api/' not in js
    assert "fetch(`/api/" not in js



def test_personal_performance_panels_and_no_new_metrics(tmp_path: Path):
    client = TestClient(create_app(data_dir=tmp_path))
    html = client.get("/carteira").text
    js = client.get("/static/carteira.js").text
    for element_id in (
        "personal-summary-cards", "personal-market-stamp", "missing-market-data",
        "cash-margin-summary", "open-sort", "open-filter", "open-options-table",
        "assets-summary-table", "premium-year", "stock-allocation-chart",
        "put-risk-chart", "monthly-premium-chart", "evolution-table",
    ):
        assert f'id="{element_id}"' in html
    assert "function renderBars" in js
    assert 'api(`summary?year=${' in js or 'api("summary?year="' in js
    for forbidden in ("ROI anual", "benchmark", "taxa de acerto", "gregas"):
        assert forbidden not in html
        assert forbidden not in js
