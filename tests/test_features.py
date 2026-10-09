import numpy as np
import pandas as pd

from perron.config import StrategyConfig
from perron.data import generate_synthetic
from perron.features import add_features, rsi, atr


def test_rsi_bounds():
    df = generate_synthetic(days=1, seed=1)
    r = rsi(df["close"], 7).dropna()
    assert ((r >= 0) & (r <= 100)).all()


def test_atr_positive():
    df = generate_synthetic(days=1, seed=2)
    a = atr(df, 14).dropna()
    assert (a > 0).all()


def test_trend_filter_does_not_look_ahead():
    """La EMA de tendencia en la vela t solo depende de velas 5m cerradas antes de t."""
    cfg = StrategyConfig()
    df = generate_synthetic(days=2, seed=3)
    full = add_features(df, cfg)
    # Perturbar el futuro: cambiar cierres a partir de la mitad y verificar que el pasado no cambia
    cut = len(df) // 2
    df2 = df.copy()
    df2.loc[df2.index[cut:], "close"] = df2.loc[df2.index[cut:], "close"] * 1.05
    part = add_features(df2, cfg)
    cols = ["trend_ema", "trend_dir", "ema_fast", "rsi", "atr", "vwap"]
    a = full[cols].iloc[: cut - 5]
    b = part[cols].iloc[: cut - 5]
    pd.testing.assert_frame_equal(a, b)


def test_feature_columns_present():
    df = add_features(generate_synthetic(days=0.5, seed=4), StrategyConfig())
    for c in ["ema_fast", "ema_slow", "rsi", "atr", "atr_pct", "vol_ratio", "vwap", "trend_ema", "trend_dir"]:
        assert c in df.columns
    assert set(np.unique(df["trend_dir"])).issubset({-1, 0, 1})
