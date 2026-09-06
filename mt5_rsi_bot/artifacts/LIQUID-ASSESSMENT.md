# What a Liquid version would take

**Date:** 2026-09-06
**Question:** could `mt5_rsi_bot` be rebuilt against Liquid (the Co-Invest
connector) instead of MetaTrader 5?
**Short answer:** not as a bot. Liquid has no unattended execution path, and
the only strategy its data can support is the one that loses money.

## The blocker: there is no programmatic execution

This is not a limitation to engineer around. It is how the connector is
deliberately built.

| Tool | What its own description says |
| --- | --- |
| `execute_order` | *"INTERNAL: Called by confirmation widgets when the user presses Confirm. **Do not call directly.**"* |
| `suggest_trade` | *"The user must press Confirm to execute — **a suggestion is NOT an execution**."* |
| `execute_tpsl` | *"SYSTEM INTERNAL — the model must **NEVER** call this tool directly."* |
| closing a position | *"there is no direct close tool available to you — the portfolio widget renders per-position Close buttons **that the user presses**."* |

Every state-changing action requires a human pressing a button in a widget.
That is a sound design for an AI trading assistant and a complete blocker for
an unattended process.

`mt5_rsi_bot` runs headless under systemd, wakes every 15 seconds, and acts on
a closed candle without anyone present. There is no version of that on Liquid.
A Liquid "bot" would sit waiting for a human to approve each entry and each
exit — at which point it is not a bot, it is a chat assistant with an opinion.

Worth noting what this costs beyond convenience: **stops.** The MT5 bot attaches
`sl` and `tp` to the order itself, so a dropped connection cannot leave a
position unprotected. On Liquid the protective exit depends on a human being
awake to press Close, or on TP/SL set through a confirmation widget. For a
strategy whose entire risk model is "the stop is where the idea is wrong", that
is a material downgrade.

## Second blocker: no candle series, so v2 cannot run

The strategy that actually works here — the confirmed v2 at PF 1.193 — needs
OHLC history on every bar for three things:

- **RSI divergence**: swing highs and lows in price against the same in RSI
- **Candlestick patterns**: engulfing, hammer, star — each reads 2–3 raw bars
- **Structure stops**: the stop goes behind the swing the setup formed on

Liquid gives none of that:

- `get_technical_indicators` returns **latest values only** — it used 810
  candles internally and handed back `{"rsi14": 54.49, "atr14": 105.71}`.
- `show_chart` caps at **200 candles** and renders a visual widget.

So the only strategy computable from Liquid's data is **v1**: the bare RSI
threshold cross. That is the version measured at **profit factor 0.533, −$255**,
with **0 of 12** parameter combinations profitable out of sample.

The one strategy Liquid can run is the one already proven to lose money. That is
the finding that settles this.

## Third issue: paper trading is off, and it routes live

```
Paper trading is DISABLED. Trades route to the live Liquid API.
```

There is an `enable_paper_trading` tool, so the mode exists. But as things
stand, any Liquid experiment is real money on the first trade. The MT5 bot
defaults to `readonly`, has a `paper` mode, and requires a typed confirmation
before live. Liquid's safety comes from the human in the loop instead — which
works, but is a different model and cannot be tested against.

## Fourth issue: it is a different instrument

Liquid BTC is a **perpetual future at up to 40x leverage**, not a CFD.

| | MT5 (`mt5_rsi_bot`) | Liquid |
| --- | --- | --- |
| Instrument | broker CFD | perpetual future |
| Sizing | fixed `LOT_SIZE` (0.01) | USD notional, min $15 collateral × leverage |
| Leverage | broker default | explicit, up to 40x |
| Ongoing cost | swap/financing | **funding rate**, typically every 8h |

The funding rate matters more than it looks. The v2 strategy holds for an
average of **27 bars**. On daily bars that is 27 days — roughly 81 funding
payments. The backtester **does not model funding at all**, so the +$189 result
would be materially worse on a perp and could plausibly go negative. On M15 the
holds are far shorter and this matters much less, which is one more reason the
M15 test is the one that counts.

Sizing would also need rewriting end to end: everything in `config.py`,
`strategy.py` and `backtest.py` reasons in lots against a `point` size. Notional
sizing with leverage is a different risk model, not a units conversion.

## What Liquid is genuinely good for

Not nothing — it has already earned its place twice today:

1. **Independent verification.** It confirmed our RSI(14) at 66.43 against its
   66.71, and flagged `latestCandleForming: true`, corroborating the repaint
   hazard the bot is built to avoid. See `INDICATOR-VALIDATION.md`.
2. **Live market state.** `analyze_market` gives real-time price, funding, open
   interest and positioning across equities, commodities, indices and crypto —
   things MT5 does not surface and the bot has no access to.
3. **Breadth.** 40x-capable markets well beyond one broker's symbol list.

## Recommendation

**Do not port the bot to Liquid.** Two independent blockers, either of which
is fatal on its own: no unattended execution, and no candle series for the only
strategy that works.

If the appeal of Liquid is that it is where you can actually trade, the honest
framing is that it is a **different product**:

- **`mt5_rsi_bot`** — unattended, rule-bound, stops attached at the broker,
  nobody watching. What exists today.
- **A Liquid assistant** — analyses on demand, proposes a trade with reasoning,
  you approve or decline. Human in the loop by design.

The second is a legitimate thing to build and Liquid is well shaped for it. But
it shares almost no code with the bot: no execution loop, no daily-loss guard
(a human is present), no lot sizing, no systemd unit. The reusable parts are
`strategy.py`'s pure functions and the backtester — and the backtester still
needs candle history Liquid will not give.

**Cheapest next step is unchanged:** get M15 history and run
`./analyse.sh`. If the confirmed strategy holds up on a real sample there, the
execution venue is worth arguing about. If it does not, the venue question never
needed answering.
