# Summary Report: "10 Viral Trading Strategies Backtested" (YouTube pAqir3dQfQs)

Source: https://youtu.be/pAqir3dQfQs (summarized from the video's transcript)

## Premise
The creator coded 10 popular YouTube trading strategies into bots and ran them on six years of market data. Ranked worst to best on: did the creator's own rules make money, on how many markets, and could the strategy be fixed.

## Headline result
- 9 of 10 failed. Only one (#1) made money on every market tested.
- Recurring finding: the claimed win rate is not what matters; the exit is the edge.

## Ranking (worst to best)
| # | Strategy | Result |
|---|----------|--------|
| 10 | 15-min strategy (4H bias, 15m sweep, 71% Fib entry) | 6/6 tests lost; GBPCAD target -92% ($10k to under $800) |
| 9 | "Sniper entries" (FVG inside order block) | 2,372 trades, 29% win rate, -500R after costs; a 1-min structure-shift filter cut losses >90% |
| 8 | ICT Silver Bullet (7 YouTubers) | 21 tests, 31,000 trades: 18 lost, 3 flat; ICT's own version -357R |
| 7 | Heikin Ashi + 100 EMA + doji | Claimed 75% win rate; real 47.6% over 4,100 trades; all 3 markets lost |
| 6 | Daily sweep (Jade Cap) | 18 tests, 17 lost, none hit 50% win rate; only survivor held to session close (+6.5%, 36% win rate) |
| 5 | TJR | +61% by Jan 2024, then gave it back; final +0.6%; start 2021 = +1%, start 2024 = -35% |
| 4 | Opening 15-min box fake-break reversal | Best win rate 56%; own exit lost more than it made, but never blew up; Nasdaq 5m held up |
| 3 | Pattern Scalp | 3 of 6 tests profitable; best Dow +31.9%, worst Nasdaq with partials -67%; exit decided everything |
| 2 | Alex G | Exact rules ~flat; Asia-session-only repair +46.8R and 13 prop-firm payouts |
| 1 | Patrick Whelan 15-min opening range | Only strategy profitable on all 3 markets (+130R combined); but on Nasdaq 5 days made most profit, with a 1,284-day stretch without a new high. Prop challenges: 23 passed, 24 failed |

## Prop-firm insight
Prop firms cap loss at the challenge fee, so a near-zero strategy can still pay out: ICT's flat S&P version had 28 challenges, $58,900 paid, net +$44k; Alex G's Asia version net +$82k. The creator warns this does not make them good strategies (e.g. Brad Go: paid $19.5k but net -$10k; results hinge on a single simulation and start date).

## Takeaways
1. Claimed win rates are routinely wrong (75% claimed vs 47.6% actual).
2. The exit rule often decides profitability more than the entry.
3. Results depend heavily on the start date; a strategy can look great for years and then give it all back.
4. Survivability (long drawdowns, lumpy profits) matters as much as total return.
5. Backtest before paying for a challenge or trading live.

## Caveats
- Figures are the creator's own claims, unverified by me.
- The video promotes the creator's backtesting site (backtestthehype.com), a free Telegram EA channel, and free GitHub bots; treat as marketing-adjacent.
- Not financial advice.
