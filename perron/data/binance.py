"""Descarga de velas (klines) de Binance. No requiere API key (endpoint público)."""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import requests

COLUMNS = ["open_time", "open", "high", "low", "close", "volume", "close_time",
           "quote_volume", "trades", "taker_buy_base", "taker_buy_quote", "ignore"]

_INTERVAL_MS = {
    "1m": 60_000, "3m": 180_000, "5m": 300_000, "15m": 900_000,
    "30m": 1_800_000, "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000,
}


def interval_to_ms(interval: str) -> int:
    return _INTERVAL_MS[interval]


def fetch_klines(symbol: str, interval: str, days: float, base_url: str = "https://api.binance.com",
                 end: datetime | None = None, session: requests.Session | None = None,
                 verbose: bool = True) -> pd.DataFrame:
    """Descarga `days` días de velas hasta `end` (UTC, ahora por defecto), paginando de 1000 en 1000."""
    sess = session or requests.Session()
    end = end or datetime.now(timezone.utc)
    start_ms = int((end - timedelta(days=days)).timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)
    step = interval_to_ms(interval)
    rows: list[list] = []
    cursor = start_ms
    while cursor < end_ms:
        resp = sess.get(
            f"{base_url}/api/v3/klines",
            params={"symbol": symbol, "interval": interval, "startTime": cursor,
                    "endTime": end_ms, "limit": 1000},
            timeout=30,
        )
        if resp.status_code == 429:
            time.sleep(5)
            continue
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        rows.extend(batch)
        cursor = batch[-1][0] + step
        if verbose:
            print(f"  descargadas {len(rows)} velas hasta {pd.to_datetime(batch[-1][0], unit='ms', utc=True)}")
        if len(batch) < 1000:
            break
        time.sleep(0.15)  # respetar límites de la API
    return _to_frame(rows)


def _to_frame(rows: list[list]) -> pd.DataFrame:
    df = pd.DataFrame(rows, columns=COLUMNS)
    df = df[["open_time", "open", "high", "low", "close", "volume", "trades"]].copy()
    df["time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = df[c].astype(float)
    df["trades"] = df["trades"].astype(int)
    df = df.drop(columns=["open_time"]).set_index("time").sort_index()
    return df[~df.index.duplicated(keep="last")]


def save_csv(df: pd.DataFrame, path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(p)
    return p


def load_csv(path: str | Path) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["time"], index_col="time")
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    return df.sort_index()


def fetch_latest(symbol: str, interval: str, limit: int, base_url: str = "https://api.binance.com",
                 session: requests.Session | None = None) -> pd.DataFrame:
    """Últimas `limit` velas (la última puede estar aún abierta)."""
    sess = session or requests.Session()
    resp = sess.get(f"{base_url}/api/v3/klines",
                    params={"symbol": symbol, "interval": interval, "limit": limit}, timeout=30)
    resp.raise_for_status()
    return _to_frame(resp.json())


def fetch_price(symbol: str, base_url: str = "https://api.binance.com",
                session: requests.Session | None = None) -> float:
    sess = session or requests.Session()
    resp = sess.get(f"{base_url}/api/v3/ticker/price", params={"symbol": symbol}, timeout=15)
    resp.raise_for_status()
    return float(resp.json()["price"])
