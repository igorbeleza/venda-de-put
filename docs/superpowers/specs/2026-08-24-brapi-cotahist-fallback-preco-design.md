# Fallback de preço: brapi.dev + Cotahist

Data: 2026-08-24

Yahoo continua a fonte principal de preço. Se falhar **3 vezes seguidas no mesmo ticker, na mesma raspagem**, o scrape busca o à vista na brapi.dev. Sem técnico anterior no snapshot, o histórico de ~2 anos vem dos ZIPs anuais Cotahist da B3 (download e cache automáticos). Scoring, strike, OpLab e Fundamentus não mudam.

Autoridade de vocabulário: `CONTEXT.md`. Ao implementar, atualizar a tabela de módulos em `docs/sdd.md` e o `.env.example`.

## Pedido

Consulta de preço não pode depender só do Yahoo. Fallback pontual, por ticker, na mesma coleta. Aviso visível quando a consulta ao vivo falhou e a tela está com o último pacote bom.

## Decisões

| Tema | Escolha |
|---|---|
| Gatilho | Por ticker, 3 tentativas Yahoo; depois brapi naquele papel. Os outros seguem no Yahoo. |
| Brapi | Só o à vista (`regularMarketPrice`). Sem série. |
| Histórico | Snapshot **não** guarda fechamentos. Com técnico anterior, reusa MM200/IFR/Boll/HV. |
| Bootstrap | Sem técnico anterior: Cotahist monta a série (anos corrente + anterior). |
| Token | `VENDA_DE_PUT_BRAPI_TOKEN` no `.env`. Sem token, brapi não chama a rede. Sem campo na Config. |
| Sem brapi | Tem técnico anterior → reusa o pacote inteiro (preço velho incluso). Sem anterior → Cotahist série + último fechamento como `preco`. |
| Aviso | Passo Config `yahoo` = `falhou` **e** faixa no Dashboard (aba das listas). |
| Fallback ok | Brapi cobriu os que o Yahoo perdeu → passo `ok`, sem faixa, sem “usou brapi” na UI. |
| Arquitetura | Três módulos; `run_scrape` encadeia. Não um `PriceSource` composto. |

## Arquitetura

O passo de progresso continua `yahoo`. Três contratos estreitos:

| Unidade | Faz | Não faz |
|---|---|---|
| `YahooHttp` | Chart 2y/1d, **3** tentativas por ticker → `CandleSeries` | Fallback |
| `BrapiSpotHttp` | GET em lote → `{ticker: preco}` | Série, indicadores |
| `CotahistBootstrap` | Baixa/cacheia `COTAHIST_A{ano}` → série de fechamentos | À vista ao vivo |

Protocolos novos em `sources/types.py`:

```
class SpotSource(Protocol):
    def fetch_spots(self, tickers: list[str]) -> dict[str, float]: ...

class HistoryBootstrap(Protocol):
    def fetch_history(self, tickers: list[str]) -> dict[str, CandleSeries]: ...
```

`PriceSource.fetch` permanece `dict[str, CandleSeries]`. `run_scrape` ganha `spot: SpotSource | None = None` e `history: HistoryBootstrap | None = None`. `None` = pular aquele estágio (testes atuais). O CLI de scrape sempre passa os dois.

`app.py` não importa `scrape.py` nem os sources novos.

## Componentes

### YahooHttp

`src/venda_de_put/sources/yahoo.py`. `range(2)` vira `range(3)`. Pausa 150–250 ms entre tickers. Falha de um ticker não aborta os outros. URL, parse, `apply_spot_as_last_period` e `null` = buraco: iguais.

### BrapiSpotHttp

`src/venda_de_put/sources/brapi.py`. Sem SDK.

- `GET https://brapi.dev/api/v2/stocks/quote?symbols=T1,T2,…`
- Header `Authorization: Bearer {token}` (nunca `?token=` na URL).
- Token: `os.environ.get("VENDA_DE_PUT_BRAPI_TOKEN", "").strip()`. `load_dotenv` já existente; não sobrescreve env exportada.
- Sem token (ausente ou vazio): `fetch_spots` devolve `{}` sem GET.
- Um único GET com o subconjunto que o Yahoo perdeu. Símbolos **sem** `.SA`.
- Parse: `results[].symbol` → `results[].regularMarketPrice` (`float`). Ticker ausente, `null` ou não-numérico: omitir.
- `httpx.Client` injetável, `USER_AGENT` e timeout 30s como as outras fontes.

### CotahistBootstrap

`src/venda_de_put/sources/cotahist.py`. Só corre se existir ticker **frio**: Yahoo não trouxe série **e** o snapshot anterior não tem esse ticker em `assets`, ou `technicals` é `None`.

- Anos: corrente e anterior (`America/Sao_Paulo` em `now`).
- URL: `https://bvmf.bmfbovespa.com.br/InstDados/SerHist/COTAHIST_A{YYYY}.ZIP`
- Cache: `data/cotahist/COTAHIST_A{YYYY}.ZIP` (`VENDA_DE_PUT_DATA` / `data_dir`). Gitignore dessa pasta (zips e `.TXT` extraídos).
- Cache hit: ZIP do ano **anterior** reusa sempre. ZIP do ano **corrente** reusa se o arquivo tem ≤ 1 dia de idade (`st_mtime`); senão tenta baixar de novo. GET falho + ZIP velho existe → usa o velho.
- Parser (fixture, não B3 ao vivo). Layout fixo 1-indexado, registro de 245 chars. Usar só: `TIPREG` 1–2 = `01`, `DATA` 3–10 (`YYYYMMDD`), `CODBDI` 11–12 = `02` (lote padrão), `CODNEG` 13–24 strip, `TPMERC` 25–27 = `010` (vista), `PREULT` 109–121 (÷ 100). Ignorar o resto da linha. Ordenar por data. Dia sem negócio = ausente na lista (não inventar `null`). `PREULT` inválido = pular a linha.
- `preco` da série = último fechamento. `max_52` / `min_52` = máx/mín dos fechamentos da série (ou `None` se vazia). Timestamps Unix em `America/Sao_Paulo` para `apply_spot_as_last_period`.
- Cotahist é **não ajustado** (desdobro/provento). Yahoo costuma ser ajustado. Aceito no bootstrap; a próxima Yahoo boa substitui a série.
- `httpx.Client` injetável. Download é o ZIP binário.

### Snapshot, API, UI

Não há campo novo obrigatório no JSON do snapshot. O carimbo `source="yahoo"` carrega o aviso:

- Consulta ao vivo falhou para pelo menos um ticker → `SourceStamp("yahoo", now, ok=False, error=<frase>, stale=True)`.
- Senão → `ok=True`, `error=None`, `stale=False`.

Frase (Config e Dashboard, a mesma):

> A consulta de preço falhou; os dados na tela podem ser os da última coleta boa.

`GET /api/dashboard` inclui `price_notice: str | null`. `null` quando o carimbo yahoo está `ok`. Valor = `error` do carimbo quando `ok` é falso. `POST /api/refresh` não muda: só relê o snapshot; a UI pede o dashboard de novo.

Dashboard (aba das listas): faixa visível **acima das listas** (entre a fita de prêmio e `.lists`), não toast, independente do badge `dado velho` (`is_stale` de horário de coleta — outro conceito). Config: passo `yahoo` `falhou` com a frase no `erro`. Sem campo de token na Config.

`.env.example` documenta `VENDA_DE_PUT_BRAPI_TOKEN=`.

## Fluxo

Uma raspagem (ciclo inteiro ou `--from-step yahoo`, que continua puxando os quatro passos):

1. `YahooHttp.fetch(universo)`. Guardar `yahoo_ok = set(series)`. Exceção → `series = {}`, `yahoo_ok = set()` e **mesmo assim** segue o fallback (não abortar brapi/Cotahist).
2. `faltou = universo − yahoo_ok`. Se `faltou` e `spot` não é `None`, `spots = spot.fetch_spots(faltou)`.
3. `frios = [t em faltou sem técnico anterior]`. Se `frios` e `history` não é `None`, `hist = history.fetch_history(frios)`. Em cada série de `hist` que tiver spot brapi, aplicar `apply_spot_as_last_period`. Depois `series.update(hist)` (todas as séries Cotahist, com ou sem spot). **Não** misturar Cotahist em `yahoo_ok`.
4. Técnico por ticker:
   1. Tem série (Yahoo ou Cotahist) → MM200, IFR, Boll Inf, HV e `preco` nessa série, como hoje.
   2. Senão tem técnico anterior → reusa MM200/IFR/Boll/HV (e IV como já); `preco` = spot brapi se houver, senão o `preco` velho.
   3. Senão → tudo `None` (“sem dado”).
5. OpLab / Fundamentus / cadeia inalterados.

**À vista desta coleta (vivo):** ticker ∈ `yahoo_ok` **ou** ticker ∈ `spots`. Série só Cotahist sem spot brapi **não** é vivo.

**Aviso acende** se existe ticker do universo fora do conjunto vivo. **Não acende** se Yahoo cobriu todos, ou o brapi cobriu os que o Yahoo perdeu.

A regra “menos da metade do Yahoo ⇒ fonte falhou” **sai**. O passo olha o à vista vivo (Yahoo **ou** brapi). Listas ①②③ e strike não reordenam por causa da fonte; só mudam se `preco`/indicadores mudarem.

Retry de passo, `retry_completo` (> 1 h) e “fonte morta não zera número” permanecem.

## Erros

| Caso | Efeito |
|---|---|
| Yahoo timeout / 4xx / 5xx / JSON sem `result` | Conta 1 tentativa. 3 no ticker → `faltou`. Outros seguem. |
| Sem token / token vazio | `fetch_spots` → `{}`, sem GET. |
| Brapi 401 / 403 / 429 / 5xx | Lote inteiro sem spot. Sem retry extra. |
| Ticker ausente em `results` | Sem spot naquele papel. |
| Cotahist GET falha, sem ZIP em cache | `frios` sem série. |
| Cotahist GET falha, ZIP velho existe | Usa o velho. |
| ZIP corrupto / TXT ausente | `frios` sem série. |
| Ticker não aparece no Cotahist | Sem série naquele papel. |
| Universo vazio | Passo falha (`no tickers`), como a guarda atual. |

Dashboard nunca inventa `0`. “sem dado” só sem série nova **e** sem técnico anterior. `stale=true` no carimbo yahoo quando o aviso acende.

## Fora de escopo

- Token na UI / `config.json`
- Persistir série de fechamentos no snapshot
- Opções, IV ou fundamentos da brapi
- Cotahist no ciclo feliz (Yahoo ok)
- Passo extra na barra de raspagem
- Ajuste de desdobro no Cotahist
- Smoke ao vivo exigindo brapi ou Cotahist
- Faixa nas abas Ativos / Dados / Setores (só Dashboard + Config)

## Testes

Fixtures e `httpx.Client` (ou fake `SpotSource` / `HistoryBootstrap`) injetados. Nenhum teste chama Yahoo, brapi ou B3 ao vivo.

- Yahoo: falha, falha, sucesso → série; três falhas → ticker omitido.
- Brapi: parse de `regularMarketPrice`; sem token → zero GET; lote pede só `faltou`.
- Cotahist: fixture com vista vs opção, `PREULT`, ticker frio vs com técnico anterior; cache hit não baixa; cache do ano corrente com `mtime` > 1 dia dispara GET; GET falho reusa ZIP; `fetch_history` só recebe `frios`.
- Scrape: Yahoo cobre todos → `spot`/`history` não chamados, sem aviso.
- Scrape: Yahoo perde um ticker **com** técnico anterior + spot brapi → indicadores velhos, `preco` novo, passo `ok`, `price_notice` null.
- Scrape: Yahoo perde, brapi vazio, há anterior → reusa tudo, carimbo `ok=False`, frase no `error`, `stale=True`.
- Scrape: sem anterior, Cotahist série + spot brapi → indicadores na série Cotahist, último período = spot, passo `ok`.
- Scrape: sem anterior, Cotahist falha, sem spot → “sem dado”, aviso aceso.
- Scrape: `price.fetch` levanta exceção → ainda chama brapi/Cotahist nos tickers.
- API/UI: `price_notice` no `GET /api/dashboard` quando carimbo yahoo falhou; faixa no HTML/JS acima das listas; passo Config `falhou` com a frase. Sem notice → faixa `hidden`.
- Guarda: `app.py` não importa `scrape.py` nem `brapi`/`cotahist`.
- Snapshot antigo: aviso sai só do carimbo `yahoo`; load sem campo extra.

`python -m pytest` no fim. Smoke ao vivo (`PETR4` Yahoo) inalterado.
