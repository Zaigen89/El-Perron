"""Estrategia v3: comprar el retroceso a valor dentro de la tendencia (no perseguir rupturas).

Qué aprendimos de la v2 con datos reales: perseguir rupturas con cuerpo grande entra tarde (62% de las
entradas a más de 0.5% del VWAP) y un stop de 1 ATR cae dentro del ruido de una sola vela (45% de las
operaciones murieron en la primera vela). La v3 invierte ambas cosas.

Long (short es espejo):
  1. Tendencia de fondo alcista en la temporalidad superior (precio sobre su EMA y EMA subiendo).
  2. En la temporalidad base el precio RETROCEDIÓ hasta la zona de valor: el mínimo de la vela tocó la
     EMA lenta (o el VWAP) o quedó a menos de `value_touch_pct` de ella.
  3. La vela RECHAZA el nivel: cierra por encima de la EMA lenta y por encima de su apertura.
  4. No está extendido: cierre a menos de `max_dist_vwap_pct` del VWAP y RSI(7) en zona de retroceso
     (entre `rsi_pb_low` y `rsi_pb_high`), no en euforia.
  5. Stop por ESTRUCTURA: debajo del mínimo de las últimas `swing_lookback` velas menos un colchón de ATR,
     acotado entre `min_stop_atr` y `max_stop_atr`. Objetivo = `rr` veces la distancia del stop.
  6. El objetivo debe cubrir las comisiones con margen (min_tp_cost_ratio).
"""
from __future__ import annotations

import pandas as pd

from ..config import StrategyConfig
from ..features import add_features
from .base import Signal


class ValuePullbackStrategy:
    name = "value_pullback_v3"

    def __init__(self, cfg: StrategyConfig, trend_interval: str = "1h", round_trip_cost_pct: float = 0.0):
        self.cfg = cfg
        self.trend_interval = trend_interval
        self.round_trip_cost_pct = round_trip_cost_pct

    def prepare(self, df: pd.DataFrame) -> pd.DataFrame:
        return add_features(df, self.cfg, self.trend_interval)

    @property
    def warmup_bars(self) -> int:
        c = self.cfg
        return max(c.ema_slow, c.atr_period, c.volume_ma, c.rsi_period, c.swing_lookback) + 5

    def signal_at(self, df: pd.DataFrame, i: int) -> Signal | None:
        if i < self.warmup_bars:
            return None
        row = df.iloc[i]
        c = self.cfg
        needed = ["ema_fast", "ema_slow", "rsi", "atr", "vol_ratio", "trend_ema", "vwap"]
        if any(pd.isna(row[k]) for k in needed):
            return None
        if not (c.atr_min_pct <= row["atr_pct"] <= c.atr_max_pct):
            return None
        if row["vol_ratio"] < c.volume_min_ratio:
            return None

        price = float(row["close"])
        a = float(row["atr"])
        ema_s = float(row["ema_slow"])
        vwap = float(row["vwap"])
        tol = price * c.value_touch_pct / 100.0
        dist_vwap_pct = (price - vwap) / price * 100.0
        window = df.iloc[i - c.swing_lookback + 1: i + 1]

        direction = 0
        reasons: list[str] = []
        if row["trend_dir"] == 1:
            touched = row["low"] <= ema_s + tol or row["low"] <= vwap + tol
            rejected = price > ema_s and price > row["open"]
            not_extended = abs(dist_vwap_pct) <= c.max_dist_vwap_pct and c.rsi_pb_low <= row["rsi"] <= c.rsi_pb_high
            if touched and rejected and not_extended:
                direction = 1
                stop = float(window["low"].min()) - c.stop_buffer_atr * a
                reasons = [f"tendencia {self.trend_interval} alcista", "retroceso tocó EMA lenta/VWAP",
                           "vela de rechazo cierra sobre el nivel", f"a {dist_vwap_pct:+.2f}% del VWAP",
                           f"RSI {row['rsi']:.0f} en zona de retroceso"]
        elif row["trend_dir"] == -1:
            touched = row["high"] >= ema_s - tol or row["high"] >= vwap - tol
            rejected = price < ema_s and price < row["open"]
            not_extended = abs(dist_vwap_pct) <= c.max_dist_vwap_pct and (100 - c.rsi_pb_high) <= row["rsi"] <= (100 - c.rsi_pb_low)
            if touched and rejected and not_extended:
                direction = -1
                stop = float(window["high"].max()) + c.stop_buffer_atr * a
                reasons = [f"tendencia {self.trend_interval} bajista", "rebote tocó EMA lenta/VWAP",
                           "vela de rechazo cierra bajo el nivel", f"a {dist_vwap_pct:+.2f}% del VWAP",
                           f"RSI {row['rsi']:.0f} en zona de rebote"]
        if direction == 0:
            return None

        stop_dist = abs(price - stop)
        if stop_dist < c.min_stop_atr * a:
            stop_dist = c.min_stop_atr * a
        if stop_dist > c.max_stop_atr * a:
            return None  # retroceso demasiado profundo: riesgo desproporcionado
        stop = price - direction * stop_dist
        tp = price + direction * c.rr * stop_dist
        tp_pct = c.rr * stop_dist / price * 100.0
        if self.round_trip_cost_pct > 0 and tp_pct < c.min_tp_cost_ratio * self.round_trip_cost_pct:
            return None

        feats = {k: (None if pd.isna(row[k]) else round(float(row[k]), 6))
                 for k in ["rsi", "atr_pct", "vol_ratio", "body_ratio", "ret_5", "trend_slope"]}
        feats["dist_vwap_pct"] = round(dist_vwap_pct, 4)
        feats["dist_ema_fast_pct"] = round((price - float(row["ema_fast"])) / price * 100.0, 4)
        feats["stop_atr"] = round(stop_dist / a, 3)
        feats["hour_utc"] = int(df.index[i].hour)
        return Signal(time=df.index[i], direction=direction, price=price, stop_loss=stop,
                      take_profit=tp, atr=a, reasons=reasons, features=feats)
