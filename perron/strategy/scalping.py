"""Estrategia de scalping por reglas: pullback a la media con confirmación de momentum.

Idea (long; el short es espejo):
  1. Tendencia de fondo alcista en 5m (precio sobre EMA50 de 5m y EMA subiendo).
  2. En 1m, EMA rápida por encima de la lenta (impulso corto alineado).
  3. El precio hizo un retroceso: RSI(7) bajó de la zona de sobreventa y acaba de cruzar hacia arriba.
  4. La vela de señal cierra alcista con cuerpo decente y volumen por encima de su media.
  5. Volatilidad en rango útil (ATR ni muerto ni caótico).
  6. Opcional: precio del lado correcto del VWAP de la sesión.
Salida: TP = tp_atr * ATR, SL = sl_atr * ATR, o salida por tiempo.
"""
from __future__ import annotations

import pandas as pd

from ..config import StrategyConfig
from ..features import add_features
from .base import Signal


class ScalpingStrategy:
    name = "scalping_pullback_v1"

    def __init__(self, cfg: StrategyConfig, trend_interval: str = "5m", round_trip_cost_pct: float = 0.0):
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
        return max(c.ema_slow, c.atr_period, c.volume_ma, c.rsi_period) + 5

    def signal_at(self, df: pd.DataFrame, i: int) -> Signal | None:
        """Evalúa la vela i (ya cerrada). Usa solo información hasta i."""
        if i < self.warmup_bars:
            return None
        row = df.iloc[i]
        prev = df.iloc[i - 1]
        c = self.cfg
        needed = ["ema_fast", "ema_slow", "rsi", "atr", "vol_ratio", "trend_ema", "vwap"]
        if any(pd.isna(row[k]) for k in needed) or pd.isna(prev["rsi"]):
            return None
        if not (c.atr_min_pct <= row["atr_pct"] <= c.atr_max_pct):
            return None
        if row["vol_ratio"] < c.volume_min_ratio:
            return None
        tp_pct = c.tp_atr * row["atr_pct"]
        if self.round_trip_cost_pct > 0 and tp_pct < c.min_tp_cost_ratio * self.round_trip_cost_pct:
            return None  # objetivo demasiado chico frente a comisiones

        reasons: list[str] = []
        direction = 0
        if row["trend_dir"] == 1 and row["ema_fast"] > row["ema_slow"]:
            rsi_cross_up = prev["rsi"] < c.rsi_oversold <= row["rsi"]
            bullish = row["body"] > 0 and row["body_ratio"] >= 0.4
            vwap_ok = (not c.use_vwap_filter) or row["close"] > row["vwap"]
            if rsi_cross_up and bullish and vwap_ok:
                direction = 1
                reasons = ["tendencia 5m alcista", "EMA9>EMA21", f"RSI cruzó {c.rsi_oversold} hacia arriba",
                           "vela alcista con cuerpo", f"volumen {row['vol_ratio']:.1f}x"]
        elif row["trend_dir"] == -1 and row["ema_fast"] < row["ema_slow"]:
            rsi_cross_down = prev["rsi"] > c.rsi_overbought >= row["rsi"]
            bearish = row["body"] < 0 and row["body_ratio"] >= 0.4
            vwap_ok = (not c.use_vwap_filter) or row["close"] < row["vwap"]
            if rsi_cross_down and bearish and vwap_ok:
                direction = -1
                reasons = ["tendencia 5m bajista", "EMA9<EMA21", f"RSI cruzó {c.rsi_overbought} hacia abajo",
                           "vela bajista con cuerpo", f"volumen {row['vol_ratio']:.1f}x"]
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
        return Signal(time=df.index[i], direction=direction, price=price, stop_loss=sl,
                      take_profit=tp, atr=a, reasons=reasons, features=feats)
