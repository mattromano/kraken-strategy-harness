#!/usr/bin/env python3
"""kraken-strategy-harness — backtest simple trading strategies on Kraken OHLC data,
then run them live against `kraken paper` (simulated money, no real funds).

Examples:
    python harness.py strategies
    python harness.py backtest --pair ETHUSD --interval 1440 --strategy sma --fast 10 --slow 30
    python harness.py backtest --pair BTCUSD --interval 60 --strategy rsi --period 14
    python harness.py live --pair ETHUSD --interval 1 --strategy sma --once
    python harness.py live --pair ETHUSD --interval 1 --strategy sma --poll 60 --iters 30

Stdlib only — no pip installs. Requires the `kraken` CLI on PATH.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys

import strategies
from data import fetch_ohlc
from data_yahoo import fetch_ohlc_yahoo, to_symbol
from backtest import run_backtest
from paper import PaperBroker, run_live


def _to_epoch(date_str: str | None) -> int | None:
    if not date_str:
        return None
    return int(dt.datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc).timestamp())

# Quote currencies tried (longest first) when splitting a pair like ETHUSD -> ETH/USD.
_QUOTES = ["USDT", "USDC", "USD", "EUR", "GBP", "XBT", "BTC", "ETH"]


def split_pair(pair: str) -> tuple[str, str]:
    up = pair.upper()
    for q in _QUOTES:
        if up.endswith(q) and len(up) > len(q):
            return up[: -len(q)], q
    return up, "USD"


def add_strategy_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--strategy", choices=list(strategies.STRATEGIES), default="sma")
    p.add_argument("--fast", type=int, default=10, help="SMA fast period")
    p.add_argument("--slow", type=int, default=30, help="SMA slow period")
    p.add_argument("--period", type=int, default=14, help="RSI period")
    p.add_argument("--oversold", type=float, default=30.0, help="RSI buy threshold")
    p.add_argument("--overbought", type=float, default=70.0, help="RSI sell threshold")


def cmd_strategies(_args) -> int:
    print("Available strategies:")
    for name, cls in strategies.STRATEGIES.items():
        print(f"  {name:6} — {cls().describe()}")
    return 0


def cmd_backtest(args) -> int:
    if args.source == "yahoo":
        base, quote = split_pair(args.pair)
        symbol = to_symbol(args.pair, base, quote)
        candles = fetch_ohlc_yahoo(symbol, args.interval, start=_to_epoch(args.start), end=_to_epoch(args.end))
        market = f"{symbol} (yahoo)"
    else:
        candles = fetch_ohlc(args.pair, args.interval, since=args.since)
        market = f"{args.pair} (kraken)"
    if len(candles) < 2:
        print("error: not enough candles returned", file=sys.stderr)
        return 1
    strat = strategies.build(args.strategy, args)
    positions = strat.target_positions([c.close for c in candles])
    r = run_backtest(candles, positions, initial_cash=args.cash, fee=args.fee, slippage=args.slippage)

    d0 = dt.datetime.utcfromtimestamp(candles[0].ts).date()
    d1 = dt.datetime.utcfromtimestamp(candles[-1].ts).date()
    span = f"{d0} → {d1}"
    edge = r.total_return - r.buy_hold_return
    print(f"\n  Strategy   : {strat.describe()}")
    print(f"  Market     : {market}  {args.interval}m  ({len(candles)} candles, {span})")
    print(f"  Fees/slip  : {args.fee * 100:.3f}% / {args.slippage * 100:.3f}%")
    print("  " + "-" * 46)
    print(f"  Start cash : ${r.initial_cash:,.2f}")
    print(f"  End equity : ${r.final_equity:,.2f}")
    print(f"  Return     : {r.total_return * 100:+.2f}%")
    print(f"  Buy & hold : {r.buy_hold_return * 100:+.2f}%")
    print(f"  Edge       : {edge * 100:+.2f}%  ({'beat' if edge > 0 else 'lagged'} buy & hold)")
    print(f"  Trades     : {r.num_trades}  (win rate {r.win_rate * 100:.0f}%)")
    print(f"  Max drawdn : {r.max_drawdown * 100:.2f}%")
    print()
    return 0


def cmd_live(args) -> int:
    base, quote = (args.base, args.quote) if args.base else split_pair(args.pair)
    strat = strategies.build(args.strategy, args)
    broker = PaperBroker()
    if not args.no_reset:
        broker.reset(balance=args.cash, currency=quote, fee=args.fee, slippage=args.slippage)
        print(f"↺ paper account reset to ${args.cash:,.2f} {quote}")
    run_live(
        args.pair, args.interval, strat,
        base=base, quote=quote, broker=broker,
        poll_seconds=args.poll, max_iters=args.iters, once=args.once,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("strategies", help="List available strategies").set_defaults(func=cmd_strategies)

    bt = sub.add_parser("backtest", help="Backtest a strategy on historical candles")
    bt.add_argument("--pair", default="ETHUSD")
    bt.add_argument("--source", choices=["kraken", "yahoo"], default="kraken",
                    help="kraken (recent ~720 candles) or yahoo (full daily history, e.g. ETH from 2017)")
    bt.add_argument("--interval", type=int, default=1440, help="candle minutes (1,5,15,30,60,240,1440,...)")
    bt.add_argument("--cash", type=float, default=10_000.0)
    bt.add_argument("--fee", type=float, default=0.0026, help="taker fee fraction (default 0.26%%)")
    bt.add_argument("--slippage", type=float, default=0.0, help="slippage fraction per fill")
    bt.add_argument("--since", type=int, default=None, help="[kraken] unix timestamp to fetch from")
    bt.add_argument("--start", default=None, help="[yahoo] start date YYYY-MM-DD")
    bt.add_argument("--end", default=None, help="[yahoo] end date YYYY-MM-DD")
    add_strategy_args(bt)
    bt.set_defaults(func=cmd_backtest)

    lv = sub.add_parser("live", help="Run a strategy live against kraken paper")
    lv.add_argument("--pair", default="ETHUSD")
    lv.add_argument("--interval", type=int, default=1)
    lv.add_argument("--cash", type=float, default=10_000.0)
    lv.add_argument("--fee", type=float, default=0.0026)
    lv.add_argument("--slippage", type=float, default=0.0)
    lv.add_argument("--base", default=None, help="base asset (auto-derived from pair if omitted)")
    lv.add_argument("--quote", default="USD", help="quote currency")
    lv.add_argument("--poll", type=int, default=60, help="seconds between iterations")
    lv.add_argument("--iters", type=int, default=None, help="max iterations (default: run until Ctrl-C)")
    lv.add_argument("--once", action="store_true", help="evaluate the signal once and exit")
    lv.add_argument("--no-reset", action="store_true", help="keep existing paper balance (don't reset)")
    add_strategy_args(lv)
    lv.set_defaults(func=cmd_live)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\ninterrupted.")
        return 130
    except (RuntimeError, ValueError, FileNotFoundError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
