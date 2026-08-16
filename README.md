# Venda de PUT

Seleção de ativos da B3 para venda de put: três listas, prêmio-alvo e strike no vencimento escolhido.

Branch de integração: **`main`** (este dashboard Python). A árvore Go que ocupava a `master` antiga está no zip local `archive/main-antes-do-reset/` (fora do git).

```
python -m pip install -e ".[dev]"
python -m venda_de_put scrape
python -m venda_de_put serve --host 127.0.0.1 --port 8765
python -m pytest
```

Quem for implementar ou revisar com IA: comece em [AGENTS.md](AGENTS.md).

Produto: [docs/mvp.md](docs/mvp.md). Desenho: [docs/sdd.md](docs/sdd.md). Deploy: [deploy/RUNBOOK.md](deploy/RUNBOOK.md).
