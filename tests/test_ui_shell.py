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
    assert "--canvas: #b4aea3" in css
    assert '[data-theme="dark"]' in css
    assert "--canvas: #121314" in css
    assert "-apple-system" in css
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
    assert 'fetch("/api/me")' in js
    assert 'data-tab="config"' in html
    assert 'id="btn-raspar"' in html
    assert 'id="scrape-incluir-fundamentus"' in html
    assert 'fetch("/api/scrape/status")' in js
    assert 'id="scrape-ultima"' in html
    scrape_panel = html.split('class="scrape-panel"', 1)[1].split("</div>", 1)[0]
    assert "Última raspagem" in scrape_panel
    assert "function paintScrapeUltima" in js
    assert "function loadScrapeUltima" in js
    assert "loadScrapeUltima()" in js
    assert "Última raspagem: sem dado" in js
    assert "Última raspagem:" in js
    assert 'id="scrape-passos"' in html
    assert "function paintScrapePassos" in js
    assert "function syncScrapePanel" in js
    assert "syncScrapePanel()" in js
    assert 'data.status === "running"' in js
    assert "loadDashboard()" in js
    assert "data-step=\"yahoo\"" in html
    assert "data-step=\"oplab\"" in html
    assert "data-step=\"fundamentus\"" in html
    assert "data-step=\"oplab_cadeia\"" in html
    assert "function retry_from" not in js
    assert "function retryScrapePasso" in js
    assert 'passo:' in js or '"passo"' in js
    assert "scrape-retry" in js
    assert "--from-step" not in js
    assert "retry_completo" in js
    assert "mais de 1 hora" in js
    assert "function refreshVisibleData" in js
    assert "refreshVisibleData()" in js
    assert 'if (name === "dashboard") loadDashboard()' in js
    assert "authState.admin) syncScrapePanel()" in js or "authState.admin && syncScrapePanel()" in js
