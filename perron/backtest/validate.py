"""Validación honesta: dentro de muestra (IS) vs fuera de muestra (OOS) y barrido de parámetros.

La regla: los parámetros se eligen mirando solo IS. OOS se mira una vez, al final, y es el número que cuenta.
Si IS gana y OOS pierde, el ajuste fue sobreajuste.
"""
from __future__ import annotations

import itertools
from dataclasses import replace

import pandas as pd

from ..config import Config
from .engine import Backtester


def split_df(df: pd.DataFrame, oos_days: float, warmup_bars: int = 0) -> tuple[pd.DataFrame, pd.DataFrame]:
    cut = df.index[-1] - pd.Timedelta(days=oos_days)
    is_df = df.loc[df.index < cut]
    # el OOS arranca un poco antes para calentar indicadores, pero el motor solo opera tras el warmup
    oos_start = max(0, len(is_df) - warmup_bars * 4)
    oos_df = df.iloc[oos_start:]
    return is_df, oos_df


def _compact(m: dict) -> dict:
    return {"n": m.get("n_trades", 0), "pnl": round(m.get("net_pnl", 0.0), 1),
            "win%": round(m.get("win_rate_pct", 0.0), 1), "pf": round(min(m.get("profit_factor", 0.0), 99.0), 2),
            "exp": round(m.get("expectancy", 0.0), 2), "dd%": round(m.get("max_drawdown_pct", 0.0), 1)}


def walk_forward(cfg: Config, strategy_factory, df: pd.DataFrame, oos_days: float) -> dict:
    strat = strategy_factory(cfg)
    is_df, oos_df = split_df(df, oos_days, strat.warmup_bars)
    r_is = Backtester(cfg, strategy_factory(cfg)).run(is_df)
    r_oos = Backtester(cfg, strategy_factory(cfg)).run(oos_df)
    return {"is": _compact(r_is.metrics), "oos": _compact(r_oos.metrics),
            "is_range": (is_df.index[0], is_df.index[-1]), "oos_range": (oos_df.index[0], oos_df.index[-1])}


def format_walk_forward(wf: dict) -> str:
    lines = ["=== Validación dentro (IS) vs fuera de muestra (OOS) ===",
             f"IS : {wf['is_range'][0]:%Y-%m-%d} -> {wf['is_range'][1]:%Y-%m-%d}",
             f"OOS: {wf['oos_range'][0]:%Y-%m-%d} -> {wf['oos_range'][1]:%Y-%m-%d}",
             f"{'':6}{'n':>6}{'pnl':>10}{'win%':>8}{'pf':>7}{'exp':>8}{'dd%':>7}"]
    for k in ("is", "oos"):
        m = wf[k]
        lines.append(f"{k.upper():6}{m['n']:>6}{m['pnl']:>10}{m['win%']:>8}{m['pf']:>7}{m['exp']:>8}{m['dd%']:>7}")
    a, b = wf["is"], wf["oos"]
    if a["exp"] > 0 and b["exp"] > 0:
        lines.append("Lectura: expectativa positiva en ambos tramos. Es la mejor señal posible con esta muestra.")
    elif a["exp"] > 0 and b["exp"] <= 0:
        lines.append("Lectura: gana dentro de muestra y pierde fuera. Olor a sobreajuste o cambio de régimen.")
    elif b["n"] < 20:
        lines.append("Lectura: muy pocas operaciones OOS para concluir algo.")
    else:
        lines.append("Lectura: sin expectativa positiva. No hay ventaja con esta configuración.")
    return "\n".join(lines)


# Rejilla por defecto para value_pullback_v3. Pequeña a propósito: más combinaciones = más sobreajuste.
DEFAULT_GRID = {
    "rr": [1.5, 2.0, 3.0],
    "max_dist_vwap_pct": [0.25, 0.35, 0.6],
    "min_stop_atr": [1.0, 1.5],
    "swing_lookback": [3, 6],
}


def sweep(cfg: Config, strategy_factory, df: pd.DataFrame, oos_days: float,
          grid: dict | None = None, progress=None) -> pd.DataFrame:
    grid = grid or DEFAULT_GRID
    keys = list(grid)
    rows = []
    combos = list(itertools.product(*(grid[k] for k in keys)))
    for idx, values in enumerate(combos):
        params = dict(zip(keys, values))
        c2 = replace(cfg, strategy=replace(cfg.strategy, **params))
        wf = walk_forward(c2, strategy_factory, df, oos_days)
        row = dict(params)
        for k in ("is", "oos"):
            for mk, mv in wf[k].items():
                row[f"{k}_{mk}"] = mv
        rows.append(row)
        if progress:
            progress(idx + 1, len(combos), row)
    out = pd.DataFrame(rows)
    return out.sort_values("is_exp", ascending=False).reset_index(drop=True)


def format_sweep(table: pd.DataFrame, top: int = 12) -> str:
    cols = [c for c in table.columns if not c.startswith(("is_", "oos_"))]
    show = table[cols + ["is_n", "is_pf", "is_exp", "oos_n", "oos_pf", "oos_exp"]].head(top)
    lines = ["=== Barrido de parámetros (ordenado por expectativa IS; mira la columna oos_exp) ===",
             show.to_string(index=False), ""]
    robust = table[(table["is_exp"] > 0) & (table["oos_exp"] > 0) & (table["oos_n"] >= 15)]
    if len(robust):
        lines.append(f"Configuraciones con expectativa positiva en IS y OOS (n OOS >= 15): {len(robust)} de {len(table)}")
        lines.append(robust[cols + ["is_exp", "oos_exp", "oos_n"]].head(5).to_string(index=False))
    else:
        lines.append(f"Ninguna de las {len(table)} combinaciones es positiva en IS y OOS a la vez. "
                     "No hay ventaja robusta en esta rejilla; cambiar la idea, no los números.")
    return "\n".join(lines)
