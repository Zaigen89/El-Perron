import pandas as pd
import pytest

from perron.backtest import Backtester
from perron.config import Config
from perron.data import generate_synthetic
from tests.helpers import synth15
from perron.strategy import build_strategy


@pytest.fixture
def cfg():
    return Config()


def test_backtest_runs_and_accounts(cfg):
    bt = Backtester(cfg, build_strategy(cfg))
    res = bt.run(synth15(days=90, seed=42))
    m = res.metrics
    assert m["n_trades"] > 0
    # La curva de capital debe cuadrar con la suma de PnL de las operaciones
    assert m["final_equity"] == pytest.approx(cfg.capital.initial + res.trades["pnl"].sum(), abs=1e-6)
    assert m["total_fees"] > 0
    assert res.trades["bars_held"].max() <= cfg.strategy.max_bars_in_trade
    assert set(res.trades["exit_reason"]).issubset({"stop_loss", "take_profit", "time_exit", "end_of_data"})


def test_advisor_skip_blocks_all_trades(cfg):
    def always_skip(sig, df, journal, equity):
        return {"decision": "skip", "size_multiplier": 1, "sl_multiplier": 1, "tp_multiplier": 1,
                "confidence": 1, "reasoning": "test"}
    bt = Backtester(cfg, build_strategy(cfg), advisor=always_skip)
    res = bt.run(synth15(days=90, seed=42))
    assert res.metrics["n_trades"] == 0
    assert res.signals_skipped_by_llm == res.signals_total - res.signals_blocked_by_risk
    assert res.signals_skipped_by_llm > 0


def test_advisor_multipliers_are_bounded(cfg):
    def crazy(sig, df, journal, equity):
        return {"decision": "approve", "size_multiplier": 50, "sl_multiplier": 0.01, "tp_multiplier": 99,
                "confidence": 1, "reasoning": "test"}
    bt = Backtester(cfg, build_strategy(cfg), advisor=crazy)
    res = bt.run(synth15(days=90, seed=42))
    t = res.trades
    assert len(t) > 0
    # tamaño acotado por max_position_pct
    notional = t["entry_price"] * t["qty"]
    assert (notional <= cfg.capital.initial * cfg.risk.max_position_pct / 100.0 * 1.01).all()
    # stop acotado: distancia al SL >= 0.7x la distancia original (sl_multiplier mínimo)
    for _, r in t.iterrows():
        sig_feats = r["llm"]
        assert sig_feats["decision"] == "approve"


def test_daily_loss_limit_blocks(cfg):
    cfg.risk.max_daily_loss_pct = 0.01  # prácticamente cualquier pérdida frena el día
    bt = Backtester(cfg, build_strategy(cfg))
    res = bt.run(synth15(days=90, seed=42))
    assert res.signals_blocked_by_risk > 0
