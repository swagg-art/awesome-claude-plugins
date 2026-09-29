#!/usr/bin/env python3
"""Rule-based technical signals for PrimeXBT-style instruments.

Pure standard library. Reads OHLC candles and prints a signal per symbol:
trend (EMA 10/30), momentum (MACD 12/26/9), RSI(14), a 20-bar Donchian
breakout check, and ATR(14)-based stop / target levels.

Input (one or more files, any mix of formats):
  * CSV with header  t,o,h,l,c   (symbol = file stem, e.g. BTCUSD.csv)
  * JSON {"SYMBOL": [{"t":..,"o":..,"h":..,"l":..,"c":..}, ...], ...}
  * Raw Crypto.com get_candlestick output {"instrument_name": .., "data": [..]}

Usage:
  signals.py data/*.csv                 # markdown table
  signals.py data/*.csv --json          # machine-readable
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

MIN_BARS = 35  # MACD(12,26,9) needs 26 + 9 bars


def load(path: Path) -> dict[str, list[dict]]:
    text = path.read_text()
    if path.suffix.lower() == ".csv":
        rows = list(csv.DictReader(text.splitlines()))
        return {path.stem.upper(): [_bar(r) for r in rows]}
    doc = json.loads(text)
    if "data" in doc and "instrument_name" in doc:
        sym = doc["instrument_name"].replace("_", "").upper()
        return {sym: [_bar(r) for r in doc["data"]]}
    return {k.upper(): [_bar(r) for r in v] for k, v in doc.items()}


def _bar(r: dict) -> dict:
    get = lambda *keys: next(r[k] for k in keys if k in r)
    return {
        "t": str(get("t", "timestamp")),
        "o": float(get("o", "open")),
        "h": float(get("h", "high")),
        "l": float(get("l", "low")),
        "c": float(get("c", "close")),
    }


def ema(values: list[float], n: int) -> list[float]:
    k = 2 / (n + 1)
    out = [sum(values[:n]) / n]
    for v in values[n:]:
        out.append(v * k + out[-1] * (1 - k))
    return [float("nan")] * (n - 1) + out


def rsi(closes: list[float], n: int = 14) -> float:
    gains = losses = 0.0
    for a, b in zip(closes[:n], closes[1 : n + 1]):
        d = b - a
        gains += max(d, 0)
        losses += max(-d, 0)
    avg_g, avg_l = gains / n, losses / n
    for a, b in zip(closes[n:], closes[n + 1 :]):
        d = b - a
        avg_g = (avg_g * (n - 1) + max(d, 0)) / n
        avg_l = (avg_l * (n - 1) + max(-d, 0)) / n
    return 100.0 if avg_l == 0 else 100 - 100 / (1 + avg_g / avg_l)


def atr(bars: list[dict], n: int = 14) -> float:
    trs = [
        max(b["h"] - b["l"], abs(b["h"] - p["c"]), abs(b["l"] - p["c"]))
        for p, b in zip(bars, bars[1:])
    ]
    val = sum(trs[:n]) / n
    for tr in trs[n:]:
        val = (val * (n - 1) + tr) / n
    return val


def analyse(symbol: str, bars: list[dict]) -> dict:
    bars = sorted(bars, key=lambda b: b["t"])
    if len(bars) < MIN_BARS:
        raise ValueError(f"{symbol}: need >= {MIN_BARS} bars, got {len(bars)}")
    closes = [b["c"] for b in bars]
    last = closes[-1]

    ema_fast, ema_slow = ema(closes, 10)[-1], ema(closes, 30)[-1]
    macd_line = [f - s for f, s in zip(ema(closes, 12), ema(closes, 26))][25:]
    signal_line = ema(macd_line, 9)
    hist, hist_prev = macd_line[-1] - signal_line[-1], macd_line[-2] - signal_line[-2]
    r = rsi(closes)
    a = atr(bars)
    prior = bars[-21:-1]
    hi20, lo20 = max(b["h"] for b in prior), min(b["l"] for b in prior)

    score, reasons = 0, []

    def vote(cond_up: bool, cond_dn: bool, up: str, dn: str) -> None:
        nonlocal score
        if cond_up:
            score += 1
            reasons.append(up)
        elif cond_dn:
            score -= 1
            reasons.append(dn)

    vote(ema_fast > ema_slow, ema_fast < ema_slow, "EMA10 > EMA30", "EMA10 < EMA30")
    vote(last > ema_slow, last < ema_slow, "price above EMA30", "price below EMA30")
    vote(hist > 0, hist < 0, "MACD histogram positive", "MACD histogram negative")
    vote(hist > hist_prev, hist < hist_prev, "MACD momentum rising", "MACD momentum fading")
    vote(55 <= r < 70, 30 < r <= 45, f"RSI {r:.0f} bullish zone", f"RSI {r:.0f} bearish zone")
    vote(last > hi20, last < lo20, "20-bar breakout", "20-bar breakdown")

    warnings = []
    if r >= 70:
        warnings.append(f"RSI {r:.0f} overbought - avoid chasing longs")
    if r <= 30:
        warnings.append(f"RSI {r:.0f} oversold - avoid chasing shorts")

    if score >= 3:
        bias = "LONG"
    elif score <= -3:
        bias = "SHORT"
    else:
        bias = "NEUTRAL"

    sign = -1 if bias == "SHORT" else 1
    levels = None
    if bias != "NEUTRAL":
        levels = {
            "entry": last,
            "stop": last - sign * 1.5 * a,
            "tp1": last + sign * 1.5 * a,
            "tp2": last + sign * 3.0 * a,
        }

    return {
        "symbol": symbol,
        "as_of": bars[-1]["t"],
        "close": last,
        "bias": bias,
        "score": score,
        "confidence": round(abs(score) / 6, 2),
        "rsi14": round(r, 1),
        "atr14": a,
        "atr_pct": round(a / last * 100, 2),
        "ema10": ema_fast,
        "ema30": ema_slow,
        "macd_hist": hist,
        "range20": {"high": hi20, "low": lo20},
        "change_30d_pct": round((last / closes[-31] - 1) * 100, 2),
        "levels": levels,
        "reasons": reasons,
        "warnings": warnings,
        "closes": closes,
    }


def fmt(x: float) -> str:
    if x >= 1000:
        return f"{x:,.0f}"
    if x >= 10:
        return f"{x:,.2f}"
    return f"{x:.4f}"


def markdown(results: list[dict]) -> str:
    lines = [
        "| Symbol | Close | Bias | Score | RSI | ATR% | Entry | Stop | TP1 | TP2 |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        lv = r["levels"] or {}
        cells = [fmt(lv[k]) if lv else "-" for k in ("entry", "stop", "tp1", "tp2")]
        lines.append(
            f"| {r['symbol']} | {fmt(r['close'])} | {r['bias']} | {r['score']:+d} | "
            f"{r['rsi14']} | {r['atr_pct']} | " + " | ".join(cells) + " |"
        )
    lines.append("")
    for r in results:
        note = "; ".join(r["reasons"] + r["warnings"])
        lines.append(f"- **{r['symbol']}**: {note}")
    lines.append("")
    lines.append("_Educational analysis only, not financial advice. Leverage magnifies losses._")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("files", nargs="+", type=Path)
    p.add_argument("--json", action="store_true", help="emit JSON instead of markdown")
    args = p.parse_args(argv)

    series: dict[str, list[dict]] = {}
    for f in args.files:
        series.update(load(f))
    results = [analyse(s, b) for s, b in series.items()]

    if args.json:
        json.dump(results, sys.stdout, indent=2)
        print()
    else:
        print(markdown(results))
    return 0


if __name__ == "__main__":
    sys.exit(main())
