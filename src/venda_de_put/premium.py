import math


def premio_alvo(meta_30d: float, dias_corridos: int) -> float:
    if dias_corridos <= 0:
        return 0.0
    return meta_30d * math.sqrt(dias_corridos / 30.0)
