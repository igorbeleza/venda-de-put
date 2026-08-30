# SDD — Venda de PUT

Desenho do sistema Python neste repositório. Autoridade de arquitetura. Glossário em `CONTEXT.md`. Escopo em `docs/mvp.md`.

## Forma

Processo único FastAPI + uvicorn, só `127.0.0.1`. O estado global de mercado continua em um snapshot JSON no disco (`data/snapshots/current.json`). Os dados pessoais usam o SQLite `data/carteira.sqlite3`, conforme `docs/adr/0005-carteira-multiusuario-sqlite.md`.

```
Yahoo ──┐  (+ brapi à vista / Cotahist se Yahoo perde ticker)
OpLab ──┼─ scrape ─► snapshot ─► GET /api/* ─► app.js
Fund. ──┘              ▲
                       └── POST /api/refresh só relê

carteira.sqlite3 ─► /api/carteira ─► carteira.js
```

As duas ramificações não mudam de fonte. Requisições da carteira nunca chamam Yahoo, brapi, Cotahist, OpLab ou Fundamentus. Quando a carteira precisa de preço ou indicador, lê o snapshot global.

Pacote: `src/venda_de_put/`. UI: `web/templates` + `web/static`. Dados editáveis globais: `data/config.json`, `data/universe.json`, `data/feriados.json`. Dados pessoais: `data/carteira.sqlite3`.

## Módulos

| Módulo | Faz |
|---|---|
| `sources/yahoo.py` | Chart 2y/1d, 3 tentativas, fecha `null` como buraco |
| `sources/brapi.py` | À vista em lote; só se o Yahoo perdeu o ticker |
| `sources/cotahist.py` | ZIP anual B3 → série de fechamentos dos tickers frios |
| `sources/oplab.py` | IV da lista; cadeia `__NEXT_DATA__` |
| `sources/fundamentus.py` | Tabela iso-8859-1, % em fração |
| `indicators.py` | SMA, Wilder 14, Bollinger /n, HV log 21 |
| `scoring.py` | ScoreF setorial, tendência, timing, listas |
| `premium.py` | `meta_30d * sqrt(dias/30)`. A meta gravada (padrão 1,15%) já inclui o ajuste da recompra com 70% do prêmio exaurido; o alvo econômico é 1% do strike em 30 dias |
| `strike.py` | Strike de entrada no vencimento |
| `calendar_b3.py` | Mensal = dia 15–21; feriado recua o efetivo. Horizonte até `cfg.calendario_ate` (Config) |
| `paths.py` | Resolve `data/`; `load_dotenv` lê `.env` sem sobrescrever env já exportada |
| `scrape.py` | Orquestra fontes, cadeias só dos recomendados. Aceita `only_steps` / `--from-step` para retry |
| `scrape_progress.py` | JSON de passos (Yahoo, OpLab, Fundamentus, Cadeia). `app.py` pode importar isto; não importa `scrape.py` |
| `snapshot.py` | Lê/grava JSON, campos novos com default |
| `web/app.py` | API. Não importa `run_scrape`; raspagem sob demanda sobe `python -m venda_de_put scrape` como subprocesso. Cookie: `Path` de `X-Forwarded-Prefix`, `Secure` se `X-Forwarded-Proto` é https |
| `auth.py` | Login de admin único: senha via env, cookie de sessão HMAC |
| `carteira/db.py` | Conexão SQLite e migrações dos dados pessoais |

## Identidade e isolamento da carteira

O administrador e as pessoas da carteira têm identidades independentes. A sessão pessoal usa o cookie `carteira_session`, e operações que mudam dados exigem o cookie `carteira_csrf`. Nenhum desses cookies concede acesso às rotas administrativas. O cookie administrativo também não autoriza `/api/carteira`.

`users` define o proprietário. Todas as outras tabelas pessoais apontam diretamente para `users.id` por `user_id`. Toda leitura, alteração ou exclusão de um registro pessoal identificado por ID usa o predicado `WHERE id = ? AND user_id = ?`. A API obtém `user_id` da sessão e nunca aceita esse campo no corpo da requisição.

O banco guarda somente entradas pessoais. Totais, posições, P&L e outros valores derivados são calculados a partir dessas entradas e do snapshot global.

## Coleta

- Horários e Fundamentus (dias 1 e 15) estão no Config, mas são ideia futura: o timer systemd (unit local, fora do git) que os executava foi desativado em 19/08/2026 (`systemctl disable --now`). Raspagem hoje é só sob demanda (botão "Raspar dados agora" do admin). Os campos do Config continuam só dizendo se o dado está velho e se o Fundamentus entra no ciclo — não disparam nada sozinhos.
- CLI de scrape é a raspagem: `python -m venda_de_put scrape`. Admin dispara o mesmo comando como subprocesso (`POST /api/scrape`).
- Painel Config / Raspagem: carimbo da última coleta, barra de passos (ok / falhou / raspando / pulado / sem dado) e botão de retry no passo que falhou.
- Retry de um passo puxa os dependentes: Yahoo → os quatro; OpLab → OpLab + Cadeia; Fundamentus → Fundamentus + Cadeia; Cadeia → só Cadeia. Se a última raspagem tem mais de 1 hora, o retry vira o ciclo inteiro (`retry_completo`).
- Sair da aba Config não mata o subprocesso. O status continua sendo consultado; ao terminar, Dashboard e a aba visível relêem o snapshot.
- Preço: Yahoo (3 tentativas/ticker). Ticker faltoso → brapi.dev à vista (`VENDA_DE_PUT_BRAPI_TOKEN`). Sem técnico anterior aproveitável (`preco`/`mm200`) → Cotahist `COTAHIST_A{ano}` em `data/cotahist/`. Consulta ao vivo falhou → carimbo yahoo `ok=false` com `PRICE_NOTICE`; Dashboard mostra `price_notice`.
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
- Bloco do ScoreF vazio anula a nota (não soma parcial). ScoreT exige SINAL preenchido (`►` ou `—`); SINAL vazio tira da ②.
- ① = 10 menores PctF; ② = 10 menores ScoreT; ③ = ScoreC (= PctF se SINAL). PctFu/ScoreTu/ScoreCu da planilha são só desempate (`ROW()/1e8`); o app usa o ticker.

Detalhe numérico: o código e os testes. Paridade Excel dos ranks: fixtures em `tests/fixtures/`.

## API

Trocar o vencimento não vai à rede e não reordena listas. Resposta traz `premio_alvo`, `strike`, `premio_bid` (valor do último), `premio_bid_pct`, `option_symbol`, `strike_status`.

`GET /api/dashboard` inclui `price_notice` (null ou a frase de `PRICE_NOTICE`) quando a consulta ao vivo falhou. `GET /api/ativos` e `GET /api/dados` devolvem também o carimbo do Yahoo (`carimbo`) e o `generated_at`; as duas abas pintam o mesmo banner de coleta das listas. O à vista da aba Ativos é o `preco` da última raspagem (Yahoo, ou brapi/Cotahist no fallback) — é dele que saem indicadores, strike e prêmio. A cotação mostrada na aba Dados é a do Fundamentus, outro número de propósito.

Instruções: `GET /api/instrucoes` lê `web/instrucoes.md`. Testes recusam certas palavras de terminal nesse texto.

HTML e JS usam caminhos relativos (`static/…`, `fetch("api/…")`), não `/static` nem `/api`. Assim o dashboard funciona na raiz local e atrás de um prefixo no proxy (`X-Forwarded-Prefix`). O seletor de vencimento é um combo da UI (fonte e scroll do tema); o `<select id="vencimento">` fica no DOM só para o valor.

`pip install` leva `web/templates`, `web/static` e `instrucoes.md` (`[tool.setuptools.package-data]`). Sem isso a home 500 e os estáticos 404 — o processo em produção lê o pacote instalado, não a pasta `src/`.

## Armadilhas de fonte

- Yahoo: `null` no close é buraco, não zero. Sem isso IFR/HV/MM mentem. O à vista do instante (`preco`) é o último período da série: troca a barra de hoje ou anexa. Ver `docs/superpowers/specs/2026-08-17-indicadores-ultimo-periodo.md`. Cotações ~15 minutos atrasadas em relação ao horário da raspagem (não é o pregão do carimbo).
- Yahoo: Chart 2y/1d, 3 tentativas por ticker; fecha `null` como buraco.
- brapi sem token não chama rede; Cotahist não ajusta desdobro; cache do ano corrente revalida após 1 dia.
- OpLab cadeia: página grande (VALE3 ~5 MB). Não persistir o HTML.
- Fundamentus: charset iso-8859-1; percentuais da tabela viram fração (0,10 = 10%).
- Snapshot antigo sem `last`: até o próximo scrape a série fica sem liquidez. Campo opcional no load.

## Como rodar

```
python -m venda_de_put scrape
python -m venda_de_put scrape --from-step oplab
python -m venda_de_put serve --host 127.0.0.1 --port 0
python -m pytest
```

Windows: duplo-clique `iniciar-dashboard.bat` (porta 8765, ou aleatória via
`scripts/pick_port.py` se estiver ocupada) — sobe e abre o navegador sozinho.

`VENDA_DE_PUT_DATA` sobrescreve o diretório `data/`. `VENDA_DE_PUT_ADMIN_PASSWORD`
e `VENDA_DE_PUT_SECRET_KEY` (login de admin, ADR 0004) e
`VENDA_DE_PUT_BRAPI_TOKEN` (fallback de à vista; sem ele a brapi não chama a rede)
vêm de `.env` na raiz (copie `.env.example`) — `paths.load_dotenv` carrega
sozinho, sem exportar na mão.
