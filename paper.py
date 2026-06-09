"""Live paper-trading loop driven by a strategy, wrapping `kraken paper`.

Simulated money only. Each iteration: pull recent candles, compute the strategy's
target position, and rebalance the paper account (all-in long / all-out flat).
"""

from __future__ import annotations

import time

import kraken
from data import fetch_ohlc
from strategies import Strategy

_DUST = 1e-8
# Size buys against slightly less than full cash: the market order fills at the live
# price, which can drift above the last candle close between fetch and fill.
_CASH_SAFETY = 0.999


class PaperBroker:
    """Wrapper over `kraken paper` subcommands (all JSON)."""

    def reset(self, balance: float, currency: str = "USD", fee: float = 0.0026, slippage: float = 0.0) -> dict:
        return kraken.run_json([
            "paper", "reset",
            "--balance", str(balance),
            "--currency", currency,
            "--fee-rate", str(fee),
            "--slippage-rate", str(slippage),
            "--yes",
        ])

    def status(self) -> dict:
        return kraken.run_json(["paper", "status"])

    def balances(self) -> dict:
        return kraken.run_json(["paper", "balance"])["balances"]

    def available(self, asset: str) -> float:
        return float(self.balances().get(asset, {}).get("available", 0.0))

    def buy(self, pair: str, volume: float) -> dict:
        return kraken.run_json(["paper", "buy", pair, f"{volume:.8f}", "--yes"])

    def sell(self, pair: str, volume: float) -> dict:
        return kraken.run_json(["paper", "sell", pair, f"{volume:.8f}", "--yes"])


def _fmt_pct(x: float) -> str:
    return f"{x * 100:+.2f}%"


def run_live(
    pair: str,
    interval: int,
    strategy: Strategy,
    *,
    base: str,
    quote: str = "USD",
    broker: PaperBroker | None = None,
    poll_seconds: int = 60,
    max_iters: int | None = None,
    once: bool = False,
) -> None:
    broker = broker or PaperBroker()
    fee = float(broker.status().get("fee_rate", 0.0026))
    print(f"▶ live paper trading: {strategy.describe()} on {pair} ({interval}m candles)")
    print(f"  base={base} quote={quote} fee={_fmt_pct(fee)} poll={poll_seconds}s\n")

    iteration = 0
    while True:
        iteration += 1
        candles = fetch_ohlc(pair, interval)
        if len(candles) < 2:
            print("  not enough candle history yet; waiting…")
        else:
            positions = strategy.target_positions([c.close for c in candles])
            target = positions[-1]
            price = candles[-1].close
            units = broker.available(base)
            currently_long = units > _DUST

            action = "hold"
            if target == 1 and not currently_long:
                cash = broker.available(quote) * _CASH_SAFETY
                volume = cash / (price * (1 + fee))
                if volume > _DUST:
                    fill = broker.buy(pair, volume)
                    action = f"BUY {fill.get('volume')} @ {fill.get('price')} (cost {fill.get('cost')})"
            elif target == 0 and currently_long:
                fill = broker.sell(pair, units)
                action = f"SELL {fill.get('volume')} @ {fill.get('price')}"

            st = broker.status()
            print(
                f"  [{iteration}] price={price:.2f} signal={'LONG' if target else 'FLAT'} "
                f"| {action} | value=${st['current_value']:.2f} "
                f"pnl={st['unrealized_pnl_pct']:+.2f}% trades={st['total_trades']}"
            )

        if once or (max_iters is not None and iteration >= max_iters):
            break
        time.sleep(poll_seconds)
