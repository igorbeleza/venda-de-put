from dataclasses import dataclass
from datetime import date
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


@dataclass(frozen=True)
class Lists:
    fundamentalista: list[ScoredAsset]
    tecnico: list[ScoredAsset]
    combinado: list[ScoredAsset]
