---
description: Review the Liquid account — exposure, stops, liquidation distance and concentration.
---

Read-only account review. Do not propose or place anything.

1. Call `get_portfolio`.
2. Map each position into `{symbol, side, notional, entry, mark, leverage, stop_loss}`
   and pass them to `liquid_assistant.review_portfolio` with the account equity
   and available balance.
3. Report, in this order:
   - **Positions with no stop.** Always first. Give the notional at risk and the
     approximate liquidation price, which is the stop they are using whether
     they meant to or not.
   - **Anything within 5% of liquidation.**
   - **Account gross leverage**, with the total notional against equity.
   - **Concentration** — several positions on assets that move together is one
     bet, not several.
4. Finish with at most three things worth doing, ranked by how much money each
   concerns.

If the account is flat, say so in one line and stop.

Do not suggest trades. This command reviews risk; it does not generate ideas.
