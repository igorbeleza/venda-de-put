import json
from pathlib import Path
from typing import Union

from venda_de_put.models import AppConfig

__all__ = ["AppConfig", "load_config", "save_config"]


def load_config(path: Union[str, Path]) -> AppConfig:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    scrape = data.get("scrape_times", ("11:00", "13:00", "16:00"))
    days = data.get("fundamentus_days", (1, 15))
    return AppConfig(
        ifr_min=data.get("ifr_min", 10),
        ifr_max=data.get("ifr_max", 50),
        folga=data.get("folga", 0.05),
        meta_premio_30d=data.get("meta_premio_30d", 0.0115),
        mm_periodos=data.get("mm_periodos", 200),
        mm_tipo=data.get("mm_tipo", "sma"),
        ifr_periodos=data.get("ifr_periodos", 14),
        boll_periodos=data.get("boll_periodos", 20),
        boll_desvios=data.get("boll_desvios", 2.0),
        hv_periodos=data.get("hv_periodos", 21),
        scrape_times=tuple(scrape),
        fundamentus_days=tuple(days),
        fundamentus_time=data.get("fundamentus_time", "07:00"),
        calendario_ate=data.get("calendario_ate", "2027-12-31"),
    )


def save_config(cfg: AppConfig, path: Union[str, Path]) -> None:
    payload = {
        "ifr_min": cfg.ifr_min,
        "ifr_max": cfg.ifr_max,
        "folga": cfg.folga,
        "meta_premio_30d": cfg.meta_premio_30d,
        "mm_periodos": cfg.mm_periodos,
        "mm_tipo": cfg.mm_tipo,
        "ifr_periodos": cfg.ifr_periodos,
        "boll_periodos": cfg.boll_periodos,
        "boll_desvios": cfg.boll_desvios,
        "hv_periodos": cfg.hv_periodos,
        "scrape_times": list(cfg.scrape_times),
        "fundamentus_days": list(cfg.fundamentus_days),
        "fundamentus_time": cfg.fundamentus_time,
        "calendario_ate": cfg.calendario_ate,
    }
    Path(path).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
