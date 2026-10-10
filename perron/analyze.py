"""Análisis del journal: ¿las reglas tienen ventaja real o es ruido más comisiones?

- Bruto vs comisiones y cuánto pesa la comisión frente al stop.
- Win rate de equilibrio dado el ratio objetivo/stop y las comisiones.
- Benchmark aleatorio: entradas al azar con las mismas salidas. Si las reglas no lo superan, no hay ventaja.
- Desglose por hora UTC, lado, volumen, volatilidad, distancia al VWAP y duración.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .backtest import Backtester
from .config import Config
from .strategy.base import Signal


def _bucket_table(t: pd.DataFrame, col: str, bins, labels=None) -> pd.DataFrame:
    g = pd.cut(t[col], bins=bins, labels=labels, include_lowest=True)
    out = t.groupby(g, observed=True)["pnl"].agg(n="count", pnl="sum", win_rate=lambda s: (s > 0).mean() * 100,
                                                  avg=lambda s: s.mean())
    return out.round(2)


def summary(trades: pd.DataFrame, cfg: Config) -> str:
    t = trades.copy()
    t["gross"] = t["pnl"] + t["fees"]
    t["risk_amt"] = (t["entry_price"] - t["stop_loss"]).abs() * t["qty"]
    t["reward_amt"] = (t["take_profit"] - t["entry_price"]).abs() * t["qty"]
    fee_over_stop = float((t["fees"] / t["risk_amt"]).median())
    rr = float((t["reward_amt"] / t["risk_amt"]).median())
    win = float((t["pnl"] > 0).mean())
    win_gross = float((t["gross"] > 0).mean())
    # Esperanza en unidades de stop: p*RR - (1-p) - fee_over_stop = 0  ->  p = (1 + f) / (1 + RR)
    breakeven = (1.0 + fee_over_stop) / (1.0 + rr)
    breakeven_nofee = 1.0 / (1.0 + rr)
    lines = ["=== ¿Hay ventaja o es ruido + comisiones? ===",
             f"{'Operaciones':34} {len(t)}",
             f"{'PnL bruto (sin comisiones)':34} {t['gross'].sum():.2f}",
             f"{'Comisiones':34} {t['fees'].sum():.2f}",
             f"{'PnL neto':34} {t['pnl'].sum():.2f}",
             f"{'Ratio objetivo/stop (mediana)':34} {rr:.2f}",
             f"{'Comisión / stop (mediana)':34} {fee_over_stop:.2f}  <- fracción del riesgo que se va en comisiones",
             f"{'Win rate neto':34} {win * 100:.1f}%",
             f"{'Win rate bruto':34} {win_gross * 100:.1f}%",
             f"{'Win rate de equilibrio sin fees':34} {breakeven_nofee * 100:.1f}%",
             f"{'Win rate de equilibrio con fees':34} {breakeven * 100:.1f}%  <- lo que necesita la estrategia para empatar",
             ""]
    if win_gross <= breakeven_nofee + 0.02:
        lines.append("Lectura: incluso sin comisiones el win rate está en el nivel del azar para este ratio. "
                     "Las reglas de entrada no están prediciendo nada en esta muestra.")
    elif win < breakeven:
        lines.append("Lectura: las entradas tienen algo de ventaja bruta pero las comisiones la borran. "
                     "Hay que agrandar stop/objetivo respecto al costo o bajar comisiones.")
    else:
        lines.append("Lectura: expectativa positiva neta. Validar en otro periodo antes de creerlo.")
    return "\n".join(lines)


def breakdown(trades: pd.DataFrame) -> str:
    t = trades.copy()
    feats = pd.json_normalize(t["features"])
    for c in feats.columns:
        t[c] = feats[c].to_numpy()
    if "hour_utc" not in t.columns:
        t["hour_utc"] = t["entry_time"].dt.hour
    out = ["=== Desglose (n, pnl, win rate %, promedio) ==="]

    def section(title, table):
        out.append(f"\n-- {title}")
        out.append(table.to_string())

    section("por lado", t.groupby("side")["pnl"].agg(n="count", pnl="sum", win_rate=lambda s: (s > 0).mean() * 100,
                                                      avg="mean").round(2))
    section("por motivo de salida", t.groupby("exit_reason")["pnl"].agg(n="count", pnl="sum", avg="mean").round(2))
    hours = t.groupby(t["hour_utc"].astype(int))["pnl"].agg(n="count", pnl="sum", win_rate=lambda s: (s > 0).mean() * 100).round(1)
    section("por hora UTC", hours)
    # Bloques de sesión
    blocks = pd.cut(t["hour_utc"].astype(int), bins=[-1, 6, 12, 16, 20, 23],
                    labels=["Asia 00-06", "Europa 07-12", "EEUU apertura 13-16", "EEUU tarde 17-20", "Noche 21-23"])
    section("por sesión", t.groupby(blocks, observed=True)["pnl"].agg(n="count", pnl="sum", win_rate=lambda s: (s > 0).mean() * 100).round(1))
    if "vol_ratio" in t.columns:
        section("por volumen relativo (vol_ratio)", _bucket_table(t, "vol_ratio", [0, 1.5, 2.0, 3.0, 100],
                                                                    ["1.2-1.5", "1.5-2", "2-3", ">3"]))
    if "atr_pct" in t.columns:
        q = t["atr_pct"].quantile([0, .25, .5, .75, 1]).to_numpy()
        section("por volatilidad (ATR% cuartiles)", _bucket_table(t, "atr_pct", np.unique(q)))
    if "dist_vwap_pct" in t.columns:
        section("por distancia al VWAP (% abs)", _bucket_table(t["dist_vwap_pct"].abs().to_frame().join(t["pnl"]),
                                                             "dist_vwap_pct", [0, 0.1, 0.25, 0.5, 100],
                                                             ["<0.1", "0.1-0.25", "0.25-0.5", ">0.5"]))
    if "body_ratio" in t.columns:
        section("por cuerpo de la vela gatillo", _bucket_table(t, "body_ratio", [0, 0.5, 0.7, 1.0], ["0.4-0.5", "0.5-0.7", ">0.7"]))
    section("por duración (velas)", _bucket_table(t, "bars_held", [0, 1, 3, 6, 100], ["1", "2-3", "4-6", ">6"]))
    return "\n".join(out)


class RandomStrategy:
    """Entra al azar con la misma frecuencia y las mismas salidas que la estrategia real. Es el 'placebo'."""
    name = "random_benchmark"

    def __init__(self, base, prob: float, seed: int):
        self.base = base
        self.cfg = base.cfg
        self.prob = prob
        self.rng = np.random.default_rng(seed)
        self.warmup_bars = base.warmup_bars

    def prepare(self, df):
        return self.base.prepare(df)

    def signal_at(self, df, i):
        if i < self.warmup_bars or self.rng.random() > self.prob:
            return None
        row = df.iloc[i]
        if pd.isna(row["atr"]) or not (self.cfg.atr_min_pct <= row["atr_pct"] <= self.cfg.atr_max_pct):
            return None
        d = int(row["trend_dir"]) or int(self.rng.choice([-1, 1]))
        price, a = float(row["close"]), float(row["atr"])
        return Signal(time=df.index[i], direction=d, price=price, stop_loss=price - d * self.cfg.sl_atr * a,
                      take_profit=price + d * self.cfg.tp_atr * a, atr=a, reasons=["aleatorio"], features={})


def random_benchmark(cfg: Config, strategy, df: pd.DataFrame, n_trades_real: int, seeds: int = 10) -> str:
    prob = n_trades_real / max(len(df), 1) * 1.3  # un poco más para compensar velas ocupadas
    rows = []
    for s in range(seeds):
        res = Backtester(cfg, RandomStrategy(strategy, prob, seed=s)).run(df)
        m = res.metrics
        rows.append({"seed": s, "n": m["n_trades"], "pnl": m.get("net_pnl", 0.0), "win_rate": m.get("win_rate_pct", 0.0),
                     "pf": m.get("profit_factor", 0.0), "expect": m.get("expectancy", 0.0)})
    r = pd.DataFrame(rows)
    lines = [f"=== Benchmark aleatorio ({seeds} corridas, mismas salidas, entradas al azar en la dirección de la tendencia) ===",
             f"{'PnL neto promedio':34} {r['pnl'].mean():.2f}  (rango {r['pnl'].min():.0f} a {r['pnl'].max():.0f})",
             f"{'Win rate promedio':34} {r['win_rate'].mean():.1f}%",
             f"{'Profit factor promedio':34} {r['pf'].replace(np.inf, np.nan).mean():.2f}",
             f"{'Expectativa por operación':34} {r['expect'].mean():.2f}",
             "",
             "Si la estrategia real no supera claramente estos números, sus reglas de entrada no aportan ventaja."]
    return "\n".join(lines)
