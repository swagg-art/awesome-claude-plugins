"""What holding a perpetual costs while you wait.

A CFD charges swap overnight. A perpetual charges funding on a schedule —
typically every eight hours — and the rate floats. Over a multi-day hold it
stops being a rounding error, which matters here because the strategy this
project measured on MetaTrader held for an average of 27 bars.

Sign convention follows the venues: a positive funding rate means longs pay
shorts. So a long with positive funding bleeds, and a short with positive
funding is paid to wait.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

INTERVALS_PER_DAY = 3  # eight-hourly, the usual schedule


@dataclass(frozen=True)
class FundingEstimate:
    notional: float
    side: str
    rate_per_interval: float
    intervals: int
    hold_hours: float
    cost: float               # positive means it costs you
    cost_pct_of_notional: float
    annualised_rate_pct: float
    verdict: str

    def to_dict(self) -> dict:
        return asdict(self)


def estimate_funding(
    *,
    notional: float,
    side: str,
    rate_per_interval: float,
    hold_hours: float,
    interval_hours: float = 8.0,
    risk_amount: float | None = None,
    reward_amount: float | None = None,
) -> FundingEstimate:
    """Funding paid (or received) over an expected hold.

    `rate_per_interval` is the decimal rate per funding interval — 0.0001 is
    one basis point, which is a common resting level.

    Pass `risk_amount` or `reward_amount` to get a verdict on whether funding
    is large enough to change the trade.
    """

    side = (side or "").strip().lower()
    if side not in {"long", "short"}:
        raise ValueError(f"side must be 'long' or 'short', got {side!r}")
    if notional <= 0:
        raise ValueError(f"notional must be positive, got {notional}")
    if hold_hours < 0:
        raise ValueError(f"hold_hours cannot be negative, got {hold_hours}")
    if interval_hours <= 0:
        raise ValueError(f"interval_hours must be positive, got {interval_hours}")

    # Funding is charged at discrete moments, so a partial interval is not
    # charged. Rounding down keeps the estimate from overstating the cost.
    intervals = int(hold_hours // interval_hours)

    direction = 1 if side == "long" else -1
    cost = notional * rate_per_interval * intervals * direction

    annualised = rate_per_interval * (24 / interval_hours) * 365 * 100

    verdict = _verdict(cost, risk_amount, reward_amount)

    return FundingEstimate(
        notional=round(notional, 2),
        side=side,
        rate_per_interval=rate_per_interval,
        intervals=intervals,
        hold_hours=hold_hours,
        cost=round(cost, 2),
        cost_pct_of_notional=round(100 * cost / notional, 4),
        annualised_rate_pct=round(annualised, 2),
        verdict=verdict,
    )


def _verdict(cost: float, risk_amount: float | None, reward_amount: float | None) -> str:
    if cost < 0:
        return f"funding pays you ${abs(cost):,.2f} over this hold"
    if cost == 0:
        return "no funding charged over a hold this short"

    if reward_amount and reward_amount > 0:
        share = cost / reward_amount
        if share >= 0.5:
            return (
                f"funding eats ${cost:,.2f}, {share:.0%} of the target. The trade "
                "has to work quickly or it does not work"
            )
        if share >= 0.2:
            return f"funding eats ${cost:,.2f}, {share:.0%} of the target — material"

    if risk_amount and risk_amount > 0 and cost / risk_amount >= 0.25:
        return (
            f"funding costs ${cost:,.2f}, {cost / risk_amount:.0%} of what the stop "
            "risks — it is a second, slower stop"
        )

    return f"funding costs ${cost:,.2f} over this hold — not decisive"


def break_even_hold_hours(
    *, rate_per_interval: float, side: str, reward_pct: float,
    interval_hours: float = 8.0,
) -> float | None:
    """How long until funding cancels the whole target.

    `reward_pct` is the target as a decimal share of entry price (0.02 for 2%).
    Returns None when funding is in your favour, so it never cancels anything.
    """

    direction = 1 if side.strip().lower() == "long" else -1
    effective = rate_per_interval * direction
    if effective <= 0:
        return None
    return (reward_pct / effective) * interval_hours
