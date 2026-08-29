# Findings log

Append-only record. Negative results stay in.

## Round 1 — EURUSD H1, 2024 IS / 2025 OOS

- Trend breakout: 21/956 parameter cells profitable (2.2%), median PF 0.649.
  Loses at zero cost. No edge.
- Variance ratio on EURUSD 2024: VR < 1 at every horizon, z = -4.76 at q=4.
  Market is MEAN-REVERTING. Trend system was structurally mismatched.
- Mean reversion: 195/691 cells profitable (28.2%), median PF 0.892.
  Dominant parameter is stop width (51% profitable at 3.0 ATR vs 6% at 1.0).
- Config locked from marginal effects, NOT the best cell. OOS run once.
- **RESULT: IS +11.53% (PF 1.19) -> OOS -5.15% (PF 0.92).** Negative at zero
  cost. No edge.

## Round 2 — USDJPY H1 2025, zero-shot cross-instrument

No parameter refitted. EURUSD-locked config applied as-is.

- Variance ratio on USDJPY 2025: VR > 1, z = +2.70 (q=2), +2.86 (q=4).
  Market is TRENDING - opposite character to EURUSD 2024.
- Mean reversion (built for reverting tape): -13.65%, PF 0.78. Fails, as the
  character predicts.
- Trend breakout (defaults, never tuned on this): +5.39%, PF 1.10, 82 trades.

### The result is NOT significant

    t-stat on mean trade P&L         +0.411   (need 1.99 at n=82)
    bootstrap 95% CI on total P&L    [-$1,889, +$3,193]   straddles zero
    P(total P&L <= 0)                35.0%
    random-timing controls beating it 90/400  (p = 0.225)

Mean P&L $6.57/trade against sd $144.74. **Treated as noise, not edge.**

### What is worth carrying forward

The hypothesis that strategy family should be selected by *measured* market
character (variance ratio), rather than by preference, predicted the correct
strategy in both markets tested. That is 2 observations. It is a hypothesis
worth testing properly, not a finding.

Testing it needs many instrument-years: measure VR on a trailing window,
select the strategy family from it, trade forward, repeat. That is a
walk-forward regime-switching test and it needs roughly 10+ years across
5+ instruments before the result would mean anything.

## Still untested
- Session/time-of-day filters
- Crypto (different microstructure)
- Walk-forward across many regimes
- Real broker cost schedule (still unknown)

## Round 3 — EURUSD 2023 added (three years now)

EURUSD 2023 measures as a **random walk**: no significant variance ratio at
any horizon, either direction. lag-1 autocorr -0.0043.

### The regime hypothesis made a prediction and it FAILED

Prediction: in a year with neither trending nor reverting character, both
strategies should lose roughly their costs.

Observed: mean reversion returned **+14.30%** (PF 1.28, 104 trades).
Trend breakout returned -11.02%, as expected. The prediction is half wrong,
which is enough to reject it as stated. Regime character does not cleanly
determine which strategy family works.

### Pooled out-of-sample — 2024 (tuning year) EXCLUDED

Mean reversion, locked config, on 2023 + 2025 only:

    trades                 226
    total P&L              +$915.50
    mean per trade         +$4.05   (sd $103.57)
    t-statistic            +0.588   (need 1.97)
    bootstrap 95% CI       [-$2,177, +$3,926]
    P(total P&L <= 0)      27.6%
    pooled profit factor   1.082
    pooled win rate        52.7%

Positive expectancy, NOT statistically distinguishable from zero.
This is neither a confirmed edge nor a refuted one. It is an unresolved one.

### The finding that reframes the whole project

Power analysis on the observed effect (mean $4.05, sd $103.57):

    80% power needs   5,133 trades   =  45 pair-years
    90% power needs   6,872 trades   =  61 pair-years
    currently have      226 trades   = 4.4% of requirement

With 226 trades, the smallest edge confirmable is $19.30/trade (~PF 1.41).
The observed edge is 4.8x smaller than that floor.

**A single currency pair cannot settle this question in a human lifetime.**
At ~113 trades/pair/year:

    pairs    years of data needed
        1          45.4
        4          11.4
        8           5.7
       12           3.8
       20           2.3

The path forward is BREADTH, not depth. Eight pairs and six years is a
tractable ask; forty-five years of EURUSD is not.

### Data quality note
EURUSD 2023 has 5,409 H1 bars vs 6,225 for 2025 - 13.1% fewer, and 731 M1
gaps vs 54-112 in other files. Coverage in that file is thinner. Treat the
2023 result as slightly weaker evidence than the others.

## Round 4 — GBPUSD 2020-2023, 2025 (fresh pair, zero tuning)

Locked mean-reversion config applied unchanged to a pair never used for
tuning, across five years.

    year   character      mean-rev    PF    n  |    trend    PF    n
    2020   reverting        -3.95%  0.93  118  |   +1.86%  1.04   73
    2021   random           +4.36%  1.08  114  |  -23.53%  0.52   72
    2022   reverting        -2.89%  0.95  130  |   +1.39%  1.03   68
    2023   random          +10.04%  1.22   97  |  -18.43%  0.57   57
    2025   random          -23.07%  0.64  125  |   +7.26%  1.20   56

GBPUSD pooled, mean reversion: 584 trades, -$1,550.63, PF 0.946,
mean -$2.66/trade, t = -0.672, P(total <= 0) = 74.7%.
GBPUSD pooled, trend breakout: 326 trades, -$3,143.75, PF 0.858,
mean -$9.64/trade, t = -1.307, P(total <= 0) = 90.2%.

### Regime hypothesis fails a second time
2020 and 2022 both measured as MEAN-REVERTING, and mean reversion lost
money in both (-3.95%, -2.89%). Character does not predict which family
works. The hypothesis is now rejected on two independent occasions and
should not be revived without a new mechanism.

## GRAND POOLED OUT-OF-SAMPLE — the answer

Every trade never used for tuning. EURUSD 2023+2025, GBPUSD 2020-2023+2025.
EURUSD 2024 (the tuning year) excluded.

    trades                810
    total P&L             -$635.12
    mean per trade        -$0.78   (sd $97.84)
    profit factor         0.984
    win rate              50.4%
    t-statistic           -0.228   (need 1.96)
    bootstrap 95% CI      [-$6,085, +$4,792]
    P(total P&L <= 0)     58.9%

Sample is 3.6x the EURUSD-only pool that showed PF 1.082. The earlier
positive reading did not survive expansion - it regressed to 0.984, i.e.
to breakeven-minus-costs. That is exactly what a strategy with no edge
looks like once the sample is large enough to stop flattering it.

**CONCLUSION: no edge. The mean-reversion result on EURUSD was sample
noise. It is not worth trading, on demo or otherwise, in its current form.**

## What is now established
- Neither strategy family shows an edge on EUR/USD or GBP/USD, H1, across
  7 instrument-years and 810 out-of-sample trades.
- Market character (variance ratio) does not select the winning family.
- With 810 trades the smallest confirmable edge is $9.63/trade. Observed:
  -$0.78. The result is not merely unconfirmed - it is centred on zero.

## Data quality note
2023 files for BOTH pairs show ~13% fewer bars and 724-731 M1 gaps vs 53-54
in every other year. This is systematic to HistData's 2023 archives.
