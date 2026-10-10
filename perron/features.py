"""Indicadores técnicos usados por la estrategia de scalping. Todo vectorizado con pandas."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import StrategyConfig


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False, min_periods=n).mean()


def rsi(close: pd.Series, n: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()
    avg_loss = loss.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    out = 100.0 - 100.0 / (1.0 + rs)
    return out.fillna(100.0).where(avg_loss.notna(), np.nan)


def atr(df: pd.DataFrame, n: int) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()


def session_vwap(df: pd.DataFrame) -> pd.Series:
    """VWAP que se reinicia cada día UTC."""
    typical = (df["high"] + df["low"] + df["close"]) / 3.0
    day = df.index.floor("D")
    pv = (typical * df["volume"]).groupby(day).cumsum()
    v = df["volume"].groupby(day).cumsum()
    return pv / v.replace(0.0, np.nan)


def resample_ohlcv(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    return df.resample(rule, label="left", closed="left").agg(agg).dropna()


def _pandas_rule(interval: str) -> str:
    unit = interval[-1]
    num = interval[:-1]
    return {"m": f"{num}min", "h": f"{num}h", "d": f"{num}D", "w": f"{num}W"}[unit]


def add_features(df: pd.DataFrame, cfg: StrategyConfig, trend_interval: str = "5m") -> pd.DataFrame:
    """Agrega columnas de indicadores al DataFrame OHLCV (índice datetime UTC)."""
    out = df.copy()
    out["ema_fast"] = ema(out["close"], cfg.ema_fast)
    out["ema_slow"] = ema(out["close"], cfg.ema_slow)
    out["rsi"] = rsi(out["close"], cfg.rsi_period)
    out["atr"] = atr(out, cfg.atr_period)
    out["atr_pct"] = out["atr"] / out["close"] * 100.0
    out["vol_ma"] = out["volume"].rolling(cfg.volume_ma, min_periods=cfg.volume_ma).mean()
    out["vol_ratio"] = out["volume"] / out["vol_ma"].replace(0.0, np.nan)
    out["vwap"] = session_vwap(out)
    out["body"] = out["close"] - out["open"]
    out["range"] = (out["high"] - out["low"]).replace(0.0, np.nan)
    out["body_ratio"] = (out["body"].abs() / out["range"]).fillna(0.0)
    out["ret_1"] = out["close"].pct_change()
    out["ret_5"] = out["close"].pct_change(5)

    # Filtro de tendencia en temporalidad superior, sin mirar al futuro:
    # la EMA de 5m se calcula sobre velas 5m CERRADAS y se desplaza una vela.
    trend = resample_ohlcv(out[["open", "high", "low", "close", "volume"]], _pandas_rule(trend_interval))
    trend_ema = ema(trend["close"], cfg.ema_trend)
    trend_slope = trend_ema.diff()
    trend_df = pd.DataFrame({"trend_ema": trend_ema, "trend_slope": trend_slope}).shift(1)
    merged = pd.merge_asof(out[[]].reset_index(), trend_df.reset_index().rename(columns={"index": "time"}),
                           on="time", direction="backward")
    merged = merged.set_index("time")
    out["trend_ema"] = merged["trend_ema"].to_numpy()
    out["trend_slope"] = merged["trend_slope"].to_numpy()
    out["trend_dir"] = np.where(
        (out["close"] > out["trend_ema"]) & (out["trend_slope"] > 0), 1,
        np.where((out["close"] < out["trend_ema"]) & (out["trend_slope"] < 0), -1, 0),
    )
    out.loc[out["trend_ema"].isna(), "trend_dir"] = 0
    return out
