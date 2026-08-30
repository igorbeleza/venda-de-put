import ast
from pathlib import Path


def _imported_modules(src: str) -> list[tuple[str | None, list[str]]]:
    tree = ast.parse(src)
    imported: list[tuple[str | None, list[str]]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported.append((node.module, [a.name for a in node.names]))
        if isinstance(node, ast.Import):
            imported.append((None, [a.name for a in node.names]))
    return imported


def _imports_scrape(src: str) -> bool:
    for mod, names in _imported_modules(src):
        if "run_scrape" in names:
            return True
        candidates = [mod] if mod else names
        if any(
            (item or "") == "scrape"
            or (item or "").endswith(".scrape")
            or (item or "") == "venda_de_put.scrape"
            for item in candidates
        ):
            return True
    return False


def test_web_app_does_not_import_run_scrape():
    src = Path("src/venda_de_put/web/app.py").read_text(encoding="utf-8")
    assert not _imports_scrape(src)
    assert "venda_de_put.sources.brapi" not in src
    assert "venda_de_put.sources.cotahist" not in src
    assert "BrapiSpotHttp" not in src
    assert "CotahistBootstrap" not in src


def test_carteira_package_does_not_import_scrape():
    paths = [Path("src/venda_de_put/web/app.py"), *sorted(
        Path("src/venda_de_put/carteira").glob("*.py")
    )]
    offenders = [str(path) for path in paths if _imports_scrape(path.read_text(encoding="utf-8"))]
    assert offenders == []
