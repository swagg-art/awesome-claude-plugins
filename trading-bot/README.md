# tbot — a backtest-first trading research harness

**Status: research harness validated. No strategy has been validated. Not
approved for real money, and nothing here should be run with real money
until the checklist at the bottom is complete.**

## What this is

A test rig built to *disprove* trading strategies. It exists because the
usual failure mode is not a bad strategy — it is a backtest that lies, and
a strategy that was never tested against the costs it will actually pay.

## Assumptions made (these resolve contradictions in the original spec)

| Spec item | Resolution |
|---|---|
| "1% risk" + "0.03 lots" | **Mutually exclusive — implemented 1% risk.** Lot size is derived per trade from equity and ATR stop distance; it is never fixed. `RiskConfig.risk_pct = 0.01`. |
| "previous trade lower than current" | Read as **swing structure**, not prior trade P&L. Longs require confirmed higher-high *and* higher-low (`indicators.structure_state`). Re-specify if you meant something else. |
| "convergence of many indicators" | Implemented as **four structurally independent gates**, not stacked oscillators. See `strategies/trend_breakout.py` docstring for why five momentum oscillators is one signal, not five. |
| "indicators most winning traders use" | No such validated set exists publicly. Built on **time-series momentum**, the best-replicated anomaly in FX/futures, instead of indicator folklore. |
| ATR / RRR | As specified. Stop = 2×ATR(14), target = 2×stop. Both configurable. |

## Honesty guarantees built into the engine

These are enforced in code, not promised in a README:

1. **No same-bar fills.** Signal from bar *t* close, filled at bar *t+1* open.
2. **No look-ahead in swings.** Fractal swings are reported at their
   *confirmation* bar, k bars late. The naive centred-window version leaks
   future data into every signal and is responsible for a large share of
   "profitable" retail backtests.
3. **Donchian excludes the current bar** — a breakout is not detectable on
   the bar that creates it.
4. **Pessimistic intrabar resolution.** If a bar's range contains both the
   stop and the target, the stop is assumed hit first. OHLC cannot tell you
   the order; assuming the good outcome is self-deception.
5. **Gaps fill at the open**, not at the stop level.
6. **Spread and slippage are charged on entry and exit**, and reported
   as a separate line rather than hidden inside fill prices.

## Validation performed

Run `python3 tests/test_engine_null.py` and `python3 run_controls.py`.

- **Null control**: random entries on a driftless random walk lose money,
  approximately the cost total. An engine that profits here has a
  look-ahead bug.
- **Frictionless null**: with costs zeroed, the same test lands near
  breakeven, confirming the loss above is costs and not a bias.
- **Risk unit**: median stop-out costs ~0.8–1.0% of equity, as specified.
- **Positive control**: on synthetic data containing a real trend, the
  strategy finds it — confirming it is not merely inert.

## The finding that matters

`python3 sweep_strength.py` measures how much real trend is needed before
the edge survives costs, on EURUSD retail assumptions (1.2 pip spread,
$3.50/lot commission, 0.5 pip slippage):

```
 trend | net w/costs     PF   win%     n | net NO costs     PF
  0.00 |       -6.9%   0.94  33.7%   154 |         9.0%   1.08
  0.01 |      -10.6%   0.91  32.7%   156 |         3.3%   1.02
  0.02 |       -8.3%   0.93  33.1%   158 |         7.5%   1.05
  0.03 |       -1.7%   0.98  34.6%   162 |        14.0%   1.10
  0.05 |       23.2%   1.19  38.9%   167 |        40.7%   1.31
  0.08 |       79.5%   1.62  45.3%   183 |       110.5%   1.81
```

**Costs consume roughly 0.12 of profit factor.** Any strategy that does not
clear ~1.15 profit factor *before* costs is a losing strategy after them.
Three of the six rows above show a frictionless profit turning into a real
loss. That is the entire game, and it is why a backtest without a cost
model is worthless.

## Not yet done — do not skip these

- [ ] Validated on **real** FX/crypto history (blocked: see below)
- [ ] Walk-forward out-of-sample testing
- [ ] Parameter sensitivity (an edge that needs exact parameters is curve-fit)
- [ ] Monte Carlo trade-order reshuffling for drawdown distribution
- [ ] Broker/exchange execution adapter
- [ ] Paper trading over a meaningful period
- [ ] Live deployment guards: kill switch, max daily loss, reconnect logic

## Layout

```
tbot/
  indicators.py   causal indicators; swing detection with confirmation lag
  instruments.py  contract specs, spreads, commissions, funding
  risk.py         ATR stops, fixed-fractional 1% sizing
  costs.py        spread, slippage, commission, funding
  engine.py       bar loop, pessimistic fills
  metrics.py      CAGR, Sharpe, Sortino, DD, profit factor, cost drag
  synthetic.py    null and positive control data generators
  strategies/     trend_breakout.py
tests/            engine null-hypothesis tests
```
