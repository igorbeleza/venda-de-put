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
