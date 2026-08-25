import ast
from pathlib import Path


def test_web_app_does_not_import_run_scrape():
    src = Path("src/venda_de_put/web/app.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported.append((node.module, [a.name for a in node.names]))
        if isinstance(node, ast.Import):
            imported.append((None, [a.name for a in node.names]))
    assert not any(
        (mod or "").endswith("scrape") or "run_scrape" in names
        for mod, names in imported
    )
    assert "venda_de_put.sources.brapi" not in src
    assert "venda_de_put.sources.cotahist" not in src
    assert "BrapiSpotHttp" not in src
    assert "CotahistBootstrap" not in src
