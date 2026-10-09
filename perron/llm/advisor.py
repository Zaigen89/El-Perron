"""Asesor LLM: recibe cada señal de las reglas y decide aprobar / omitir / ajustar.

Usa el SDK oficial de Anthropic con salida estructurada (JSON validado por esquema) y
fallback de refusals del lado del servidor. Las decisiones se cachean por contexto
para que repetir un backtest no vuelva a pagar las mismas llamadas.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pandas as pd

from ..config import Config
from ..journal import Journal
from ..strategy.base import Signal
from .memory import Memory
from .prompts import ADVISOR_SCHEMA, ADVISOR_SYSTEM, build_advisor_user_prompt

FALLBACK_BETA = "server-side-fallback-2026-07-01"


class ClaudeClient:
    """Envoltorio mínimo sobre el SDK para obtener JSON validado contra un esquema."""

    def __init__(self, model: str, effort: str = "low"):
        import anthropic  # import tardío para que el resto del proyecto no lo necesite
        self._anthropic = anthropic
        self.client = anthropic.Anthropic()
        self.model = model
        self.effort = effort
        self.calls = 0
        self.input_tokens = 0
        self.output_tokens = 0

    def json(self, system: str, user: str, schema: dict, max_tokens: int = 2048) -> dict[str, Any]:
        resp = self.client.beta.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
            output_config={"effort": self.effort, "format": {"type": "json_schema", "schema": schema}},
            betas=[FALLBACK_BETA],
            fallbacks="default",
        )
        self.calls += 1
        self.input_tokens += getattr(resp.usage, "input_tokens", 0) or 0
        self.output_tokens += getattr(resp.usage, "output_tokens", 0) or 0
        if resp.stop_reason == "refusal":
            raise RuntimeError(f"El modelo rechazó la solicitud: {getattr(resp, 'stop_details', None)}")
        if resp.stop_reason == "max_tokens":
            raise RuntimeError("Respuesta truncada por max_tokens")
        text = next(b.text for b in resp.content if b.type == "text")
        return json.loads(text)


class ClaudeAdvisor:
    def __init__(self, cfg: Config, client: Any | None = None, memory: Memory | None = None):
        self.cfg = cfg
        self.llm = cfg.llm
        self.client = client or ClaudeClient(cfg.llm.model, cfg.llm.effort)
        self.memory = memory or Memory(cfg.llm.knowledge_dir, cfg.llm.memory_dir)
        self.cache_path = Path(cfg.llm.memory_dir) / "llm_cache.json"
        self._cache: dict[str, dict] = {}
        if cfg.llm.cache and self.cache_path.exists():
            self._cache = json.loads(self.cache_path.read_text(encoding="utf-8"))
        self.calls = 0
        self.budget_exhausted = False
        self.errors = 0
        # El conocimiento y las lecciones se leen una vez por corrida (estables -> cacheables)
        self._knowledge = self.memory.knowledge()
        self._lessons = self.memory.lessons()

    def _save_cache(self) -> None:
        if self.llm.cache:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(json.dumps(self._cache, ensure_ascii=False), encoding="utf-8")

    def __call__(self, sig: Signal, df: pd.DataFrame, journal: Journal, equity: float) -> dict:
        user = build_advisor_user_prompt(sig, df, journal, equity, self._knowledge, self._lessons,
                                         self.llm.context_bars)
        key = hashlib.sha256((self.llm.model + ADVISOR_SYSTEM + user).encode("utf-8")).hexdigest()
        if key in self._cache:
            return dict(self._cache[key], cached=True)
        if self.calls >= self.llm.max_calls_per_run:
            self.budget_exhausted = True
            return {"decision": "approve", "size_multiplier": 1.0, "sl_multiplier": 1.0, "tp_multiplier": 1.0,
                    "confidence": 0.0, "reasoning": "presupuesto de llamadas agotado; se aplican solo las reglas"}
        try:
            out = self.client.json(ADVISOR_SYSTEM, user, ADVISOR_SCHEMA, max_tokens=1024)
        except Exception as exc:  # cualquier fallo del LLM -> seguimos solo con reglas
            self.errors += 1
            return {"decision": "approve", "size_multiplier": 1.0, "sl_multiplier": 1.0, "tp_multiplier": 1.0,
                    "confidence": 0.0, "reasoning": f"error del asesor, se aplican solo las reglas: {exc}"[:300]}
        self.calls += 1
        out = {k: out.get(k) for k in ADVISOR_SCHEMA["properties"]}
        self._cache[key] = out
        if self.calls % 10 == 0:
            self._save_cache()
        return dict(out)

    def close(self) -> None:
        self._save_cache()


def build_advisor(cfg: Config, enabled: bool) -> ClaudeAdvisor | None:
    if not enabled:
        return None
    return ClaudeAdvisor(cfg)
