from perron.data import generate_synthetic
from perron.features import resample_ohlcv


def synth5(days=30, seed=42):
    """Velas sintéticas de 5m (la temporalidad base por defecto)."""
    return resample_ohlcv(generate_synthetic(days=days, seed=seed), "5min")
