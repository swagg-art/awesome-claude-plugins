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
