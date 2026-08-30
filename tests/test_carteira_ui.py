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
