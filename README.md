# Venda de PUT

Seleção de ativos da B3 para venda de put: três listas, prêmio-alvo e strike no vencimento escolhido.

Branch de integração: **`main`** (este dashboard Python). Zips locais (fora do git): árvore Go em `archive/main-antes-do-reset/`; `main` de 18/08/2026 (antes do merge de `igorbeleza/designs`) em `archive/main-antes-do-merge-designs/`.

```
python -m pip install -e ".[dev]"
cp .env.example .env   # preencha VENDA_DE_PUT_ADMIN_PASSWORD e VENDA_DE_PUT_SECRET_KEY p/ login de admin
python -m venda_de_put scrape
python -m venda_de_put serve --host 127.0.0.1 --port 8765
python -m pytest
```

Windows sem terminal: duplo-clique `iniciar-dashboard.bat`.

Quem for implementar ou revisar com IA: comece em [AGENTS.md](AGENTS.md).

Produto: [docs/mvp.md](docs/mvp.md). Desenho: [docs/sdd.md](docs/sdd.md). Deploy: [deploy/RUNBOOK.md](deploy/RUNBOOK.md).
