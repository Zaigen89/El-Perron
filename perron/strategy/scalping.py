"""Estrategia de scalping por reglas: retroceso a la media en tendencia + ruptura de la vela previa.

Idea (long; el short es espejo):
  1. Tendencia de fondo alcista en la temporalidad superior (precio sobre su EMA y EMA subiendo).
  2. En la temporalidad base, EMA rápida por encima de la lenta (impulso alineado).
  3. Hubo un RETROCESO reciente: en las últimas `pullback_lookback` velas el precio tocó la EMA rápida
     o el RSI cayó por debajo de `rsi_oversold` (nivel de retroceso, 45 por defecto; no es "sobreventa" clásica).
  4. GATILLO: la vela actual cierra por encima de la EMA rápida, rompe el máximo de la vela anterior,
     es alcista con cuerpo decente, el RSI ya volvió por encima del nivel, y el volumen supera su media.
  5. Volatilidad en rango útil y objetivo que cubre las comisiones con margen.
  6. Opcional: precio del lado correcto del VWAP de la sesión.
Salida: TP = tp_atr * ATR, SL = sl_atr * ATR, o salida por tiempo.
"""
from __future__ import annotations

import pandas as pd

from ..config import StrategyConfig
from ..features import add_features
from .base import Signal


class ScalpingStrategy:
    name = "scalping_pullback_v2"

    def __init__(self, cfg: StrategyConfig, trend_interval: str = "15m", round_trip_cost_pct: float = 0.0):
        self.cfg = cfg
        self.trend_interval = trend_interval
        # Costo ida y vuelta (comisiones + slippage) en % del precio. Una señal cuyo objetivo
        # no supera este costo por un margen (min_tp_cost_ratio) se descarta: no vale la pena.
        self.round_trip_cost_pct = round_trip_cost_pct

    def prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        return add_features(df, self.cfg, self.trend_interval)

    @property
    def warmup_bars(self) -> int:
        c = self.cfg
        return max(c.ema_slow, c.atr_period, c.volume_ma, c.rsi_period, c.pullback_lookback) + 5

    def signal_at(self, df: pd.DataFrame, i: int) -> Signal | None:
        """Evalúa la vela i (ya cerrada). Usa solo información hasta i."""
        if i < self.warmup_bars:
            return None
        row = df.iloc[i]
        prev = df.iloc[i - 1]
        c = self.cfg
        needed = ["ema_fast", "ema_slow", "rsi", "atr", "vol_ratio", "trend_ema", "vwap"]
        if any(pd.isna(row[k]) for k in needed):
            return None
        if not (c.atr_min_pct <= row["atr_pct"] <= c.atr_max_pct):
            return None
        if row["vol_ratio"] < c.volume_min_ratio:
            return None
        tp_pct = c.tp_atr * row["atr_pct"]
        if self.round_trip_cost_pct > 0 and tp_pct < c.min_tp_cost_ratio * self.round_trip_cost_pct:
            return None  # objetivo demasiado chico frente a comisiones

        recent = df.iloc[i - c.pullback_lookback: i]  # velas previas, sin incluir la actual
        reasons: list[str] = []
        direction = 0
        if row["trend_dir"] == 1 and row["ema_fast"] > row["ema_slow"]:
            pulled_back = bool((recent["rsi"] < c.rsi_oversold).any() or (recent["low"] <= recent["ema_fast"]).any())
            trigger = (row["close"] > row["ema_fast"] and row["close"] > prev["high"]
                       and row["body"] > 0 and row["body_ratio"] >= c.min_body_ratio and row["rsi"] >= c.rsi_oversold)
            vwap_ok = (not c.use_vwap_filter) or row["close"] > row["vwap"]
            if pulled_back and trigger and vwap_ok:
                direction = 1
                reasons = [f"tendencia {self.trend_interval} alcista", "EMA rápida>lenta",
                           f"retroceso reciente (RSI<{c.rsi_oversold:g} o toque de EMA)",
                           "cierre sobre EMA rápida y máximo previo", f"volumen {row['vol_ratio']:.1f}x"]
        elif row["trend_dir"] == -1 and row["ema_fast"] < row["ema_slow"]:
            pulled_back = bool((recent["rsi"] > c.rsi_overbought).any() or (recent["high"] >= recent["ema_fast"]).any())
            trigger = (row["close"] < row["ema_fast"] and row["close"] < prev["low"]
                       and row["body"] < 0 and row["body_ratio"] >= c.min_body_ratio and row["rsi"] <= c.rsi_overbought)
            vwap_ok = (not c.use_vwap_filter) or row["close"] < row["vwap"]
            if pulled_back and trigger and vwap_ok:
                direction = -1
                reasons = [f"tendencia {self.trend_interval} bajista", "EMA rápida<lenta",
                           f"rebote reciente (RSI>{c.rsi_overbought:g} o toque de EMA)",
                           "cierre bajo EMA rápida y mínimo previo", f"volumen {row['vol_ratio']:.1f}x"]
        if direction == 0:
            return None

        price = float(row["close"])
        a = float(row["atr"])
        sl = price - direction * c.sl_atr * a
        tp = price + direction * c.tp_atr * a
        feats = {k: (None if pd.isna(row[k]) else round(float(row[k]), 6))
                 for k in ["rsi", "atr_pct", "vol_ratio", "body_ratio", "ret_5", "trend_slope"]}
        feats["dist_vwap_pct"] = round((price - float(row["vwap"])) / price * 100.0, 4)
        feats["dist_ema_fast_pct"] = round((price - float(row["ema_fast"])) / price * 100.0, 4)
        feats["hour_utc"] = int(df.index[i].hour)
        return Signal(time=df.index[i], direction=direction, price=price, stop_loss=sl,
                      take_profit=tp, atr=a, reasons=reasons, features=feats)
