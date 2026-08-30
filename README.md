# Venda de PUT

**Versão 1.0.0** — primeira versão estável.

Página web que responde: **quais papéis do universo da B3 aceito vender put agora**,
com strike e taxa no vencimento escolhido. Substitui a planilha Excel que dependia
de colar Fundamentus e de um terminal de corretora via RTD.

Três listas no Dashboard (fundamentalista, técnico, combinado), prêmio-alvo
escalado por √(dias/30) e strike de entrada no vencimento. Ferramenta de seleção,
não recomendação de compra ou venda.

Como as fórmulas da planilha viraram esta página: [docs/conversao-excel.md](docs/conversao-excel.md).
Glossário: [CONTEXT.md](CONTEXT.md).

## O que faz

- Oito abas: Dashboard, Ativos, Dados, Setores, Config, Vencimentos, Feriados, Instruções.
- Universo curado (ticker → grupo) em `data/universe.json`.
- Coleta: Yahoo (preço e série), OpLab (IV e cadeia de puts), Fundamentus (balanço). Se o Yahoo perde um ticker (3 tentativas), o à vista vem da brapi.dev; sem técnico anterior, a série vem dos ZIPs Cotahist da B3.
- Estado de mercado = um JSON em disco. A UI só lê. Atualizar relê o arquivo; raspar é outro passo.
- Login de administrador único gateia Config, Feriados e o botão de raspar.
- `/carteira` é a carteira pessoal: login de usuário próprio, independente do admin. Cada pessoa só vê os próprios lançamentos.
- Dados pessoais em `data/carteira.sqlite3` (runtime, fora do git). Mercado continua no snapshot JSON.
- Detalhe da carteira: [docs/carteira-pessoal.md](docs/carteira-pessoal.md).
- Cotações ~15 minutos atrasadas em relação ao horário da raspagem.

Escopo fechado: [docs/mvp.md](docs/mvp.md). Desenho: [docs/sdd.md](docs/sdd.md).

## Requisitos

- Python 3.11 ou mais novo
- Rede só na hora do scrape (Yahoo, OpLab, Fundamentus; brapi e Cotahist no fallback)

## Subir local

```
python -m pip install -e ".[dev]"
cp .env.example .env
```

No Windows o equivalente do `cp` é `copy .env.example .env`. Preencha:

| Variável | Para quê |
|---|---|
| `VENDA_DE_PUT_ADMIN_PASSWORD` | senha do admin (Config / Feriados / raspar) |
| `VENDA_DE_PUT_SECRET_KEY` | assina o cookie; `openssl rand -hex 32` |
| `VENDA_DE_PUT_BRAPI_TOKEN` | opcional; à vista se o Yahoo falhar 3 vezes no ticker |

```
python -m venda_de_put scrape
python -m venda_de_put serve --host 127.0.0.1 --port 8765
python -m pytest
```

Windows sem terminal: duplo-clique em `iniciar-dashboard.bat` (abre o navegador;
se 8765 estiver ocupada, escolhe outra porta).

HTML e JS usam URL relativa (`static/…`, `api/…`): funciona na raiz e atrás de
um prefixo no proxy. Assets de UI entram no `pip install` (`package-data`).

`VENDA_DE_PUT_DATA` aponta o diretório `data/` para outro lugar, se precisar.

## Como está organizado

```
scrape (Yahoo + OpLab + Fundamentus [+ brapi/Cotahist])
   → data/snapshots/current.json
   → GET /api/*  →  app.js (uma página, oito abas)

carteira.sqlite3
   → /api/carteira  →  /carteira (login de usuário, não o admin)
```

| Pasta / arquivo | Papel |
|---|---|
| `src/venda_de_put/` | pacote: fontes, indicadores, scoring, strike, API |
| `src/venda_de_put/web/` | HTML/CSS/JS e o texto da aba Instruções |
| `data/` | `config.json`, `universe.json`, `feriados.json` (editáveis) |
| `tests/` | pytest; fixtures extraídas da planilha em `tests/fixtures/` |
| `docs/` | MVP, SDD, scoring, ADRs, conversão Excel, planos |

Quem for implementar ou revisar com IA: comece em [AGENTS.md](AGENTS.md).

## O que não vai para o GitHub

Segredos e artefatos de máquina ficam fora do git (veja `.gitignore`):

- `.env` (senha, chave de sessão, token brapi)
- a planilha `.xlsx`
- snapshot gerado (`data/snapshots/current.json`, Cotahist baixado)
- SQLite da carteira (`data/carteira.sqlite3`, `-wal`, `-shm`)
- `deploy/` (units systemd, nginx, runbook da VPS)
- zips de checkouts antigos em `archive/`
- rascunhos locais (`.scratch/`, dumps, editores)

O repositório público leva código, testes, docs de produto e o `.env.example`
com as chaves **vazias**.

## Documentos

| Documento | Quando abrir |
|---|---|
| [CONTEXT.md](CONTEXT.md) | vocabulário (SINAL, PctF, prêmio-alvo…) |
| [docs/conversao-excel.md](docs/conversao-excel.md) | planilha → esta página |
| [docs/mvp.md](docs/mvp.md) | o que entra e o que fica fora |
| [docs/sdd.md](docs/sdd.md) | scrape, snapshot, strike, fontes |
| [docs/carteira-pessoal.md](docs/carteira-pessoal.md) | carteira pessoal, campos amarelos/calculados, backup SQLite |
| [docs/scoring.md](docs/scoring.md) | ScoreF, PctF, ScoreT, ScoreC, listas ①②③ |
| [docs/adr/](docs/adr/) | decisões que não se revertem de leve |
| [docs/plano-implementacao.md](docs/plano-implementacao.md) | ponte para o plano executável |

Branch de integração: **`main`**.
