import pandas as pd

from perron.config import StrategyConfig
from perron.data import generate_synthetic
from perron.strategy import ScalpingStrategy


def test_signal_geometry():
    cfg = StrategyConfig()
    strat = ScalpingStrategy(cfg)
    df = strat.prepare(generate_synthetic(days=10, seed=42))
    signals = [s for i in range(len(df)) if (s := strat.signal_at(df, i)) is not None]
    assert signals, "la estrategia debería generar al menos una señal en 10 días sintéticos"
    for s in signals:
        if s.direction > 0:
            assert s.stop_loss < s.price < s.take_profit
        else:
            assert s.take_profit < s.price < s.stop_loss
        assert abs(s.take_profit - s.price) / abs(s.price - s.stop_loss) == __import__("pytest").approx(cfg.tp_atr / cfg.sl_atr)
        assert s.reasons


def test_no_signal_in_warmup():
    strat = ScalpingStrategy(StrategyConfig())
    df = strat.prepare(generate_synthetic(days=1, seed=5))
    for i in range(strat.warmup_bars):
        assert strat.signal_at(df, i) is None
