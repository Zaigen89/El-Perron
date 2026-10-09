from __future__ import annotations

import numpy as np
import pandas as pd


def compute_metrics(trades: pd.DataFrame, equity_curve: pd.Series, initial_capital: float,
                    bars_per_day: int = 1440) -> dict:
    m: dict = {"initial_capital": initial_capital, "n_trades": int(len(trades))}
    if equity_curve is None or len(equity_curve) == 0:
        m["final_equity"] = initial_capital
        return m
    final = float(equity_curve.iloc[-1])
    m["final_equity"] = final
    m["net_pnl"] = final - initial_capital
    m["return_pct"] = (final / initial_capital - 1.0) * 100.0
    peak = equity_curve.cummax()
    dd = (equity_curve / peak - 1.0) * 100.0
    m["max_drawdown_pct"] = float(dd.min())
    if len(trades) == 0:
        return m
    pnl = trades["pnl"].astype(float)
    wins = pnl[pnl > 0]
    losses = pnl[pnl <= 0]
    m["win_rate_pct"] = len(wins) / len(pnl) * 100.0
    m["avg_win"] = float(wins.mean()) if len(wins) else 0.0
    m["avg_loss"] = float(losses.mean()) if len(losses) else 0.0
    gross_profit = float(wins.sum())
    gross_loss = float(-losses.sum())
    m["profit_factor"] = gross_profit / gross_loss if gross_loss > 0 else float("inf")
    m["expectancy"] = float(pnl.mean())
    m["total_fees"] = float(trades["fees"].sum())
    m["avg_bars_held"] = float(trades["bars_held"].mean())
    # Sharpe diario a partir de la curva de capital muestreada por día
    daily = equity_curve.resample("1D").last().dropna().pct_change().dropna()
    if len(daily) > 1 and daily.std() > 0:
        m["sharpe_daily_annualized"] = float(daily.mean() / daily.std() * np.sqrt(365))
    else:
        m["sharpe_daily_annualized"] = 0.0
    by_reason = trades.groupby("exit_reason")["pnl"].agg(["count", "sum"])
    m["by_exit_reason"] = {k: {"count": int(v["count"]), "pnl": float(v["sum"])} for k, v in by_reason.iterrows()}
    by_side = trades.groupby("side")["pnl"].agg(["count", "sum"])
    m["by_side"] = {k: {"count": int(v["count"]), "pnl": float(v["sum"])} for k, v in by_side.iterrows()}
    return m


def format_metrics(m: dict) -> str:
    lines = ["=== Resultados ==="]
    def row(label, key, fmt="{:.2f}"):
        if key in m:
            v = m[key]
            lines.append(f"{label:<28} {fmt.format(v) if isinstance(v, (int, float)) else v}")
    row("Capital inicial", "initial_capital")
    row("Capital final", "final_equity")
    row("PnL neto", "net_pnl")
    row("Retorno %", "return_pct")
    row("Drawdown máximo %", "max_drawdown_pct")
    row("Operaciones", "n_trades", "{}")
    row("Win rate %", "win_rate_pct")
    row("Ganancia promedio", "avg_win")
    row("Pérdida promedio", "avg_loss")
    row("Profit factor", "profit_factor")
    row("Expectativa por operación", "expectancy")
    row("Comisiones totales", "total_fees")
    row("Velas promedio en posición", "avg_bars_held")
    row("Sharpe (diario, anualizado)", "sharpe_daily_annualized")
    for group in ("by_exit_reason", "by_side"):
        if group in m:
            lines.append(f"-- {group.replace('by_', 'por ')}")
            for k, v in m[group].items():
                lines.append(f"   {k:<12} n={v['count']:<4} pnl={v['pnl']:.2f}")
    return "\n".join(lines)
