# Dashboard de Venda de PUT — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Substituir a planilha `carteira_venda_put (4).xlsx` por um dashboard web no VPS que recomenda ativos da B3 para venda de PUT, com o mesmo modelo de scoring e as mesmas 8 abas, sem Profit/RTD e sem motor de strike.

**Architecture:** Três adapters (`PriceSource`, `IvSource`, `FundamentalsSource`) gravam um snapshot JSON. O motor de scoring é puro (sem I/O) e produz as três listas. FastAPI serve HTML/CSS/JS e um JSON API que **só lê** o snapshot. Um CLI `python -m venda_de_put scrape` é disparado por `systemd` timer (11h/13h/16h BRT). Nginx faz `proxy_pass` + `auth_basic`. A app escuta só `127.0.0.1`.

**Tech Stack:** Python 3.11+, FastAPI, uvicorn, httpx, beautifulsoup4, lxml, pandas, pytest, HTML/CSS/JS puro (sem bundler, sem Tailwind, sem React). Persistência = arquivos JSON em `data/`.

**Spec:** `PROMPT-DASHBOARD.md` é a autoridade de produto. O `.xlsx` é a autoridade do modelo. Este plano não reabre decisões de produto.

## Global Constraints

- Código neste worktree (`prompt-grok/`), pacote `src/venda_de_put/`.
- Datas/horas: `dd/MM/yyyy` + `HH:mm:ss`, timezone **sempre** `America/Sao_Paulo`. Nunca hora local do aparelho.
- Números: `1.234,56`. Percentuais: `12,3%`. Dias da semana e meses em português.
- Menor rank / menor score = melhor. Teste explícito contra inversão.
- Financeiro **não** pula `nMrgL`. Pula só `nROIC`, `nDív`, `nLiqC`, `nEV/EB`.
- Indicador impossível → texto `"sem dado"`. Nunca `0` no lugar de ausente.
- Botão Atualizar / `POST /api/refresh` **nunca** chama fonte externa.
- Sem strike, sem cadeia OpLab `/mercado/acoes/opcoes/{TICKER}`, sem registro de operação, sem banco.
- Sem Tailwind, sem framework de front, sem build step.
- VPS: nenhum arquivo nginx pré-existente é editado; `reload` nunca `restart`; app em `127.0.0.1`; senha só no nginx.
- Fase 3 (VPS) não começa antes do gate da Fase 2. Fase 2 não começa antes do gate da Fase 1.
- Rodapé de toda tela: *“Ferramenta de seleção, não recomendação de compra ou venda de ativo.”*
- Verde `#14492E`, amarelo editável `#FFF7D6`, tema claro.
- User-Agent identificável: `venda-de-put/1.0 (+uso-pessoal)`.

### Decisões desta sessão (não reabrir)

| Item | Escolha |
|---|---|
| Onde o código mora | Este worktree |
| Prova do scoring | Offline é o gate; 1 smoke ao vivo no fim da Fase 1 |
| Raspagem | `systemd` timer + CLI separado |
| Senha | só `nginx auth_basic` |
| Forma do plano | um arquivo, 3 fases, gate entre elas |

### Mapa de arquivos (o que cada um faz)

```
src/venda_de_put/
  tz.py                 # TZ, formatadores pt-BR
  models.py             # dataclasses + Protocols
  config.py             # load/save data/config.json
  universe.py           # ticker → grupo (data/universe.json)
  calendar_b3.py        # feriados, vencimentos, mensal = dia 15–21
  indicators.py         # MM200, RSI Wilder, Bollinger, HV, range 52s
  scoring.py            # ranks, ScoreF, listas ①②③
  premium.py            # meta_30d × √(dias/30)
  snapshot.py           # ler/gravar snapshot + histórico diário
  scrape.py             # orquestra adapters → snapshot (único lugar que chama rede)
  smoke.py              # 3 GETs de sanidade (fim da Fase 1)
  sources/
    yahoo.py            # chart 2y/1d → OHLC + meta
    oplab.py            # __NEXT_DATA__ da lista de mercado
    fundamentus.py      # ISO-8859-1, 22 colunas por posição
  web/
    app.py              # FastAPI: páginas + JSON; refresh NÃO raspa
    static/app.css
    static/app.js
    templates/index.html
  __main__.py           # scrape | serve | smoke
data/                   # config, universo, feriados, snapshots (git: exemplos; runtime: gravável)
tests/fixtures/         # extraídos do xlsx + HTML/JSON gravados
deploy/                 # units systemd + template nginx (não aplicar sem levantamento)
```

**Seams reais (dois ou mais adapters):** `PriceSource` / `IvSource` / `FundamentalsSource`. O motor (`scoring.score_fundamentals` + `apply_technical` + `build_lists`) não conhece HTTP.

`src/venda_de_put/models.py` — contrato único (criar na Task 2, completar campos nas tasks que os introduzem; **não** duplicar dataclasses em `scoring.py`):

```python
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional, Protocol

@dataclass(frozen=True)
class Vencimento:
    nominal: date
    efetivo: date
    tipo: str          # "MENSAL" | "Semanal"
    feriado_na_sexta: bool
    dia_semana: str
    dias_corridos: int
    dias_uteis: int
    status: str

@dataclass
class AppConfig:
    ifr_min: float = 10.0
    ifr_max: float = 50.0
    folga_banda: float = 0.05
    meta_premio_30d: float = 0.0115
    mm_periodos: int = 200
    mm_tipo: str = "sma"
    ifr_periodos: int = 14
    boll_periodos: int = 20
    boll_desvios: float = 2.0
    hv_periodos: int = 21
    scrape_times: tuple[str, ...] = ("11:00", "13:00", "16:00")
    fundamentus_days: tuple[int, ...] = (1, 15)
    fundamentus_time: str = "07:00"

@dataclass(frozen=True)
class AssetInput:
    ticker: str
    grupo: str
    pl: Optional[float]
    pvp: Optional[float]
    ev_ebitda: Optional[float]
    mrg_liq: Optional[float]
    liq_corr: Optional[float]
    roic: Optional[float]
    roe: Optional[float]
    div_pat: Optional[float]
    cresc: Optional[float]

@dataclass(frozen=True)
class TechnicalInput:
    preco: Optional[float]
    mm200: Optional[float]
    ifr: Optional[float]
    boll_inf: Optional[float]
    iv: Optional[float]
    hv: Optional[float]

@dataclass(frozen=True)
class CandleSeries:
    ticker: str
    closes: list[Optional[float]]
    preco: Optional[float]
    max_52: Optional[float]
    min_52: Optional[float]
    collected_at: datetime

@dataclass(frozen=True)
class IvPoint:
    ticker: str
    iv: Optional[float]
    iv_rank: Optional[float]
    iv_percentile: Optional[float]

@dataclass(frozen=True)
class Fundamentals:
    ticker: str
    cotacao: Optional[float]
    pl: Optional[float]
    pvp: Optional[float]
    psr: Optional[float]
    dy: Optional[float]
    p_ativo: Optional[float]
    p_cap_giro: Optional[float]
    p_ebit: Optional[float]
    p_ativ_circ_liq: Optional[float]
    ev_ebit: Optional[float]
    ev_ebitda: Optional[float]
    mrg_bruta: Optional[float]
    mrg_ebit: Optional[float]
    mrg_liq: Optional[float]
    liq_corr: Optional[float]
    roic: Optional[float]
    roe: Optional[float]
    liq_2meses: Optional[float]
    patrim_liq: Optional[float]
    div_liq_patrim: Optional[float]
    cresc_rec_5a: Optional[float]

@dataclass(frozen=True)
class SourceStamp:
    source: str          # "yahoo" | "oplab" | "fundamentus"
    collected_at: datetime
    ok: bool
    error: Optional[str]
    stale: bool

# FundScore, ScoredAsset, Lists, Snapshot: definidos em models.py na task que os usa (5, 6, 8).
```

`config.py` só faz load/save de `AppConfig`. `scoring.py` só calcula.

---

# Fase 1 — Núcleo (sem UI)

**Gate:** `pytest` verde; lista ① reproduz o Excel nos mesmos fundamentos; `POST`/CLI de refresh não existe ainda, mas `scrape()` é a **única** função que aceita os três adapters; smoke ao vivo documentado e executado uma vez.

---

### Task 1: Scaffold, timezone e fixture extraída do Excel

**Files:**
- Create: `pyproject.toml`
- Create: `src/venda_de_put/__init__.py`
- Create: `src/venda_de_put/tz.py`
- Create: `scripts/extract_excel_fixtures.py`
- Create: `tests/test_tz.py`
- Create: `.gitignore`

**Interfaces:**
- Consumes: `carteira_venda_put (4).xlsx` na raiz do worktree
- Produces: `venda_de_put.tz.TZ` (`ZoneInfo("America/Sao_Paulo")`); `format_date(d) -> str`; `format_datetime(dt) -> str`; `format_number(x, nd=2) -> str`; `format_percent(x, nd=1) -> str` (x já em fração: `0.123` → `"12,3%"`); fixtures em `tests/fixtures/excel_ativos.json` e `tests/fixtures/excel_dados.json`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_tz.py
from datetime import date, datetime
from zoneinfo import ZoneInfo

from venda_de_put.tz import TZ, format_date, format_datetime, format_number, format_percent


def test_timezone_is_sao_paulo():
    assert TZ.key == "America/Sao_Paulo"


def test_format_date_br():
    assert format_date(date(2026, 8, 13)) == "13/08/2026"


def test_format_datetime_converts_from_utc():
    utc = datetime(2026, 8, 13, 15, 5, 29, tzinfo=ZoneInfo("UTC"))
    assert format_datetime(utc) == "13/08/2026 12:05:29"


def test_format_number_and_percent_br():
    assert format_number(1234.56) == "1.234,56"
    assert format_percent(0.123) == "12,3%"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pip install -e ".[dev]"
pytest tests/test_tz.py -v
```

Expected: FAIL — `ModuleNotFoundError: venda_de_put` ou `tz` não existe.

- [ ] **Step 3: Write minimal implementation**

`pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "venda-de-put"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.30",
  "httpx>=0.27",
  "beautifulsoup4>=4.12",
  "lxml>=5.0",
  "pandas>=2.2",
]

[project.optional-dependencies]
dev = ["pytest>=8", "openpyxl>=3.1"]

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
pythonpath = ["src"]
```

`src/venda_de_put/tz.py`:

```python
from datetime import date, datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Sao_Paulo")


def format_date(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def format_datetime(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=TZ)
    return dt.astimezone(TZ).strftime("%d/%m/%Y %H:%M:%S")


def format_number(x: float, nd: int = 2) -> str:
    formatted = f"{x:,.{nd}f}"
    return formatted.replace(",", "X").replace(".", ",").replace("X", ".")


def format_percent(x: float, nd: int = 1) -> str:
    return format_number(x * 100.0, nd) + "%"
```

`.gitignore`:

```
.venv/
__pycache__/
*.pyc
.pytest_cache/
data/snapshots/current.json
data/snapshots/history/
*.egg-info/
```

`scripts/extract_excel_fixtures.py` — lê o xlsx (`data_only=True`) e grava:

- `tests/fixtures/excel_ativos.json`: 86 objetos com `ticker, grupo, pl, pvp, dy, ev_ebitda, mrg_liq, liq_corr, roic, roe, div_pat, cresc, preco, mm200, ifr, boll_inf, sinal, nroe, nroic, nmrgl, ndiv, nliqc, npl, npvp, neveb, ncrsc, scoref, pctf, scoret, scorec` (colunas A–B, C–L, M–O, Q, X–AG, AL–AM, AO, AQ).
- `tests/fixtures/excel_dados.json`: lista `{papel, colunas[22]}` da aba Dados.
- `data/universe.json`: `{"ITUB4": "Financeiro", ...}` dos 86.
- `data/feriados.json`: `[{"date": "2026-01-01", "descricao": "..."}, ...]` da aba Feriados.

Rodar:

```bash
python scripts/extract_excel_fixtures.py
```

Conferir: 86 ativos, BRSR6 `scoref == 4.4`, `pctf` ≈ `0.07142857`.

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_tz.py -v
```

Expected: PASS (4 testes).

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml .gitignore src/venda_de_put/tz.py src/venda_de_put/__init__.py tests/test_tz.py scripts/extract_excel_fixtures.py tests/fixtures data/universe.json data/feriados.json
git commit -m "chore: scaffold, formatadores pt-BR e fixtures extraídas do Excel"
```

---

### Task 2: Calendário B3 e detector de mensal

**Files:**
- Create: `src/venda_de_put/calendar_b3.py`
- Create: `tests/test_calendar_b3.py`

**Interfaces:**
- Consumes: `data/feriados.json` (lista de ISO dates); `venda_de_put.tz.TZ`
- Produces:
  - `load_holidays(path: Path) -> set[date]`
  - `is_business_day(d: date, holidays: set[date]) -> bool`
  - `adjust_friday(nominal: date, holidays: set[date]) -> date` — se `nominal` é feriado, recua 1–3 dias até dia útil (espelha coluna D da aba Vencimentos)
  - `is_monthly(nominal: date) -> bool` — `15 <= day <= 21` sobre a **sexta nominal**, não sobre a data efetiva
  - `weekday_pt(d: date, curto: bool = False) -> str` — `segunda`…`domingo` ou `seg`…`dom`
  - `business_days_inclusive(start: date, end: date, holidays) -> int` — `NETWORKDAYS`
  - `build_calendar(today: date, holidays, through: date) -> list[Vencimento]`
  - `Vencimento` em `models.py` (criar o arquivo aqui): `nominal, efetivo, tipo ("MENSAL"|"Semanal"), feriado_na_sexta: bool, dia_semana: str, dias_corridos: int, dias_uteis: int, status: str`
  - `default_vencimento(rows: list[Vencimento], so_mensais: bool = True) -> Vencimento` — próximo mensal com `efetivo >= today`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_calendar_b3.py
from datetime import date
from pathlib import Path

from venda_de_put.calendar_b3 import (
    adjust_friday,
    build_calendar,
    default_vencimento,
    is_monthly,
    load_holidays,
    weekday_pt,
)


def test_novembro_2026_mensal_e_quinta_19():
    holidays = load_holidays(Path("data/feriados.json"))
    assert date(2026, 11, 20) in holidays  # Consciência Negra
    nominal = date(2026, 11, 20)  # 3ª sexta — feriado
    assert is_monthly(nominal) is True
    efetivo = adjust_friday(nominal, holidays)
    assert efetivo == date(2026, 11, 19)
    assert weekday_pt(efetivo) == "quinta"


def test_abril_2028_mensal_e_quinta_20():
    holidays = {date(2028, 4, 21)}  # Tiradentes
    nominal = date(2028, 4, 21)
    assert is_monthly(nominal) is True
    assert adjust_friday(nominal, holidays) == date(2028, 4, 20)


def test_terceira_sexta_nao_e_a_regra():
    """16/10/2026 é sexta e mensal; 23/10 não é mensal mesmo sendo sexta."""
    assert is_monthly(date(2026, 10, 16)) is True
    assert is_monthly(date(2026, 10, 23)) is False


def test_default_e_proximo_mensal():
    holidays = load_holidays(Path("data/feriados.json"))
    rows = build_calendar(date(2026, 8, 13), holidays, through=date(2026, 12, 31))
    escolhido = default_vencimento(rows, so_mensais=True)
    assert escolhido.tipo == "MENSAL"
    assert escolhido.efetivo >= date(2026, 8, 13)
    assert 15 <= escolhido.nominal.day <= 21
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_calendar_b3.py -v
```

Expected: FAIL — módulo ausente.

- [ ] **Step 3: Write minimal implementation**

Gerar todas as sextas de `today` até `through`. Tipo: `MENSAL` se `15 <= nominal.day <= 21`. Efetivo = `adjust_friday`. `dias_corridos = (efetivo - today).days`. `dias_uteis = NETWORKDAYS(today, efetivo, holidays)` (inclui os dois extremos se úteis; se `dias_corridos < 0`, 0). Status: `Vencido` / `VENCE HOJE` / `Esta semana` / `""`.

`adjust_friday`: se nominal ∉ holidays, devolve nominal; senão tenta `nominal-1`, `nominal-2`, `nominal-3`.

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_calendar_b3.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/venda_de_put/models.py src/venda_de_put/calendar_b3.py tests/test_calendar_b3.py
git commit -m "feat: calendário B3 e mensal pela janela dia 15–21"
```

---

### Task 3: Prêmio-alvo

**Files:**
- Create: `src/venda_de_put/premium.py`
- Create: `tests/test_premium.py`

**Interfaces:**
- Consumes: `meta_30d: float`, `dias_corridos: int`
- Produces: `premio_alvo(meta_30d: float, dias_corridos: int) -> float` — `meta_30d * sqrt(dias_corridos / 30)`. Se `dias_corridos <= 0`, devolve `0.0`.

**Janela de abertura da operação:** as vendas de put são abertas com **45 a 21 dias corridos** até o vencimento (inclusive). O seletor pode listar outras séries; a regra de operação é só essa faixa. Autoridade: `PROMPT-DASHBOARD.md` §6.7.

**Strike de entrada (fase 2):** `prêmio_% = último negócio / strike`. Primeiro strike OTM (menor) cujo % ≥ meta do vencimento. Autoridade: spec `2026-08-13-fase2-strike-design.md`.

- [ ] **Step 1: Write the failing test**

```python
from math import isclose, sqrt

from venda_de_put.premium import premio_alvo


def test_excel_example_40_days():
    # Config texto: 1,15% e 40 dias → ~1,33%
    got = premio_alvo(0.0115, 40)
    assert isclose(got, 0.0115 * sqrt(40 / 30), rel_tol=1e-12)
    assert isclose(got, 0.013279, rel_tol=1e-3)


def test_zero_or_negative_days():
    assert premio_alvo(0.0115, 0) == 0.0
    assert premio_alvo(0.0115, -3) == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_premium.py -v
```

Expected: FAIL — função ausente.

- [ ] **Step 3: Write minimal implementation**

```python
import math

def premio_alvo(meta_30d: float, dias_corridos: int) -> float:
    if dias_corridos <= 0:
        return 0.0
    return meta_30d * math.sqrt(dias_corridos / 30.0)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_premium.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/venda_de_put/premium.py tests/test_premium.py
git commit -m "feat: prêmio-alvo por raiz do tempo"
```

---

### Task 4: Indicadores técnicos (OHLC)

**Files:**
- Create: `src/venda_de_put/indicators.py`
- Create: `tests/test_indicators.py`

**Interfaces:**
- Consumes: série de fechamentos (`list[Optional[float]]`, mais recente por último) e, para 52s, `high_52`/`low_52`/`preco` opcionais
- Produces:
  - `sma(values, n) -> Optional[float]`
  - `rsi_wilder(closes, n=14) -> Optional[float]`
  - `bollinger_lower(closes, n=20, k=2.0) -> Optional[float]` — SMA − k·σ amostral (`n-1`) ou populacional? Usar **populacional** (`stdev` de `n` pontos, divisão por `n`) — padrão Bollinger. Documentar no docstring. Se preferir amostral, o teste abaixo trava o contrato: implemente o que o teste fixar (populacional).
  - `hv_log(closes, n=21) -> Optional[float]` — σ dos `n` log-retornos × `sqrt(252)`
  - `posicao_52s(preco, low, high) -> Optional[float]`
  - Qualquer entrada insuficiente → `None` (a UI traduz para `"sem dado"`)

- [ ] **Step 1: Write the failing test**

```python
import math

from venda_de_put.indicators import (
    bollinger_lower,
    hv_log,
    posicao_52s,
    rsi_wilder,
    sma,
)


def test_sma_needs_full_window():
    assert sma([1, 2, 3], 4) is None
    assert sma([1.0, 2.0, 3.0], 3) == 2.0


def test_rsi_wilder_flat_series_is_none_or_edge():
    # 20 fechamentos iguais: ganhos=perdas=0 → sem dado, não 50 inventado
    assert rsi_wilder([10.0] * 20, 14) is None


def test_rsi_wilder_known_climb():
    # 15 dias: 1,2,...,15. Só ganhos. RSI deve ir a 100.
    closes = [float(i) for i in range(1, 16)]
    assert rsi_wilder(closes, 14) == 100.0


def test_auau3_cannot_have_mm200():
    assert sma([1.0] * 153, 200) is None


def test_hv_and_range():
    closes = [100.0, 101.0, 100.0, 102.0] + [100.0] * 20
    hv = hv_log(closes, 21)
    assert hv is not None and hv > 0
    assert posicao_52s(15.0, 10.0, 20.0) == 0.5
    assert posicao_52s(15.0, 15.0, 15.0) is None


def test_bollinger_lower_below_sma():
    closes = [float(i % 5) for i in range(20)]
    mid = sma(closes, 20)
    low = bollinger_lower(closes, 20, 2.0)
    assert mid is not None and low is not None
    assert low < mid
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_indicators.py -v
```

Expected: FAIL — módulo ausente.

- [ ] **Step 3: Write minimal implementation**

RSI Wilder: primeira média de ganhos/perdas = média simples dos 14 primeiros deltas; depois `avg = (avg * (n-1) + delta) / n`. Se `avg_loss == 0` e `avg_gain > 0` → 100. Se ambos 0 → `None`.

**IFR × Profit.** O Profit tem dois tipos no indicador IFR (RSI) 14 — [documentação Nelogica](https://ajuda.nelogica.com.br/hc/pt-br/articles/360040975932-IFR-%C3%8Dndice-de-For%C3%A7a-Relativa). Os dois usam `IFR = 100 − 100/(1+FR)` e mudam só o FR:

- **Simples** — `FR = média(var. positivas) / média(var. negativas)` nos últimos 14 deltas. Sem memória (RSI de Cutler / SMA).
- **Clássico** — “média das médias”: `X = (média_anterior × 13 + variação_atual) / 14` em ganhos e perdas. É o RSI de Wilder.

Este plano implementa o **Clássico** (`rsi_wilder`). A planilha Excel original não calculava IFR: lia o RTD do Profit no tipo que estivesse no gráfico. Comparar o IFR daqui com o **Simples** do Profit é erro de método (no ITUB4, 14/08/2026 fechamento 39,00: Simples Profit 24,49 vs Clássico Profit 29,85 vs Clássico daqui 34,92). Mesmo no Clássico o nível pode divergir ~5 pp — a série de fechamentos do gráfico Profit não é idêntica à do Yahoo/COTAHIST. Autoridade de produto: `PROMPT-DASHBOARD.md` §6.6.

HV: ignorar pares com `None` ou `<= 0`; precisa de `n` retornos válidos.

Null no meio da série: pular o ponto (não interpolar como zero). SMA/RSI/Bollinger usam só valores não-`None`, **na ordem**, e exigem `n` pontos válidos no final da série (janela dos últimos `n` válidos, não “últimos `n` slots com buraco”).

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_indicators.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/venda_de_put/indicators.py tests/test_indicators.py
git commit -m "feat: MM200, RSI Wilder, Bollinger, HV e range 52s"
```

---

### Task 5: Ranks e ScoreF

**Files:**
- Create: `src/venda_de_put/scoring.py` (ranks + `score_fundamentals` nesta task; listas na Task 6)
- Create: `tests/test_scoring_ranks.py`

**Interfaces:**
- Consumes: `list[AssetInput]` — `ticker, grupo, pl, pvp, ev_ebitda, mrg_liq, liq_corr, roic, roe, div_pat, cresc` (`Optional[float]`; `0` é valor, `None` é ausente)
- Produces: `score_fundamentals(assets: list[AssetInput]) -> list[FundScore]` com os campos `n_roe, n_roic, n_mrgl, n_div, n_liqc, n_pl, n_pvp, n_eveb, n_crsc, qualid, saude, valuat, consist, score_f, pct_f`

Regras (cópia da aba Ativos, linha 2):

```
nROE  = count(mesmo grupo, ROE > meu) + 1          se ROE não é None
nROIC = ...                                        se grupo != Financeiro e ROIC não é None; senão None
nMrgL = count(mesmo grupo, MrgL > minha) + 1       SEMPRE, inclusive Financeiro
nLiqC = ...                                        se grupo != Financeiro
nDív  = count(mesmo grupo, Dív < minha) + 1        se grupo != Financeiro (menos dívida = melhor)
nCrsc = count(Cresc > meu) + 1

nP/L, nP/VP, nEV/EB:
  se valor <= 0: tamanho_do_grupo + 1
  senão: count(0 < par < meu) + 1
  nEV/EB pulado se Financeiro

Qualid  = média dos n* não-None em {nROE, nROIC, nMrgL}
Saúde   = média de {nDív, nLiqC} não-None
Valuat  = média de {nP/L, nP/VP, nEV/EB} não-None
Consist = nCrsc

ScoreF Financeiro = 0.50*Qualid + 0.30*Valuat + 0.20*Consist
ScoreF demais     = 0.40*Qualid + 0.25*Saúde + 0.20*Valuat + 0.15*Consist

PctF = (count(mesmo grupo, ScoreF < meu) + 1) / count(mesmo grupo, ScoreF > 0)
```

`tamanho_do_grupo` = número de tickers do grupo (86-universo), não só os que têm o indicador.

- [ ] **Step 1: Write the failing test**

```python
from venda_de_put.models import AssetInput
from venda_de_put.scoring import score_fundamentals


def _fin(ticker, roe, mrg, pl, pvp, cresc):
    return AssetInput(
        ticker=ticker, grupo="Financeiro",
        pl=pl, pvp=pvp, ev_ebitda=None, mrg_liq=mrg, liq_corr=None,
        roic=None, roe=roe, div_pat=None, cresc=cresc,
    )


def test_financeiro_computes_nmrgl_and_skips_nroic():
    assets = [
        _fin("AAA", roe=0.30, mrg=0.20, pl=8, pvp=1.0, cresc=0.10),
        _fin("BBB", roe=0.10, mrg=0.05, pl=20, pvp=3.0, cresc=0.01),
    ]
    out = {a.ticker: a for a in score_fundamentals(assets)}
    assert out["AAA"].n_roic is None
    assert out["BBB"].n_roic is None
    assert out["AAA"].n_mrgl == 1
    assert out["BBB"].n_mrgl == 2
    assert out["AAA"].n_div is None
    assert out["AAA"].score_f is not None
    assert out["AAA"].score_f < out["BBB"].score_f


def test_menor_e_melhor_no_topo():
    """ROE alto, dívida baixa, P/L baixo → PctF menor."""
    grupo = "Varejo"
    bom = AssetInput("BOM3", grupo, pl=5, pvp=1, ev_ebitda=4, mrg_liq=0.2,
                     liq_corr=2, roic=0.2, roe=0.3, div_pat=0.1, cresc=0.2)
    ruim = AssetInput("RUI3", grupo, pl=40, pvp=8, ev_ebitda=20, mrg_liq=0.02,
                      liq_corr=0.8, roic=0.02, roe=0.03, div_pat=2.0, cresc=-0.1)
    out = {a.ticker: a for a in score_fundamentals([bom, ruim])}
    assert out["BOM3"].pct_f < out["RUI3"].pct_f


def test_pl_negativo_vai_para_o_fim():
    grupo = "Saúde"
    a = AssetInput("NEG3", grupo, pl=-10, pvp=1, ev_ebitda=5, mrg_liq=0.1,
                   liq_corr=1.5, roic=0.1, roe=0.1, div_pat=0.2, cresc=0.1)
    b = AssetInput("POS3", grupo, pl=8, pvp=1, ev_ebitda=5, mrg_liq=0.1,
                   liq_corr=1.5, roic=0.1, roe=0.1, div_pat=0.2, cresc=0.1)
    out = {x.ticker: x for x in score_fundamentals([a, b])}
    assert out["NEG3"].n_pl == 3  # tamanho 2 + 1
    assert out["POS3"].n_pl == 1


def test_paridade_brsr6_itub4_contra_excel():
    import json
    from pathlib import Path
    raw = json.loads(Path("tests/fixtures/excel_ativos.json").read_text(encoding="utf-8"))
    assets = [
        AssetInput(
            ticker=r["ticker"], grupo=r["grupo"],
            pl=r["pl"], pvp=r["pvp"], ev_ebitda=r["ev_ebitda"],
            mrg_liq=r["mrg_liq"], liq_corr=r["liq_corr"], roic=r["roic"],
            roe=r["roe"], div_pat=r["div_pat"], cresc=r["cresc"],
        )
        for r in raw
    ]
    out = {a.ticker: a for a in score_fundamentals(assets)}
    expect = {r["ticker"]: r for r in raw}
    for t in ("BRSR6", "ITUB4", "PSSA3", "IRBR3"):
        assert out[t].n_mrgl == expect[t]["nmrgl"]
        assert abs(out[t].score_f - expect[t]["scoref"]) < 1e-6
        assert abs(out[t].pct_f - expect[t]["pctf"]) < 1e-9
```

Atenção: a fixture Excel traz `0` onde o Fundamentus mandou zero. Trate `0` como número. Se a paridade falhar por `None` vs `0`, o parser da fixture deve preservar `0` e só usar `None` para células realmente vazias (`nroic` do Financeiro).

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_scoring_ranks.py -v
```

Expected: FAIL — `scoring` ausente.

- [ ] **Step 3: Write minimal implementation**

`AssetInput` e `FundScore` moram em `models.py`. `scoring.py` só tem funções. Assinatura:

```python
def score_fundamentals(assets: list[AssetInput]) -> list[FundScore]: ...
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_scoring_ranks.py -v
```

Expected: PASS, inclusive paridade BRSR6/ITUB4.

- [ ] **Step 5: Commit**

```bash
git add src/venda_de_put/scoring.py src/venda_de_put/models.py tests/test_scoring_ranks.py
git commit -m "feat: ranks setoriais e ScoreF fieis ao Excel"
```

---

### Task 6: Camada técnica, três listas e aceite “menor é melhor”

**Files:**
- Modify: `src/venda_de_put/scoring.py`
- Create: `src/venda_de_put/config.py`
- Create: `data/config.json`
- Create: `tests/test_scoring_lists.py`

**Interfaces:**
- Consumes: `FundScore` + `TechnicalInput(preco, mm200, ifr, boll_inf, iv, hv)` + `AppConfig`
- Produces:
  - `apply_technical(fund: FundScore, tech: TechnicalInput, cfg: AppConfig) -> ScoredAsset`
  - `build_lists(assets: list[ScoredAsset], n: int = 10) -> Lists`
  - `load_config(path) -> AppConfig` / `save_config(cfg, path)`

```
Tendência = alta se preco > mm200; fora senão; None se faltar dado
Timing    = ENTRADA se ifr ∈ [ifr_min, ifr_max] e preco <= boll_inf * (1+folga)
SINAL     = "► VENDER PUT" se alta e ENTRADA; "—" se ambos calculáveis; None se faltar dado
ScoreT    = (preco - boll_inf)/boll_inf  se SINAL aceso
          = 100 + ifr/1000               se não (e ifr presente)
ScoreC    = PctF se SINAL aceso; senão None
IV/HV     = iv/hv se ambos presentes e hv != 0
```

Listas: ① 10 menores `pct_f` (desempate ticker); ② 10 menores `score_t` (sem `score_t` fica de fora; o truque 100+IFR preenche); ③ os que têm `score_c`, ordenados, **podem ser 0**.

`AppConfig` padrão = Config do Excel: `ifr_min=10, ifr_max=50, folga=0.05, meta_premio_30d=0.0115, mm_periodos=200, mm_tipo="sma", ifr_periodos=14, boll_periodos=20, boll_desvios=2.0, hv_periodos=21, scrape_times=["11:00","13:00","16:00"], fundamentus_days=[1,15], fundamentus_time="07:00"`.

- [ ] **Step 1: Write the failing test**

```python
from venda_de_put.config import AppConfig
from venda_de_put.models import AssetInput, TechnicalInput
from venda_de_put.scoring import apply_technical, build_lists, score_fundamentals


def test_itub4_cached_excel_is_fora_not_sinal():
    # preço 38.54 < MM200 40.95 → fora; ScoreT = 100 + 23.23/1000
    fund = score_fundamentals([
        AssetInput("ITUB4", "Financeiro", 10.15, 2.36, None, 0, None, None, 0.2324, None, 0.7155)
    ])[0]
    asset = apply_technical(fund, TechnicalInput(38.54, 40.95, 23.23, 38.81, None, None), AppConfig())
    assert asset.tendencia == "fora"
    assert asset.sinal == "—"
    assert abs(asset.score_t - 100.02323) < 1e-9
    assert asset.score_c is None


def test_sinal_aceso_entra_lista_combinada():
    fund = score_fundamentals([
        AssetInput("BOM3", "Varejo", 5, 1, 4, 0.2, 2, 0.2, 0.3, 0.1, 0.2)
    ])[0]
    cfg = AppConfig()
    # preço > MM200 e colado na banda, IFR 40
    asset = apply_technical(fund, TechnicalInput(20.0, 18.0, 40.0, 19.5, 0.4, 0.3), cfg)
    assert asset.sinal == "► VENDER PUT"
    lists = build_lists([asset])
    assert [a.ticker for a in lists.combinado] == ["BOM3"]
    assert asset.score_t == (20.0 - 19.5) / 19.5


def test_lista1_top_equals_excel_fixture():
    import json
    from pathlib import Path
    from venda_de_put.models import AssetInput
    from venda_de_put.scoring import apply_technical, build_lists, score_fundamentals
    raw = json.loads(Path("tests/fixtures/excel_ativos.json").read_text(encoding="utf-8"))
    funds = score_fundamentals([
        AssetInput(r["ticker"], r["grupo"], r["pl"], r["pvp"], r["ev_ebitda"],
                   r["mrg_liq"], r["liq_corr"], r["roic"], r["roe"], r["div_pat"], r["cresc"])
        for r in raw
    ])
    scored = []
    for f, r in zip(funds, raw, strict=True):
        scored.append(apply_technical(
            f,
            TechnicalInput(r["preco"], r["mm200"], r["ifr"], r["boll_inf"], None, None),
            AppConfig(),
        ))
    lists = build_lists(scored)
    expect = ["BRSR6", "SBSP3", "RECV3", "CMIN3", "PSSA3", "VIVA3", "ISAE4", "CURY3", "ECOR3", "BEEF3"]
    # CMIN3 e PSSA3 e VIVA3 empatam em 0.142857 — desempate alfabético
    # CMIN3, PSSA3, VIVA3. O Excel usou ROW(); nós usamos ticker.
    # Aceite da spec: desempate alfabético. A ORDEM dos empatados pode
    # divergir do Excel. Os 10 CONJUNTOS devem bater; a ordem só é rígida
    # quando PctF é distinto.
    got = [a.ticker for a in lists.fundamentalista]
    assert set(got) == set(expect)
    assert got[0] == "BRSR6"
    assert got[1] == "SBSP3"
    assert got[2] == "RECV3"
```

Se o conjunto dos 10 não bater, **pare**. É erro de transcrição, não de desempate.

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_scoring_lists.py -v
```

Expected: FAIL — `apply_technical` / `build_lists` ausentes.

- [ ] **Step 3: Write minimal implementation** + `data/config.json` com os padrões.

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_scoring_lists.py tests/test_scoring_ranks.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/venda_de_put/scoring.py src/venda_de_put/config.py data/config.json tests/test_scoring_lists.py
git commit -m "feat: sinal técnico e as três listas Top 10"
```

---

### Task 7: Parsers das três fontes (fixtures, sem rede)

**Files:**
- Create: `src/venda_de_put/sources/__init__.py`
- Create: `src/venda_de_put/sources/types.py`
- Create: `src/venda_de_put/sources/yahoo.py`
- Create: `src/venda_de_put/sources/oplab.py`
- Create: `src/venda_de_put/sources/fundamentus.py`
- Create: `tests/test_sources.py`
- Create: `tests/fixtures/yahoo_petr4.json` (recorte mínimo do chart: `timestamp`, `indicators.quote[0].close` com um `null` no meio, `meta.regularMarketPrice`, `meta.fiftyTwoWeekHigh/Low`)
- Create: `tests/fixtures/oplab_next_data.html` (um `<script id="__NEXT_DATA__">{...}</script>` com 2 stocks, um deles `RAIZ4` sem `iv_current`)
- Create: `tests/fixtures/fundamentus.html` (tabela com 22 `<th>` na ordem da spec e 2 linhas, encoding testado via bytes `iso-8859-1` no teste)

**Interfaces:**
- Consumes: bytes / dict já baixados (as funções de parse **não** fazem HTTP)
- Produces:
  - `class PriceSource(Protocol): def fetch(self, tickers: list[str]) -> dict[str, CandleSeries]`
  - `class IvSource(Protocol): def fetch(self) -> dict[str, IvPoint]`
  - `class FundamentalsSource(Protocol): def fetch(self) -> list[Fundamentals]`
  - `parse_yahoo_chart(payload: dict, ticker: str) -> CandleSeries`
  - `parse_oplab_next_data(html: str) -> dict[str, IvPoint]`
  - `parse_fundamentus_html(raw: bytes) -> list[Fundamentals]`
  - `CandleSeries(ticker, closes: list[Optional[float]], preco, max_52, min_52, collected_at)`
  - `IvPoint(ticker, iv, iv_rank, iv_percentile)` — campos ausentes = `None`
  - HTTP live fica em `YahooHttp`, `OplabHttp`, `FundamentusHttp` nesta mesma task, mas os testes **não as chamam**. Elas usam `httpx.Client` injetável. Yahoo: **somente** `range=2y&interval=1d`. Nunca `range=max`.

Contratos:

- Yahoo: `None` no close permanece `None`. Não preencher com 0. `preco` = `meta.regularMarketPrice`.
- OpLab: extrair `script#__NEXT_DATA__` → `props.pageProps.stocks[]`. Sem script ou sem `stocks` → `ValueError` alto (não devolver `{}`).
- Fundamentus: `raw.decode("iso-8859-1")`. Colunas **por índice**, não por texto do `<th>` (`Dív.Líq/ Patrim.` ≠ Excel). Números pt-BR: `1.234,56` e `-208,15%` → float. Linha sem papel → ignore.

- [ ] **Step 1: Write the failing test**

```python
from pathlib import Path

from venda_de_put.sources.fundamentus import parse_fundamentus_html
from venda_de_put.sources.oplab import parse_oplab_next_data
from venda_de_put.sources.yahoo import parse_yahoo_chart


def test_yahoo_keeps_null_and_refuses_to_need_max_range():
    payload = {
        "chart": {"result": [{
            "meta": {"regularMarketPrice": 41.75, "fiftyTwoWeekHigh": 42.0, "fiftyTwoWeekLow": 30.0},
            "timestamp": [1, 2, 3],
            "indicators": {"quote": [{"close": [40.0, None, 41.0]}]},
        }]}
    }
    series = parse_yahoo_chart(payload, "PETR4")
    assert series.closes == [40.0, None, 41.0]
    assert series.preco == 41.75


def test_oplab_raiz4_sem_iv_e_petr4_com_iv():
    html = Path("tests/fixtures/oplab_next_data.html").read_text(encoding="utf-8")
    pts = parse_oplab_next_data(html)
    assert pts["PETR4"].iv is not None
    assert pts["RAIZ4"].iv is None


def test_oplab_sem_next_data_falha_alto():
    import pytest
    with pytest.raises(ValueError):
        parse_oplab_next_data("<html></html>")


def test_fundamentus_iso8859_and_position():
    raw = Path("tests/fixtures/fundamentus.html").read_bytes()
    rows = parse_fundamentus_html(raw)
    petr = next(r for r in rows if r.ticker == "PETR4")
    assert petr.pl is not None
```

Montar as fixtures à mão com o mínimo que faz o teste passar. O HTML do Fundamentus no fixture pode ser UTF-8 no disco **desde que o teste passe `raw` já em `iso-8859-1`** (`"cotações".encode("iso-8859-1")` numa célula) para provar o decode.

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_sources.py -v
```

Expected: FAIL.

- [ ] **Step 3: Write parsers + HTTP adapters com `User-Agent: venda-de-put/1.0 (+uso-pessoal)`.**

Yahoo URL fixa:

```
https://query1.finance.yahoo.com/v8/finance/chart/{ticker}.SA?range=2y&interval=1d
```

OpLab URL:

```
https://opcoes.oplab.com.br/mercado-de-opcoes
```

Fundamentus URL:

```
https://fundamentus.com.br/resultado.php
```

Pausa de 150–250 ms entre tickers Yahoo no `YahooHttp.fetch` (não no parse).

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_sources.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/venda_de_put/sources tests/test_sources.py tests/fixtures/yahoo_petr4.json tests/fixtures/oplab_next_data.html tests/fixtures/fundamentus.html
git commit -m "feat: parsers Yahoo, OpLab e Fundamentus atrás de Protocols"
```

---

### Task 8: Snapshot, scrape CLI e “refresh não raspa”

**Files:**
- Create: `src/venda_de_put/snapshot.py`
- Create: `src/venda_de_put/scrape.py`
- Create: `src/venda_de_put/__main__.py`
- Create: `tests/test_scrape.py`
- Create: `tests/test_snapshot.py`

**Interfaces:**
- Consumes: os três Protocols + `universe.json` + `AppConfig` + `calendar_b3` + `indicators` + `scoring`
- Produces:
  - `Snapshot` (dataclasses serializáveis): `generated_at`, `stamps: list[SourceStamp]`, `assets: list[ScoredAsset]`, `lists: Lists`, `fundamentus_rows: list[Fundamentals]`
  - `write_snapshot(snap, current: Path, history_dir: Path, archive_if_1600: bool)`
  - `read_snapshot(path) -> Snapshot`
  - `run_scrape(price, iv, fundamentals, cfg, universe, holidays, now) -> Snapshot`
  - `is_stale(stamps, now, cfg, holidays) -> bool` — `True` se o stamp mais recente é anterior ao último horário de scrape que já deveria ter rodado num dia útil
  - CLI: `python -m venda_de_put scrape` e `python -m venda_de_put serve` (serve pode ser stub que só importa; UI na Fase 2)

Degradação: se um adapter levantar exceção, manter o bloco correspondente do snapshot anterior (se existir) e marcar o `SourceStamp(ok=False, error=str(e), stale=True)`. Se não houver anterior, o dashboard ainda sobe com listas possíveis a partir do que veio; campos da fonte morta = `"sem dado"`.

Yahoo: nunca concluir “sem dado” com uma única falha de um ticker — `YahooHttp` tenta 2 vezes; se persistir, aquele ticker fica sem técnico, os outros seguem.

`run_scrape` é o **único** símbolo do pacote que chama `.fetch()` nos adapters.

- [ ] **Step 1: Write the failing test**

```python
from datetime import datetime
from pathlib import Path

from venda_de_put.config import AppConfig
from venda_de_put.models import CandleSeries, Fundamentals, IvPoint
from venda_de_put.scrape import run_scrape
from venda_de_put.snapshot import read_snapshot, write_snapshot
from venda_de_put.tz import TZ


class FakePrice:
    def __init__(self, series: dict[str, CandleSeries]):
        self.series = series
        self.calls = 0

    def fetch(self, tickers: list[str]) -> dict[str, CandleSeries]:
        self.calls += 1
        return {t: self.series[t] for t in tickers if t in self.series}


class FakeIv:
    def __init__(self, pts: dict[str, IvPoint], fail: bool = False):
        self.pts = pts
        self.fail = fail
        self.calls = 0

    def fetch(self) -> dict[str, IvPoint]:
        self.calls += 1
        if self.fail:
            raise RuntimeError("oplab down")
        return self.pts


class FakeFund:
    def __init__(self, rows: list[Fundamentals]):
        self.rows = rows
        self.calls = 0

    def fetch(self) -> list[Fundamentals]:
        self.calls += 1
        return self.rows


def _petr_inputs():
    now = datetime(2026, 8, 13, 16, 0, tzinfo=TZ)
    price = FakePrice({
        "PETR4": CandleSeries(
            ticker="PETR4",
            closes=[30.0] * 210,
            preco=41.75,
            max_52=45.0,
            min_52=28.0,
            collected_at=now,
        )
    })
    iv = FakeIv({"PETR4": IvPoint("PETR4", iv=0.35, iv_rank=40, iv_percentile=0.55)})
    fund = FakeFund([
        Fundamentals(
            ticker="PETR4", cotacao=41.75, pl=6.0, pvp=1.2, psr=None, dy=0.1,
            p_ativo=None, p_cap_giro=None, p_ebit=None, p_ativ_circ_liq=None,
            ev_ebit=None, ev_ebitda=4.0, mrg_bruta=None, mrg_ebit=None,
            mrg_liq=0.2, liq_corr=1.1, roic=0.15, roe=0.22, liq_2meses=None,
            patrim_liq=None, div_liq_patrim=0.4, cresc_rec_5a=0.1,
        )
    ])
    universe = {"PETR4": "Petróleo e Gás"}
    return price, iv, fund, universe, now


def test_write_and_read_roundtrip(tmp_path: Path):
    price, iv, fund, universe, now = _petr_inputs()
    snap = run_scrape(price, iv, fund, AppConfig(), universe, holidays=set(), now=now)
    path = tmp_path / "current.json"
    write_snapshot(snap, path, tmp_path / "history", archive_if_1600=False)
    back = read_snapshot(path)
    assert back.assets[0].ticker == "PETR4"
    assert back.assets[0].technicals.iv == 0.35


def test_run_scrape_uses_adapters_once():
    price, iv, fund, universe, now = _petr_inputs()
    snap = run_scrape(price, iv, fund, AppConfig(), universe, set(), now)
    assert price.calls == 1 and iv.calls == 1 and fund.calls == 1
    assert snap.lists.fundamentalista[0].ticker == "PETR4"


def test_failed_source_keeps_previous_block(tmp_path: Path):
    price, iv, fund, universe, now = _petr_inputs()
    first = run_scrape(price, iv, fund, AppConfig(), universe, set(), now)
    write_snapshot(first, tmp_path / "current.json", tmp_path / "history", False)
    iv2 = FakeIv({}, fail=True)
    second = run_scrape(price, iv2, fund, AppConfig(), universe, set(), now, previous=first)
    assert iv2.calls == 1
    petr = next(a for a in second.assets if a.ticker == "PETR4")
    assert petr.technicals.iv == 0.35
    stamp = next(s for s in second.stamps if s.source == "oplab")
    assert stamp.ok is False
    assert stamp.stale is True
```

Assinatura que esta task trava e a Task 10 reutiliza:

```python
def run_scrape(
    price: PriceSource,
    iv: IvSource,
    fundamentals: FundamentalsSource,
    cfg: AppConfig,
    universe: dict[str, str],
    holidays: set[date],
    now: datetime,
    previous: Snapshot | None = None,
) -> Snapshot: ...
```

`web.app` **não** chama `run_scrape`. O “refresh” da Fase 2 só chama `read_snapshot`.

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_scrape.py tests/test_snapshot.py -v
```

Expected: FAIL.

- [ ] **Step 3: Implement snapshot JSON estável** (ISO UTC internamente; a UI formata). Histórico: se `now` em São Paulo é `16:00` ± 10 min e o scrape fechou ok, copiar para `data/snapshots/history/YYYY-MM-DD.json`. Sem tela.

`__main__.py`:

```python
import argparse
import sys

def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["scrape", "serve", "smoke"])
    args = p.parse_args(argv)
    if args.cmd == "scrape":
        from venda_de_put.scrape import cli_scrape
        return cli_scrape()
    if args.cmd == "smoke":
        from venda_de_put.smoke import cli_smoke
        return cli_smoke()
    from venda_de_put.web.app import cli_serve
    return cli_serve()

if __name__ == "__main__":
    sys.exit(main())
```

Nesta task, `cli_serve` pode levantar `NotImplementedError` — a Task 10 implementa.

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_scrape.py tests/test_snapshot.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/venda_de_put/snapshot.py src/venda_de_put/scrape.py src/venda_de_put/__main__.py tests/test_scrape.py tests/test_snapshot.py
git commit -m "feat: snapshot em disco e CLI de scrape com degradação por fonte"
```

---

### Task 9: Smoke ao vivo (gate da Fase 1)

**Files:**
- Create: `src/venda_de_put/smoke.py`
- Create: `tests/test_smoke_offline.py`

**Interfaces:**
- Consumes: `YahooHttp`, `OplabHttp`, `FundamentusHttp`
- Produces: `cli_smoke() -> int` — 0 se os três responderam o contrato; ≠0 se algum falhou. **Não** raspa os 86. Só: 1 chart `PETR4.SA` `range=2y`, 1 GET OpLab, 1 GET Fundamentus.

- [ ] **Step 1: Write the failing offline test** (httpx mock)

```python
from venda_de_put.smoke import run_smoke

class Boom:
    def get(self, url, **kw):
        raise AssertionError(url)

def test_smoke_uses_2y_not_max(monkeypatch):
    seen = []
    class C:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def get(self, url, **kw):
            seen.append(url)
            class R:
                content = b"<html></html>"
                text = "{}"
                def raise_for_status(self): pass
                def json(self):
                    return {"chart": {"result": [{"meta": {"regularMarketPrice": 1},
                                                  "timestamp": [1],
                                                  "indicators": {"quote": [{"close": [1.0]}]}}]}}
            return R()
    # injetar C; assert nenhuma URL contém range=max
```

O teste offline não precisa parsear OpLab/Fundamentus de verdade se você stubar `run_smoke` em três funções já testadas na Task 7. O que importa: URLs certas, `range=2y`, uma chamada cada.

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_smoke_offline.py -v
```

Expected: FAIL.

- [ ] **Step 3: Implement `run_smoke` + `cli_smoke`.** Imprimir em pt-BR: `PETR4 preço=… coletado em dd/MM/yyyy HH:mm:ss` / `OpLab stocks=N PETR4 iv=…` / `Fundamentus linhas=N encoding=iso-8859-1`.

- [ ] **Step 4: Run offline tests, then one live smoke**

```bash
pytest tests/test_smoke_offline.py tests/test_tz.py tests/test_calendar_b3.py tests/test_premium.py tests/test_indicators.py tests/test_scoring_ranks.py tests/test_scoring_lists.py tests/test_sources.py tests/test_scrape.py tests/test_snapshot.py -v
python -m venda_de_put smoke
```

Expected: pytest 100% PASS. Smoke ao vivo: três linhas ok **ou** falha explicada (não silenciar). Se o smoke ao vivo falhar por rede, registrar o erro no commit message da Fase 1 e **não** avançar parsers “no chute”.

**GATE FASE 1:** todos os testes acima verdes. Sem isso não existe Task 10.

- [ ] **Step 5: Commit**

```bash
git add src/venda_de_put/smoke.py tests/test_smoke_offline.py
git commit -m "feat: smoke ao vivo das três fontes (uma chamada cada)"
```

---

# Fase 2 — Interface

**Gate:** Dashboard usável em viewport 390px e 1280px; 8 abas; Atualizar não raspa (teste com adapter que explode se chamado); vencimento recalcula prêmio-alvo sem I/O; todas as datas em pt-BR.

---

### Task 10: FastAPI — JSON API e refresh que só relê

**Files:**
- Create: `src/venda_de_put/web/app.py`
- Create: `tests/test_api.py`

**Interfaces:**
- Consumes: `read_snapshot`, `load_config`, `save_config`, `build_lists`/`score_*` (recalc), `build_calendar`, `premio_alvo`
- Produces: app FastAPI com:

| Método | Rota | Comportamento |
|---|---|---|
| GET | `/api/dashboard?vencimento=YYYY-MM-DD&so_mensais=1` | listas + prêmio-alvo + stamps + `stale` + vencimento rotulado |
| GET | `/api/ativos` | 86 scored; query `calculo=1` inclui ranks |
| GET | `/api/dados` | snapshot Fundamentus + carimbo |
| GET | `/api/setores` | 14 grupos, contagem, ScoreF médio |
| GET | `/api/config` | `AppConfig` |
| PUT | `/api/config` | grava JSON e **recalcula** listas do snapshot em memória/disco, sem fetch |
| GET | `/api/vencimentos` | calendário |
| GET | `/api/feriados` | lista |
| PUT | `/api/feriados` | grava e o próximo GET de vencimentos muda |
| GET | `/api/instrucoes` | texto (IFR 10–50, sem Profit) |
| POST | `/api/refresh` | `read_snapshot` de novo. **Proibido** importar `run_scrape` neste módulo |

Injetar caminhos via `app.state` (`snapshot_path`, `config_path`, …) para os testes usarem `tmp_path`.

Trocar vencimento **não** reordena as três listas. Teste: duas queries com vencimentos diferentes → mesmos tickers na ①②③, `premio_alvo` diferente.

- [ ] **Step 1: Write the failing test**

```python
from fastapi.testclient import TestClient
from venda_de_put.web.app import create_app

def test_refresh_does_not_scrape(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise AssertionError("scrape called")
    monkeypatch.setattr("venda_de_put.scrape.run_scrape", boom)
    app = create_app(data_dir=tmp_path)  # snapshot mínimo já gravado no tmp
    c = TestClient(app)
    r = c.post("/api/refresh")
    assert r.status_code == 200
    assert "coletado" in r.text.lower() or "generated_at" in r.json() or "stamps" in r.json()

def test_trocar_vencimento_nao_reordena(tmp_path):
    app = create_app(data_dir=tmp_path)
    c = TestClient(app)
    a = c.get("/api/dashboard", params={"vencimento": "2026-08-21", "so_mensais": 1}).json()
    b = c.get("/api/dashboard", params={"vencimento": "2026-09-18", "so_mensais": 1}).json()
    tickers = lambda payload, key: [x["ticker"] for x in payload["listas"][key]]
    assert tickers(a, "fundamentalista") == tickers(b, "fundamentalista")
    assert tickers(a, "tecnico") == tickers(b, "tecnico")
    assert tickers(a, "combinado") == tickers(b, "combinado")
    assert a["premio_alvo"] != b["premio_alvo"]
    assert a["vencimento"]["efetivo"] != b["vencimento"]["efetivo"]
```

Antes do teste, grave em `tmp_path` um `current.json` e um `config.json` válidos (use `run_scrape` + fakes da Task 8 no `setup` do teste, ou copie `tests/fixtures/snapshot_min.json` se você o extrair nessa task). `create_app` lê só disco.

JSON de `/api/dashboard`:

```python
{
  "listas": {"fundamentalista": [...], "tecnico": [...], "combinado": [...]},
  "premio_alvo": 0.0133,
  "vencimento": {"efetivo": "2026-09-18", "label": "18/09/2026 · sex · … · MENSAL"},
  "stamps": [...],
  "stale": false,
}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_api.py -v
```

Expected: FAIL.

- [ ] **Step 3: Implement `create_app(data_dir: Path) -> FastAPI`.** Datas no JSON podem ir ISO; o front formata. Inclua `premio_alvo` e o rótulo `18/09/2026 · sex · 36 dias corridos · 25 úteis · MENSAL` já montado no back (`label_vencimento(v: Vencimento) -> str`) para o card/WhatsApp não depender de JS.

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_api.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/venda_de_put/web/app.py tests/test_api.py
git commit -m "feat: API JSON; refresh só relê snapshot"
```

---

### Task 11: Casca HTML e aba Dashboard

**Files:**
- Create: `src/venda_de_put/web/templates/index.html`
- Create: `src/venda_de_put/web/static/app.css`
- Create: `src/venda_de_put/web/static/app.js`
- Modify: `src/venda_de_put/web/app.py` — `GET /` serve o HTML; estáticos em `/static`
- Create: `tests/test_ui_shell.py`

**Interfaces:**
- Consumes: `/api/dashboard`, `/api/refresh`, `/api/vencimentos`
- Produces: página única. Sidebar esquerda fixa, **um** item “Venda de PUT”. Abas horizontais nesta ordem: Dashboard, Ativos, Dados, Setores, Config, Vencimentos, Feriados, Instruções. Aba inicial = Dashboard.

Dashboard:

- Seletor `<select id="vencimento">` + toggle “Só mensais” (ligado).
- Carimbo visível: `Atualizado em 13/08/2026 12:05:29` + badge `dado velho` se `stale`.
- Botão Atualizar → `POST /api/refresh` (nunca scrape).
- Três blocos de cards. Textos narrativos **literais** da spec (copiar e colar, não reescrever).
- Colunas: ① ticker grupo ScoreF ROE P/L P/VP DY; ② ticker SINAL IFR preço Boll Inf IV/HV; ③ ticker grupo ScoreF SINAL IFR preço IV/HV.
- Cada card mostra o vencimento em `dd/MM/yyyy`.
- Lista ③ pode ter 0 cards e um estado vazio: *“Nenhum ativo com as duas pontas alinhadas agora.”*
- Campo `"sem dado"` quando o JSON vier `null`.

CSS: variáveis `--verde: #14492E`, `--amarelo: #FFF7D6`. Referência visual: Records Table / Recommendation Card / Sidebar do beautifului.dev — **reconstruídos**, sem copiar kit. Fonte do sistema, densidade alta, cards com borda suave.

- [ ] **Step 1: Write the failing test**

```python
from fastapi.testclient import TestClient
from venda_de_put.web.app import create_app

def test_home_has_eight_tabs_and_narratives(tmp_path):
    app = create_app(data_dir=tmp_path)
    html = TestClient(app).get("/").text
    for name in ["Dashboard", "Ativos", "Dados", "Setores", "Config", "Vencimentos", "Feriados", "Instruções"]:
        assert name in html
    assert "Ferramenta de seleção, não recomendação" in html
    assert "empresa que eu aceitaria carregar" in html
    assert "faca caindo" in html
    assert "às vezes essa lista vem com menos de 10" in html
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_ui_shell.py -v
```

Expected: FAIL.

- [ ] **Step 3: Implement HTML/CSS/JS.** `app.js` formata com `Intl.NumberFormat("pt-BR")` e **não** usa `Date#toLocaleString` sem `timeZone: "America/Sao_Paulo"`. Qualquer `new Date(iso)` de carimbo passa por:

```javascript
new Intl.DateTimeFormat("pt-BR", {
  timeZone: "America/Sao_Paulo",
  day: "2-digit", month: "2-digit", year: "numeric",
  hour: "2-digit", minute: "2-digit", second: "2-digit",
  hour12: false,
}).format(d);
```

Trocar o `<select>` só chama `/api/dashboard?vencimento=` de novo. Com as DevTools em offline, a troca ainda funciona se o payload do seletor já veio no primeiro GET (o back calcula na hora sobre o snapshot — precisa de rede local até o FastAPI, não até Yahoo). Teste manual: parar não se aplica a Yahoo; o teste de API da Task 10 já cobre “sem fetch de fonte”.

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_ui_shell.py -v
python -m venda_de_put serve
```

Abrir `http://127.0.0.1:8765`, conferir as 3 listas e o seletor. Sem senha local (auth é nginx).

- [ ] **Step 5: Commit**

```bash
git add src/venda_de_put/web tests/test_ui_shell.py
git commit -m "feat: casca com abas e Dashboard em cards"
```

---

### Task 12: As outras 7 abas, Config amarelo, responsivo

**Files:**
- Modify: `src/venda_de_put/web/static/app.js`
- Modify: `src/venda_de_put/web/static/app.css`
- Modify: `src/venda_de_put/web/templates/index.html`
- Create: `tests/test_ui_abas.py`
- Create: `src/venda_de_put/web/instrucoes.md` (texto da aba Instruções, IFR 10–50, sem Profit)

**Interfaces:**
- Consumes: rotas da Task 10
- Produces: as 7 abas restantes, funcionais.

| Aba | Comportamento |
|---|---|
| Ativos | tabela 86, sort por clique no th, filtro texto no ticker/grupo. Toggle “mostrar cálculo” revela nROE…ScoreC |
| Dados | tabela Fundamentus + carimbo |
| Setores | 14 linhas |
| Config | inputs fundo `#FFF7D6`. PUT no blur/salvar. Recalcula listas sem scrape. Sem campos RTD |
| Vencimentos | tabela do calendário; clique → muda aba para Dashboard com aquele vencimento |
| Feriados | lista editável (adicionar/remover). PUT. Vencimentos atualizam |
| Instruções | HTML do `instrucoes.md` |

Responsivo: `@media (max-width: 720px)` — cada linha de tabela vira card (`display: block` no `tr`/`td` com `::before { content: attr(data-label) }`). Dashboard permanece usável (seletor empilha, 1 coluna de cards).

- [ ] **Step 1: Write the failing test**

```python
def test_config_put_recalculates_without_scrape(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "venda_de_put.scrape.run_scrape",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("scrape")),
    )
    app = create_app(data_dir=tmp_path)
    client = TestClient(app)
    before = client.get("/api/dashboard").json()
    cfg = client.get("/api/config").json()
    cfg["ifr_max"] = 45
    r = client.put("/api/config", json=cfg)
    assert r.status_code == 200
    dash = client.get("/api/dashboard").json()
    assert dash["stamps"] == before["stamps"]
    saved = client.get("/api/config").json()
    assert saved["ifr_max"] == 45
```

```python
def test_instrucoes_corrigem_ifr_e_tiram_profit():
    html = client.get("/").text
    # o JS carrega /api/instrucoes — teste a API
    text = client.get("/api/instrucoes").json()["texto"]
    assert "10" in text and "50" in text
    assert "Profit" not in text
    assert "RTD" not in text
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_ui_abas.py -v
```

Expected: FAIL.

- [ ] **Step 3: Implement as 7 abas + CSS móvel.** Verificar na mão em 390px e 1280px (DevTools). Checklist visual: carimbo visível sem tooltip; amarelo só no que é editável; verde nos cabeçalhos.

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_ui_abas.py tests/test_ui_shell.py tests/test_api.py -v
```

Expected: PASS.

**GATE FASE 2:** API + 8 abas + pt-BR + refresh sem scrape. Sem isso não existe Task 13 no servidor.

- [ ] **Step 5: Commit**

```bash
git add src/venda_de_put/web tests/test_ui_abas.py
git commit -m "feat: sete abas restantes, Config persistente e layout móvel"
```

---

# Fase 3 — Operação e VPS

**Gate:** levantamento mostrado ao usuário **antes** de qualquer escrita; sites antigos respondem depois do `reload`; sem senha o dashboard não entrega.

---

### Task 13: systemd, nginx novo e runbook de deploy

**Files:**
- Create: `deploy/venda-de-put.service`
- Create: `deploy/venda-de-put-scrape.service`
- Create: `deploy/venda-de-put-scrape.timer`
- Create: `deploy/nginx-venda-de-put.conf.template`
- Create: `deploy/RUNBOOK.md`
- Create: `tests/test_refresh_import_guard.py` (guarda permanente: `web.app` não importa `run_scrape`)

**Interfaces:**
- Consumes: `python -m venda_de_put serve` e `python -m venda_de_put scrape`
- Produces: unidades e um runbook que um humano segue. **Nenhum passo do runbook é executado pelo agente sem o output do levantamento colado na conversa e o hostname informado pelo usuário.**

`venda-de-put.service`:

```ini
[Unit]
Description=Dashboard venda de PUT
After=network.target

[Service]
Type=simple
User=venda-de-put
Group=venda-de-put
WorkingDirectory=/opt/venda-de-put
Environment=VENDA_DE_PUT_DATA=/opt/venda-de-put/data
ExecStart=/opt/venda-de-put/.venv/bin/python -m venda_de_put serve --host 127.0.0.1 --port 8765
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

`venda-de-put-scrape.service` (oneshot) + `.timer`:

```ini
[Unit]
Description=Scrape periódico venda de PUT

[Service]
Type=oneshot
User=venda-de-put
WorkingDirectory=/opt/venda-de-put
Environment=VENDA_DE_PUT_DATA=/opt/venda-de-put/data
ExecStart=/opt/venda-de-put/.venv/bin/python -m venda_de_put scrape
```

```ini
[Unit]
Description=Horários de scrape venda de PUT

[Timer]
OnCalendar=Mon..Fri *-*-* 11:00:00 America/Sao_Paulo
OnCalendar=Mon..Fri *-*-* 13:00:00 America/Sao_Paulo
OnCalendar=Mon..Fri *-*-* 16:00:00 America/Sao_Paulo
Persistent=true

[Install]
WantedBy=timers.target
```

O scrape de Fundamentus (dias 1 e 15 às 07h) é decisão **dentro** de `cli_scrape`: se hoje (São Paulo) é dia 1 ou 15 e ainda não há stamp de Fundamentus desse dia, busca; senão reutiliza o bloco anterior. Não precisa de um quarto timer. (07h cai antes do 11h — o timer das 11h do dia 1/15 deve achar o fundamento do dia se um timer extra de 07h for adicionado. Adicione um quarto `OnCalendar=*-*-1,15 07:00:00 America/Sao_Paulo` no mesmo `.timer` para cumprir a spec ao pé da letra.)

Template nginx (`SERVER_NAME` e `PORT` substituídos à mão):

```nginx
server {
    listen 80;
    server_name SERVER_NAME;
    auth_basic "venda de put";
    auth_basic_user_file /opt/venda-de-put/etc/htpasswd;

    location / {
        proxy_pass http://127.0.0.1:8765;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

Certificado HTTPS: só se o levantamento mostrar certbot já em uso com o mesmo padrão dos outros sites. Replicar **o mesmo esquema** (não inventar). Se os outros usam um `include snippets/ssl.conf` + 443, o arquivo **novo** segue esse padrão. Sem inventar `certbot` se não houver.

- [ ] **Step 1: Write the import-guard test**

```python
import ast
from pathlib import Path

def test_web_app_does_not_import_run_scrape():
    src = Path("src/venda_de_put/web/app.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported.append((node.module, [a.name for a in node.names]))
        if isinstance(node, ast.Import):
            imported.append((None, [a.name for a in node.names]))
    assert not any(
        (mod or "").endswith("scrape") or "run_scrape" in names
        for mod, names in imported
    )
```

- [ ] **Step 2: Run test to verify it fails** (se `app.py` ainda importar scrape, vermelho; se já estiver limpo, o teste já passa — nesse caso o step 3 é só o runbook)

```bash
pytest tests/test_refresh_import_guard.py -v
```

- [ ] **Step 3: Write units + `deploy/RUNBOOK.md` com esta ordem, literal:**

1. **Não escrever nada.** Rodar e **colar na conversa**:
   - `nginx -T`
   - `ss -tlnp`
   - `systemctl list-units --type=service --state=running`
   - `df -h`
2. Esperar o usuário confirmar e informar `SERVER_NAME` + senha (a senha não vai para o git).
3. `sudo tar czf ~/nginx-backup-$(date +%F).tar.gz /etc/nginx`
4. Criar usuário `venda-de-put`, diretório `/opt/venda-de-put`, venv, `pip install` do projeto. Porta 8765 **somente se** `ss` mostrou livre; senão outra alta livre.
5. `htpasswd -c /opt/venda-de-put/etc/htpasswd igor` (ou o nome que o usuário quiser).
6. Copiar o arquivo **novo** para `/etc/nginx/sites-available/venda-de-put`, symlink em `sites-enabled/`. **Zero** edits em arquivos que já existiam.
7. `sudo nginx -t` — qualquer erro: remover o symlink e parar.
8. `sudo systemctl reload nginx` (nunca `restart`).
9. `curl -I https://SITE_ANTIGO` (os hosts que o `nginx -T` listou) deve continuar 200/301 como antes.
10. `curl -I http://SERVER_NAME` sem senha → `401`. Com senha → `200` e o HTML do Dashboard.
11. `systemctl enable --now venda-de-put.service venda-de-put-scrape.timer`

Proibido no runbook: `apt upgrade`, `pip install` no Python do sistema, `ufw`/`iptables`, Security List, `certbot` em certificado alheio, `0.0.0.0`.

- [ ] **Step 4: Run the guard test**

```bash
pytest tests/test_refresh_import_guard.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add deploy tests/test_refresh_import_guard.py
git commit -m "chore: units systemd, template nginx e runbook que não toca site alheio"
```

**Não executar o runbook nesta task.** Deploy é um passo humano depois do levantamento.

---

## Mapa spec → task (cobertura)

| Spec | Task |
|---|---|
| §3 arquitetura / fronteira de fontes | 7, 8 |
| §4 VPS | 13 |
| §5.1 Yahoo `range=2y`, null≠0, AUAU3 | 4, 7, 9 |
| §5.2 OpLab `__NEXT_DATA__`, sem cadeia | 7 (proibido chamar `/opcoes/{TICKER}`) |
| §5.3 Fundamentus ISO-8859-1, colunas por posição | 7 |
| §5.4 cadência e botão | 8, 10, 13 |
| §6.1 universo 86 | 1 (`universe.json`) |
| §6.2–6.3 ranks / ScoreF / nMrgL no Financeiro | 5 |
| §6.4–6.5 sinal e listas | 6 |
| §6.6 indicadores | 4 |
| §6.7 prêmio-alvo e mensal 15–21 | 2, 3, 10 |
| nov/2026 = 19/11 quinta | 2 |
| §7 oito telas + narrativas | 11, 12 |
| §8 pt-BR / fuso | 1, 11 |
| §9 stack | 1 |
| §12 aceite 1–2 paridade / menor é melhor | 5, 6 |
| §12.6 refresh não raspa | 10, 13 |
| §12.7 vencimento não reordena | 10 |
| §12.9 fonte morta | 8 |
| §12.10 celular | 12 |
| §12.11–12 nginx / senha | 13 |
| §13 strike futuro | fora — nenhum arquivo de cadeia |
| §14 fora de escopo | nenhum task cria isso |

## Fora deste plano

- Motor de strike / cadeia OpLab
- Registro de operações, carteira, P&L
- Auth na FastAPI, OAuth, multi-usuário
- Scrape no clique
- Qualquer escrita na VPS sem o levantamento colado e o hostname do usuário

## Aberto até o deploy (não bloqueia executar Fases 1–2)

- `SERVER_NAME` (subdomínio → `[VPS]`)
- Senha do `htpasswd`
- Confirmação do `nginx -T` / portas
