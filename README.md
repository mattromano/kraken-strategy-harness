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

# Long-horizon backtest from 2017 — the 50/200 golden/death cross (Yahoo daily history)
python3 harness.py backtest --pair ETHUSD --source yahoo --strategy sma --fast 50 --slow 200

# Relative-value: trade ETH off its ratio to an equity index (novel)
python3 harness.py ratio --asset ETHUSD --reference '^RUT'  --mode momentum --fast 50 --slow 200
python3 harness.py ratio --asset ETHUSD --reference '^IXIC' --mode reversion --window 100 --entry 1.0

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
| `data.py` | Fetches & parses OHLC candles (Kraken, recent ~720) |
| `data_yahoo.py` | Full daily OHLC history from Yahoo Finance (`--source yahoo`, no key) |
| `ratio.py` | Relative-value engine: align asset/reference, ratio momentum & z-score reversion |
| `strategies.py` | Strategy interface + `sma` (crossover) and `rsi` (mean-reversion) |
| `backtest.py` | No-lookahead backtest engine with fees/slippage and metrics |
| `paper.py` | Live loop wrapping `kraken paper` (all-in long / all-out flat) |

## Strategies

- **`sma`** — long when the fast SMA is above the slow SMA, flat otherwise (`--fast`, `--slow`).
- **`rsi`** — buy when RSI dips below `--oversold`, sell when it rises above `--overbought` (`--period`).

Add your own: subclass `Strategy` in `strategies.py`, implement
`target_positions(closes) -> list[int]` (0/1), and register it in the `STRATEGIES` dict.
Both the backtest and live engines pick it up automatically.

## Case study: the ETH / Russell-2000 relative-value signal

A worked example of using the harness to vet a *novel* idea — trading ETH off its ratio to an
equity risk index (`ratio` command) — and the methodology lessons that came out of it.

**The idea.** ETH is a high-beta risk asset. Small-caps (Russell 2000) are the purest risk-on/
risk-off barometer in equities. So `ETH-USD / ^RUT` momentum should track crypto's risk appetite —
and it does, beating buy & hold across a parameter sweep and beating Nasdaq/S&P as the denominator.

**The trap — raw returns lie across regimes.** On the full 2017→2026 sample the slow `50/200` and
`100/200` params posted gaudy returns (+900% to +1700%). But an out-of-sample split (fit 2017–22,
test 2023–26) showed they **collapsed** — the numbers were inflated by the 2020–21 parabolic bull
sitting in the training window. Raw total return measures *the market's generosity*, not the
strategy's skill.

**The fix — risk-adjusted, regime-neutral metrics.** Comparing **Sharpe** and the **buy-&-hold
return multiple** instead of raw return flips the verdict:

- The fast `20/50` param — which looked *worse* on raw OOS return — actually had **higher Sharpe,
  more than 2× the buy-&-hold multiple, and half the drawdown** out-of-sample. Its edge *grew*.
- Walk-forward (fixed `20/50` by calendar year) beat buy & hold on Sharpe in **7 of 9 years** — it
  only "lost" in the two parabolic bull years (2020, 2021), when nothing beats holding a vertical
  asset. In every bear/chop/normal year it won by cutting losses hard.
- Walk-forward *optimization* (re-pick best Sharpe on a rolling 3y train, trade it blind the next
  year) beat buy & hold in **5 of 6 test years**.

**The RSI exit-delay overlay (a validated improvement).** The base signal re-enters late and bails
on shallow dips, missing the first leg of recoveries (e.g. a 2025 whipsaw: sold $2,422 → rebought
$3,372). Adding a "let winners run" rule — *when the ratio flips to SELL but ETH's RSI is still
strong (>45), hold instead of exiting* — fixes exactly that. It held through the June 2025 dip and
rode ETH from ~$2,200 to a $4,200 exit, **with fewer trades, not more**. It survived out-of-sample
(Sharpe 1.36 vs base 1.10, 3.9× buy-hold) and walk-forward. Enable it with `--rsi-exit 45` on the
`ratio`, `signal`, and `chart` commands. *(What did NOT survive: oversold-RSI buy overrides and a
trailing-1yr-return filter — both mean-reversion ideas that fight the trend; tested, rejected.)*

**The takeaway.** The signal is real and robust — but it's a **drawdown-reducer / risk-adjusted-
return improver, not a return-maximizer.** It gives up a little in melt-ups and protects hard
everywhere else. And the bigger lesson: **never judge a backtest on raw total return** — always look
at CAGR, Sharpe, drawdown, and out-of-sample / walk-forward behavior. The engine now reports these
by default.

```bash
# Reproduce the robust signal:
python3 harness.py ratio --asset ETHUSD --reference '^RUT' --mode momentum --fast 20 --slow 50 --slippage 0.001
```

### Every strategy, head-to-head — $10,000 → ?

All strategies, same window (ETH-USD daily, 2017-11-09 → 2026-06-10, 3,135 days), same costs
(0.26% fee + 0.1% slippage per fill), sorted by final balance:

| Strategy | Final $ | Return | CAGR | Sharpe | Max DD | Trades |
|----------|--------:|-------:|-----:|-------:|-------:|-------:|
| **ETH/Russell momentum 20/50** ⭐ | **$198,453** | +1885% | +41.6% | 0.88 | −69% | 31 |
| ETH/S&P 500 momentum 20/50 | $158,137 | +1481% | +37.9% | 0.84 | −64% | 28 |
| ETH price SMA 20/50 | $132,996 | +1230% | +35.2% | 0.80 | −67% | 29 |
| ETH/Russell momentum 50/200 *(overfit)* | $100,543 | +905% | +30.8% | 0.76 | −77% | 7 |
| ETH price golden cross 50/200 | $67,883 | +579% | +25.0% | 0.68 | −78% | 8 |
| Buy & Hold ETH | $50,997 | +410% | +20.9% | 0.65 | **−94%** | 0 |
| ETH/Nasdaq momentum 20/50 | $46,985 | +370% | +19.7% | 0.61 | −73% | 33 |
| RSI(14) mean-reversion | $5,343 | −47% | −7.0% | 0.10 | −78% | 11 |
| ETH/Russell z-reversion *(disaster)* | $2,290 | −77% | −15.8% | −0.07 | −84% | 16 |

⭐ The only strategy that survived **both** out-of-sample and walk-forward validation.

**Reading it:** every *momentum* variant beat buy & hold, in the risk-appetite order the thesis
predicted (Russell > S&P > raw ETH > Nasdaq), and all of them roughly halved buy & hold's brutal
−94% drawdown. The robust ETH/Russell signal made **~4.6× more money than holding, with a third less
drawdown.** The *mean-reversion* variants lost money fighting a trending asset — knowing what
*doesn't* work is a result too. And the 50/200 entries are a reminder that a great full-sample
number (here $100k) can still be overfit; only out-of-sample testing tells them apart.

> ⚠️ Backtest results on one asset over one historical window. Not predictive, not advice, paper only.

## Visualize the signals (HTML chart)

Generate a self-contained, dark-themed candlestick chart with a green ▲ at every BUY and a red ▼
at every SELL, plus a stats header (return, Sharpe, drawdown, current stance):

```bash
# The robust ETH/Russell signal (default):
python3 harness.py chart --asset ETHUSD --reference '^RUT' --fast 20 --slow 50 --out eth_russell.html

# With the validated RSI exit-delay overlay (fewer trades, holds through shallow dips):
python3 harness.py chart --asset ETHUSD --reference '^RUT' --fast 20 --slow 50 --rsi-exit 45 --out eth_russell_overlay.html

# The price golden cross instead (reference 'none' -> plain price SMA crossover):
python3 harness.py chart --asset ETHUSD --reference none --fast 50 --slow 200 --out eth_golden_cross.html

open eth_russell.html   # macOS; or just open the file in any browser
```

Output is one portable `.html` file (candles + markers embedded as JSON, charting lib from CDN) —
no build step, no dependencies. Generated charts are git-ignored since they're regenerable.

## Daily signal monitor (GitHub Actions)

A scheduled workflow (`.github/workflows/daily-signal.yml`) checks the validated ETH/Russell signal
(with the RSI exit-delay overlay) once a day and **opens a GitHub issue when the stance flips**
(FLAT ↔ LONG) — so you get an email without running anything yourself.

```bash
# Check the live stance yourself anytime (same config the monitor uses):
python3 harness.py signal --asset ETHUSD --reference '^RUT' --fast 20 --slow 50 --rsi-exit 45
python3 harness.py signal --rsi-exit 45 --json   # machine-readable (what the workflow consumes)
```

- Runs daily at 13:00 UTC (and on-demand via the Actions tab).
- Compares the current stance to `state/last_signal.json`; on a change it opens an issue and commits
  the new state (no commit on unchanged days, so no daily noise).
- Stdlib + Yahoo only — no secrets, no API keys. Uses the built-in `GITHUB_TOKEN`.
- Informational only — it does **not** place trades.

> Note: GitHub disables scheduled workflows after ~60 days of repo inactivity; push or re-enable to resume.

## Design notes & caveats

- **No look-ahead:** the position decided at candle *i-1*'s close is executed at candle *i*'s open.
- **Fees & slippage** are applied on every fill; buy & hold is charged the same fees for a fair comparison.
- **Risk-adjusted metrics** (CAGR, annualized Sharpe, max drawdown, buy-&-hold multiple) are reported
  alongside raw return — because raw return alone is misleading across regimes (see the case study above).
- **Long-only** (spot) — positions are all-in cash→asset or all-out asset→cash. A small (0.1%) cash
  buffer covers price drift between the quoted candle and the live market fill.
- **Kraken OHLC history is bounded** (~720 candles per request), so daily candles only cover ~2
  years. For long-horizon backtests (e.g. the golden cross from 2017), use `--source yahoo`, which
  pulls full daily history from Yahoo Finance (ETH-USD from late 2017). Live trading stays Kraken-only.
- **Not financial advice. Paper trading only.** This is a learning/experimentation harness, not a
  production trading system — there is no risk management, position sizing, or order-retry logic.

## Future ideas

- More strategies (MACD, Bollinger bands, momentum) and parameter sweeps.
- Equity-curve export/plot; multi-strategy leaderboard.
- Fractional position sizing and stop-losses.
- Persisted backtest runs for comparison over time.
