# Kraken Strategy Harness

Backtest simple trading strategies on [Kraken](https://github.com/krakenfx/kraken-cli) OHLC data,
then run them live against **`kraken paper`** — simulated money, **no real funds, ever**.

> Sibling project to [kraken-market-assistant](https://github.com/mattromano/kraken-market-assistant).
> Python **standard library only** — no `pip install`. Requires the `kraken` CLI on your PATH.

## Quick start

```bash
# List strategies
python3 harness.py strategies

# Backtest SMA crossover on ~2 years of ETH daily candles
python3 harness.py backtest --pair ETHUSD --interval 1440 --strategy sma --fast 10 --slow 30

# Backtest RSI mean-reversion on hourly BTC
python3 harness.py backtest --pair BTCUSD --interval 60 --strategy rsi --period 14

# Paper-trade live: evaluate the signal once and act
python3 harness.py live --pair ETHUSD --interval 1 --strategy sma --once

# Paper-trade live: poll every 60s for 30 iterations
python3 harness.py live --pair ETHUSD --interval 1 --strategy sma --poll 60 --iters 30
```

## Example backtest output

```
  Strategy   : SMA crossover (fast=10, slow=30)
  Market     : ETHUSD  1440m  (721 candles)
  Fees/slip  : 0.260% / 0.000%
  ----------------------------------------------
  Start cash : $10,000.00
  End equity : $9,853.84
  Return     : -1.46%
  Buy & hold : -52.87%
  Edge       : +51.41%  (beat buy & hold)
  Trades     : 15  (win rate 33%)
  Max drawdn : -46.07%
```

## How it works

```
                 ┌───────────────┐
  OHLC candles ─►│  strategies   │─► target position series (0 flat / 1 long)
 (kraken ohlc)   └───────┬───────┘
                         │
          ┌──────────────┴───────────────┐
          ▼                              ▼
   ┌─────────────┐               ┌──────────────────┐
   │  backtest   │               │   live (paper)   │
   │  engine     │               │  kraken paper    │
   └─────────────┘               └──────────────────┘
   metrics vs buy&hold           real fills + P&L, no real money
```

| File | Purpose |
|------|---------|
| `harness.py` | CLI entry point (`strategies` / `backtest` / `live`) |
| `kraken.py` | Locates the `kraken` binary; runs commands and parses JSON |
| `data.py` | Fetches & parses OHLC candles |
| `strategies.py` | Strategy interface + `sma` (crossover) and `rsi` (mean-reversion) |
| `backtest.py` | No-lookahead backtest engine with fees/slippage and metrics |
| `paper.py` | Live loop wrapping `kraken paper` (all-in long / all-out flat) |

## Strategies

- **`sma`** — long when the fast SMA is above the slow SMA, flat otherwise (`--fast`, `--slow`).
- **`rsi`** — buy when RSI dips below `--oversold`, sell when it rises above `--overbought` (`--period`).

Add your own: subclass `Strategy` in `strategies.py`, implement
`target_positions(closes) -> list[int]` (0/1), and register it in the `STRATEGIES` dict.
Both the backtest and live engines pick it up automatically.

## Design notes & caveats

- **No look-ahead:** the position decided at candle *i-1*'s close is executed at candle *i*'s open.
- **Fees & slippage** are applied on every fill; buy & hold is charged the same fees for a fair comparison.
- **Long-only** (spot) — positions are all-in cash→asset or all-out asset→cash. A small (0.1%) cash
  buffer covers price drift between the quoted candle and the live market fill.
- **Kraken OHLC history is bounded** (~720 candles per request), so daily candles cover ~2 years;
  finer intervals cover proportionally less. Use `--since` to page further back.
- **Not financial advice. Paper trading only.** This is a learning/experimentation harness, not a
  production trading system — there is no risk management, position sizing, or order-retry logic.

## Future ideas

- More strategies (MACD, Bollinger bands, momentum) and parameter sweeps.
- Equity-curve export/plot; multi-strategy leaderboard.
- Fractional position sizing and stop-losses.
- Persisted backtest runs for comparison over time.
