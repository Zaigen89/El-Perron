"""Pruebas del asesor y revisor con un cliente falso (sin llamadas reales a la API)."""
import json

from perron.backtest import Backtester
from perron.config import Config
from perron.data import generate_synthetic
from perron.llm.advisor import ClaudeAdvisor
from perron.llm.memory import Memory
from perron.llm.prompts import ADVISOR_SCHEMA, REVIEWER_SCHEMA
from perron.llm.reviewer import apply_proposals, review
from perron.strategy import ScalpingStrategy


class FakeClient:
    def __init__(self, answer):
        self.answer = answer
        self.calls = 0
        self.last_user = None

    def json(self, system, user, schema, max_tokens=1024):
        self.calls += 1
        self.last_user = user
        assert schema in (ADVISOR_SCHEMA, REVIEWER_SCHEMA)
        return json.loads(json.dumps(self.answer))


def _cfg(tmp_path):
    cfg = Config()
    cfg.llm.knowledge_dir = str(tmp_path / "knowledge")
    cfg.llm.memory_dir = str(tmp_path / "memory")
    (tmp_path / "knowledge").mkdir()
    (tmp_path / "knowledge" / "01_ideas.md").write_text("Nunca operar contra la tendencia de 5m.", encoding="utf-8")
    return cfg


def test_advisor_uses_knowledge_and_caches(tmp_path):
    cfg = _cfg(tmp_path)
    fake = FakeClient({"decision": "reduce", "size_multiplier": 0.5, "sl_multiplier": 1.0,
                       "tp_multiplier": 1.2, "confidence": 0.6, "reasoning": "ok"})
    advisor = ClaudeAdvisor(cfg, client=fake)
    bt = Backtester(cfg, ScalpingStrategy(cfg.strategy, cfg.trend_interval, cfg.fees.round_trip_fraction * 100), advisor=advisor)
    res = bt.run(generate_synthetic(days=10, seed=42))
    advisor.close()
    assert fake.calls > 0
    assert "Nunca operar contra la tendencia" in fake.last_user
    assert res.trades["llm"].iloc[0]["decision"] == "reduce"
    # Segunda corrida: todo sale del cache
    fake2 = FakeClient(fake.answer)
    advisor2 = ClaudeAdvisor(cfg, client=fake2)
    Backtester(cfg, ScalpingStrategy(cfg.strategy, cfg.trend_interval, cfg.fees.round_trip_fraction * 100), advisor=advisor2).run(
        generate_synthetic(days=10, seed=42))
    assert fake2.calls == 0


def test_advisor_budget_and_errors_fall_back_to_rules(tmp_path):
    cfg = _cfg(tmp_path)
    cfg.llm.max_calls_per_run = 2
    cfg.llm.cache = False

    class Boom(FakeClient):
        def json(self, *a, **k):
            self.calls += 1
            raise RuntimeError("api caída")

    advisor = ClaudeAdvisor(cfg, client=Boom(None))
    bt = Backtester(cfg, ScalpingStrategy(cfg.strategy, cfg.trend_interval, cfg.fees.round_trip_fraction * 100), advisor=advisor)
    res = bt.run(generate_synthetic(days=10, seed=42))
    assert res.metrics["n_trades"] > 0          # las reglas siguen operando
    assert advisor.errors > 0


def test_review_writes_lessons_and_filters_proposals(tmp_path):
    cfg = _cfg(tmp_path)
    bt = Backtester(cfg, ScalpingStrategy(cfg.strategy, cfg.trend_interval, cfg.fees.round_trip_fraction * 100))
    res = bt.run(generate_synthetic(days=10, seed=42))
    fake = FakeClient({
        "lessons_markdown": "- Evitar entradas con vol_ratio < 1.5",
        "parameter_proposals": [
            {"parameter": "volume_min_ratio", "current": 1.2, "proposed": 1.5, "justification": "mejor"},
            {"parameter": "tp_atr", "current": 1.5, "proposed": 50, "justification": "fuera de rango"},
            {"parameter": "ema_fast", "current": 9, "proposed": 5, "justification": "no ajustable"},
        ],
        "summary": "resumen"})
    out = review(cfg, res.metrics, res.trades, client=fake, memory=Memory(cfg.llm.knowledge_dir, cfg.llm.memory_dir))
    assert [p["parameter"] for p in out["parameter_proposals"]] == ["volume_min_ratio"]
    assert "vol_ratio" in Memory(cfg.llm.knowledge_dir, cfg.llm.memory_dir).lessons()
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text("strategy:\n  volume_min_ratio: 1.2\n", encoding="utf-8")
    changed = apply_proposals(cfg_path, out["parameter_proposals"])
    assert changed == ["volume_min_ratio: 1.2 -> 1.5"]
    assert Config.load(cfg_path).strategy.volume_min_ratio == 1.5
