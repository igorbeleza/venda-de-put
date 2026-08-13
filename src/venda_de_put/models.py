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
