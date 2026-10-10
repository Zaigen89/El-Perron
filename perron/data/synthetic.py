"""Generador de velas sintéticas de BTC para probar el sistema sin conexión.

Simula regímenes (tendencia alcista, bajista, lateral) con volatilidad variable
y clusters de volumen. NO sirve para validar una estrategia, solo para probar
que el flujo completo funciona.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def generate_synthetic(days: float = 7, interval_minutes: int = 1, start_price: float = 60_000.0,
                       seed: int | None = 42, start: str = "2025-01-01") -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    n = int(days * 24 * 60 / interval_minutes)
    idx = pd.date_range(start=start, periods=n, freq=f"{interval_minutes}min", tz="UTC")

    # Regímenes: drift y vol cambian por bloques de ~4 horas
    block = max(1, int(240 / interval_minutes))
    n_blocks = n // block + 1
    drifts = rng.choice([-0.00004, 0.0, 0.00004], size=n_blocks, p=[0.3, 0.4, 0.3])
    vols = rng.choice([0.00025, 0.0005, 0.0010], size=n_blocks, p=[0.4, 0.4, 0.2])
    drift = np.repeat(drifts, block)[:n]
    vol = np.repeat(vols, block)[:n]

    rets = drift + vol * rng.standard_t(df=4, size=n) / np.sqrt(2) * 0.6
    close = start_price * np.exp(np.cumsum(rets))
    open_ = np.concatenate([[start_price], close[:-1]])
    wick = np.abs(rng.normal(0, 1, size=n)) * vol * close
    high = np.maximum(open_, close) + wick
    low = np.minimum(open_, close) - np.abs(rng.normal(0, 1, size=n)) * vol * close

    base_vol = 20.0
    volume = base_vol * (1 + 3 * np.abs(rets) / (vol + 1e-9)) * rng.lognormal(0, 0.5, size=n)
    trades = (volume * 40).astype(int)

    df = pd.DataFrame({"open": open_, "high": high, "low": low, "close": close,
                       "volume": volume, "trades": trades}, index=idx)
    df.index.name = "time"
    return df
