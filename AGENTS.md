# Venda de PUT

Dashboard FastAPI que recomenda ativos da B3 para venda de put. Código é a autoridade. Os prompts da raiz foram arquivados.

## Ler primeiro

- [CONTEXT.md](CONTEXT.md) — vocabulário. Use estes termos no código e na conversa.
- [docs/mvp.md](docs/mvp.md) — escopo do produto: o que entra, o que fica fora, janela e meta.
- [docs/sdd.md](docs/sdd.md) — desenho: scrape → snapshot → API → UI, strike, fontes.
- [docs/adr/](docs/adr/) — decisões que não se revertem de leve.
- [src/venda_de_put/web/instrucoes.md](src/venda_de_put/web/instrucoes.md) — texto da aba Instruções (sem nomes de terminal).

## Quando abrir o quê

- **Escopo, listas, meta, janela 45–21** → `docs/mvp.md`.
- **Strike, prêmio, cadeia OpLab, `bs.bid`** → `docs/sdd.md` e `docs/superpowers/specs/2026-08-13-fase2-strike-design.md`.
- **Indicadores (IFR, MM200, Bollinger, HV)** → `src/venda_de_put/indicators.py` e `docs/sdd.md`.
- **Deploy VPS** → `deploy/RUNBOOK.md`.
- **Briefs antigos** → `docs/archive/2026-08-prompts-iniciais/` só como história. Nunca como regra.

## Trabalho

1. Comportamento novo ou mudado: teste que falha, depois o mínimo de código.
2. `python -m pytest` no fim. Sem isso o trabalho não está feito.
3. Mudança de UI: exercitar no browser (trocar vencimento, abrir as abas que leem o mesmo estado).
4. `POST /api/refresh` só relê o snapshot. Raspar é `python -m venda_de_put scrape`.

## Invariantes

- Prêmio da entrada = último negócio / strike, com volume no dia. Bid é livro.
- `put.bs.bid` é a call do mesmo strike. A put usa `put.close` e `put.bid` de primeiro nível.
- Abertura da operação: 45 a 21 dias corridos até o vencimento.
- Trocar o vencimento recalcula strike e prêmio-alvo. Não reordena as três listas.
- Dado ausente é o texto “sem dado”, nunca zero inventado.
- Aba Instruções e testes dela: sem as palavras de terminal de corretora.
