from ..config import Config
from .base import Signal, Strategy
from .scalping import ScalpingStrategy
from .value_pullback import ValuePullbackStrategy

REGISTRY = {
    "scalping_pullback_v2": ScalpingStrategy,
    "value_pullback_v3": ValuePullbackStrategy,
}


def build_strategy(cfg: Config, name: str | None = None):
    """Construye la estrategia indicada en config.yaml (strategy.name) con el costo de comisiones."""
    key = name or cfg.strategy.name
    if key not in REGISTRY:
        raise ValueError(f"estrategia desconocida: {key}. Opciones: {', '.join(REGISTRY)}")
    return REGISTRY[key](cfg.strategy, cfg.trend_interval,
                         round_trip_cost_pct=cfg.fees.round_trip_fraction * 100.0)


__all__ = ["Signal", "Strategy", "ScalpingStrategy", "ValuePullbackStrategy", "REGISTRY", "build_strategy"]
