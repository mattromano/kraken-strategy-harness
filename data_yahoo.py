"""Fetch historical daily OHLC from Yahoo Finance (free, no API key).

Kraken's OHLC endpoint only serves the most recent ~720 candles, so daily data
doesn't reach far back. Yahoo provides full daily history (ETH-USD from late 2017),
which is what we need to backtest long-horizon strategies like the 50/200 golden cross.

Stdlib only — uses urllib.
"""

from __future__ import annotations

import json
import time
import urllib.request

from data import Candle

_INTERVAL_MAP = {1440: "1d", 10080: "1wk", 43200: "1mo"}


def to_symbol(pair: str, base: str, quote: str) -> str:
    """Map a Kraken-style pair to a Yahoo ticker, e.g. ETHUSD -> ETH-USD."""
    return f"{base}-{quote}".upper()


def fetch_ohlc_yahoo(
    symbol: str,
    interval_min: int = 1440,
    start: int | None = None,
    end: int | None = None,
) -> list[Candle]:
    """Return daily (or weekly/monthly) OHLC candles for a Yahoo symbol, oldest-first."""
    yint = _INTERVAL_MAP.get(interval_min, "1d")
    p1 = start if start is not None else 0
    p2 = end if end is not None else int(time.time())
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        f"?period1={p1}&period2={p2}&interval={yint}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.load(resp)
    except Exception as e:  # network / HTTP errors
        raise RuntimeError(f"Yahoo request failed for {symbol}: {e}") from e

    chart = payload.get("chart", {})
    if chart.get("error"):
        raise RuntimeError(f"Yahoo returned an error for {symbol}: {chart['error']}")
    results = chart.get("result")
    if not results:
        raise RuntimeError(f"Yahoo returned no data for {symbol} (check the ticker)")

    res = results[0]
    timestamps = res.get("timestamp") or []
    quote = res["indicators"]["quote"][0]
    o, h, l, c = quote["open"], quote["high"], quote["low"], quote["close"]
    vol = quote.get("volume", [None] * len(timestamps))

    candles: list[Candle] = []
    for i, ts in enumerate(timestamps):
        if None in (o[i], h[i], l[i], c[i]):
            continue  # skip gaps
        candles.append(
            Candle(int(ts), float(o[i]), float(h[i]), float(l[i]), float(c[i]), float(vol[i] or 0.0))
        )
    candles.sort(key=lambda cd: cd.ts)
    return candles
