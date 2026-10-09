from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import pandas as pd


@dataclass
class Signal:
    """Señal de entrada producida por las reglas en el cierre de una vela."""
    time: pd.Timestamp
    direction: int            # +1 long, -1 short
    price: float              # cierre de la vela de señal
    stop_loss: float
    take_profit: float
    atr: float
    reasons: list[str] = field(default_factory=list)
    features: dict = field(default_factory=dict)

    @property
    def side(self) -> str:
        return "long" if self.direction > 0 else "short"

    @property
    def risk_per_unit(self) -> float:
        return abs(self.price - self.stop_loss)


class Strategy(Protocol):
    def prepare(self, df: pd.DataFrame) -> pd.DataFrame: ...
    def signal_at(self, df: pd.DataFrame, i: int) -> Signal | None: ...
