"""Prompts del asesor y del revisor. Texto estable primero (se cachea), contexto variable al final."""
from __future__ import annotations

import json

import pandas as pd

from ..journal import Journal
from ..strategy.base import Signal

ADVISOR_SYSTEM = """Eres el asesor de un bot de scalping sobre BTCUSDT que opera en PAPER TRADING (dinero ficticio).
Un motor de reglas ya detectó una señal de entrada. Tu trabajo es decidir si se ejecuta, se omite o se ajusta.

Lo que puedes hacer:
- decision: "approve" (ejecutar), "skip" (omitir), "reduce" (ejecutar con menos tamaño).
- size_multiplier: multiplicador del tamaño de posición (1.0 = tamaño normal). El sistema lo acota a límites duros.
- sl_multiplier / tp_multiplier: ajuste del stop y del objetivo respecto a los calculados por las reglas (1.0 = sin cambio).
- confidence: 0 a 1.
- reasoning: una o dos frases concretas, en español.

Lo que NO puedes hacer: abrir operaciones sin señal, saltarte los límites de riesgo, ni cambiar la dirección.

Criterios: usa el conocimiento de trading provisto, las lecciones aprendidas de operaciones pasadas y el contexto
de mercado reciente. En scalping el costo de comisiones es alto: omite señales mediocres. Sé escéptico con señales
contra la estructura reciente, con volatilidad extrema, tras una racha de pérdidas en condiciones parecidas,
o cuando el movimiento ya se extendió. Responde SOLO con el JSON pedido."""

ADVISOR_SCHEMA = {
    "type": "object",
    "properties": {
        "decision": {"type": "string", "enum": ["approve", "skip", "reduce"]},
        "size_multiplier": {"type": "number"},
        "sl_multiplier": {"type": "number"},
        "tp_multiplier": {"type": "number"},
        "confidence": {"type": "number"},
        "reasoning": {"type": "string"},
    },
    "required": ["decision", "size_multiplier", "sl_multiplier", "tp_multiplier", "confidence", "reasoning"],
    "additionalProperties": False,
}

REVIEWER_SYSTEM = """Eres el revisor de desempeño de un bot de scalping sobre BTCUSDT en paper trading.
Recibes las métricas y el detalle de las operaciones recientes, el conocimiento de trading que el usuario le dio al bot,
las lecciones que ya tenía y los parámetros actuales de la estrategia.

Tu trabajo:
1. Escribir una lista corta de LECCIONES accionables (máximo 12 puntos) que el asesor usará en futuras decisiones.
   Deben basarse en patrones observables en las operaciones (p. ej. "las entradas con vol_ratio < 1.5 pierden en promedio").
   Conserva las lecciones previas que sigan siendo válidas, elimina las que los datos contradigan.
2. Proponer cambios de parámetros SOLO si los datos los justifican, dentro de los rangos permitidos, con una
   justificación de una frase cada uno. Si no hay evidencia suficiente, propón una lista vacía.
3. Ser honesto sobre el tamaño de muestra: con menos de 30 operaciones casi nada es concluyente.
Responde SOLO con el JSON pedido. Escribe en español."""

REVIEWER_SCHEMA = {
    "type": "object",
    "properties": {
        "lessons_markdown": {"type": "string"},
        "parameter_proposals": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "parameter": {"type": "string"},
                    "current": {"type": "number"},
                    "proposed": {"type": "number"},
                    "justification": {"type": "string"},
                },
                "required": ["parameter", "current", "proposed", "justification"],
                "additionalProperties": False,
            },
        },
        "summary": {"type": "string"},
    },
    "required": ["lessons_markdown", "parameter_proposals", "summary"],
    "additionalProperties": False,
}

# Parámetros que el revisor puede proponer cambiar y sus rangos permitidos
TUNABLE_PARAMS = {
    "rsi_oversold": (20, 45), "rsi_overbought": (55, 80), "volume_min_ratio": (1.0, 3.0),
    "atr_min_pct": (0.01, 0.10), "atr_max_pct": (0.15, 1.0), "tp_atr": (0.8, 3.0),
    "sl_atr": (0.5, 2.0), "max_bars_in_trade": (5, 60),
}


def _bars_block(df: pd.DataFrame, n: int) -> str:
    cols = ["open", "high", "low", "close", "volume", "rsi", "atr_pct", "vol_ratio"]
    tail = df[cols].tail(n).copy()
    tail.index = tail.index.strftime("%m-%d %H:%M")
    return tail.round(2).to_string()


def _recent_trades_block(journal: Journal, n: int = 8) -> str:
    rows = []
    for t in journal.recent(n):
        rows.append(f"- {t.entry_time[:16]} {t.side} pnl={t.pnl:.2f} salida={t.exit_reason} "
                    f"vol_ratio={t.features.get('vol_ratio')} rsi={t.features.get('rsi')} "
                    f"atr%={t.features.get('atr_pct')}")
    return "\n".join(rows) if rows else "(sin operaciones previas)"


def build_advisor_user_prompt(sig: Signal, df: pd.DataFrame, journal: Journal, equity: float,
                              knowledge: str, lessons: str, context_bars: int) -> str:
    stats = ""
    if journal.trades:
        pnl = [t.pnl for t in journal.trades if t.pnl is not None]
        wins = sum(1 for p in pnl if p > 0)
        stats = f"Operaciones previas: {len(pnl)}, win rate {wins / len(pnl) * 100:.0f}%, pnl acumulado {sum(pnl):.2f}"
    return f"""## Conocimiento de trading del usuario
{knowledge or '(vacío)'}

## Lecciones aprendidas
{lessons or '(ninguna todavía)'}

## Señal detectada por las reglas
{json.dumps({
    'time': sig.time.isoformat(), 'side': sig.side, 'price': sig.price,
    'stop_loss': round(sig.stop_loss, 2), 'take_profit': round(sig.take_profit, 2),
    'atr': round(sig.atr, 2), 'reasons': sig.reasons, 'features': sig.features,
}, ensure_ascii=False)}

## Estado de la cuenta
Capital: {equity:.2f} USDT. {stats}

## Últimas operaciones
{_recent_trades_block(journal)}

## Últimas {context_bars} velas (1m)
{_bars_block(df, context_bars)}
"""


def build_reviewer_user_prompt(metrics: dict, trades: pd.DataFrame, knowledge: str, lessons: str,
                               params: dict) -> str:
    detail = ""
    if len(trades):
        cols = ["entry_time", "side", "pnl", "exit_reason", "bars_held"]
        t = trades[cols].copy()
        t["entry_time"] = t["entry_time"].dt.strftime("%m-%d %H:%M")
        feats = pd.json_normalize(trades["features"]).round(3)
        t = pd.concat([t.reset_index(drop=True), feats.reset_index(drop=True)], axis=1)
        detail = t.tail(150).round(2).to_string(index=False)
    tunable = {k: {"actual": params.get(k), "rango": list(v)} for k, v in TUNABLE_PARAMS.items()}
    return f"""## Conocimiento de trading del usuario
{knowledge or '(vacío)'}

## Lecciones previas
{lessons or '(ninguna)'}

## Parámetros ajustables y rangos permitidos
{json.dumps(tunable, ensure_ascii=False)}

## Métricas del periodo
{json.dumps({k: v for k, v in metrics.items() if not isinstance(v, dict)}, ensure_ascii=False, default=str)}
Por motivo de salida: {json.dumps(metrics.get('by_exit_reason', {}), ensure_ascii=False)}
Por lado: {json.dumps(metrics.get('by_side', {}), ensure_ascii=False)}

## Operaciones (hasta 150 más recientes)
{detail or '(ninguna)'}
"""
