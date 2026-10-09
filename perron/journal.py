"""Registro de operaciones (journal). Es la fuente de verdad para métricas y para que el LLM aprenda."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

import pandas as pd


@dataclass
class Trade:
    entry_time: str
    exit_time: str | None
    side: str
    entry_price: float
    exit_price: float | None
    qty: float
    stop_loss: float
    take_profit: float
    pnl: float | None
    pnl_pct: float | None
    fees: float
    exit_reason: str | None
    bars_held: int
    reasons: list[str] = field(default_factory=list)
    features: dict = field(default_factory=dict)
    llm: dict | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class Journal:
    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else None
        self.trades: list[Trade] = []
        if self.path and self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    self.trades.append(Trade(**json.loads(line)))

    def add(self, trade: Trade) -> None:
        self.trades.append(trade)
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(trade.to_dict(), ensure_ascii=False) + "\n")

    def to_frame(self) -> pd.DataFrame:
        if not self.trades:
            return pd.DataFrame()
        df = pd.DataFrame([t.to_dict() for t in self.trades])
        df["entry_time"] = pd.to_datetime(df["entry_time"], utc=True)
        df["exit_time"] = pd.to_datetime(df["exit_time"], utc=True)
        return df

    def recent(self, n: int = 10) -> list[Trade]:
        return self.trades[-n:]
