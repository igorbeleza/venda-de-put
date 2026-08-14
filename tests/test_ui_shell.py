from fastapi.testclient import TestClient
from venda_de_put.web.app import create_app


def test_home_has_eight_tabs_and_narratives(tmp_path):
    app = create_app(data_dir=tmp_path)
    html = TestClient(app).get("/").text
    for name in ["Dashboard", "Ativos", "Dados", "Setores", "Config", "Vencimentos", "Feriados", "Instruções"]:
        assert name in html
    assert "Ferramenta de seleção, não recomendação" in html
    assert "empresa que eu aceitaria carregar" in html
    assert "faca caindo" in html
    assert "às vezes essa lista vem com menos de 10" in html
    assert "Prêmio-alvo para esse vencimento" in html
    assert "Meta de prêmio p/ 30 dias" in html
    assert "Calculadora de prêmio-alvo por vencimento" in html
    assert "fonts.googleapis.com" in html
    assert "class=\"shell\"" in html
    assert 'data-theme-set="light"' in html
    assert 'data-theme-set="dark"' in html
    assert "Tema claro" in html
    assert "Tema escuro" in html
    assert "vdp-theme" in html
    css = TestClient(app).get("/static/app.css").text
    assert "--canvas: #f1f2f3" in css
    assert '[data-theme="dark"]' in css
    assert "--canvas: #1c1d1f" in css
    assert "Inter" in css
    assert "width: 100%" in css
    assert "min(1440px" not in css
    assert "--card-min" in css
    assert ".list-block h2" in css
    assert "linear-gradient" in css
    assert "list-banner" in html
    assert "zoom-in" in html
    assert "zoom-out" in html
    assert "Zoom da tela" in html
    js = TestClient(app).get("/static/app.js").text
    assert "function applyTheme" in js
    assert "function applyUiZoom" in js
    assert "function fitCards" in js
    assert "ZOOM_STEPS" in js
