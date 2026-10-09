from __future__ import annotations

from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any

import yaml


def _build(cls, raw: dict[str, Any] | None):
    raw = raw or {}
    known = {f.name for f in fields(cls)}
    return cls(**{k: v for k, v in raw.items() if k in known})


@dataclass
class DataConfig:
    base_url: str = "https://api.binance.com"
    dir: str = "data"


@dataclass
class CapitalConfig:
    initial: float = 10_000.0


@dataclass
class FeesConfig:
    taker_pct: float = 0.04
    slippage_pct: float = 0.01

    @property
    def round_trip_fraction(self) -> float:
        """Costo total ida y vuelta como fracción (fees + slippage, dos lados)."""
        return 2 * (self.taker_pct + self.slippage_pct) / 100.0


@dataclass
class StrategyConfig:
    ema_fast: int = 9
    ema_slow: int = 21
    ema_trend: int = 50
    rsi_period: int = 7
    rsi_oversold: float = 35.0
    rsi_overbought: float = 65.0
    atr_period: int = 14
    volume_ma: int = 20
    volume_min_ratio: float = 1.2
    atr_min_pct: float = 0.03
    atr_max_pct: float = 0.40
    tp_atr: float = 1.5
    sl_atr: float = 1.0
    max_bars_in_trade: int = 15
    use_vwap_filter: bool = True


@dataclass
class RiskConfig:
    risk_per_trade_pct: float = 0.5
    max_position_pct: float = 50.0
    max_daily_loss_pct: float = 2.0
    max_trades_per_day: int = 30
    cooldown_bars_after_loss: int = 5


@dataclass
class LLMConfig:
    enabled: bool = False
    model: str = "claude-opus-5-5"
    effort: str = "low"
    max_calls_per_run: int = 200
    context_bars: int = 30
    knowledge_dir: str = "knowledge"
    memory_dir: str = "memory"
    cache: bool = True
    size_multiplier_bounds: list[float] = field(default_factory=lambda: [0.0, 1.5])
    sl_multiplier_bounds: list[float] = field(default_factory=lambda: [0.7, 1.5])
    tp_multiplier_bounds: list[float] = field(default_factory=lambda: [0.7, 2.0])


@dataclass
class PaperConfig:
    poll_seconds: int = 10
    log_dir: str = "memory"


@dataclass
class Config:
    symbol: str = "BTCUSDT"
    interval: str = "1m"
    trend_interval: str = "5m"
    data: DataConfig = field(default_factory=DataConfig)
    capital: CapitalConfig = field(default_factory=CapitalConfig)
    fees: FeesConfig = field(default_factory=FeesConfig)
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    paper: PaperConfig = field(default_factory=PaperConfig)

    @classmethod
    def load(cls, path: str | Path = "config.yaml") -> "Config":
        p = Path(path)
        raw: dict[str, Any] = {}
        if p.exists():
            raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        return cls(
            symbol=raw.get("symbol", "BTCUSDT"),
            interval=raw.get("interval", "1m"),
            trend_interval=raw.get("trend_interval", "5m"),
            data=_build(DataConfig, raw.get("data")),
            capital=_build(CapitalConfig, raw.get("capital")),
            fees=_build(FeesConfig, raw.get("fees")),
            strategy=_build(StrategyConfig, raw.get("strategy")),
            risk=_build(RiskConfig, raw.get("risk")),
            llm=_build(LLMConfig, raw.get("llm")),
            paper=_build(PaperConfig, raw.get("paper")),
        )
