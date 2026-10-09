"""Paper trading en vivo: consulta velas de Binance, evalúa reglas (+ LLM) y simula ejecución.

- Opera solo sobre velas CERRADAS (la última vela de la API está abierta y se descarta).
- SL/TP se verifican con el precio actual en cada sondeo.
- Todo queda en memory/paper_journal.jsonl y memory/paper_state.json para reanudar.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import pandas as pd
import requests

from ..config import Config
from ..data.binance import fetch_latest, fetch_price, interval_to_ms
from ..journal import Journal, Trade
from ..risk import RiskManager
from ..strategy.base import Signal, Strategy


@dataclass
class LivePosition:
    signal: dict
    entry_time: str
    entry_price: float
    qty: float
    stop_loss: float
    take_profit: float
    entry_fee: float
    bars_held: int
    decision: dict | None


class PaperTrader:
    def __init__(self, cfg: Config, strategy: Strategy, advisor: Callable | None = None,
                 state_dir: str | Path | None = None):
        self.cfg = cfg
        self.strategy = strategy
        self.advisor = advisor
        self.session = requests.Session()
        self.state_dir = Path(state_dir or cfg.paper.log_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.journal = Journal(self.state_dir / "paper_journal.jsonl")
        self.state_path = self.state_dir / "paper_state.json"
        self.risk = RiskManager(cfg.risk)
        self.equity = cfg.capital.initial
        self.position: LivePosition | None = None
        self.last_bar_time: pd.Timestamp | None = None
        self.bar_counter = 0
        self._load_state()

    # ---------- persistencia ----------
    def _load_state(self) -> None:
        if self.state_path.exists():
            s = json.loads(self.state_path.read_text(encoding="utf-8"))
            self.equity = s.get("equity", self.equity)
            self.bar_counter = s.get("bar_counter", 0)
            if s.get("position"):
                self.position = LivePosition(**s["position"])
            if s.get("last_bar_time"):
                self.last_bar_time = pd.Timestamp(s["last_bar_time"])

    def _save_state(self) -> None:
        s = {"equity": self.equity, "bar_counter": self.bar_counter,
             "last_bar_time": self.last_bar_time.isoformat() if self.last_bar_time is not None else None,
             "position": self.position.__dict__ if self.position else None,
             "updated": datetime.now(timezone.utc).isoformat()}
        self.state_path.write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---------- lógica ----------
    def _log(self, msg: str) -> None:
        print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] {msg}", flush=True)

    def _closed_bars(self) -> pd.DataFrame:
        n = max(400, self.strategy.warmup_bars * 3) if hasattr(self.strategy, "warmup_bars") else 400
        df = fetch_latest(self.cfg.symbol, self.cfg.interval, min(n, 1000), self.cfg.data.base_url, self.session)
        now_ms = int(time.time() * 1000)
        step = interval_to_ms(self.cfg.interval)
        # descartar la vela en curso
        last_open_ms = int(df.index[-1].timestamp() * 1000)
        if now_ms < last_open_ms + step:
            df = df.iloc[:-1]
        return df

    def _check_exit(self, price: float, reason_time: str) -> None:
        pos = self.position
        if pos is None:
            return
        d = 1 if pos.signal["side"] == "long" else -1
        reason = None
        exit_price = None
        if (d > 0 and price <= pos.stop_loss) or (d < 0 and price >= pos.stop_loss):
            reason, exit_price = "stop_loss", pos.stop_loss
        elif (d > 0 and price >= pos.take_profit) or (d < 0 and price <= pos.take_profit):
            reason, exit_price = "take_profit", pos.take_profit
        elif pos.bars_held >= self.cfg.strategy.max_bars_in_trade:
            reason, exit_price = "time_exit", price
        if reason is None:
            return
        slip = self.cfg.fees.slippage_pct / 100.0
        fee_frac = self.cfg.fees.taker_pct / 100.0
        fill = exit_price * (1 - d * slip)
        fee = fill * pos.qty * fee_frac
        gross = (fill - pos.entry_price) * pos.qty * d
        pnl = gross - fee - pos.entry_fee
        self.equity += gross - fee
        self.risk.register_exit(pd.Timestamp(reason_time), pnl, self.bar_counter)
        self.journal.add(Trade(
            entry_time=pos.entry_time, exit_time=reason_time, side=pos.signal["side"], entry_price=pos.entry_price,
            exit_price=fill, qty=pos.qty, stop_loss=pos.stop_loss, take_profit=pos.take_profit, pnl=pnl,
            pnl_pct=pnl / (pos.entry_price * pos.qty) * 100.0, fees=fee + pos.entry_fee, exit_reason=reason,
            bars_held=pos.bars_held, reasons=pos.signal.get("reasons", []), features=pos.signal.get("features", {}),
            llm=pos.decision))
        self._log(f"SALIDA {reason} @ {fill:.2f} pnl={pnl:.2f} equity={self.equity:.2f}")
        self.position = None
        self._save_state()

    def _try_enter(self, sig: Signal, df: pd.DataFrame, price: float) -> None:
        ok, why = self.risk.can_trade(sig.time, self.bar_counter, self.equity)
        if not ok:
            self._log(f"señal {sig.side} bloqueada por riesgo: {why}")
            return
        decision = None
        if self.advisor is not None:
            decision = self.advisor(sig, df, self.journal, self.equity)
            self._log(f"LLM: {decision.get('decision')} conf={decision.get('confidence')} - {decision.get('reasoning')}")
            if decision.get("decision") == "skip":
                return
        b = self.cfg.llm
        size = 1.0
        sl, tp = sig.stop_loss, sig.take_profit
        if decision:
            size = min(max(float(decision.get("size_multiplier", 1.0)), b.size_multiplier_bounds[0]), b.size_multiplier_bounds[1])
            slm = min(max(float(decision.get("sl_multiplier", 1.0)), b.sl_multiplier_bounds[0]), b.sl_multiplier_bounds[1])
            tpm = min(max(float(decision.get("tp_multiplier", 1.0)), b.tp_multiplier_bounds[0]), b.tp_multiplier_bounds[1])
            sl = sig.price - sig.direction * abs(sig.price - sig.stop_loss) * slm
            tp = sig.price + sig.direction * abs(sig.take_profit - sig.price) * tpm
        fill = price * (1 + sig.direction * self.cfg.fees.slippage_pct / 100.0)
        qty = self.risk.position_size(self.equity, fill, abs(fill - sl), size)
        if qty <= 0:
            return
        fee = fill * qty * self.cfg.fees.taker_pct / 100.0
        self.equity -= fee
        self.risk.register_entry(sig.time)
        self.position = LivePosition(
            signal={"side": sig.side, "reasons": sig.reasons, "features": sig.features, "time": sig.time.isoformat()},
            entry_time=datetime.now(timezone.utc).isoformat(), entry_price=fill, qty=qty, stop_loss=sl,
            take_profit=tp, entry_fee=fee, bars_held=0, decision=decision)
        self._log(f"ENTRADA {sig.side} @ {fill:.2f} qty={qty:.5f} sl={sl:.2f} tp={tp:.2f} | {', '.join(sig.reasons)}")
        self._save_state()

    def step(self) -> None:
        """Un ciclo: precio actual -> revisar salida -> si hay vela nueva cerrada, buscar señal."""
        price = fetch_price(self.cfg.symbol, self.cfg.data.base_url, self.session)
        now = datetime.now(timezone.utc).isoformat()
        self._check_exit(price, now)
        df_raw = self._closed_bars()
        last = df_raw.index[-1]
        if self.last_bar_time is not None and last <= self.last_bar_time:
            return  # sin vela nueva
        self.last_bar_time = last
        self.bar_counter += 1
        if self.position is not None:
            self.position.bars_held += 1
            self._check_exit(price, now)
        df = self.strategy.prepare(df_raw)
        if self.position is None:
            sig = self.strategy.signal_at(df, len(df) - 1)
            if sig is not None:
                self._try_enter(sig, df, price)
        self._log(f"vela {last.strftime('%H:%M')} close={df_raw['close'].iloc[-1]:.2f} equity={self.equity:.2f} "
                  f"pos={'sí' if self.position else 'no'}")
        self._save_state()

    def run(self, max_minutes: float | None = None) -> None:
        self._log(f"Paper trading {self.cfg.symbol} {self.cfg.interval} | capital {self.equity:.2f} | "
                  f"LLM {'activo' if self.advisor else 'desactivado'}")
        start = time.time()
        while True:
            try:
                self.step()
            except requests.RequestException as exc:
                self._log(f"error de red: {exc}")
            except KeyboardInterrupt:
                self._log("detenido por el usuario")
                break
            if max_minutes is not None and (time.time() - start) / 60.0 >= max_minutes:
                break
            time.sleep(self.cfg.paper.poll_seconds)
        self._save_state()
