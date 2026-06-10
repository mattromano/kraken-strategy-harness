"""Trading strategies. Each returns a target position series (0 = flat, 1 = long).

Long-only (spot). Add a new strategy by subclassing Strategy and registering it
in STRATEGIES — the backtest and live engines consume the common interface.
"""

from __future__ import annotations


def sma(values: list[float], period: int) -> list[float | None]:
    """Simple moving average; None during the warmup window."""
    out: list[float | None] = []
    running = 0.0
    for i, v in enumerate(values):
        running += v
        if i >= period:
            running -= values[i - period]
        out.append(running / period if i >= period - 1 else None)
    return out


def rsi(values: list[float], period: int) -> list[float | None]:
    """Wilder's RSI; None during the warmup window."""
    out: list[float | None] = [None] * len(values)
    if len(values) <= period:
        return out
    gains = losses = 0.0
    for i in range(1, period + 1):
        delta = values[i] - values[i - 1]
        gains += max(delta, 0.0)
        losses += max(-delta, 0.0)
    avg_gain = gains / period
    avg_loss = losses / period
    out[period] = 100.0 if avg_loss == 0 else 100 - 100 / (1 + avg_gain / avg_loss)
    for i in range(period + 1, len(values)):
        delta = values[i] - values[i - 1]
        avg_gain = (avg_gain * (period - 1) + max(delta, 0.0)) / period
        avg_loss = (avg_loss * (period - 1) + max(-delta, 0.0)) / period
        out[i] = 100.0 if avg_loss == 0 else 100 - 100 / (1 + avg_gain / avg_loss)
    return out


def rsi_exit_delay(base_positions: list[int], price_closes: list[float],
                   period: int = 14, threshold: float = 45.0) -> list[int]:
    """Overlay: 'let winners run' — hold a long through a base SELL while price RSI stays strong.

    Entries follow the base strategy unchanged. The only difference: when the base flips to
    flat but price RSI is still above `threshold` (momentum intact), stay long instead of
    exiting. This captures upside the lagging base signal would prematurely give up.
    """
    r = rsi(price_closes, period)
    out: list[int] = []
    state = 0
    for i in range(len(base_positions)):
        if base_positions[i] == 1:
            state = 1
        elif state == 1 and r[i] is not None and r[i] > threshold:
            state = 1  # base says exit, but momentum still strong -> hold
        else:
            state = 0
        out.append(state)
    return out


class Strategy:
    name = "base"

    def target_positions(self, closes: list[float]) -> list[int]:
        raise NotImplementedError

    def describe(self) -> str:
        return self.name


class SmaCrossover(Strategy):
    name = "sma"

    def __init__(self, fast: int = 10, slow: int = 30):
        if fast >= slow:
            raise ValueError("fast period must be < slow period")
        self.fast, self.slow = fast, slow

    def target_positions(self, closes: list[float]) -> list[int]:
        f, s = sma(closes, self.fast), sma(closes, self.slow)
        return [1 if (fv is not None and sv is not None and fv > sv) else 0 for fv, sv in zip(f, s)]

    def describe(self) -> str:
        return f"SMA crossover (fast={self.fast}, slow={self.slow})"


class RsiReversion(Strategy):
    name = "rsi"

    def __init__(self, period: int = 14, oversold: float = 30.0, overbought: float = 70.0):
        self.period, self.oversold, self.overbought = period, oversold, overbought

    def target_positions(self, closes: list[float]) -> list[int]:
        r = rsi(closes, self.period)
        pos, out = 0, []
        for val in r:
            if val is not None:
                if pos == 0 and val < self.oversold:
                    pos = 1
                elif pos == 1 and val > self.overbought:
                    pos = 0
            out.append(pos)
        return out

    def describe(self) -> str:
        return f"RSI mean-reversion (period={self.period}, buy<{self.oversold}, sell>{self.overbought})"


STRATEGIES = {"sma": SmaCrossover, "rsi": RsiReversion}


def build(name: str, args) -> Strategy:
    """Construct a strategy from a parsed argparse namespace."""
    if name == "sma":
        return SmaCrossover(fast=args.fast, slow=args.slow)
    if name == "rsi":
        return RsiReversion(period=args.period, oversold=args.oversold, overbought=args.overbought)
    raise ValueError(f"unknown strategy '{name}'. Available: {', '.join(STRATEGIES)}")
