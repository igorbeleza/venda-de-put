# SDD — Venda de PUT

Desenho do sistema Python neste repositório. Autoridade de arquitetura. Glossário em `CONTEXT.md`. Escopo em `docs/mvp.md`.

## Forma

Processo único FastAPI + uvicorn, só `127.0.0.1`. Estado de mercado = um snapshot JSON no disco (`data/snapshots/current.json`). Sem banco.

```
Yahoo ──┐
OpLab ──┼─ scrape ─► snapshot ─► GET /api/* ─► app.js
Fund. ──┘              ▲
                       └── POST /api/refresh só relê
```

Pacote: `src/venda_de_put/`. UI: `web/templates` + `web/static`. Dados editáveis: `data/config.json`, `data/universe.json`, `data/feriados.json`.

## Módulos

| Módulo | Faz |
|---|---|
| `sources/yahoo.py` | Chart 2y/1d, fecha `null` como buraco |
| `sources/oplab.py` | IV da lista; cadeia `__NEXT_DATA__` |
| `sources/fundamentus.py` | Tabela iso-8859-1, % em fração |
| `indicators.py` | SMA, Wilder 14, Bollinger /n, HV log 21 |
| `scoring.py` | ScoreF setorial, tendência, timing, listas |
| `premium.py` | `meta_30d * sqrt(dias/30)` |
| `strike.py` | Strike de entrada no vencimento |
| `calendar_b3.py` | Mensal = dia 15–21; feriado recua o efetivo |
| `scrape.py` | Orquestra fontes, cadeias só dos recomendados |
| `snapshot.py` | Lê/grava JSON, campos novos com default |
| `web/app.py` | API. Não importa `run_scrape`; raspagem sob demanda sobe `python -m venda_de_put scrape` como subprocesso |
| `auth.py` | Login de admin único: senha via env, cookie de sessão HMAC |

## Coleta

- Horários e Fundamentus (dias 1 e 15) estão no Config. CLI de scrape é a raspagem.
- Cadeia: só tickers das três listas, séries ≤ 120 dias. Campos: `due_date`, `strike`, `bid`, `ask`, `last` (`put.close`), `symbol`, `delta`, `poe`, `volume`.
- Fonte morta: mantém o pedaço anterior e carimba `ok=false` / `stale`.

## Strike

Código: `select_strike`. Spec: `docs/superpowers/specs/2026-08-13-fase2-strike-design.md`.

1. Puts do vencimento escolhido, strike < à vista, delta ≥ −0,45 (se vier delta).
2. `last > 0` e `volume > 0`.
3. Taxa = last / strike.
4. Menor strike com taxa ≥ prêmio-alvo → `ok`. Senão maior taxa → `abaixo_da_meta`.
5. Sem puts na data → `sem_serie`. Sem last+volume útil → `sem_liquidez`.
6. A linha do ativo permanece.

`put.bs.bid` / `put.bs.ask` são a **call** do mesmo strike. Bid da put é `put.bid`. Último é `put.close`.

## Scoring (resumo)

Fórmulas e relação com as listas ①②③: `docs/scoring.md`.

- Ranks **dentro do grupo**. Financeiro: sem ROIC, dívida, liquidez corrente, EV/EBITDA no ScoreF (nMrgL entra).
- Múltiplo ≤ 0 vai para o fim do rank, não é “barato”.
- Tendência alta ⇔ preço > MM200.
- Entrada ⇔ IFR ∈ [ifr_min, ifr_max] e preço ≤ Boll Inf × (1+folga).
- SINAL acende só com os dois.
- ① = 10 menores PctF; ② = 10 menores ScoreT; ③ = ScoreC (= PctF se SINAL). PctFu/ScoreTu/ScoreCu da planilha são só desempate (`ROW()/1e8`); o app usa o ticker.

Detalhe numérico: o código e os testes. Paridade Excel dos ranks: fixtures em `tests/fixtures/`.

## API

Trocar `?vencimento=` não vai à rede e não reordena listas. Resposta traz `premio_alvo`, `strike`, `premio_bid` (valor do último), `premio_bid_pct`, `option_symbol`, `strike_status`.

Instruções: `GET /api/instrucoes` lê `web/instrucoes.md`. Testes recusam certas palavras de terminal nesse texto.

## Armadilhas de fonte

- Yahoo: `null` no close é buraco, não zero. Sem isso IFR/HV/MM mentem. O à vista do instante (`preco`) é o último período da série: troca a barra de hoje ou anexa. Ver `docs/superpowers/specs/2026-08-17-indicadores-ultimo-periodo.md`.
- OpLab cadeia: página grande (VALE3 ~5 MB). Não persistir o HTML.
- Fundamentus: charset iso-8859-1; percentuais da tabela viram fração (0,10 = 10%).
- Snapshot antigo sem `last`: até o próximo scrape a série fica sem liquidez. Campo opcional no load.

## Como rodar

```
python -m venda_de_put scrape
python -m venda_de_put serve --host 127.0.0.1 --port 0
python -m pytest
```

`VENDA_DE_PUT_DATA` sobrescreve o diretório `data/`.
