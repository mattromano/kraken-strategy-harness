"""Generate a self-contained HTML candlestick chart with buy/sell markers.

Renders OHLC candles for the asset and overlays a green BUY arrow / red SELL
arrow at each point where the strategy's position flips. Uses TradingView's
lightweight-charts from a CDN so the output is a single portable .html file.

Strategy plotted:
  - reference given (e.g. ^RUT)  -> ratio-momentum (asset/reference) fast/slow SMA
  - reference "none"/empty       -> price SMA crossover on the asset itself (golden cross)
"""

from __future__ import annotations

import datetime as dt
import json

from data import Candle
from data_yahoo import fetch_ohlc_yahoo, to_symbol
from ratio import align_ratio
from strategies import SmaCrossover
from backtest import run_backtest


def _date(ts: int) -> str:
    return dt.datetime.utcfromtimestamp(ts).date().isoformat()


def build_chart_data(asset_pair: str, reference: str, fast: int, slow: int,
                     split_pair, fee: float = 0.0026, slippage: float = 0.001):
    """Return (candles, positions, result, meta) for charting."""
    base, quote = split_pair(asset_pair)
    asset_sym = to_symbol(asset_pair, base, quote)
    asset = fetch_ohlc_yahoo(asset_sym, 1440)

    use_ratio = bool(reference) and reference.lower() != "none"
    if use_ratio:
        ref = fetch_ohlc_yahoo(reference, 1440)
        candles, series = align_ratio(asset, ref)
        strat_label = f"{asset_sym} / {reference} ratio momentum  {fast}/{slow}"
    else:
        candles = asset
        series = [c.close for c in candles]
        strat_label = f"{asset_sym} price SMA crossover  {fast}/{slow}"

    positions = SmaCrossover(fast, slow).target_positions(series)
    result = run_backtest(candles, positions, fee=fee, slippage=slippage)
    meta = {
        "asset": asset_sym,
        "strat_label": strat_label,
        "use_ratio": use_ratio,
    }
    return candles, positions, result, meta


def _markers(candles: list[Candle], positions: list[int]) -> list[dict]:
    """One marker per position flip: BUY (enter long) / SELL (exit)."""
    out = []
    for i in range(1, len(positions)):
        if positions[i] == positions[i - 1]:
            continue
        if positions[i] == 1:
            out.append({"time": _date(candles[i].ts), "position": "belowBar",
                        "color": "#26a69a", "shape": "arrowUp",
                        "text": f"BUY ${candles[i].close:,.0f}"})
        else:
            out.append({"time": _date(candles[i].ts), "position": "aboveBar",
                        "color": "#ef5350", "shape": "arrowDown",
                        "text": f"SELL ${candles[i].close:,.0f}"})
    return out


def render_html(candles: list[Candle], positions: list[int], result, meta) -> str:
    ohlc = [{"time": _date(c.ts), "open": c.open, "high": c.high,
             "low": c.low, "close": c.close} for c in candles]
    markers = _markers(candles, positions)
    current = "LONG (holding)" if positions[-1] == 1 else "FLAT (in cash)"
    stance_color = "#26a69a" if positions[-1] == 1 else "#ef5350"
    span = f"{_date(candles[0].ts)} → {_date(candles[-1].ts)}"

    stats = [
        ("Strategy return", f"{result.total_return * 100:+.0f}%"),
        ("Buy &amp; hold", f"{result.buy_hold_return * 100:+.0f}%"),
        ("CAGR", f"{result.cagr * 100:+.1f}%"),
        ("Sharpe", f"{result.sharpe:.2f}"),
        ("Max drawdown", f"{result.max_drawdown * 100:.0f}%"),
        ("Trades", f"{result.num_trades}"),
    ]
    stat_html = "".join(
        f'<div class="stat"><div class="k">{k}</div><div class="v">{v}</div></div>'
        for k, v in stats
    )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{meta['asset']} — strategy signals</title>
<script src="https://unpkg.com/lightweight-charts@4.1.3/dist/lightweight-charts.standalone.production.js"></script>
<style>
  :root {{ color-scheme: dark; }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; background: #0d1117; color: #e6edf3;
         font: 14px/1.4 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
  header {{ padding: 16px 20px 10px; border-bottom: 1px solid #21262d; }}
  h1 {{ margin: 0 0 2px; font-size: 17px; font-weight: 650; }}
  .sub {{ color: #8b949e; font-size: 12.5px; }}
  .stance {{ display: inline-block; margin-left: 8px; padding: 1px 8px; border-radius: 999px;
             font-size: 11.5px; font-weight: 600; background: {stance_color}22; color: {stance_color};
             border: 1px solid {stance_color}55; }}
  .stats {{ display: flex; flex-wrap: wrap; gap: 22px; padding: 12px 20px; border-bottom: 1px solid #21262d; }}
  .stat .k {{ color: #8b949e; font-size: 11px; text-transform: uppercase; letter-spacing: .4px; }}
  .stat .v {{ font-size: 17px; font-weight: 650; margin-top: 1px; }}
  .legend {{ display: flex; gap: 16px; padding: 8px 20px; color: #8b949e; font-size: 12px; align-items: center; }}
  .legend b {{ font-weight: 600; }}
  .up {{ color: #26a69a; }} .down {{ color: #ef5350; }}
  #chart {{ width: 100%; height: calc(100vh - 190px); }}
  footer {{ padding: 8px 20px; color: #6e7681; font-size: 11.5px; border-top: 1px solid #21262d; }}
</style>
</head>
<body>
  <header>
    <h1>{meta['asset']} <span class="stance">{current}</span></h1>
    <div class="sub">{meta['strat_label']} &nbsp;·&nbsp; {span} &nbsp;·&nbsp; 0.26% fee + 0.1% slippage</div>
  </header>
  <div class="stats">{stat_html}</div>
  <div class="legend">
    <span><b class="up">▲ BUY</b> — strategy enters long (signal turns on)</span>
    <span><b class="down">▼ SELL</b> — strategy exits to cash (signal turns off)</span>
  </div>
  <div id="chart"></div>
  <footer>Backtest visualization · informational only, not financial advice · paper/research</footer>
<script>
  const candles = {json.dumps(ohlc)};
  const markers = {json.dumps(markers)};
  const chart = LightweightCharts.createChart(document.getElementById('chart'), {{
    layout: {{ background: {{ color: '#0d1117' }}, textColor: '#c9d1d9' }},
    grid: {{ vertLines: {{ color: '#161b22' }}, horzLines: {{ color: '#161b22' }} }},
    rightPriceScale: {{ borderColor: '#21262d' }},
    timeScale: {{ borderColor: '#21262d', timeVisible: false }},
    crosshair: {{ mode: LightweightCharts.CrosshairMode.Normal }},
  }});
  const series = chart.addCandlestickSeries({{
    upColor: '#26a69a', downColor: '#ef5350', borderVisible: false,
    wickUpColor: '#26a69a', wickDownColor: '#ef5350',
  }});
  series.setData(candles);
  series.setMarkers(markers);
  chart.timeScale().fitContent();
  window.addEventListener('resize', () => chart.timeScale().fitContent());
</script>
</body>
</html>
"""
