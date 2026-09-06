# Liquid Assistant — build summary

**Date:** 2026-09-06
**Location:** `liquid_assistant/` (new sub-project)

Built the human-in-the-loop assistant recommended in
`../mt5_rsi_bot/artifacts/LIQUID-ASSESSMENT.md`, after that assessment
established an unattended bot is impossible on Liquid.

## What it is

A Python package of pure risk arithmetic plus a Claude Code plugin. It does the
part Liquid's own tools do not: converting a risk budget into the USD notional
and leverage `suggest_trade` expects, and refusing trades where leverage would
liquidate the position before the stop is reached.

- `sizing.py` — `size_trade`, `liquidation_price`
- `funding.py` — `estimate_funding`, `break_even_hold_hours`
- `review.py` — `review_portfolio`
- `plugin/` — the `liquid-trade` skill, `/liquid-review`, `/liquid-setup`

## The idea it is built around

Two constraints pull against each other, and both are easy to get backwards:

| | |
| --- | --- |
| **The stop sets the size** | notional = risk ÷ stop distance. A *tighter* stop means a *larger* position. |
| **Leverage sets the liquidation point** | at 40x the exchange closes you after roughly a 2% move. |

Together: a 3% stop on 40x is a stop that will never be reached. The position is
closed by the venue before the idea has been proven wrong.

So leverage is chosen as the **lowest** value that fits the available collateral,
which maximises the distance to liquidation. Verified across stop widths from
0.5% to 10% that liquidation always sits beyond the stop.

## Refusals name the exact remedy

A refusal is an answer, not a failure. Each computes what would actually work:

> risking 2% of 10,000.00 on a 0.50% stop needs $40,000.00 of exposure, which
> even at the 40x ceiling requires $1,000.00 collateral against $300.00
> available. **At this stop distance the most you can risk is 0.60%.**

> No stop width fixes this: keeping liquidation 2x beyond the stop needs at least
> 2x the risk budget in collateral ($400.00) and only $300.00 is available.
> **Risk at most 1.48%, or fund the account.**

The second case is worth noting: when `risk × buffer > available balance`, no
stop width helps at all, because that term does not depend on the stop. The
module detects this and says so instead of suggesting a wider stop that would
not work.

Two tests take the number each refusal names and check it produces a sizeable
trade. Advice that reads well but does not work is worse than none.

## Bugs caught while building

1. **The advice was backwards.** Both refusals originally said "use a tighter
   stop". Since notional = risk ÷ stop distance, tightening *raises* the
   collateral needed — it makes both failure modes worse. Now they compute the
   remedy rather than gesturing at one.
2. **The README example was fabricated.** It claimed `$41,808 notional at 8.4x`
   where the code actually returns `$4,181 at 1x` — an order of magnitude out.
   Every example in the README is now pasted from a real run.

## Verification

| Check | Result |
| --- | --- |
| `python -m unittest discover -s tests` | **44 tests OK**, no dependencies |
| `ruff check src tests` | clean |
| Liquidation beyond stop, 0.5%–10% stop widths | holds at every width |
| Stop actually costs the risk budget | verified by recomputation |
| Each refusal's suggested remedy | tested to produce a valid trade |
| README examples | pasted from real output |

## Limits

- **Liquidation is approximate.** Liquid does not publish its maintenance-margin
  schedule through the connector, so 0.5% is assumed and fees and funding are
  ignored — all of which bring liquidation *closer*. It is a ceiling on how far
  price can move, not an exact level.
- **Funding rates must be supplied**, from `analyze_market`. They float.
- **No candle series** from Liquid, so anything needing bar history cannot be
  computed. This is why the confirmed MT5 strategy cannot run here.
- **Paper trading is disabled** on the account tested. Confirm means real money,
  and the skill says so before the first proposal.

## What it deliberately does not do

Execute. `execute_order` and `execute_tpsl` are internal tools belonging to
Liquid's confirmation widgets, and the skill instructs the model never to call
them. Every trade requires the user to press Confirm.

That is not a limitation worked around — it is the product. The unattended
version is `mt5_rsi_bot`, on MetaTrader, for exactly this reason.
