"""Backtester vela a vela con comisiones, slippage, SL/TP intra-vela y salida por tiempo.

Convenciones (conservadoras):
  - La señal se evalúa al cierre de la vela i y se entra en la APERTURA de la vela i+1.
  - Dentro de una vela, si el precio toca SL y TP a la vez, se asume que tocó primero el SL.
  - Comisión y slippage se aplican en ambos lados.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import pandas as pd

from ..config import Config
from ..journal import Journal, Trade
from ..risk import RiskManager
from ..strategy.base import Signal, Strategy
from .metrics import compute_metrics

# Un "advisor" recibe (signal, df_hasta_la_señal, journal, equity) y devuelve una decisión
Decision = dict
Advisor = Callable[[Signal, pd.DataFrame, Journal, float], Decision]


@dataclass
class OpenPosition:
    signal: Signal
    entry_index: int
    entry_time: pd.Timestamp
    entry_price: float
    qty: float
    stop_loss: float
    take_profit: float | None
    entry_fee: float
    decision: dict | None


@dataclass
class BacktestResult:
    metrics: dict
    trades: pd.DataFrame
    equity_curve: pd.Series
    signals_total: int
    signals_skipped_by_llm: int
    signals_blocked_by_risk: int


class Backtester:
    def __init__(self, cfg: Config, strategy: Strategy, advisor: Advisor | None = None,
                 journal: Journal | None = None, verbose: bool = False):
        self.cfg = cfg
        self.strategy = strategy
        self.advisor = advisor
        self.journal = journal or Journal()
        self.verbose = verbose

    def _apply_decision(self, sig: Signal, decision: dict | None) -> tuple[float, float, float]:
        """Devuelve (size_multiplier, stop_loss, take_profit) acotados por la config."""
        if not decision:
            return 1.0, sig.stop_loss, sig.take_profit
        b = self.cfg.llm
        size = min(max(float(decision.get("size_multiplier", 1.0)), b.size_multiplier_bounds[0]), b.size_multiplier_bounds[1])
        slm = min(max(float(decision.get("sl_multiplier", 1.0)), b.sl_multiplier_bounds[0]), b.sl_multiplier_bounds[1])
        tpm = min(max(float(decision.get("tp_multiplier", 1.0)), b.tp_multiplier_bounds[0]), b.tp_multiplier_bounds[1])
        sl = sig.price - sig.direction * abs(sig.price - sig.stop_loss) * slm
        tp = None if sig.take_profit is None else sig.price + sig.direction * abs(sig.take_profit - sig.price) * tpm
        return size, sl, tp

    def run(self, raw: pd.DataFrame) -> BacktestResult:
        cfg = self.cfg
        df = self.strategy.prepare(raw)
        fee_frac = cfg.fees.taker_pct / 100.0
        slip_frac = cfg.fees.slippage_pct / 100.0
        risk = RiskManager(cfg.risk)
        equity = cfg.capital.initial
        equity_points: list[tuple[pd.Timestamp, float]] = []
        pos: OpenPosition | None = None
        pending: tuple[Signal, dict | None] | None = None
        n_signals = n_skipped = n_blocked = 0

        opens = df["open"].to_numpy()
        highs = df["high"].to_numpy()
        lows = df["low"].to_numpy()
        closes = df["close"].to_numpy()
        times = df.index

        for i in range(len(df)):
            t = times[i]
            # 1) Ejecutar entrada pendiente en la apertura de esta vela
            if pending is not None and pos is None:
                sig, decision = pending
                pending = None
                size_mult, sl, tp = self._apply_decision(sig, decision)
                fill = opens[i] * (1 + sig.direction * slip_frac)
                qty = risk.position_size(equity, fill, abs(fill - sl), size_mult)
                if qty > 0:
                    fee = fill * qty * fee_frac
                    equity -= fee
                    risk.register_entry(t)
                    pos = OpenPosition(sig, i, t, fill, qty, sl, tp, fee, decision)
                    if self.verbose:
                        print(f"{t} ENTRADA {sig.side} @ {fill:.2f} qty={qty:.5f} sl={sl:.2f} tp={'móvil' if tp is None else f'{tp:.2f}'}")

            # 2) Gestionar posición abierta en esta vela
            if pos is not None and i > pos.entry_index:
                d = pos.signal.direction
                exit_price = None
                reason = None
                hit_sl = lows[i] <= pos.stop_loss if d > 0 else highs[i] >= pos.stop_loss
                has_tp = pos.take_profit is not None and not pd.isna(pos.take_profit)
                hit_tp = has_tp and (highs[i] >= pos.take_profit if d > 0 else lows[i] <= pos.take_profit)
                if hit_sl:
                    exit_price, reason = pos.stop_loss, "stop_loss"
                elif hit_tp:
                    exit_price, reason = pos.take_profit, "take_profit"
                elif hasattr(self.strategy, "should_exit") and self.strategy.should_exit(df, i, d, pos.entry_price):
                    exit_price, reason = closes[i], "signal_exit"
                elif i - pos.entry_index >= cfg.strategy.max_bars_in_trade:
                    exit_price, reason = closes[i], "time_exit"
                elif i == len(df) - 1:
                    exit_price, reason = closes[i], "end_of_data"
                if exit_price is not None:
                    fill = exit_price * (1 - d * slip_frac)
                    fee = fill * pos.qty * fee_frac
                    gross = (fill - pos.entry_price) * pos.qty * d
                    pnl = gross - fee - pos.entry_fee
                    equity += gross - fee
                    risk.register_exit(t, pnl, i)
                    self.journal.add(Trade(
                        entry_time=pos.entry_time.isoformat(), exit_time=t.isoformat(), side=pos.signal.side,
                        entry_price=pos.entry_price, exit_price=fill, qty=pos.qty, stop_loss=pos.signal.stop_loss,
                        take_profit=pos.take_profit if pos.take_profit is not None else float("nan"), pnl=pnl, pnl_pct=pnl / (pos.entry_price * pos.qty) * 100.0,
                        fees=fee + pos.entry_fee, exit_reason=reason, bars_held=i - pos.entry_index,
                        reasons=pos.signal.reasons, features=pos.signal.features, llm=pos.decision))
                    if self.verbose:
                        print(f"{t} SALIDA {reason} @ {fill:.2f} pnl={pnl:.2f} equity={equity:.2f}")
                    pos = None
                elif hasattr(self.strategy, "trail_stop"):
                    # Stop móvil: solo puede acercarse al precio, nunca alejarse. Se actualiza al cierre.
                    new_stop = self.strategy.trail_stop(df, i, d, pos.entry_price, pos.stop_loss)
                    if new_stop is not None and ((d > 0 and new_stop > pos.stop_loss) or (d < 0 and new_stop < pos.stop_loss)):
                        pos.stop_loss = float(new_stop)

            equity_points.append((t, equity))

            # 3) Buscar nueva señal al cierre de esta vela (solo si no hay posición ni pendiente)
            if pos is None and pending is None and i < len(df) - 1:
                sig = self.strategy.signal_at(df, i)
                if sig is None:
                    continue
                n_signals += 1
                ok, why = risk.can_trade(t, i, equity)
                if not ok:
                    n_blocked += 1
                    continue
                decision = None
                if self.advisor is not None:
                    decision = self.advisor(sig, df.iloc[: i + 1], self.journal, equity)
                    if decision and decision.get("decision") == "skip":
                        n_skipped += 1
                        continue
                pending = (sig, decision)

        equity_curve = pd.Series([e for _, e in equity_points], index=[t for t, _ in equity_points], name="equity")
        trades = self.journal.to_frame()
        metrics = compute_metrics(trades, equity_curve, cfg.capital.initial)
        metrics["signals_total"] = n_signals
        metrics["signals_skipped_by_llm"] = n_skipped
        metrics["signals_blocked_by_risk"] = n_blocked
        return BacktestResult(metrics, trades, equity_curve, n_signals, n_skipped, n_blocked)
