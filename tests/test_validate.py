from perron.backtest.validate import sweep, walk_forward
from perron.config import Config
from perron.strategy import build_strategy
from tests.helpers import synth15


def test_walk_forward_splits_without_overlap_of_trades():
    cfg = Config()
    df = synth15(days=90, seed=42)
    wf = walk_forward(cfg, build_strategy, df, oos_days=30)
    assert wf["is_range"][1] < wf["oos_range"][1]
    assert wf["is"]["n"] > 0 and wf["oos"]["n"] >= 0


def test_sweep_small_grid():
    cfg = Config()
    df = synth15(days=60, seed=7)
    table = sweep(cfg, build_strategy, df, oos_days=20, grid={"rr": [1.5, 3.0], "min_stop_atr": [1.0]})
    assert len(table) == 2
    assert {"rr", "min_stop_atr", "is_exp", "oos_exp", "oos_n"} <= set(table.columns)
