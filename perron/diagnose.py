"""Diagnóstico: ¿los datos tienen suficiente volatilidad para que el scalping pague las comisiones?

Muestra la distribución del ATR en % del precio, el mínimo que exige el filtro de costo,
y el embudo de señales (cuántas pasan cada filtro) para la temporalidad actual y para
otras temporalidades resampleadas de los mismos datos.
"""
from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd

from .config import Config
from .features import add_features, resample_ohlcv
from .strategy import ScalpingStrategy

_RULE = {"1m": "1min", "3m": "3min", "5m": "5min", "15m": "15min", "30m": "30min", "1h": "1h"}
_TREND_FOR = {"1m": "5m", "3m": "15m", "5m": "15m", "15m": "1h", "30m": "2h", "1h": "4h"}
_MINUTES = {"1m": 1, "3m": 3, "5m": 5, "15m": 15, "30m": 30, "1h": 60}


def _funnel(df: pd.DataFrame, cfg: Config, trend_interval: str, cost_pct: float) -> dict:
    c = cfg.strategy
    feats = add_features(df, c, trend_interval)
    valid = feats.dropna(subset=["atr_pct", "vol_ratio", "trend_ema"])
    n = len(valid)
    out: dict = {"velas": len(df)}
    atr = valid["atr_pct"]
    out["atr_pct_p10"] = float(atr.quantile(0.10))
    out["atr_pct_p50"] = float(atr.quantile(0.50))
    out["atr_pct_p90"] = float(atr.quantile(0.90))
    out["atr_min_requerido_por_costo"] = c.min_tp_cost_ratio * cost_pct / c.tp_atr
    out["pct_velas_atr_en_rango"] = float(((atr >= c.atr_min_pct) & (atr <= c.atr_max_pct)).mean() * 100)
    out["pct_velas_atr_cubre_costo"] = float((atr >= out["atr_min_requerido_por_costo"]).mean() * 100)
    out["pct_velas_volumen_ok"] = float((valid["vol_ratio"] >= c.volume_min_ratio).mean() * 100)
    out["pct_velas_con_tendencia"] = float((valid["trend_dir"] != 0).mean() * 100)

    free = ScalpingStrategy(c, trend_interval, round_trip_cost_pct=0.0)
    paid = ScalpingStrategy(c, trend_interval, round_trip_cost_pct=cost_pct)
    n_free = sum(1 for i in range(len(feats)) if free.signal_at(feats, i) is not None)
    n_paid = sum(1 for i in range(len(feats)) if paid.signal_at(feats, i) is not None)
    out["senales_sin_filtro_costo"] = n_free
    out["senales_con_filtro_costo"] = n_paid
    # Sin ningún filtro de ATR: ¿cuántas señales hay por las reglas de precio/volumen solamente?
    loose = ScalpingStrategy(replace(c, atr_min_pct=0.0, atr_max_pct=100.0), trend_interval, 0.0)
    out["senales_sin_filtros_atr"] = sum(1 for i in range(len(feats)) if loose.signal_at(feats, i) is not None)
    return out


def diagnose(df: pd.DataFrame, cfg: Config, intervals: list[str] | None = None) -> str:
    base = cfg.interval
    cost_pct = cfg.fees.round_trip_fraction * 100.0
    intervals = intervals or [base] + [i for i in ["3m", "5m", "15m"] if _MINUTES[i] > _MINUTES[base]]
    days = (df.index[-1] - df.index[0]).total_seconds() / 86400.0
    lines = [f"=== Diagnóstico de {cfg.symbol} | {days:.1f} días | costo ida y vuelta {cost_pct:.3f}% ===",
             f"Filtro de costo: objetivo ({cfg.strategy.tp_atr} ATR) >= {cfg.strategy.min_tp_cost_ratio}x costo "
             f"=> ATR% mínimo {cfg.strategy.min_tp_cost_ratio * cost_pct / cfg.strategy.tp_atr:.3f}%", ""]
    results = {}
    for iv in intervals:
        d = df if iv == base else resample_ohlcv(df, _RULE[iv])
        if len(d) < 300:
            continue
        results[iv] = _funnel(d, cfg, _TREND_FOR[iv], cost_pct)
    header = f"{'':34}" + "".join(f"{iv:>12}" for iv in results)
    lines.append(header)
    rows = [("velas", "velas", "{:.0f}"),
            ("ATR% p10", "atr_pct_p10", "{:.3f}"), ("ATR% mediana", "atr_pct_p50", "{:.3f}"),
            ("ATR% p90", "atr_pct_p90", "{:.3f}"),
            ("% velas ATR en rango config", "pct_velas_atr_en_rango", "{:.1f}"),
            ("% velas ATR cubre costo", "pct_velas_atr_cubre_costo", "{:.1f}"),
            ("% velas volumen ok", "pct_velas_volumen_ok", "{:.1f}"),
            ("% velas con tendencia", "pct_velas_con_tendencia", "{:.1f}"),
            ("señales sin filtros ATR", "senales_sin_filtros_atr", "{:.0f}"),
            ("señales sin filtro costo", "senales_sin_filtro_costo", "{:.0f}"),
            ("señales CON filtro costo", "senales_con_filtro_costo", "{:.0f}")]
    for label, key, fmt in rows:
        lines.append(f"{label:34}" + "".join(f"{fmt.format(results[iv][key]):>12}" for iv in results))
    lines.append("")
    best = max(results, key=lambda k: results[k]["senales_con_filtro_costo"])
    n_best = results[best]["senales_con_filtro_costo"]
    if n_best == 0:
        lines.append("Conclusión: con estas comisiones ninguna temporalidad genera señales rentables. Opciones:\n"
                     "  - bajar fees.taker_pct (0.02 maker) y fees.slippage_pct en config.yaml si tu exchange lo permite\n"
                     "  - subir strategy.tp_atr (2.0-2.5) o bajar strategy.min_tp_cost_ratio (1.5)\n"
                     "  - usar una temporalidad mayor (interval: 15m)")
    else:
        lines.append(f"Conclusión: la temporalidad con más señales viables es {best} ({n_best} en {days:.0f} días, "
                     f"~{n_best / max(days, 1):.1f} por día).")
        if best != base:
            lines.append(f"  Para usarla: en config.yaml pon interval: {best} y trend_interval: {_TREND_FOR[best]}, "
                         f"luego `python -m perron fetch --days 60` y `python -m perron backtest`.")
    return "\n".join(lines)
