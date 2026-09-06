"""Portfolio-level checks, run before proposing anything new.

Liquid's `get_portfolio` reports positions. It does not tell you which of them
are unprotected, how leveraged the account is in aggregate, or how close
anything is to liquidation. Those are the things worth knowing before adding
another position, so they are computed here.

The caller maps `get_portfolio`'s output into the simple dicts this expects,
which keeps the arithmetic testable without pinning it to one response shape.
"""

from __future__ import annotations

from .sizing import DEFAULT_MAINTENANCE_MARGIN, liquidation_price


def _position_findings(position: dict, equity: float) -> list[dict]:
    """Findings for one position. Each carries a severity so they can be ranked."""

    findings: list[dict] = []
    symbol = position.get("symbol", "?")
    side = (position.get("side") or "long").strip().lower()
    notional = float(position.get("notional") or 0)
    entry = float(position.get("entry") or 0)
    mark = float(position.get("mark") or entry)
    leverage = float(position.get("leverage") or 1)
    stop = position.get("stop_loss")

    if notional <= 0 or entry <= 0:
        return findings

    if not stop:
        findings.append({
            "severity": "high",
            "symbol": symbol,
            "finding": "no stop loss",
            "detail": (
                f"${notional:,.0f} of {side} exposure with nothing defining where "
                "the idea is wrong. On a perpetual the exchange will eventually "
                "define it for you, at liquidation."
            ),
        })
    else:
        stop = float(stop)
        wrong_side = (side == "long" and stop >= mark) or (side == "short" and stop <= mark)
        if wrong_side:
            findings.append({
                "severity": "high",
                "symbol": symbol,
                "finding": "stop is already past the mark",
                "detail": f"stop {stop:,.2f} against a mark of {mark:,.2f}",
            })

    try:
        liq = liquidation_price(entry, side, leverage, DEFAULT_MAINTENANCE_MARGIN)
    except Exception:
        liq = None

    if liq is not None:
        distance = abs(mark - liq) / mark if mark else 0
        if distance < 0.02:
            findings.append({
                "severity": "high",
                "symbol": symbol,
                "finding": "close to liquidation",
                "detail": (
                    f"liquidation about {liq:,.2f}, {distance:.1%} from the mark "
                    f"at {leverage:g}x"
                ),
            })
        elif distance < 0.05:
            findings.append({
                "severity": "medium",
                "symbol": symbol,
                "finding": "liquidation within 5%",
                "detail": f"liquidation about {liq:,.2f}, {distance:.1%} away",
            })

    if equity > 0 and notional / equity > 1.0:
        findings.append({
            "severity": "medium",
            "symbol": symbol,
            "finding": "single position exceeds account equity",
            "detail": f"${notional:,.0f} notional against ${equity:,.0f} equity",
        })

    return findings


def review_portfolio(
    *,
    equity: float,
    available_balance: float,
    positions: list[dict],
    max_gross_leverage: float = 3.0,
) -> dict:
    """Summarise account risk and return findings worth acting on.

    Each position is a dict with: symbol, side, notional, entry, mark,
    leverage, and optionally stop_loss.
    """

    gross_notional = sum(float(p.get("notional") or 0) for p in positions)
    gross_leverage = gross_notional / equity if equity > 0 else 0.0
    unprotected = [p for p in positions if not p.get("stop_loss")]
    unprotected_notional = sum(float(p.get("notional") or 0) for p in unprotected)

    findings: list[dict] = []
    for position in positions:
        findings.extend(_position_findings(position, equity))

    if gross_leverage > max_gross_leverage:
        findings.append({
            "severity": "high",
            "symbol": "ACCOUNT",
            "finding": "account leverage above the limit you set",
            "detail": (
                f"${gross_notional:,.0f} of exposure on ${equity:,.0f} equity is "
                f"{gross_leverage:.1f}x, over the {max_gross_leverage:g}x ceiling"
            ),
        })

    # Several positions on correlated assets is one bet, not several.
    symbols = [str(p.get("symbol", "")).upper() for p in positions]
    crypto = [s for s in symbols if s in {"BTC", "ETH", "SOL", "DOGE", "XRP", "AVAX"}]
    if len(crypto) >= 3:
        findings.append({
            "severity": "medium",
            "symbol": "ACCOUNT",
            "finding": "concentrated in one asset class",
            "detail": (
                f"{len(crypto)} crypto positions ({', '.join(crypto)}). These move "
                "together — this is closer to one large bet than several small ones."
            ),
        })

    order = {"high": 0, "medium": 1, "low": 2}
    findings.sort(key=lambda f: order.get(f["severity"], 3))

    return {
        "equity": round(equity, 2),
        "available_balance": round(available_balance, 2),
        "positions": len(positions),
        "gross_notional": round(gross_notional, 2),
        "gross_leverage": round(gross_leverage, 2),
        "unprotected_positions": len(unprotected),
        "unprotected_notional": round(unprotected_notional, 2),
        "findings": findings,
        "headline": _headline(findings, len(positions), gross_leverage, len(unprotected)),
    }


def _headline(findings: list[dict], positions: int, gross_leverage: float,
              unprotected: int) -> str:
    if positions == 0:
        return "Flat. Nothing at risk."
    high = sum(1 for f in findings if f["severity"] == "high")
    if unprotected:
        return (
            f"{unprotected} of {positions} position(s) have no stop. That is the "
            "first thing to fix."
        )
    if high:
        return f"{high} finding(s) need attention now."
    return f"{positions} position(s), {gross_leverage:.1f}x account leverage, all stopped."
