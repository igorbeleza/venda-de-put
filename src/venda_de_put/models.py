from dataclasses import dataclass
from datetime import date


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
