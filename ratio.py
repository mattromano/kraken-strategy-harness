"""Relative-value strategy: trade a crypto asset off its ratio to a reference series
(e.g. ETH-USD / Nasdaq, or ETH-USD / Russell 2000).

Because ETH supply and an index's divisor both move slowly, `asset_price / index_level`
is signal-equivalent to the market-cap ratio for momentum/z-score purposes.

Two signal modes:
  - momentum  : long the asset while the ratio's fast SMA > slow SMA (ratio trending up)
  - reversion : long the asset when the ratio is z-score cheap, flat when it reverts

Positions are long/flat on the ASSET (we hold ETH, never the index). Stdlib only.
"""

from __future__ import annotations

import datetime as dt

from data import Candle


def _date(ts: int) -> dt.date:
    return dt.datetime.utcfromtimestamp(ts).date()


def align_ratio(asset: list[Candle], ref: list[Candle]) -> tuple[list[Candle], list[float]]:
    """Align reference closes onto the asset's calendar (forward-fill), return (candles, ratio).

    Crypto trades daily; indices skip weekends/holidays, so each asset date uses the most
    recent prior reference close. Asset dates before the reference's first date are dropped.
    No look-ahead: only past/current reference values are used.
    """
    ref_by_date = {_date(c.ts): c.close for c in ref}
    if not ref_by_date:
        raise RuntimeError("reference series is empty")
    first_ref = min(ref_by_date)

    out_candles: list[Candle] = []
    out_ratio: list[float] = []
    last_ref: float | None = None
    for c in asset:
        d = _date(c.ts)
        if d < first_ref:
            continue
        if d in ref_by_date:
            last_ref = ref_by_date[d]
        if last_ref is None or last_ref == 0:
            continue
        out_candles.append(c)
        out_ratio.append(c.close / last_ref)
    return out_candles, out_ratio


def zscore_positions(ratio: list[float], window: int, entry: float, exit_z: float) -> list[int]:
    """Mean-reversion on the ratio: go long when z < -entry, exit when z > exit_z.

    z is the current ratio's standard score against the trailing `window` of prior values.
    """
    pos = 0
    out: list[int] = []
    for i in range(len(ratio)):
        if i < window:
            out.append(pos)
            continue
        win = ratio[i - window:i]
        mu = sum(win) / window
        sd = (sum((x - mu) ** 2 for x in win) / window) ** 0.5
        z = (ratio[i] - mu) / sd if sd > 0 else 0.0
        if pos == 0 and z < -entry:
            pos = 1
        elif pos == 1 and z > exit_z:
            pos = 0
        out.append(pos)
    return out
