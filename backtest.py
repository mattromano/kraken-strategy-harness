"""Backtest engine: simulate a long-only strategy over historical candles.

No look-ahead: the target position decided at candle i-1's close is executed at
candle i's open. Fees and slippage are applied on every fill.

Reports risk-adjusted metrics (CAGR, Sharpe, max drawdown) alongside raw return,
because raw total return is misleading across regimes: a parabolic bull market
inflates percentage gains independent of strategy skill. Sharpe and the buy-&-hold
return multiple normalize for that.
"""

from __future__ import annotations

import math
from typing import NamedTuple

from data import Candle

# Crypto trades every day; annualize daily stats over a 365-day year.
_TRADING_DAYS = 365.0


class Trade(NamedTuple):
    entry_price: float
    exit_price: float

    @property
    def return_pct(self) -> float:
        return self.exit_price / self.entry_price - 1


class BacktestResult(NamedTuple):
    initial_cash: float
    final_equity: float
    total_return: float       # strategy return, fraction
    buy_hold_return: float    # buy & hold over same window (fees applied), fraction
    num_trades: int           # completed round trips
    win_rate: float           # fraction of round trips with exit > entry
    max_drawdown: float       # worst peak-to-trough on the equity curve, fraction
    cagr: float               # annualized compound growth rate, fraction
    sharpe: float             # annualized Sharpe ratio (rf=0) of the equity curve
    bh_cagr: float            # buy & hold annualized growth, fraction
    bh_sharpe: float          # buy & hold annualized Sharpe
    bh_multiple: float        # (1+strategy_return) / (1+buy_hold_return); regime-neutral
    equity_curve: list[float]
    trades: list[Trade]


def _sharpe(equity: list[float]) -> float:
    """Annualized Sharpe (rf=0) from an equity curve's daily simple returns."""
    rets = [equity[i] / equity[i - 1] - 1 for i in range(1, len(equity)) if equity[i - 1] > 0]
    if len(rets) < 2:
        return 0.0
    mu = sum(rets) / len(rets)
    var = sum((r - mu) ** 2 for r in rets) / len(rets)
    sd = var ** 0.5
    return (mu / sd) * math.sqrt(_TRADING_DAYS) if sd > 0 else 0.0


def _cagr(equity: list[float], years: float) -> float:
    if not equity or equity[0] <= 0 or years <= 0:
        return 0.0
    return (equity[-1] / equity[0]) ** (1 / years) - 1


def _max_drawdown(equity: list[float]) -> float:
    peak = equity[0] if equity else 0.0
    worst = 0.0
    for v in equity:
        peak = max(peak, v)
        if peak > 0:
            worst = min(worst, v / peak - 1)
    return worst


def _buy_hold_curve(candles: list[Candle], cash: float, fee: float, slippage: float) -> list[float]:
    """Equity curve for buy-at-first-open, hold, mark-to-close — same fees/slippage.

    The final point nets the exit fee/slippage so it matches a realized round trip.
    """
    entry = candles[0].open * (1 + slippage)
    units = (cash - cash * fee) / entry
    curve = [units * c.close for c in candles]
    exit_price = candles[-1].close * (1 - slippage)
    gross = units * exit_price
    curve[-1] = gross - gross * fee
    return curve


def _years(candles: list[Candle]) -> float:
    span_days = (candles[-1].ts - candles[0].ts) / 86400.0
    return span_days / _TRADING_DAYS if span_days > 0 else 0.0


def run_backtest(
    candles: list[Candle],
    positions: list[int],
    *,
    initial_cash: float = 10_000.0,
    fee: float = 0.0026,
    slippage: float = 0.0,
) -> BacktestResult:
    if len(candles) != len(positions):
        raise ValueError("candles and positions must be the same length")
    if len(candles) < 2:
        raise ValueError("need at least 2 candles to backtest")

    cash = initial_cash
    units = 0.0
    entry_price: float | None = None
    equity_curve: list[float] = []
    trades: list[Trade] = []

    for i, candle in enumerate(candles):
        if i > 0:
            desired = positions[i - 1]  # decided at prior close -> execute at this open
            price = candle.open
            if desired == 1 and units == 0.0:               # enter long
                exec_price = price * (1 + slippage)
                cash_after_fee = cash - cash * fee
                units = cash_after_fee / exec_price
                cash = 0.0
                entry_price = exec_price
            elif desired == 0 and units > 0.0:              # exit long
                exec_price = price * (1 - slippage)
                gross = units * exec_price
                cash = gross - gross * fee
                trades.append(Trade(entry_price, exec_price))  # type: ignore[arg-type]
                units = 0.0
                entry_price = None
        equity_curve.append(cash + units * candle.close)

    final_equity = equity_curve[-1]
    wins = sum(1 for t in trades if t.exit_price > t.entry_price)
    years = _years(candles)
    bh_curve = _buy_hold_curve(candles, initial_cash, fee, slippage)
    bh_return = bh_curve[-1] / initial_cash - 1
    total_return = final_equity / initial_cash - 1
    return BacktestResult(
        initial_cash=initial_cash,
        final_equity=final_equity,
        total_return=total_return,
        buy_hold_return=bh_return,
        num_trades=len(trades),
        win_rate=(wins / len(trades)) if trades else 0.0,
        max_drawdown=_max_drawdown(equity_curve),
        cagr=_cagr(equity_curve, years),
        sharpe=_sharpe(equity_curve),
        bh_cagr=_cagr(bh_curve, years),
        bh_sharpe=_sharpe(bh_curve),
        bh_multiple=(1 + total_return) / (1 + bh_return) if bh_return != -1 else 0.0,
        equity_curve=equity_curve,
        trades=trades,
    )
