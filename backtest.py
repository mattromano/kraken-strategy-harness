"""Backtest engine: simulate a long-only strategy over historical candles.

No look-ahead: the target position decided at candle i-1's close is executed at
candle i's open. Fees and slippage are applied on every fill.
"""

from __future__ import annotations

from typing import NamedTuple

from data import Candle


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
    equity_curve: list[float]
    trades: list[Trade]


def _max_drawdown(equity: list[float]) -> float:
    peak = equity[0] if equity else 0.0
    worst = 0.0
    for v in equity:
        peak = max(peak, v)
        if peak > 0:
            worst = min(worst, v / peak - 1)
    return worst


def _buy_hold(candles: list[Candle], cash: float, fee: float, slippage: float) -> float:
    """Buy at first open, hold, sell at last close — with the same fees/slippage."""
    entry = candles[0].open * (1 + slippage)
    units = (cash - cash * fee) / entry
    exit_price = candles[-1].close * (1 - slippage)
    gross = units * exit_price
    return gross - gross * fee


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
    return BacktestResult(
        initial_cash=initial_cash,
        final_equity=final_equity,
        total_return=final_equity / initial_cash - 1,
        buy_hold_return=_buy_hold(candles, initial_cash, fee, slippage) / initial_cash - 1,
        num_trades=len(trades),
        win_rate=(wins / len(trades)) if trades else 0.0,
        max_drawdown=_max_drawdown(equity_curve),
        equity_curve=equity_curve,
        trades=trades,
    )
