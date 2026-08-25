# Fallback de preço brapi + Cotahist — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Se o Yahoo falhar 3 vezes no mesmo ticker na mesma raspagem, buscar o à vista na brapi.dev; sem técnico anterior, montar o histórico pelos ZIPs Cotahist da B3; avisar no Config e no Dashboard quando a consulta ao vivo falhou.

**Architecture:** `YahooHttp` continua `PriceSource`. `BrapiSpotHttp` (`SpotSource`) devolve só `{ticker: preco}`. `CotahistBootstrap` (`HistoryBootstrap`) devolve `CandleSeries` para tickers frios. `run_scrape` encadeia os três e carimba o passo `yahoo`. Scoring/strike/OpLab não mudam. `app.py` não importa `scrape.py` nem os sources novos.

**Tech Stack:** Python, httpx, pytest, FastAPI, HTML/CSS/JS do dashboard. Sem SDK brapi. Sem banco.

**Spec:** `docs/superpowers/specs/2026-08-24-brapi-cotahist-fallback-preco-design.md`

## Global Constraints

- Frase do aviso (Config e Dashboard, idêntica): `A consulta de preço falhou; os dados na tela podem ser os da última coleta boa.`
- Token: `VENDA_DE_PUT_BRAPI_TOKEN` no `.env` via `paths.load_dotenv`. Sem token → brapi não faz GET. Sem campo na Config.
- Yahoo: **3** tentativas por ticker (`range(3)`). Pausa 150–250 ms só entre tickers.
- Brapi: `GET https://brapi.dev/api/v2/stocks/quote?symbols=T1,T2,…` com `Authorization: Bearer`. Nunca `?token=` na URL. Símbolos sem `.SA`. Sem retry extra.
- Cotahist URL: `https://bvmf.bmfbovespa.com.br/InstDados/SerHist/COTAHIST_A{YYYY}.ZIP`. Layout 1-indexado 245 chars: `TIPREG` 1–2=`01`, `DATA` 3–10, `CODBDI` 11–12=`02`, `CODNEG` 13–24, `TPMERC` 25–27=`010`, `PREULT` 109–121 ÷ 100. Timeout **60s** no ZIP (as outras fontes: 30s). Validar ZIP antes de gravar no cache; ZIP ruim num ano não descarta o outro.
- Ticker **frio** = Yahoo não trouxe série **e** não há técnico anterior **aproveitável**: `technicals` ausente/`None`, ou `preco` e `mm200` ambos `None`. O `TechnicalInput` de oito nulos que `run_scrape` grava em “sem dado” **é frio** — senão o Cotahist nunca dispara na segunda raspagem.
- Passo de progresso continua `yahoo`. Sem passo extra na barra.
- `app.py` não importa `scrape.py`, `sources.brapi` nem `sources.cotahist`.
- Snapshot **não** persiste série de fechamentos. Overlay: indicadores do técnico anterior + `preco` brapi (ou o velho).
- À vista vivo = ticker ∈ `yahoo_ok` ∪ `spots`. Cotahist sozinho não é vivo.
- Aviso acende se **algum** ticker do universo não é vivo. A regra “menos da metade do Yahoo” sai.
- Dado ausente = texto “sem dado”, nunca zero inventado.
- `python -m pytest` no fim de cada tarefa. Testes sem rede (Yahoo/brapi/B3 ao vivo).
- User-Agent: `venda-de-put/1.0 (+uso-pessoal)`.

## File map

| File | Responsibility |
|---|---|
| `src/venda_de_put/sources/types.py` | Protocolos `SpotSource`, `HistoryBootstrap` |
| `src/venda_de_put/sources/yahoo.py` | 3 tentativas por ticker |
| `src/venda_de_put/sources/brapi.py` | Parse + GET lote de à vista |
| `src/venda_de_put/sources/cotahist.py` | Cache ZIP + parser + `CandleSeries` |
| `src/venda_de_put/models.py` | `CandleSeries.timestamps` opcional |
| `src/venda_de_put/scrape.py` | Encadeia Yahoo → brapi → Cotahist; overlay de `preco`; carimbo |
| `src/venda_de_put/scrape_progress.py` | Constante `PRICE_NOTICE` |
| `src/venda_de_put/web/app.py` | `price_notice` no `GET /api/dashboard` |
| `src/venda_de_put/web/templates/index.html` | Faixa `#price-notice` |
| `src/venda_de_put/web/static/app.js` | Liga/desliga a faixa |
| `src/venda_de_put/web/static/app.css` | Estilo da faixa |
| `.env.example` | Documenta o token |
| `.gitignore` | `data/cotahist/` |
| `docs/sdd.md` | Tabela de módulos + apagar “Planejado (não implementado)” |
| `AGENTS.md` | Linha do fallback: deixa de dizer “ainda sem código” |

---

### Task 1: YahooHttp — 3 tentativas por ticker

**Files:**
- Modify: `src/venda_de_put/sources/yahoo.py` (`range(2)` → `range(3)`)
- Test: `tests/test_yahoo_http.py` (criar)

**Interfaces:**
- Consumes: `YahooHttp.fetch(tickers: list[str]) -> dict[str, CandleSeries]` (já existe)
- Produces: o mesmo contrato; 3 GET por ticker antes de omitir

- [ ] **Step 1: Write the failing tests**

```python
from venda_de_put.sources.yahoo import YahooHttp, YAHOO_CHART


class _Resp:
    def __init__(self, status: int, payload: dict | None = None) -> None:
        self.status_code = status
        self._payload = payload or {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")

    def json(self) -> dict:
        return self._payload


class _Scripted:
    def __init__(self, outcomes: list) -> None:
        self.outcomes = list(outcomes)
        self.n = 0

    def get(self, url, headers=None):
        self.n += 1
        item = self.outcomes.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _chart(preco: float = 41.75) -> dict:
    return {
        "chart": {
            "result": [{
                "meta": {
                    "regularMarketPrice": preco,
                    "fiftyTwoWeekHigh": 42.0,
                    "fiftyTwoWeekLow": 30.0,
                },
                "timestamp": [1, 2, 3],
                "indicators": {"quote": [{"close": [40.0, 40.5, 41.0]}]},
            }]
        }
    }


def test_yahoo_http_terceira_tentativa_grava_serie():
    client = _Scripted([
        RuntimeError("net"),
        _Resp(500),
        _Resp(200, _chart()),
    ])
    out = YahooHttp(client).fetch(["PETR4"])
    assert "PETR4" in out
    assert out["PETR4"].preco == 41.75
    assert client.n == 3
    assert YAHOO_CHART.format(ticker="PETR4")


def test_yahoo_http_tres_falhas_omitam_ticker():
    client = _Scripted([
        RuntimeError("a"),
        RuntimeError("b"),
        RuntimeError("c"),
    ])
    out = YahooHttp(client).fetch(["PETR4"])
    assert out == {}
    assert client.n == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_yahoo_http.py -v`

Expected: FAIL — terceira tentativa não chega (`range(2)`); `test_yahoo_http_terceira_tentativa_grava_serie` falha com ticker omitido ou `n != 3`.

- [ ] **Step 3: Write minimal implementation**

In `src/venda_de_put/sources/yahoo.py`, change only the retry loop:

```python
for _attempt in range(3):
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_yahoo_http.py tests/test_sources.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_yahoo_http.py src/venda_de_put/sources/yahoo.py
git commit -m "feat: Yahoo tenta 3 vezes por ticker"
```

---

### Task 2: BrapiSpotHttp

**Files:**
- Modify: `src/venda_de_put/sources/types.py`
- Modify: `src/venda_de_put/sources/__init__.py`
- Create: `src/venda_de_put/sources/brapi.py`
- Test: `tests/test_brapi.py`

**Interfaces:**
- Consumes: `USER_AGENT`; env `VENDA_DE_PUT_BRAPI_TOKEN`
- Produces:
  - `class SpotSource(Protocol): def fetch_spots(self, tickers: list[str]) -> dict[str, float]: ...`
  - `parse_brapi_quote(payload: dict) -> dict[str, float]`
  - `class BrapiSpotHttp: def __init__(self, token: str | None = None, client: httpx.Client | None = None) -> None`
  - `BrapiSpotHttp.fetch_spots(tickers: list[str]) -> dict[str, float]`
  - Constante `BRAPI_QUOTE = "https://brapi.dev/api/v2/stocks/quote"`

- [ ] **Step 1: Write the failing tests**

```python
import httpx

from venda_de_put.sources.brapi import BRAPI_QUOTE, BrapiSpotHttp, parse_brapi_quote


def test_parse_brapi_quote_pega_preco():
    payload = {
        "results": [
            {"symbol": "PETR4", "regularMarketPrice": 41.75},
            {"symbol": "VALE3", "regularMarketPrice": None},
            {"symbol": "ITUB4", "regularMarketPrice": "35.1"},
            {"symbol": "BAD", "regularMarketPrice": "x"},
        ]
    }
    out = parse_brapi_quote(payload)
    assert out["PETR4"] == 41.75
    assert out["ITUB4"] == 35.1
    assert "VALE3" not in out
    assert "BAD" not in out


def test_brapi_sem_token_nao_faz_get(monkeypatch):
    monkeypatch.delenv("VENDA_DE_PUT_BRAPI_TOKEN", raising=False)
    n = {"get": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        n["get"] += 1
        return httpx.Response(200, json={"results": []})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    out = BrapiSpotHttp(token="", client=client).fetch_spots(["PETR4"])
    assert out == {}
    assert n["get"] == 0


def test_brapi_lote_so_os_pedidos():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["request"] = request
        seen["auth"] = request.headers.get("authorization")
        assert "token=" not in str(request.url)
        return httpx.Response(200, json={
            "results": [{"symbol": "PETR4", "regularMarketPrice": 10.0}]
        })

    client = httpx.Client(transport=httpx.MockTransport(handler))
    out = BrapiSpotHttp(token="abc", client=client).fetch_spots(["PETR4", "VALE3"])
    assert out == {"PETR4": 10.0}
    # httpx percent-encoda a vírgula (PETR4%2CVALE3). Assertar o valor decodificado.
    assert seen["request"].url.params["symbols"] == "PETR4,VALE3"
    assert seen["auth"] == "Bearer abc"
    assert str(seen["request"].url).startswith(BRAPI_QUOTE)


def test_brapi_http_erro_devolve_vazio():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"message": "rate"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    out = BrapiSpotHttp(token="abc", client=client).fetch_spots(["PETR4"])
    assert out == {}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_brapi.py -v`

Expected: FAIL — `ModuleNotFoundError: venda_de_put.sources.brapi`

- [ ] **Step 3: Write minimal implementation**

`src/venda_de_put/sources/types.py` — append:

```python
class SpotSource(Protocol):
    def fetch_spots(self, tickers: list[str]) -> dict[str, float]: ...


class HistoryBootstrap(Protocol):
    def fetch_history(self, tickers: list[str]) -> dict[str, CandleSeries]: ...
```

`src/venda_de_put/sources/__init__.py`:

```python
from venda_de_put.sources.types import (
    FundamentalsSource,
    HistoryBootstrap,
    IvSource,
    PriceSource,
    SpotSource,
)

__all__ = [
    "PriceSource",
    "IvSource",
    "FundamentalsSource",
    "SpotSource",
    "HistoryBootstrap",
]
```

`src/venda_de_put/sources/brapi.py`:

```python
from __future__ import annotations

import os
import httpx

from venda_de_put.sources.types import USER_AGENT

BRAPI_QUOTE = "https://brapi.dev/api/v2/stocks/quote"


def parse_brapi_quote(payload: dict) -> dict[str, float]:
    out: dict[str, float] = {}
    for row in payload.get("results") or []:
        sym = row.get("symbol")
        px = row.get("regularMarketPrice")
        if not sym or px is None:
            continue
        try:
            out[str(sym)] = float(px)
        except (TypeError, ValueError):
            continue
    return out


class BrapiSpotHttp:
    def __init__(
        self,
        token: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        if token is None:
            token = os.environ.get("VENDA_DE_PUT_BRAPI_TOKEN", "")
        self._token = (token or "").strip()
        self._client = client
        self._owns = client is None

    def fetch_spots(self, tickers: list[str]) -> dict[str, float]:
        if not self._token or not tickers:
            return {}
        client = self._client or httpx.Client(
            headers={"User-Agent": USER_AGENT}, timeout=30.0
        )
        try:
            resp = client.get(
                BRAPI_QUOTE,
                params={"symbols": ",".join(tickers)},
                headers={
                    "User-Agent": USER_AGENT,
                    "Authorization": f"Bearer {self._token}",
                },
            )
            resp.raise_for_status()
            return parse_brapi_quote(resp.json())
        except Exception:
            return {}
        finally:
            if self._owns and self._client is None:
                client.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_brapi.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/venda_de_put/sources/types.py src/venda_de_put/sources/__init__.py src/venda_de_put/sources/brapi.py tests/test_brapi.py
git commit -m "feat: brapi.dev como fonte de a vista em lote"
```

---

### Task 3: CotahistBootstrap

**Files:**
- Modify: `src/venda_de_put/models.py` (`CandleSeries.timestamps`)
- Create: `src/venda_de_put/sources/cotahist.py`
- Create: `tests/test_cotahist.py`
- Modify: `.gitignore` (pasta `data/cotahist/`)

**Interfaces:**
- Consumes: `SpotSource` não; só tickers frios que o scrape passar. `USER_AGENT`, `TZ`, `CandleSeries`
- Produces:
  - `COTAHIST_URL = "https://bvmf.bmfbovespa.com.br/InstDados/SerHist/COTAHIST_A{year}.ZIP"`
  - `parse_cotahist_line(line: str) -> tuple[date, str, float] | None`
  - `parse_cotahist_text(text: str, tickers: list[str]) -> dict[str, list[tuple[date, float]]]`
  - `class CotahistBootstrap:`
    - `__init__(self, cache_dir: Path, client: httpx.Client | None = None, now: datetime | None = None)`
    - `fetch_history(self, tickers: list[str]) -> dict[str, CandleSeries]`
  - Timeout 60s no GET do ZIP. `zipfile.is_zipfile` antes de gravar no cache; `_read_zip` try/except por ano.
  - `CandleSeries.timestamps: list[Optional[int]]` (default `[]`; construtores posicionais de 6 args continuam válidos)

- [ ] **Step 1: Write the failing tests**

Helper no próprio teste (não no src):

```python
from datetime import date, datetime
from pathlib import Path
import io
import os
import time
import zipfile

import httpx

from venda_de_put.models import CandleSeries
from venda_de_put.sources.cotahist import (
    COTAHIST_URL,
    CotahistBootstrap,
    parse_cotahist_line,
    parse_cotahist_text,
)
from venda_de_put.tz import TZ


def _line(
    d: str,
    ticker: str,
    close: float,
    *,
    tipreg: str = "01",
    bdi: str = "02",
    tpmerc: str = "010",
) -> str:
    chars = [" "] * 245
    chars[0:2] = list(tipreg)
    chars[2:10] = list(d)
    chars[10:12] = list(bdi)
    chars[12:24] = list(ticker.ljust(12))
    chars[24:27] = list(tpmerc)
    chars[108:121] = list(f"{int(round(close * 100)):013d}")
    return "".join(chars)


def test_parse_cotahist_linha_vista_lote_padrao():
    row = parse_cotahist_line(_line("20260815", "PETR4", 41.75))
    assert row == (date(2026, 8, 15), "PETR4", 41.75)


def test_parse_cotahist_ignora_opcao_e_header():
    header = _line("20260815", "PETR4", 1.0, tipreg="00")
    opcao = _line("20260815", "PETR4", 2.0, tpmerc="070")
    frac = _line("20260815", "PETR4", 3.0, bdi="12")
    ok = _line("20260815", "PETR4", 41.75)
    text = "\n".join([header, opcao, frac, ok])
    by = parse_cotahist_text(text, ["PETR4"])
    assert by["PETR4"] == [(date(2026, 8, 15), 41.75)]


def _zip_bytes(year: int, text: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(f"COTAHIST_A{year}.TXT", text)
    return buf.getvalue()


def test_cotahist_cache_hit_nao_baixa(tmp_path: Path):
    now = datetime(2026, 8, 15, 16, 0, tzinfo=TZ)
    n = {"get": 0}
    text = _line("20250815", "PETR4", 30.0) + "\n" + _line("20260814", "PETR4", 40.0)
    (tmp_path / "COTAHIST_A2025.ZIP").write_bytes(_zip_bytes(2025, text))
    (tmp_path / "COTAHIST_A2026.ZIP").write_bytes(_zip_bytes(2026, text))

    def handler(request: httpx.Request) -> httpx.Response:
        n["get"] += 1
        return httpx.Response(500)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    out = CotahistBootstrap(tmp_path, client=client, now=now).fetch_history(["PETR4"])
    assert n["get"] == 0
    assert "PETR4" in out
    assert out["PETR4"].closes[-1] == 40.0
    assert out["PETR4"].preco == 40.0
    assert len(out["PETR4"].timestamps) == len(out["PETR4"].closes)


def test_cotahist_ano_corrente_velho_dispara_get(tmp_path: Path):
    now = datetime(2026, 8, 15, 16, 0, tzinfo=TZ)
    n = {"urls": []}
    p2025 = tmp_path / "COTAHIST_A2025.ZIP"
    p2026 = tmp_path / "COTAHIST_A2026.ZIP"
    p2025.write_bytes(_zip_bytes(2025, _line("20250815", "PETR4", 30.0) + "\n"))
    p2026.write_bytes(_zip_bytes(2026, _line("20260102", "PETR4", 10.0) + "\n"))
    old_mtime = time.time() - 86400 - 5
    os.utime(p2026, (old_mtime, old_mtime))

    def handler(request: httpx.Request) -> httpx.Response:
        n["urls"].append(str(request.url))
        body = _zip_bytes(2026, _line("20260814", "PETR4", 40.0) + "\n")
        return httpx.Response(200, content=body)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    out = CotahistBootstrap(tmp_path, client=client, now=now).fetch_history(["PETR4"])
    assert any("COTAHIST_A2026.ZIP" in u for u in n["urls"])
    assert not any("COTAHIST_A2025.ZIP" in u for u in n["urls"])
    assert out["PETR4"].preco == 40.0
    assert n["urls"][0] == COTAHIST_URL.format(year=2026)


def test_cotahist_get_falho_reusa_zip(tmp_path: Path):
    now = datetime(2026, 8, 15, 16, 0, tzinfo=TZ)
    p2025 = tmp_path / "COTAHIST_A2025.ZIP"
    p2026 = tmp_path / "COTAHIST_A2026.ZIP"
    p2025.write_bytes(_zip_bytes(2025, _line("20250815", "PETR4", 30.0) + "\n"))
    p2026.write_bytes(_zip_bytes(2026, _line("20260814", "PETR4", 40.0) + "\n"))
    os.utime(p2026, (time.time() - 86400 - 5, time.time() - 86400 - 5))

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    out = CotahistBootstrap(tmp_path, client=client, now=now).fetch_history(["PETR4"])
    assert out["PETR4"].preco == 40.0


def test_cotahist_get_404_sem_cache_omite(tmp_path: Path):
    now = datetime(2026, 8, 15, 16, 0, tzinfo=TZ)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    out = CotahistBootstrap(tmp_path, client=client, now=now).fetch_history(["PETR4"])
    assert out == {}


def test_cotahist_200_invalido_nao_envenena_cache(tmp_path: Path):
    now = datetime(2026, 8, 15, 16, 0, tzinfo=TZ)
    p2025 = tmp_path / "COTAHIST_A2025.ZIP"
    p2026 = tmp_path / "COTAHIST_A2026.ZIP"
    p2025.write_bytes(_zip_bytes(2025, _line("20250815", "PETR4", 30.0) + "\n"))
    p2026.write_bytes(_zip_bytes(2026, _line("20260814", "PETR4", 40.0) + "\n"))
    os.utime(p2026, (time.time() - 86400 - 5, time.time() - 86400 - 5))

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<html>erro da B3</html>")

    client = httpx.Client(transport=httpx.MockTransport(handler))
    out = CotahistBootstrap(tmp_path, client=client, now=now).fetch_history(["PETR4"])
    assert out["PETR4"].preco == 40.0
    assert zipfile.is_zipfile(p2026)


def test_cotahist_zip_corrupto_num_ano_nao_descarta_o_outro(tmp_path: Path):
    now = datetime(2026, 8, 15, 16, 0, tzinfo=TZ)
    p2025 = tmp_path / "COTAHIST_A2025.ZIP"
    p2026 = tmp_path / "COTAHIST_A2026.ZIP"
    p2025.write_bytes(_zip_bytes(2025, _line("20250815", "PETR4", 30.0) + "\n"))
    p2026.write_bytes(b"not a zip")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    out = CotahistBootstrap(tmp_path, client=client, now=now).fetch_history(["PETR4"])
    assert out["PETR4"].preco == 30.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_cotahist.py -v`

Expected: FAIL — `ModuleNotFoundError: venda_de_put.sources.cotahist`

- [ ] **Step 3: Write minimal implementation**

`src/venda_de_put/models.py` — em `CandleSeries`, depois de `collected_at`:

```python
    timestamps: list[Optional[int]] = field(default_factory=list)
```

`src/venda_de_put/sources/cotahist.py`:

```python
from __future__ import annotations

import io
import time
import zipfile
from datetime import date, datetime
from pathlib import Path

import httpx

from venda_de_put.models import CandleSeries
from venda_de_put.sources.types import USER_AGENT
from venda_de_put.tz import TZ

COTAHIST_URL = "https://bvmf.bmfbovespa.com.br/InstDados/SerHist/COTAHIST_A{year}.ZIP"
CURRENT_YEAR_MAX_AGE = 86400.0


def parse_cotahist_line(line: str) -> tuple[date, str, float] | None:
    if len(line) < 121:
        return None
    if line[0:2] != "01":
        return None
    if line[10:12] != "02":
        return None
    if line[24:27] != "010":
        return None
    raw_date = line[2:10]
    ticker = line[12:24].strip()
    raw_px = line[108:121]
    try:
        d = date(int(raw_date[0:4]), int(raw_date[4:6]), int(raw_date[6:8]))
        px = int(raw_px) / 100.0
    except (TypeError, ValueError):
        return None
    if not ticker:
        return None
    return d, ticker, px


def parse_cotahist_text(
    text: str, tickers: list[str]
) -> dict[str, list[tuple[date, float]]]:
    wanted = set(tickers)
    out: dict[str, list[tuple[date, float]]] = {t: [] for t in tickers}
    for line in text.splitlines():
        row = parse_cotahist_line(line)
        if row is None:
            continue
        d, ticker, px = row
        if ticker in wanted:
            out[ticker].append((d, px))
    for t in list(out):
        if not out[t]:
            del out[t]
        else:
            out[t].sort(key=lambda x: x[0])
    return out


def _ts(d: date) -> int:
    return int(datetime(d.year, d.month, d.day, 18, 0, tzinfo=TZ).timestamp())


class CotahistBootstrap:
    def __init__(
        self,
        cache_dir: Path,
        client: httpx.Client | None = None,
        now: datetime | None = None,
    ) -> None:
        self._cache = Path(cache_dir)
        self._client = client
        self._owns = client is None
        self._now = now or datetime.now(TZ)

    def fetch_history(self, tickers: list[str]) -> dict[str, CandleSeries]:
        if not tickers:
            return {}
        year = self._now.astimezone(TZ).year
        texts: list[str] = []
        for y in (year - 1, year):
            raw = self._zip_bytes(y)
            if not raw:
                continue
            try:
                texts.append(self._read_zip(raw))
            except Exception:
                continue
        merged: dict[str, list[tuple[date, float]]] = {}
        for text in texts:
            part = parse_cotahist_text(text, tickers)
            for t, rows in part.items():
                merged.setdefault(t, []).extend(rows)
        out: dict[str, CandleSeries] = {}
        collected = self._now
        for t, rows in merged.items():
            rows.sort(key=lambda x: x[0])
            closes = [px for _, px in rows]
            stamps = [_ts(d) for d, _ in rows]
            if not closes:
                continue
            out[t] = CandleSeries(
                ticker=t,
                closes=closes,
                preco=closes[-1],
                max_52=max(closes),
                min_52=min(closes),
                collected_at=collected,
                timestamps=stamps,
            )
        return out

    def _zip_bytes(self, year: int) -> bytes | None:
        path = self._cache / f"COTAHIST_A{year}.ZIP"
        current = self._now.astimezone(TZ).year
        if path.is_file():
            age = time.time() - path.stat().st_mtime
            if year != current or age <= CURRENT_YEAR_MAX_AGE:
                return path.read_bytes()
        url = COTAHIST_URL.format(year=year)
        client = self._client or httpx.Client(
            headers={"User-Agent": USER_AGENT}, timeout=60.0
        )
        try:
            resp = client.get(url, headers={"User-Agent": USER_AGENT})
            resp.raise_for_status()
            if not zipfile.is_zipfile(io.BytesIO(resp.content)):
                if path.is_file():
                    return path.read_bytes()
                return None
            self._cache.mkdir(parents=True, exist_ok=True)
            path.write_bytes(resp.content)
            return resp.content
        except Exception:
            if path.is_file():
                return path.read_bytes()
            return None
        finally:
            if self._owns and self._client is None:
                client.close()

    def _read_zip(self, raw: bytes) -> str:
        if not zipfile.is_zipfile(io.BytesIO(raw)):
            raise zipfile.BadZipFile("not a zip")
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            names = zf.namelist()
            if not names:
                raise zipfile.BadZipFile("empty zip")
            data = zf.read(names[0])
        try:
            return data.decode("latin-1")
        except Exception:
            return data.decode("utf-8", errors="replace")
```

`.gitignore` — append:

```
# Cache local dos ZIPs Cotahist (bootstrap de histórico)
data/cotahist/
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_cotahist.py tests/test_sources.py tests/test_scrape.py tests/test_api.py -v`

Expected: PASS. Construtores `CandleSeries(..., collected_at=now)` de 6 args continuam válidos.

- [ ] **Step 5: Commit**

```bash
git add src/venda_de_put/models.py src/venda_de_put/sources/cotahist.py tests/test_cotahist.py .gitignore
git commit -m "feat: bootstrap Cotahist para serie de fechamentos"
```

---

### Task 4: `run_scrape` encadeia Yahoo → brapi → Cotahist

**Files:**
- Modify: `src/venda_de_put/scrape_progress.py` (constante `PRICE_NOTICE`)
- Modify: `src/venda_de_put/scrape.py` (`run_scrape` + imports)
- Test: `tests/test_scrape.py`

**Interfaces:**
- Consumes: `SpotSource.fetch_spots`, `HistoryBootstrap.fetch_history`, `apply_spot_as_last_period`, `PRICE_NOTICE`
- Produces: `run_scrape(..., spot: SpotSource | None = None, history: HistoryBootstrap | None = None)`. `None` = pular o estágio. Carimbo `yahoo` usa `PRICE_NOTICE` quando existe ticker não-vivo.

`PRICE_NOTICE` em `scrape_progress.py` (app.py já importa este módulo; scrape também):

```python
PRICE_NOTICE = (
    "A consulta de preço falhou; os dados na tela podem ser os da última coleta boa."
)
```

- [ ] **Step 1: Write the failing tests**

Acrescentar fakes e testes em `tests/test_scrape.py`:

```python
from dataclasses import replace
from venda_de_put.scrape_progress import PRICE_NOTICE


class FakeSpot:
    def __init__(self, spots: dict[str, float]):
        self.spots = spots
        self.calls: list[list[str]] = []

    def fetch_spots(self, tickers: list[str]) -> dict[str, float]:
        self.calls.append(list(tickers))
        return {t: self.spots[t] for t in tickers if t in self.spots}


class BoomSpot:
    def __init__(self):
        self.calls: list[list[str]] = []

    def fetch_spots(self, tickers: list[str]) -> dict[str, float]:
        self.calls.append(list(tickers))
        raise RuntimeError("brapi down")


class FakeHistory:
    def __init__(self, series: dict[str, CandleSeries]):
        self.series = series
        self.calls: list[list[str]] = []

    def fetch_history(self, tickers: list[str]) -> dict[str, CandleSeries]:
        self.calls.append(list(tickers))
        return {t: self.series[t] for t in tickers if t in self.series}


class BoomPrice:
    def fetch(self, tickers: list[str]) -> dict[str, CandleSeries]:
        raise RuntimeError("yahoo down")
```

Testes (todos neste step). `FakePrice` / `_petr_inputs` já existem no arquivo.

```python
def _serie_ontem(ticker: str, now: datetime, preco: float = 40.0) -> CandleSeries:
    yesterday = int(datetime(2026, 8, 14, 18, 0, tzinfo=TZ).timestamp())
    return CandleSeries(
        ticker=ticker,
        closes=[30.0] * 210,
        preco=preco,
        max_52=45.0,
        min_52=20.0,
        collected_at=now,
        timestamps=[yesterday] * 210,
    )


def test_yahoo_cobre_todos_nao_chama_spot_nem_history():
    price, iv, fund, universe, now = _petr_inputs()
    spot = FakeSpot({"PETR4": 99.0})
    hist = FakeHistory({})
    snap = run_scrape(
        price, iv, fund, AppConfig(), universe, set(), now,
        spot=spot, history=hist,
    )
    assert spot.calls == []
    assert hist.calls == []
    stamp = next(s for s in snap.stamps if s.source == "yahoo")
    assert stamp.ok is True
    assert stamp.error is None


def test_yahoo_perde_com_tecnico_anterior_brapi_atualiza_preco():
    price, iv, fund, universe, now = _petr_inputs()
    first = run_scrape(price, iv, fund, AppConfig(), universe, set(), now)
    petr_first = next(a for a in first.assets if a.ticker == "PETR4")
    spot = FakeSpot({"PETR4": 50.0})
    hist = FakeHistory({})
    second = run_scrape(
        FakePrice({}), iv, fund, AppConfig(), universe, set(), now,
        previous=first, spot=spot, history=hist,
    )
    petr = next(a for a in second.assets if a.ticker == "PETR4")
    assert petr.technicals.preco == 50.0
    assert petr.technicals.mm200 == petr_first.technicals.mm200
    stamp = next(s for s in second.stamps if s.source == "yahoo")
    assert stamp.ok is True
    assert spot.calls[0] == ["PETR4"]
    assert hist.calls == []


def test_yahoo_perde_brapi_vazio_reusa_tudo_e_avisa():
    price, iv, fund, universe, now = _petr_inputs()
    first = run_scrape(price, iv, fund, AppConfig(), universe, set(), now)
    petr_first = next(a for a in first.assets if a.ticker == "PETR4")
    second = run_scrape(
        FakePrice({}), iv, fund, AppConfig(), universe, set(), now,
        previous=first, spot=FakeSpot({}),
    )
    petr = next(a for a in second.assets if a.ticker == "PETR4")
    assert petr.technicals.preco == petr_first.technicals.preco
    stamp = next(s for s in second.stamps if s.source == "yahoo")
    assert stamp.ok is False
    assert stamp.error == PRICE_NOTICE
    assert stamp.stale is True


def test_sem_anterior_cotahist_mais_spot_calcula_na_serie():
    price, iv, fund, universe, now = _petr_inputs()
    hist = FakeHistory({"PETR4": _serie_ontem("PETR4", now)})
    spot = FakeSpot({"PETR4": 41.75})
    snap = run_scrape(
        FakePrice({}), iv, fund, AppConfig(), universe, set(), now,
        previous=None, spot=spot, history=hist,
    )
    petr = next(a for a in snap.assets if a.ticker == "PETR4")
    assert petr.technicals.preco == 41.75
    assert petr.technicals.mm200 is not None
    stamp = next(s for s in snap.stamps if s.source == "yahoo")
    assert stamp.ok is True
    assert hist.calls[0] == ["PETR4"]


def test_sem_anterior_cotahist_falha_sem_spot_sem_dado():
    price, iv, fund, universe, now = _petr_inputs()
    hist = FakeHistory({})
    snap = run_scrape(
        FakePrice({}), iv, fund, AppConfig(), universe, set(), now,
        previous=None, spot=FakeSpot({}), history=hist,
    )
    petr = next(a for a in snap.assets if a.ticker == "PETR4")
    assert petr.technicals.preco is None
    stamp = next(s for s in snap.stamps if s.source == "yahoo")
    assert stamp.ok is False
    assert stamp.error == PRICE_NOTICE


def test_price_fetch_excecao_ainda_chama_brapi():
    price, iv, fund, universe, now = _petr_inputs()
    first = run_scrape(price, iv, fund, AppConfig(), universe, set(), now)
    spot = FakeSpot({"PETR4": 50.0})
    second = run_scrape(
        BoomPrice(), iv, fund, AppConfig(), universe, set(), now,
        previous=first, spot=spot,
    )
    assert spot.calls
    petr = next(a for a in second.assets if a.ticker == "PETR4")
    assert petr.technicals.preco == 50.0
    stamp = next(s for s in second.stamps if s.source == "yahoo")
    assert stamp.ok is True


def test_sem_anterior_cotahist_sem_spot_avisa():
    price, iv, fund, universe, now = _petr_inputs()
    hist = FakeHistory({"PETR4": _serie_ontem("PETR4", now, preco=40.0)})
    snap = run_scrape(
        FakePrice({}), iv, fund, AppConfig(), universe, set(), now,
        previous=None, spot=FakeSpot({}), history=hist,
    )
    petr = next(a for a in snap.assets if a.ticker == "PETR4")
    assert petr.technicals.preco == 40.0
    assert petr.technicals.mm200 is not None
    stamp = next(s for s in snap.stamps if s.source == "yahoo")
    assert stamp.ok is False
    assert stamp.error == PRICE_NOTICE
    assert hist.calls[0] == ["PETR4"]


def test_snapshot_sem_dado_ainda_e_frio_na_proxima():
    price, iv, fund, universe, now = _petr_inputs()
    first = run_scrape(
        FakePrice({}), iv, fund, AppConfig(), universe, set(), now,
        previous=None, spot=FakeSpot({}), history=FakeHistory({}),
    )
    petr_first = next(a for a in first.assets if a.ticker == "PETR4")
    assert petr_first.technicals.preco is None
    assert petr_first.technicals.mm200 is None
    hist = FakeHistory({"PETR4": _serie_ontem("PETR4", now, preco=40.0)})
    second = run_scrape(
        FakePrice({}), iv, fund, AppConfig(), universe, set(), now,
        previous=first, spot=FakeSpot({}), history=hist,
    )
    assert hist.calls == [["PETR4"]]
    petr = next(a for a in second.assets if a.ticker == "PETR4")
    assert petr.technicals.preco == 40.0
    assert petr.technicals.mm200 is not None
    stamp = next(s for s in second.stamps if s.source == "yahoo")
    assert stamp.ok is False
    assert stamp.error == PRICE_NOTICE
```

7. `test_dois_de_tres_yahoo_sem_brapi_avisa` — universo 3 tickers, second scrape só PETR4+VALE3 no FakePrice, sem spot; stamp `ok is False` (a regra da metade saiu):

```python
def test_dois_de_tres_yahoo_sem_brapi_avisa():
    now = datetime(2026, 8, 15, 16, 0, tzinfo=TZ)
    universe = {"PETR4": "A", "VALE3": "B", "ITUB4": "C"}
    series = {
        t: CandleSeries(t, [30.0] * 210, 40.0, 45.0, 20.0, now)
        for t in universe
    }
    first = run_scrape(
        FakePrice(series),
        FakeIv({t: IvPoint(t, 0.3, 10, 0.2) for t in universe}),
        FakeFund([]),
        AppConfig(), universe, set(), now,
    )
    second = run_scrape(
        FakePrice({"PETR4": series["PETR4"], "VALE3": series["VALE3"]}),
        FakeIv({t: IvPoint(t, 0.3, 10, 0.2) for t in universe}),
        FakeFund([]),
        AppConfig(), universe, set(), now, previous=first,
    )
    stamp = next(s for s in second.stamps if s.source == "yahoo")
    assert stamp.ok is False
    assert stamp.error == PRICE_NOTICE
    itub = next(a for a in second.assets if a.ticker == "ITUB4")
    assert itub.technicals.preco == 40.0
```

8. `test_yahoo_perde_um_brapi_cobre_passo_ok` — 2/3 Yahoo + FakeSpot no que faltou → `ok is True`:

```python
def test_yahoo_perde_um_brapi_cobre_passo_ok():
    now = datetime(2026, 8, 15, 16, 0, tzinfo=TZ)
    universe = {"PETR4": "A", "VALE3": "B", "ITUB4": "C"}
    series = {
        t: CandleSeries(t, [30.0] * 210, 40.0, 45.0, 20.0, now)
        for t in universe
    }
    first = run_scrape(
        FakePrice(series),
        FakeIv({t: IvPoint(t, 0.3, 10, 0.2) for t in universe}),
        FakeFund([]),
        AppConfig(), universe, set(), now,
    )
    second = run_scrape(
        FakePrice({"PETR4": series["PETR4"], "VALE3": series["VALE3"]}),
        FakeIv({t: IvPoint(t, 0.3, 10, 0.2) for t in universe}),
        FakeFund([]),
        AppConfig(), universe, set(), now, previous=first,
        spot=FakeSpot({"ITUB4": 41.0}),
    )
    stamp = next(s for s in second.stamps if s.source == "yahoo")
    assert stamp.ok is True
    itub = next(a for a in second.assets if a.ticker == "ITUB4")
    assert itub.technicals.preco == 41.0
    assert itub.technicals.mm200 == next(
        a.technicals.mm200 for a in first.assets if a.ticker == "ITUB4"
    )
```

Em `test_empty_yahoo_fetch_stamps_failed_and_reuses_previous` trocar `assert stamp.error` por `assert stamp.error == PRICE_NOTICE`.

Em `test_yahoo_half_tickers_stamps_failed_and_merges_previous` acrescentar `assert stamp.error == PRICE_NOTICE`.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_scrape.py -v`

Expected: FAIL — `run_scrape` não aceita `spot=` / `history=`; 2 de 3 Yahoo hoje marca `ok=True` (regra da metade).

- [ ] **Step 3: Write minimal implementation**

`scrape_progress.py`: adicionar `PRICE_NOTICE` no topo, depois de `RETRY_MAX_AGE`.

`scrape.py`:

- Import: `from dataclasses import replace`
- Import: `apply_spot_as_last_period` junto dos outros indicators
- Import: `SpotSource, HistoryBootstrap` em `sources.types`
- Import: `PRICE_NOTICE` de `scrape_progress`
- Antes de `run_scrape`, helper de ticker frio (B2 — `TechnicalInput` de nulos é truthy):

```python
def _tecnico_aproveitavel(tech: TechnicalInput | None) -> bool:
    return tech is not None and (
        tech.preco is not None or tech.mm200 is not None
    )
```

- Assinatura de `run_scrape`: depois de `only_steps`,

```python
    spot: SpotSource | None = None,
    history: HistoryBootstrap | None = None,
```

Substituir o bloco yahoo (o `if wanted is None or "yahoo" in wanted`) por:

```python
    series: dict = {}
    yahoo_ok: set[str] = set()
    spots: dict[str, float] = {}
    if wanted is None or "yahoo" in wanted:
        _prog(progress, "yahoo", "raspando")
        try:
            series = price.fetch(tickers)
        except Exception:
            series = {}
        yahoo_ok = set(series)
        faltou = [t for t in tickers if t not in yahoo_ok]
        if faltou and spot is not None:
            try:
                spots = dict(spot.fetch_spots(faltou))
            except Exception:
                spots = {}
        prev_tech_early = {}
        if previous is not None:
            prev_tech_early = {
                a.ticker: a.technicals for a in previous.assets
            }
        frios = [
            t for t in faltou
            if not _tecnico_aproveitavel(prev_tech_early.get(t))
        ]
        if frios and history is not None:
            try:
                hist = dict(history.fetch_history(frios))
            except Exception:
                hist = {}
            for t, cs in list(hist.items()):
                px = spots.get(t)
                if px is not None:
                    closes = apply_spot_as_last_period(
                        cs.closes, px, cs.timestamps or None, now
                    )
                    hist[t] = replace(cs, closes=closes, preco=px)
            series.update(hist)
        if not tickers:
            err = "no tickers"
            stamps.append(SourceStamp("yahoo", now, False, err, True))
            _prog(progress, "yahoo", "falhou", err)
        else:
            live = yahoo_ok | set(spots)
            if any(t not in live for t in tickers):
                stamps.append(SourceStamp("yahoo", now, False, PRICE_NOTICE, True))
                _prog(progress, "yahoo", "falhou", PRICE_NOTICE)
            else:
                stamps.append(SourceStamp("yahoo", now, True, None, False))
                _prog(progress, "yahoo", "ok")
    else:
        _keep_stamp(stamps, previous, "yahoo")
```

No loop do técnico, no `elif prev is not None`:

```python
            mm200, ifr, boll, hv = (
                prev.mm200,
                prev.ifr,
                prev.boll_inf,
                prev.hv,
            )
            preco = spots.get(fund.ticker, prev.preco)
```

`cli_scrape` **ainda não** instancia brapi/cotahist (Task 5). Testes injetam fakes.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_scrape.py tests/test_api.py tests/test_ui_abas.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/venda_de_put/scrape.py src/venda_de_put/scrape_progress.py tests/test_scrape.py
git commit -m "feat: scrape encadeia brapi e Cotahist no passo de preco"
```

---

### Task 5: CLI, `.env.example`, `data/cotahist`

**Files:**
- Modify: `src/venda_de_put/scrape.py` (`cli_scrape`)
- Modify: `.env.example`
- Test: `tests/test_scrape.py` (asserção de fonte do CLI)

**Interfaces:**
- Consumes: `BrapiSpotHttp`, `CotahistBootstrap`, `os.environ`, `resolve_data_dir`
- Produces: `cli_scrape` passa `spot=BrapiSpotHttp()` e `history=CotahistBootstrap(root / "cotahist")` para `run_scrape`. Token lido dentro de `BrapiSpotHttp` (env já carregada por `load_dotenv` no processo). A local hoje chamada `history = snapshot_history(root)` **renomeia para** `history_dir` — senão um `history = CotahistBootstrap(...)` local pisa o diretório e `write_snapshot` recebe a fonte no lugar da pasta.

- [ ] **Step 1: Write the failing test**

```python
def test_cli_scrape_instancia_brapi_e_cotahist():
    src = Path("src/venda_de_put/scrape.py").read_text(encoding="utf-8")
    assert "BrapiSpotHttp" in src
    assert "CotahistBootstrap" in src
    assert "spot=BrapiSpotHttp()" in src
    assert "CotahistBootstrap(root / \"cotahist\"" in src
    assert "history=CotahistBootstrap" in src
    assert "history_dir = snapshot_history(root)" in src
    assert "write_snapshot(snap, current, history_dir" in src
    assert "history = snapshot_history(root)" not in src


def test_env_example_documenta_brapi_token():
    text = Path(".env.example").read_text(encoding="utf-8")
    assert "VENDA_DE_PUT_BRAPI_TOKEN=" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_scrape.py::test_cli_scrape_instancia_brapi_e_cotahist tests/test_scrape.py::test_env_example_documenta_brapi_token -v`

Expected: FAIL — `BrapiSpotHttp` ainda não aparece em `cli_scrape`; `.env.example` sem a chave.

- [ ] **Step 3: Write minimal implementation**

Em `cli_scrape`:

- Junto dos imports de Yahoo/OpLab:

```python
    from venda_de_put.sources.brapi import BrapiSpotHttp
    from venda_de_put.sources.cotahist import CotahistBootstrap
```

- Renomear a local do diretório de histórico (hoje `history = snapshot_history(root)`):

```python
    current = snapshot_current(root)
    history_dir = snapshot_history(root)
```

e a escrita:

```python
    write_snapshot(snap, current, history_dir, archive_if_1600=True)
```

- Na chamada `run_scrape(...)`, acrescentar o kwarg (não criar local `history = CotahistBootstrap(...)`):

```python
        spot=BrapiSpotHttp(),
        history=CotahistBootstrap(root / "cotahist", now=now),
```

`.env.example` — append:

```
# Token brapi.dev (fallback de à vista se o Yahoo falhar 3 vezes no ticker).
# Sem ele, o fallback de à vista não dispara; Cotahist ainda pode montar histórico.
VENDA_DE_PUT_BRAPI_TOKEN=
```

Não leia o token em `cli_scrape`: `BrapiSpotHttp()` lê `VENDA_DE_PUT_BRAPI_TOKEN` sozinho.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_scrape.py tests/test_refresh_import_guard.py -v`

Expected: PASS. `cli_scrape` importa brapi/cotahist **dentro da função** (já o padrão do Yahoo), então `app.py` continua limpo.

- [ ] **Step 5: Commit**

```bash
git add src/venda_de_put/scrape.py .env.example tests/test_scrape.py
git commit -m "feat: CLI de scrape liga brapi e Cotahist"
```

---

### Task 6: `price_notice` na API e faixa no Dashboard

**Files:**
- Modify: `src/venda_de_put/web/app.py` (`GET /api/dashboard`)
- Modify: `src/venda_de_put/web/templates/index.html`
- Modify: `src/venda_de_put/web/static/app.js` (`loadDashboard`)
- Modify: `src/venda_de_put/web/static/app.css`
- Modify: `tests/test_api.py`
- Modify: `tests/test_ui_shell.py`
- Modify: `tests/test_refresh_import_guard.py`

**Interfaces:**
- Consumes: carimbo `yahoo` (`ok`, `error`)
- Produces: `GET /api/dashboard` → `"price_notice": str | null` (`error` se `ok` é falso; senão `null`). Faixa `#price-notice` entre `.premio-tape` e `.lists`. Config já mostra `erro` do passo via `passos_from_stamps`.

- [ ] **Step 1: Write the failing tests**

Em `tests/test_api.py`:

```python
from venda_de_put.scrape_progress import PRICE_NOTICE


def test_dashboard_price_notice_null_quando_yahoo_ok(data_dir):
    app = create_app(data_dir=data_dir)
    payload = TestClient(app).get("/api/dashboard").json()
    assert payload["price_notice"] is None


def test_dashboard_price_notice_quando_yahoo_falhou(data_dir):
    from dataclasses import replace
    from venda_de_put.snapshot import read_snapshot, write_snapshot

    app = create_app(data_dir=data_dir)
    snap = read_snapshot(app.state.snapshot_path)
    stamps = []
    for s in snap.stamps:
        if s.source == "yahoo":
            stamps.append(replace(s, ok=False, error=PRICE_NOTICE, stale=True))
        else:
            stamps.append(s)
    write_snapshot(
        replace(snap, stamps=stamps),
        app.state.snapshot_path,
        app.state.history_dir,
        archive_if_1600=False,
    )
    app.state.snapshot = None
    payload = TestClient(app).get("/api/dashboard").json()
    assert payload["price_notice"] == PRICE_NOTICE
```

`SourceStamp` é frozen — `replace` funciona.

Em `tests/test_ui_shell.py` (`test_home_has_eight_tabs_and_narratives` ou teste novo):

```python
def test_dashboard_faixa_price_notice(tmp_path):
    app = create_app(data_dir=tmp_path)
    client = TestClient(app)
    html = client.get("/").text
    assert 'id="price-notice"' in html
    assert "premio-tape" in html
    # faixa depois da fita, antes das listas
    assert html.find("premio-tape") < html.find('id="price-notice"') < html.find('class="lists"')
    css = client.get("/static/app.css").text
    assert ".price-notice" in css
    js = client.get("/static/app.js").text
    assert "price_notice" in js
    assert 'getElementById("price-notice")' in js
```

Em `tests/test_refresh_import_guard.py`, além de `run_scrape`:

```python
    src = Path("src/venda_de_put/web/app.py").read_text(encoding="utf-8")
    assert "venda_de_put.sources.brapi" not in src
    assert "venda_de_put.sources.cotahist" not in src
    assert "BrapiSpotHttp" not in src
    assert "CotahistBootstrap" not in src
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_api.py::test_dashboard_price_notice_null_quando_yahoo_ok tests/test_api.py::test_dashboard_price_notice_quando_yahoo_falhou tests/test_ui_shell.py::test_dashboard_faixa_price_notice tests/test_refresh_import_guard.py -v`

Expected: FAIL — chave `price_notice` ausente; HTML sem `#price-notice`.

- [ ] **Step 3: Write minimal implementation**

`app.py` no return de `dashboard`:

```python
        yahoo_stamp = next((s for s in snap.stamps if s.source == "yahoo"), None)
        price_notice = (
            yahoo_stamp.error
            if yahoo_stamp is not None and not yahoo_stamp.ok
            else None
        )
```

Incluir `"price_notice": price_notice` no dict. Não importar `scrape.py`.

`index.html` — entre o fechamento de `.premio-tape` e `<div class="lists">`:

```html
      <p id="price-notice" class="price-notice hidden" role="status"></p>
```

`app.js` em `loadDashboard`, depois do badge-stale:

```javascript
  const notice = document.getElementById("price-notice");
  if (notice) {
    const text = data.price_notice || "";
    notice.textContent = text;
    notice.classList.toggle("hidden", !text);
  }
```

`app.css`:

```css
.price-notice {
  margin: 0 0 14px;
  padding: 10px 14px;
  background: var(--warn-tint);
  color: var(--warn-ink);
  border: 0;
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--warn) 28%, transparent);
  font-size: 0.95rem;
  line-height: 1.45;
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_api.py tests/test_ui_shell.py tests/test_refresh_import_guard.py tests/test_ui_abas.py -v`

Expected: PASS. Exercitar também: aviso **não** substitui o badge `dado velho`.

- [ ] **Step 5: Commit**

```bash
git add src/venda_de_put/web/app.py src/venda_de_put/web/templates/index.html src/venda_de_put/web/static/app.js src/venda_de_put/web/static/app.css tests/test_api.py tests/test_ui_shell.py tests/test_refresh_import_guard.py
git commit -m "feat: aviso de consulta de preco no dashboard e na API"
```

---

### Task 7: `docs/sdd.md`, `AGENTS.md` e pytest completo

**Files:**
- Modify: `docs/sdd.md` (tabela de módulos + diagrama de coleta + apagar “Planejado (não implementado)”)
- Modify: `AGENTS.md` (linha do fallback, hoje “ainda sem código”)

**Interfaces:**
- Consumes: módulos já criados nas tasks 1–6
- Produces: SDD e AGENTS alinhados à spec; nenhuma frase afirmando que brapi/Cotahist não existem no código

- [ ] **Step 1: Write the failing check**

Não há teste automatizado de prosa. Gate: o diff do SDD contém as linhas abaixo. Se faltar, a revisão da task rejeita.

- [ ] **Step 2: Update SDD**

Na tabela de módulos, depois de `sources/yahoo.py`:

| `sources/brapi.py` | À vista em lote; só se o Yahoo perdeu o ticker |
| `sources/cotahist.py` | ZIP anual B3 → série de fechamentos dos tickers frios |

Ajustar a linha do Yahoo: `Chart 2y/1d, 3 tentativas, fecha null como buraco`.

Diagrama:

```
Yahoo ─┐
brapi ─┼─ (fallback à vista / Cotahist histórico) ─┐
Cotahist┘                                          ├─ scrape ─► snapshot ─► GET /api/* ─► app.js
OpLab ─────────────────────────────────────────────┤
Fund. ─────────────────────────────────────────────┘
```

Ou, mais simples, manter o diagrama de três fontes e na seção Coleta acrescentar:

- Preço: Yahoo (3 tentativas/ticker). Ticker faltoso → brapi.dev à vista (`VENDA_DE_PUT_BRAPI_TOKEN`). Sem técnico anterior aproveitável (`preco`/`mm200`) → Cotahist `COTAHIST_A{ano}` em `data/cotahist/`. Consulta ao vivo falhou → carimbo yahoo `ok=false` com `PRICE_NOTICE`; Dashboard mostra `price_notice`.

Armadilhas de fonte: brapi sem token não chama rede; Cotahist não ajusta desdobro; cache do ano corrente revalida após 1 dia.

**Apagar** a seção `## Planejado (não implementado)` e o parágrafo que começa em “Nada disso existe no código hoje” (`docs/sdd.md` ~93–95). O comportamento passa a viver na Coleta; deixar essa seção de pé vira mentira.

Em `AGENTS.md`, substituir a linha:

```
- **Fallback de preço brapi/Cotahist** → desenhado, ainda sem código: `docs/superpowers/specs/2026-08-24-brapi-cotahist-fallback-preco-design.md`.
```

por:

```
- **Fallback de preço brapi/Cotahist** → `docs/superpowers/specs/2026-08-24-brapi-cotahist-fallback-preco-design.md`; código em `sources/brapi.py`, `sources/cotahist.py`, encadeado em `scrape.py`.
```

- [ ] **Step 3: Run the full suite**

Run: `python -m pytest`

Expected: PASS (100% dos testes do repo).

- [ ] **Step 4: Commit**

```bash
git add docs/sdd.md AGENTS.md
git commit -m "docs: brapi e Cotahist na tabela de fontes do SDD"
```

---

## Self-review (spec coverage)

| Spec | Task |
|---|---|
| Yahoo 3 tentativas/ticker | 1 |
| Brapi só à vista, lote, Bearer, sem token = zero GET | 2 |
| Cotahist bootstrap, cache, offsets, URL B3, ZIP válido | 3 |
| Ticker frio = técnico não aproveitável (`preco`/`mm200`); 2ª raspagem “sem dado” ainda é frio | 4 (`_tecnico_aproveitavel` + `test_snapshot_sem_dado_ainda_e_frio_na_proxima`) |
| `timestamps` para último período | 3 + 4 |
| Encadeamento scrape, `yahoo_ok` vs Cotahist, overlay `preco` | 4 |
| Cotahist sozinho (sem spot) monta série e acende aviso | 4 (`test_sem_anterior_cotahist_sem_spot_avisa`) |
| Exceção Yahoo ainda chama fallback | 4 |
| Regra da metade sai; aviso se algum ticker não-vivo | 4 |
| `PRICE_NOTICE` no carimbo | 4 |
| CLI instancia as duas fontes; local `history` → `history_dir` | 5 |
| `.env.example` | 5 |
| `gitignore data/cotahist/` | 3 |
| `GET /api/dashboard` `price_notice` | 6 |
| Faixa acima das listas, não toast, independente de `dado velho` | 6 |
| Config passo `falhou` via carimbo/`passos_from_stamps` | 4 + 6 (já pintava `erro`) |
| `app.py` sem scrape/brapi/cotahist | 6 |
| SDD + apagar “Planejado (não implementado)” | 7 |
| `AGENTS.md` deixa de dizer “ainda sem código” | 7 |
| Sem persistir série; sem passo extra; sem token na UI | fora / não criar |
| Smoke ao vivo inalterado | nenhum task mexe em `smoke.py` |
