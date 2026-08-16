# Venda de PUT

Seleção de ativos da B3 para venda de put: três listas, prêmio-alvo e strike no vencimento escolhido.

```
python -m pip install -e ".[dev]"
python -m venda_de_put scrape
python -m venda_de_put serve --host 127.0.0.1 --port 8765
python -m pytest
```

Quem for implementar ou revisar com IA: comece em [AGENTS.md](AGENTS.md).

Produto: [docs/mvp.md](docs/mvp.md). Desenho: [docs/sdd.md](docs/sdd.md). Deploy: [deploy/RUNBOOK.md](deploy/RUNBOOK.md).
