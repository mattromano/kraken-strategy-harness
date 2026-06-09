"""Fetch and parse OHLC candle data from the Kraken CLI."""

from __future__ import annotations

from typing import NamedTuple

import kraken


class Candle(NamedTuple):
    ts: int       # unix time (candle open)
    open: float
    high: float
    low: float
    close: float
    volume: float


def fetch_ohlc(pair: str, interval: int, since: int | None = None) -> list[Candle]:
    """Return OHLC candles for `pair` at `interval` minutes, oldest-first.

    Kraken returns: { "<NORMALIZED_PAIR>": [[ts, o, h, l, c, vwap, vol, count], ...], "last": ts }
    The pair key is normalized (e.g. ETHUSD -> XETHZUSD), so we take the first non-"last" key.
    """
    args = ["ohlc", pair, "--interval", str(interval)]
    if since is not None:
        args += ["--since", str(since)]
    payload = kraken.run_json(args)
    if not isinstance(payload, dict):
        raise RuntimeError(f"unexpected OHLC payload shape: {type(payload).__name__}")

    rows = None
    for key, value in payload.items():
        if key == "last":
            continue
        if isinstance(value, list):
            rows = value
            break
    if rows is None:
        raise RuntimeError(f"no candle array found in OHLC payload (keys: {list(payload)})")

    candles = [
        Candle(
            ts=int(r[0]),
            open=float(r[1]),
            high=float(r[2]),
            low=float(r[3]),
            close=float(r[4]),
            volume=float(r[6]),
        )
        for r in rows
    ]
    candles.sort(key=lambda c: c.ts)
    return candles


def closes(candles: list[Candle]) -> list[float]:
    return [c.close for c in candles]
