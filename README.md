# Venda de PUT

Seleção de ativos da B3 para venda de put: três listas, prêmio-alvo e strike no vencimento escolhido.

Branch de integração: **`main`** (este dashboard Python). Zips locais (fora do git): árvore Go em `archive/main-antes-do-reset/`; `main` de 18/08/2026 (antes do merge de `igorbeleza/designs`) em `archive/main-antes-do-merge-designs/`.

```
python -m pip install -e ".[dev]"
cp .env.example .env   # admin: VENDA_DE_PUT_ADMIN_PASSWORD e VENDA_DE_PUT_SECRET_KEY
                       # opcional: VENDA_DE_PUT_BRAPI_TOKEN (à vista se o Yahoo falhar 3 vezes no ticker)
python -m venda_de_put scrape
python -m venda_de_put serve --host 127.0.0.1 --port 8765
python -m pytest
```

Windows sem terminal: duplo-clique `iniciar-dashboard.bat`.

HTML/JS usam URL relativa (`static/…`, `api/…`): o dashboard roda na raiz local e também atrás de um prefixo no proxy. Assets de UI vão no `pip install` (`package-data`). Detalhe de hospedagem fica na pasta local `deploy/` (fora do git).

Quem for implementar ou revisar com IA: comece em [AGENTS.md](AGENTS.md).

Produto: [docs/mvp.md](docs/mvp.md). Desenho: [docs/sdd.md](docs/sdd.md).
