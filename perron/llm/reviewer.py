"""Revisor: después de una corrida, Claude analiza el journal, reescribe las lecciones
y propone cambios de parámetros dentro de rangos permitidos. Este es el ciclo de mejora."""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from ..config import Config
from .advisor import ClaudeClient
from .memory import Memory
from .prompts import REVIEWER_SCHEMA, REVIEWER_SYSTEM, TUNABLE_PARAMS, build_reviewer_user_prompt


def review(cfg: Config, metrics: dict, trades: pd.DataFrame, client: Any | None = None,
           memory: Memory | None = None) -> dict:
    memory = memory or Memory(cfg.llm.knowledge_dir, cfg.llm.memory_dir)
    client = client or ClaudeClient(cfg.llm.model, effort="high")
    user = build_reviewer_user_prompt(metrics, trades, memory.knowledge(), memory.lessons(), asdict(cfg.strategy))
    out = client.json(REVIEWER_SYSTEM, user, REVIEWER_SCHEMA, max_tokens=4096)
    # Filtrar propuestas fuera de rango o de parámetros desconocidos
    valid = []
    for p in out.get("parameter_proposals", []):
        name = p.get("parameter")
        if name not in TUNABLE_PARAMS:
            continue
        lo, hi = TUNABLE_PARAMS[name]
        if not (lo <= float(p["proposed"]) <= hi):
            continue
        valid.append(p)
    out["parameter_proposals"] = valid
    memory.write_lessons(out["lessons_markdown"])
    proposals_path = Path(cfg.llm.memory_dir) / "proposals.json"
    proposals_path.write_text(json.dumps(valid, ensure_ascii=False, indent=2), encoding="utf-8")
    out["lessons_path"] = str(memory.lessons_path)
    out["proposals_path"] = str(proposals_path)
    return out


def apply_proposals(config_path: str | Path, proposals: list[dict]) -> list[str]:
    """Escribe las propuestas válidas en config.yaml (sección strategy). Devuelve lo cambiado."""
    p = Path(config_path)
    raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    strat = raw.setdefault("strategy", {})
    changed = []
    for prop in proposals:
        name = prop["parameter"]
        if name not in TUNABLE_PARAMS:
            continue
        lo, hi = TUNABLE_PARAMS[name]
        val = float(prop["proposed"])
        if not (lo <= val <= hi):
            continue
        if name in ("max_bars_in_trade", "pullback_lookback"):
            val = int(val)
        old = strat.get(name)
        strat[name] = val
        changed.append(f"{name}: {old} -> {val}")
    p.write_text(yaml.safe_dump(raw, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return changed
