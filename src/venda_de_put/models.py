from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional


@dataclass(frozen=True)
class Vencimento:
    nominal: date
    efetivo: date
    tipo: str  # "MENSAL" | "Semanal"
    feriado_na_sexta: bool
    dia_semana: str
    dias_corridos: int
    dias_uteis: int
    status: str


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
class FundScore:
    ticker: str
    n_roe: Optional[int]
    n_roic: Optional[int]
    n_mrgl: Optional[int]
    n_div: Optional[int]
    n_liqc: Optional[int]
    n_pl: Optional[int]
    n_pvp: Optional[int]
    n_eveb: Optional[int]
    n_crsc: Optional[int]
    qualid: Optional[float]
    saude: Optional[float]
    valuat: Optional[float]
    consist: Optional[int]
    score_f: Optional[float]
    pct_f: Optional[float]


@dataclass(frozen=True)
class TechnicalInput:
    preco: Optional[float]
    mm200: Optional[float]
    ifr: Optional[float]
    boll_inf: Optional[float]
    iv: Optional[float]
    hv: Optional[float]
    iv_rank: Optional[float] = None
    iv_percentile: Optional[float] = None


@dataclass(frozen=True)
class AppConfig:
    ifr_min: float = 10
    ifr_max: float = 50
    folga: float = 0.05
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
    calendario_ate: str = "2027-12-31"


@dataclass(frozen=True)
class SourceStamp:
    source: str
    collected_at: datetime
    ok: bool
    error: Optional[str]
    stale: bool


@dataclass(frozen=True)
class ScoredAsset:
    ticker: str
    fund: FundScore
    tendencia: Optional[str]
    timing: Optional[str]
    sinal: Optional[str]
    score_t: Optional[float]
    score_c: Optional[float]
    iv_hv: Optional[float]
    technicals: Optional[TechnicalInput] = None


@dataclass(frozen=True)
class Lists:
    fundamentalista: list[ScoredAsset]
    tecnico: list[ScoredAsset]
    combinado: list[ScoredAsset]


@dataclass(frozen=True)
class CandleSeries:
    ticker: str
    closes: list[Optional[float]]
    preco: Optional[float]
    max_52: Optional[float]
    min_52: Optional[float]
    collected_at: datetime
    timestamps: list[Optional[int]] = field(default_factory=list)


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
class PutQuote:
    due_date: date
    strike: float
    bid: Optional[float]
    ask: Optional[float]
    delta: Optional[float]
    poe: Optional[float]
    volume: Optional[float]
    last: Optional[float] = None
    symbol: Optional[str] = None


@dataclass(frozen=True)
class StrikePick:
    status: str  # ok | abaixo_da_meta | sem_serie | sem_liquidez
    due_date: date
    strike: Optional[float]
    bid: Optional[float]
    bid_pct: Optional[float]
    ask: Optional[float]
    distancia_pct: Optional[float]
    delta: Optional[float]
    poe: Optional[float]
    volume: Optional[float]
    last: Optional[float] = None
    last_pct: Optional[float] = None
    symbol: Optional[str] = None


@dataclass(frozen=True)
class Snapshot:
    generated_at: datetime
    stamps: list[SourceStamp]
    assets: list[ScoredAsset]
    lists: Lists
    fundamentus_rows: list[Fundamentals]
    chains: dict[str, list[PutQuote]] = field(default_factory=dict)
    # "fraction" = DY/ROE/margens já em 0.1772. Ausente no JSON antigo = pontos (17.72).
    fundamentus_unit: str = "fraction"
