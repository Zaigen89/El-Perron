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
    rr_series = (t["reward_amt"] / t["risk_amt"]).dropna()
    # Sin objetivo fijo (stop móvil): usamos el ratio ganancia media / pérdida media observado
    if len(rr_series):
        rr = float(rr_series.median())
    else:
        wins, losses = t.loc[t["gross"] > 0, "gross"], t.loc[t["gross"] <= 0, "gross"]
        rr = float(wins.mean() / abs(losses.mean())) if len(wins) and len(losses) and losses.mean() != 0 else 1.0
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
        if self.cfg.name == "value_pullback_v3":
            stop_dist = max(self.cfg.min_stop_atr, 1.0) * a * 1.3  # ~ stop estructural típico
            tp_dist = self.cfg.rr * stop_dist
        elif self.cfg.name == "trend_follow_v4":
            stop_dist, tp_dist = self.cfg.initial_stop_atr * a, None
        else:
            stop_dist, tp_dist = self.cfg.sl_atr * a, self.cfg.tp_atr * a
        return Signal(time=df.index[i], direction=d, price=price, stop_loss=price - d * stop_dist,
                      take_profit=None if tp_dist is None else price + d * tp_dist, atr=a,
                      reasons=["aleatorio"], features={})

    def trail_stop(self, df, i, direction, entry_price, current_stop):
        if hasattr(self.base, "trail_stop"):
            return self.base.trail_stop(df, i, direction, entry_price, current_stop)
        return None

    def should_exit(self, df, i, direction, entry_price):
        if hasattr(self.base, "should_exit"):
            return self.base.should_exit(df, i, direction, entry_price)
        return False


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


def yearly(trades: pd.DataFrame, df: pd.DataFrame, initial_capital: float) -> str:
    """Rendimiento por año de la estrategia contra comprar y mantener, con drawdown de cada uno."""
    t = trades.sort_values("exit_time").copy()
    t["year"] = t["exit_time"].dt.year
    g = t.groupby("year")["pnl"].agg(n="count", pnl="sum", win_rate=lambda s: (s > 0).mean() * 100).round(1)
    eq = initial_capital + t.set_index("exit_time")["pnl"].cumsum()
    rows = []
    for y in g.index:
        yr = df.loc[str(y), "close"]
        bh = (yr.iloc[-1] / yr.iloc[0] - 1) * 100
        bh_dd = ((yr / yr.cummax()) - 1).min() * 100
        e = eq.loc[str(y)]
        start = eq.loc[: f"{y - 1}-12-31"].iloc[-1] if len(eq.loc[: f"{y - 1}-12-31"]) else initial_capital
        strat = (e.iloc[-1] / start - 1) * 100 if len(e) else 0.0
        e_full = pd.concat([pd.Series([start], index=[pd.Timestamp(f"{y}-01-01", tz="UTC")]), e])
        s_dd = ((e_full / e_full.cummax()) - 1).min() * 100
        rows.append({"year": y, "n": int(g.loc[y, "n"]), "win%": g.loc[y, "win_rate"], "estrategia%": round(strat, 1),
                     "dd_estrategia%": round(s_dd, 1), "buy_hold%": round(bh, 1), "dd_buy_hold%": round(bh_dd, 1)})
    out = pd.DataFrame(rows).set_index("year")
    total_bh = (df["close"].iloc[-1] / df["close"].iloc[0] - 1) * 100
    total_bh_dd = ((df["close"] / df["close"].cummax()) - 1).min() * 100
    total_s = (eq.iloc[-1] / initial_capital - 1) * 100
    total_s_dd = ((eq / eq.cummax()) - 1).min() * 100
    lines = ["=== Por año: estrategia vs comprar y mantener ===", out.to_string(),
             f"\nTotal: estrategia {total_s:+.1f}% (dd {total_s_dd:.1f}%) | buy&hold {total_bh:+.1f}% (dd {total_bh_dd:.1f}%)",
             f"Retorno/drawdown: estrategia {abs(total_s / total_s_dd) if total_s_dd else 0:.1f}x | buy&hold {abs(total_bh / total_bh_dd) if total_bh_dd else 0:.1f}x",
             "Nota: el retorno de la estrategia escala con risk_per_trade_pct; compara retorno/drawdown, no retorno bruto."]
    return "\n".join(lines)
