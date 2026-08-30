from pathlib import Path


def test_product_docs_describe_personal_wallet_boundaries():
    context = Path("CONTEXT.md").read_text(encoding="utf-8")
    mvp = Path("docs/mvp.md").read_text(encoding="utf-8")
    sdd = Path("docs/sdd.md").read_text(encoding="utf-8")
    detail = Path("docs/carteira-pessoal.md").read_text(encoding="utf-8")
    assert "Carteira pessoal" in context
    assert "/carteira" in mvp
    assert "carteira.sqlite3" in sdd
    assert "carteira_session" in sdd
    assert "Campos amarelos" in detail
    assert "Campos calculados" in detail
    assert "sem dado" in detail
    assert "spec-carteira.xlsx" in detail


def test_mvp_no_longer_declares_users_and_database_out_of_scope():
    mvp = Path("docs/mvp.md").read_text(encoding="utf-8")
    assert "Banco, usuário, multi-tenant." not in mvp
    assert "O dashboard público não registra nem fecha a operação" in mvp
