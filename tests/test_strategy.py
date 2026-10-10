import pandas as pd

from perron.config import StrategyConfig
from perron.data import generate_synthetic
from tests.helpers import synth5, synth15
from perron.strategy import ScalpingStrategy, ValuePullbackStrategy


def test_signal_geometry():
    cfg = StrategyConfig()
    strat = ScalpingStrategy(cfg, "15m")
    df = strat.prepare(synth5(days=30, seed=42))
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


def test_cost_filter_drops_small_targets():
    cfg = StrategyConfig()
    raw = synth5(days=30, seed=42)
    free = ScalpingStrategy(cfg, round_trip_cost_pct=0.0)
    df = free.prepare(raw)
    n_free = sum(1 for i in range(len(df)) if free.signal_at(df, i) is not None)
    # Costo absurdo: ninguna señal debería pasar
    pricey = ScalpingStrategy(cfg, round_trip_cost_pct=5.0)
    n_pricey = sum(1 for i in range(len(df)) if pricey.signal_at(df, i) is not None)
    assert n_free > 0 and n_pricey == 0
    # Costo realista (0.1%): las que pasan tienen objetivo >= 2x el costo
    real = ScalpingStrategy(cfg, round_trip_cost_pct=0.1)
    for i in range(len(df)):
        s = real.signal_at(df, i)
        if s is not None:
            assert abs(s.take_profit - s.price) / s.price * 100 >= 2.0 * 0.1 - 1e-9



def test_value_pullback_v3_geometry_and_cost():
    cfg = StrategyConfig()
    strat = ValuePullbackStrategy(cfg, "1h", round_trip_cost_pct=0.1)
    df = strat.prepare(synth15(days=90, seed=42))
    signals = [s for i in range(len(df)) if (s := strat.signal_at(df, i)) is not None]
    assert signals, "v3 debería generar señales en 90 días sintéticos de 15m"
    for s in signals:
        stop_dist = abs(s.price - s.stop_loss)
        assert cfg.min_stop_atr * s.atr - 1e-9 <= stop_dist <= cfg.max_stop_atr * s.atr + 1e-9
        assert abs(s.take_profit - s.price) == __import__("pytest").approx(cfg.rr * stop_dist)
        assert abs(s.features["dist_vwap_pct"]) <= cfg.max_dist_vwap_pct
        assert abs(s.take_profit - s.price) / s.price * 100 >= cfg.min_tp_cost_ratio * 0.1 - 1e-9
        if s.direction > 0:
            assert s.stop_loss < s.price < s.take_profit
        else:
            assert s.take_profit < s.price < s.stop_loss
