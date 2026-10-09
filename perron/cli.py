"""Línea de comandos: python -m perron <comando> [opciones]"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import Config
from .strategy import ScalpingStrategy


def cmd_fetch(args, cfg: Config) -> int:
    from .data import fetch_klines, save_csv
    print(f"Descargando {args.days} días de {cfg.symbol} {cfg.interval} desde {cfg.data.base_url} ...")
    df = fetch_klines(cfg.symbol, cfg.interval, args.days, cfg.data.base_url)
    out = Path(cfg.data.dir) / f"{cfg.symbol}_{cfg.interval}.csv"
    save_csv(df, out)
    print(f"Guardadas {len(df)} velas en {out} ({df.index[0]} -> {df.index[-1]})")
    return 0


def cmd_synth(args, cfg: Config) -> int:
    from .data import generate_synthetic, save_csv
    df = generate_synthetic(days=args.days, seed=args.seed)
    out = Path(cfg.data.dir) / f"SYNTH_{cfg.interval}.csv"
    save_csv(df, out)
    print(f"Generadas {len(df)} velas sintéticas en {out}")
    return 0


def _load_data(args, cfg: Config):
    from .data import load_csv
    path = args.data or (Path(cfg.data.dir) / f"{cfg.symbol}_{cfg.interval}.csv")
    if not Path(path).exists():
        print(f"No existe {path}. Ejecuta primero `python -m perron fetch` o `python -m perron synth`.")
        sys.exit(1)
    df = load_csv(path)
    if args.last_days:
        df = df.loc[df.index >= df.index[-1] - __import__("pandas").Timedelta(days=args.last_days)]
    return df


def cmd_backtest(args, cfg: Config) -> int:
    from .backtest import Backtester, format_metrics
    from .journal import Journal
    from .llm import build_advisor

    df = _load_data(args, cfg)
    use_llm = args.llm or cfg.llm.enabled
    advisor = build_advisor(cfg, use_llm)
    journal_path = Path(cfg.llm.memory_dir) / "backtest_journal.jsonl"
    if journal_path.exists():
        journal_path.unlink()
    bt = Backtester(cfg, ScalpingStrategy(cfg.strategy, cfg.trend_interval), advisor,
                    Journal(journal_path), verbose=args.verbose)
    print(f"Backtest sobre {len(df)} velas ({df.index[0]} -> {df.index[-1]}) | LLM {'activo' if advisor else 'desactivado'}")
    res = bt.run(df)
    if advisor is not None:
        advisor.close()
        c = advisor.client
        print(f"LLM: {advisor.calls} llamadas nuevas, {advisor.errors} errores, "
              f"tokens in={getattr(c, 'input_tokens', 0)} out={getattr(c, 'output_tokens', 0)}"
              + (" | presupuesto de llamadas agotado" if advisor.budget_exhausted else ""))
    print(format_metrics(res.metrics))
    print(f"Señales: {res.signals_total} | omitidas por LLM: {res.signals_skipped_by_llm} | "
          f"bloqueadas por riesgo: {res.signals_blocked_by_risk}")
    Path(cfg.llm.memory_dir).mkdir(parents=True, exist_ok=True)
    (Path(cfg.llm.memory_dir) / "last_backtest_metrics.json").write_text(
        json.dumps(res.metrics, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    res.equity_curve.to_csv(Path(cfg.llm.memory_dir) / "last_equity_curve.csv")
    print(f"Journal: {journal_path}")
    return 0


def cmd_paper(args, cfg: Config) -> int:
    from .llm import build_advisor
    from .paper import PaperTrader
    advisor = build_advisor(cfg, args.llm or cfg.llm.enabled)
    trader = PaperTrader(cfg, ScalpingStrategy(cfg.strategy, cfg.trend_interval), advisor)
    trader.run(max_minutes=args.minutes)
    if advisor is not None:
        advisor.close()
    return 0


def cmd_review(args, cfg: Config) -> int:
    from .journal import Journal
    from .backtest.metrics import compute_metrics
    from .llm.reviewer import apply_proposals, review
    import pandas as pd

    journal_path = Path(cfg.llm.memory_dir) / (args.journal or "backtest_journal.jsonl")
    if not journal_path.exists():
        print(f"No existe {journal_path}. Corre un backtest o paper trading primero.")
        return 1
    trades = Journal(journal_path).to_frame()
    if trades.empty:
        print("El journal no tiene operaciones.")
        return 1
    equity = cfg.capital.initial + trades.sort_values("exit_time")["pnl"].cumsum()
    equity.index = pd.DatetimeIndex(trades.sort_values("exit_time")["exit_time"])
    metrics = compute_metrics(trades, equity, cfg.capital.initial)
    print(f"Revisando {len(trades)} operaciones con {cfg.llm.model} ...")
    out = review(cfg, metrics, trades)
    print("\n=== Resumen del revisor ===\n" + out["summary"])
    print("\n=== Lecciones (guardadas en " + out["lessons_path"] + ") ===\n" + out["lessons_markdown"])
    print("\n=== Propuestas de parámetros ===")
    if not out["parameter_proposals"]:
        print("(ninguna)")
    for p in out["parameter_proposals"]:
        print(f"- {p['parameter']}: {p['current']} -> {p['proposed']}  ({p['justification']})")
    if args.apply and out["parameter_proposals"]:
        changed = apply_proposals(args.config, out["parameter_proposals"])
        print("\nAplicado a config.yaml:\n  " + "\n  ".join(changed))
    elif out["parameter_proposals"]:
        print("\nPara aplicarlas: python -m perron review --apply   (o edita config.yaml a mano)")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="perron", description="El Perrón - bot de scalping BTC (paper trading)")
    p.add_argument("--config", default="config.yaml")
    sub = p.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("fetch", help="descargar velas históricas de Binance")
    f.add_argument("--days", type=float, default=30)

    s = sub.add_parser("synth", help="generar velas sintéticas para probar sin conexión")
    s.add_argument("--days", type=float, default=7)
    s.add_argument("--seed", type=int, default=42)

    b = sub.add_parser("backtest", help="correr la estrategia sobre datos históricos")
    b.add_argument("--data", help="ruta CSV (por defecto data/<symbol>_<interval>.csv)")
    b.add_argument("--last-days", type=float, default=None, help="usar solo los últimos N días")
    b.add_argument("--llm", action="store_true", help="activar el asesor Claude")
    b.add_argument("--verbose", action="store_true")

    pp = sub.add_parser("paper", help="paper trading en vivo con precios de Binance")
    pp.add_argument("--llm", action="store_true")
    pp.add_argument("--minutes", type=float, default=None, help="detener tras N minutos")

    r = sub.add_parser("review", help="Claude revisa el journal, escribe lecciones y propone parámetros")
    r.add_argument("--journal", default=None, help="archivo dentro de memory/ (backtest_journal.jsonl o paper_journal.jsonl)")
    r.add_argument("--apply", action="store_true", help="aplicar las propuestas a config.yaml")

    args = p.parse_args(argv)
    cfg = Config.load(args.config)
    return {"fetch": cmd_fetch, "synth": cmd_synth, "backtest": cmd_backtest,
            "paper": cmd_paper, "review": cmd_review}[args.cmd](args, cfg)
