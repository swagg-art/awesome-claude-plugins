"""Turn a risk budget and a stop into a notional and a leverage.

The arithmetic that matters on a perpetual is not "how many lots". It is:

  * how much money is lost if the stop is hit  (that is the risk budget)
  * how far the price can move before the exchange closes the position for you
    (that is liquidation, and it is a function of leverage alone)

Those two interact in a way that is easy to get wrong and expensive to get
wrong. A 1% stop on 40x leverage is a stop that will never be reached, because
liquidation sits at roughly 2.5%... in the same direction, but closer once fees
and maintenance margin are counted. The position is closed by the exchange
before the trading idea has been proven wrong.

So leverage here is not an aggression dial. It is chosen as the *lowest* value
that still fits the available collateral, which maximises the distance to
liquidation.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field

# Liquid does not publish a maintenance-margin schedule through the connector,
# and it varies by asset and size. This is a deliberately conservative stand-in:
# assuming a larger maintenance requirement moves liquidation *closer*, so the
# safety checks here fire earlier rather than later. Override it if the real
# figure is known.
DEFAULT_MAINTENANCE_MARGIN = 0.005  # 0.5%

# A stop must sit comfortably inside liquidation, not just barely. At 2.0 the
# price has to travel twice the stop distance before the exchange intervenes.
DEFAULT_LIQUIDATION_BUFFER = 2.0

# From the connector: "Minimum $15 collateral x leverage."
MIN_COLLATERAL = 15.0


class SizingError(ValueError):
    """The inputs describe a trade that cannot be sized safely."""


@dataclass(frozen=True)
class Trade:
    """A fully specified proposal, ready to hand to `suggest_trade`."""

    symbol: str
    side: str  # "long" | "short"
    entry: float
    stop_loss: float
    take_profit: float | None

    notional: float          # the `size` argument, in USD
    leverage: float
    collateral: float        # notional / leverage — what it ties up

    risk_amount: float       # lost if the stop is hit
    risk_pct: float          # as a share of equity
    stop_distance_pct: float

    liquidation_price: float
    liquidation_distance_pct: float
    stop_to_liquidation_ratio: float

    reward_amount: float | None
    reward_risk_ratio: float | None

    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    def summary(self) -> str:
        """One block a human can check before pressing Confirm."""
        lines = [
            f"{self.side.upper()} {self.symbol} @ {self.entry:,.2f}",
            f"  size        ${self.notional:,.2f} notional at {self.leverage:g}x "
            f"(${self.collateral:,.2f} collateral)",
            f"  stop        {self.stop_loss:,.2f}  "
            f"({self.stop_distance_pct:.2f}% away, risks ${self.risk_amount:,.2f} "
            f"= {self.risk_pct:.2f}% of equity)",
        ]
        if self.take_profit is not None:
            lines.append(
                f"  target      {self.take_profit:,.2f}  "
                f"(makes ${self.reward_amount:,.2f}, {self.reward_risk_ratio:.2f}R)"
            )
        lines.append(
            f"  liquidation {self.liquidation_price:,.2f}  "
            f"({self.liquidation_distance_pct:.2f}% away — "
            f"{self.stop_to_liquidation_ratio:.1f}x the stop distance)"
        )
        for warning in self.warnings:
            lines.append(f"  WARNING     {warning}")
        return "\n".join(lines)


def liquidation_price(entry: float, side: str, leverage: float,
                      maintenance_margin: float = DEFAULT_MAINTENANCE_MARGIN) -> float:
    """Approximate price at which the position is force-closed.

    Isolated-margin approximation: the position is liquidated once losses eat
    the collateral down to the maintenance requirement, so the move it can
    survive is about (1/leverage - maintenance_margin) of the entry price.

    Approximate on purpose, and conservative — it ignores fees and funding,
    both of which bring liquidation *closer*. Treat the number as a ceiling on
    how far the price can move, never as an exact level.
    """

    if leverage <= 0:
        raise SizingError(f"leverage must be positive, got {leverage}")

    survivable = 1.0 / leverage - maintenance_margin
    if survivable <= 0:
        raise SizingError(
            f"{leverage:g}x is at or past the maintenance-margin floor "
            f"({maintenance_margin:.1%}) — such a position is liquidated on any "
            "adverse tick"
        )

    return entry * (1 - survivable) if side == "long" else entry * (1 + survivable)


def _round_leverage(value: float) -> float:
    """Leverage to one decimal, rounded up.

    Up, because rounding leverage down raises the collateral needed, which can
    push the trade past the available balance after it was checked.
    """
    return math.ceil(value * 10) / 10


def size_trade(
    *,
    symbol: str,
    side: str,
    entry: float,
    stop_loss: float,
    equity: float,
    available_balance: float,
    risk_pct: float = 1.0,
    take_profit: float | None = None,
    max_leverage: float = 40.0,
    maintenance_margin: float = DEFAULT_MAINTENANCE_MARGIN,
    liquidation_buffer: float = DEFAULT_LIQUIDATION_BUFFER,
) -> Trade:
    """Size a Liquid perp trade so the stop costs `risk_pct` of equity.

    Raises SizingError when no leverage satisfies both the available collateral
    and the liquidation buffer — which is a real answer, not a failure. It means
    the trade as described cannot be taken safely on this account.
    """

    side = (side or "").strip().lower()
    if side not in {"long", "short"}:
        raise SizingError(f"side must be 'long' or 'short', got {side!r}")
    if entry <= 0:
        raise SizingError(f"entry must be positive, got {entry}")
    if equity <= 0:
        raise SizingError(f"equity must be positive, got {equity}")
    if available_balance <= 0:
        raise SizingError(
            f"available balance is {available_balance}; fund the account before "
            "sizing a trade"
        )
    if not 0 < risk_pct <= 100:
        raise SizingError(f"risk_pct must be in (0, 100], got {risk_pct}")
    if side == "long" and stop_loss >= entry:
        raise SizingError("a long's stop_loss must sit below the entry price")
    if side == "short" and stop_loss <= entry:
        raise SizingError("a short's stop_loss must sit above the entry price")

    stop_distance = abs(entry - stop_loss) / entry
    risk_amount = equity * risk_pct / 100.0
    notional = risk_amount / stop_distance

    # Leverage is bounded from below by the collateral we have, and from above
    # by the need to keep liquidation well beyond the stop.
    min_leverage = notional / available_balance
    survivable_needed = stop_distance * liquidation_buffer + maintenance_margin
    max_safe_leverage = 1.0 / survivable_needed

    if min_leverage > max_leverage:
        needed = notional / max_leverage
        # r <= A * L_max * d / E, from notional/L_max <= A.
        affordable_pct = 100 * available_balance * max_leverage * stop_distance / equity
        raise SizingError(
            f"risking {risk_pct:g}% of {equity:,.2f} on a {stop_distance:.2%} stop "
            f"needs ${notional:,.2f} of exposure, which even at the "
            f"{max_leverage:g}x ceiling requires ${needed:,.2f} collateral against "
            f"${available_balance:,.2f} available. At this stop distance the most "
            f"you can risk is {affordable_pct:.2f}%. A wider stop also helps — "
            "notional is risk divided by stop distance, so tightening it needs "
            "more collateral, not less."
        )

    if min_leverage > max_safe_leverage:
        # Failure means  E*r*b/A + E*r*mm/(d*A) > 1.  The first term does not
        # depend on the stop at all, so when it alone exceeds 1 no stop width
        # can rescue the trade and only risking less will.
        risk_floor = risk_amount * liquidation_buffer
        max_risk_here_pct = (
            100 * available_balance
            / (equity * (liquidation_buffer + maintenance_margin / stop_distance))
        )
        if risk_floor >= available_balance:
            remedy = (
                f"No stop width fixes this: keeping liquidation {liquidation_buffer:g}x "
                f"beyond the stop needs at least {liquidation_buffer:g}x the risk "
                f"budget in collateral (${risk_floor:,.2f}) and only "
                f"${available_balance:,.2f} is available. Risk at most "
                f"{max_risk_here_pct:.2f}%, or fund the account."
            )
        else:
            # d_min from  E*r*b/A + E*r*mm/(d*A) = 1
            min_distance = (
                risk_amount * maintenance_margin / (available_balance - risk_floor)
            )
            widened = (
                entry * (1 - min_distance) if side == "long"
                else entry * (1 + min_distance)
            )
            remedy = (
                f"Either risk at most {max_risk_here_pct:.2f}%, or widen the stop "
                f"past {min_distance:.2%} (about {widened:,.2f}). Tightening it "
                "raises the notional and makes this worse."
            )

        raise SizingError(
            f"no safe leverage exists for this trade. Fitting ${notional:,.2f} of "
            f"exposure into ${available_balance:,.2f} needs at least "
            f"{min_leverage:.1f}x, but a {stop_distance:.2%} stop allows at most "
            f"{max_safe_leverage:.1f}x if liquidation is to stay "
            f"{liquidation_buffer:g}x beyond the stop. Above that the exchange "
            f"closes the position before the idea is proven wrong. {remedy}"
        )

    leverage = min(max(_round_leverage(min_leverage), 1.0), max_leverage, max_safe_leverage)
    leverage = max(leverage, 1.0)
    collateral = notional / leverage

    warnings: list[str] = []

    if collateral < MIN_COLLATERAL:
        # Below the venue minimum the trade cannot be placed at all. Report the
        # smallest risk that would clear it rather than silently inflating size.
        min_risk_pct = (MIN_COLLATERAL * leverage * stop_distance) / equity * 100
        raise SizingError(
            f"this sizes to ${collateral:,.2f} of collateral, below Liquid's "
            f"${MIN_COLLATERAL:,.0f} minimum. Risking about {min_risk_pct:.2f}% "
            "would clear it — decide whether that risk is acceptable rather than "
            "taking it by default."
        )

    liq = liquidation_price(entry, side, leverage, maintenance_margin)
    liq_distance = abs(entry - liq) / entry
    ratio = liq_distance / stop_distance

    if ratio < liquidation_buffer:
        warnings.append(
            f"liquidation is only {ratio:.1f}x the stop distance away "
            f"(wanted {liquidation_buffer:g}x)"
        )
    if stop_distance < 0.001:
        warnings.append(
            f"the stop is {stop_distance:.3%} from entry — inside normal noise "
            "and likely inside the spread"
        )
    if collateral > available_balance:  # defensive; the bounds above should prevent it
        warnings.append(
            f"collateral ${collateral:,.2f} exceeds available "
            f"${available_balance:,.2f}"
        )

    reward = reward_ratio = None
    if take_profit is not None:
        if side == "long" and take_profit <= entry:
            raise SizingError("a long's take_profit must sit above the entry price")
        if side == "short" and take_profit >= entry:
            raise SizingError("a short's take_profit must sit below the entry price")
        reward = notional * abs(take_profit - entry) / entry
        reward_ratio = reward / risk_amount if risk_amount else None
        if reward_ratio is not None and reward_ratio < 1:
            warnings.append(
                f"the target pays {reward_ratio:.2f}R — less than the stop costs"
            )

    return Trade(
        symbol=symbol.strip().upper(),
        side=side,
        entry=entry,
        stop_loss=stop_loss,
        take_profit=take_profit,
        notional=round(notional, 2),
        leverage=leverage,
        collateral=round(collateral, 2),
        risk_amount=round(risk_amount, 2),
        risk_pct=risk_pct,
        stop_distance_pct=round(stop_distance * 100, 4),
        liquidation_price=round(liq, 2),
        liquidation_distance_pct=round(liq_distance * 100, 4),
        stop_to_liquidation_ratio=round(ratio, 2),
        reward_amount=round(reward, 2) if reward is not None else None,
        reward_risk_ratio=round(reward_ratio, 3) if reward_ratio is not None else None,
        warnings=warnings,
    )
