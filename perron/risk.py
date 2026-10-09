"""Gestión de riesgo: tamaño de posición y límites diarios. Las reglas aquí son límites duros
que el LLM no puede saltarse."""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from .config import RiskConfig


@dataclass
class RiskState:
    day: pd.Timestamp | None = None
    daily_pnl: float = 0.0
    trades_today: int = 0
    cooldown_until_bar: int = -1
    halted_days: set = field(default_factory=set)


class RiskManager:
    def __init__(self, cfg: RiskConfig):
        self.cfg = cfg
        self.state = RiskState()

    def _roll_day(self, t: pd.Timestamp) -> None:
        day = t.floor("D")
        if self.state.day != day:
            self.state.day = day
            self.state.daily_pnl = 0.0
            self.state.trades_today = 0

    def can_trade(self, t: pd.Timestamp, bar_index: int, equity: float) -> tuple[bool, str]:
        self._roll_day(t)
        s = self.state
        if s.daily_pnl <= -equity * self.cfg.max_daily_loss_pct / 100.0:
            return False, "límite de pérdida diaria alcanzado"
        if s.trades_today >= self.cfg.max_trades_per_day:
            return False, "máximo de operaciones por día"
        if bar_index < s.cooldown_until_bar:
            return False, "en enfriamiento tras pérdida"
        return True, ""

    def position_size(self, equity: float, price: float, risk_per_unit: float,
                      size_multiplier: float = 1.0) -> float:
        """Unidades de BTC: arriesga risk_per_trade_pct del capital hasta el stop, con tope de notional."""
        if risk_per_unit <= 0:
            return 0.0
        risk_amount = equity * self.cfg.risk_per_trade_pct / 100.0 * size_multiplier
        qty = risk_amount / risk_per_unit
        max_qty = equity * self.cfg.max_position_pct / 100.0 / price
        return max(0.0, min(qty, max_qty))

    def register_entry(self, t: pd.Timestamp) -> None:
        self._roll_day(t)
        self.state.trades_today += 1

    def register_exit(self, t: pd.Timestamp, pnl: float, bar_index: int) -> None:
        self._roll_day(t)
        self.state.daily_pnl += pnl
        if pnl < 0:
            self.state.cooldown_until_bar = bar_index + self.cfg.cooldown_bars_after_loss
