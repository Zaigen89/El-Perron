"""Estrategia v4: seguimiento de tendencia en 4h / diario (Donchian + stop móvil por ATR).

Por qué: el estudio de eventos sobre 180 días de BTC en 15m mostró que a horizontes de minutos a pocas
horas ninguna señal simple predice el precio; la única fuente de retorno observable es la deriva de
tendencias de días y semanas. En 4h/1d el ATR es de 1% a 3% y las comisiones (0.1%) dejan de importar.

Reglas (long; short es espejo si long_only = false):
  Entrada: cierre por encima del máximo de las últimas `donchian_entry` velas (sin contar la actual),
           con filtro de régimen opcional (cierre > EMA `regime_ema`).
  Stop inicial: `initial_stop_atr` ATR por debajo del cierre.
  Stop móvil: `trail_atr` ATR por debajo del máximo alcanzado desde la entrada (solo sube).
  Salida por señal: cierre por debajo del mínimo de las últimas `donchian_exit` velas.
  Sin objetivo fijo: se deja correr la tendencia. Sin salida por tiempo real (max_bars_in_trade alto).
"""
from __future__ import annotations

import pandas as pd

from ..config import StrategyConfig
from ..features import add_features, ema
from .base import Signal


class TrendFollowStrategy:
    name = "trend_follow_v4"

    def __init__(self, cfg: StrategyConfig, trend_interval: str = "1d", round_trip_cost_pct: float = 0.0):
        self.cfg = cfg
        self.trend_interval = trend_interval
        self.round_trip_cost_pct = round_trip_cost_pct

    def prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        c = self.cfg
        out = add_features(df, c, self.trend_interval)
        out["dc_high"] = out["high"].rolling(c.donchian_entry).max().shift(1)
        out["dc_low"] = out["low"].rolling(c.donchian_entry).min().shift(1)
        out["dc_exit_low"] = out["low"].rolling(c.donchian_exit).min().shift(1)
        out["dc_exit_high"] = out["high"].rolling(c.donchian_exit).max().shift(1)
        out["regime"] = ema(out["close"], c.regime_ema) if c.regime_ema > 0 else out["close"] * 0
        return out

    @property
    def warmup_bars(self) -> int:
        c = self.cfg
        return max(c.donchian_entry, c.atr_period, c.regime_ema, c.ema_slow) + 5

    def signal_at(self, df: pd.DataFrame, i: int) -> Signal | None:
        if i < self.warmup_bars:
            return None
        row = df.iloc[i]
        c = self.cfg
        if pd.isna(row["atr"]) or pd.isna(row["dc_high"]) or pd.isna(row["regime"]):
            return None
        if not (c.atr_min_pct <= row["atr_pct"] <= c.atr_max_pct):
            return None
        price = float(row["close"])
        a = float(row["atr"])
        direction = 0
        if price > row["dc_high"] and (c.regime_ema == 0 or price > row["regime"]):
            direction = 1
        elif not c.long_only and price < row["dc_low"] and (c.regime_ema == 0 or price < row["regime"]):
            direction = -1
        if direction == 0:
            return None
        stop = price - direction * c.initial_stop_atr * a
        feats = {k: (None if pd.isna(row[k]) else round(float(row[k]), 6))
                 for k in ["rsi", "atr_pct", "vol_ratio", "ret_5"]}
        feats["dist_regime_pct"] = round((price - float(row["regime"])) / price * 100.0, 3) if c.regime_ema else None
        feats["hour_utc"] = int(df.index[i].hour)
        reasons = [f"cierre {'sobre máximo' if direction > 0 else 'bajo mínimo'} de {c.donchian_entry} velas",
                   f"régimen EMA{c.regime_ema} {'alcista' if direction > 0 else 'bajista'}" if c.regime_ema else "sin filtro de régimen",
                   f"stop inicial {c.initial_stop_atr} ATR, móvil {c.trail_atr} ATR"]
        return Signal(time=df.index[i], direction=direction, price=price, stop_loss=stop,
                      take_profit=None, atr=a, reasons=reasons, features=feats)

    def trail_stop(self, df: pd.DataFrame, i: int, direction: int, entry_price: float, current_stop: float):
        row = df.iloc[i]
        a = float(row["atr"])
        if direction > 0:
            return float(row["high"]) - self.cfg.trail_atr * a
        return float(row["low"]) + self.cfg.trail_atr * a

    def should_exit(self, df: pd.DataFrame, i: int, direction: int, entry_price: float) -> bool:
        row = df.iloc[i]
        if direction > 0:
            return bool(row["close"] < row["dc_exit_low"]) if not pd.isna(row["dc_exit_low"]) else False
        return bool(row["close"] > row["dc_exit_high"]) if not pd.isna(row["dc_exit_high"]) else False
