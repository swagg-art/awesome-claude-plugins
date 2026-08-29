"""Pre-trade guards. Every one of these exists because of a way accounts die.

The guards run BEFORE an order is built, not after it is rejected. A guard
that only reports damage is a log, not a guard.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path


class GuardTripped(RuntimeError):
    """Raised when a guard blocks a trade. Never caught silently."""


@dataclass
class GuardConfig:
    max_daily_loss_pct: float = 0.03     # stop trading after -3% on the day
    max_open_positions: int = 1
    max_consecutive_losses: int = 4
    max_orders_per_day: int = 20
    min_seconds_between_orders: float = 5.0
    kill_switch_file: str = "KILL"       # touch this file to halt everything
    require_demo: bool = True            # refuse to trade a live account


@dataclass
class RiskGuard:
    cfg: GuardConfig = field(default_factory=GuardConfig)
    day: dt.date | None = None
    day_start_equity: float | None = None
    orders_today: int = 0
    consecutive_losses: int = 0
    last_order_ts: float = 0.0

    def _roll_day(self, now: dt.datetime, equity: float) -> None:
        today = now.date()
        if self.day != today:
            self.day = today
            self.day_start_equity = equity
            self.orders_today = 0

    def check(self, *, now: dt.datetime, equity: float, open_positions: int,
              monotonic: float) -> None:
        """Raise GuardTripped if this trade must not happen."""
        self._roll_day(now, equity)

        if Path(self.cfg.kill_switch_file).exists():
            raise GuardTripped(
                f"kill switch present ({self.cfg.kill_switch_file}) - delete it to resume")

        if self.day_start_equity:
            dd = equity / self.day_start_equity - 1.0
            if dd <= -self.cfg.max_daily_loss_pct:
                raise GuardTripped(
                    f"daily loss {dd*100:.2f}% breached limit "
                    f"{-self.cfg.max_daily_loss_pct*100:.2f}% - halted until tomorrow")

        if open_positions >= self.cfg.max_open_positions:
            raise GuardTripped(
                f"{open_positions} position(s) open, limit {self.cfg.max_open_positions}")

        if self.consecutive_losses >= self.cfg.max_consecutive_losses:
            raise GuardTripped(
                f"{self.consecutive_losses} consecutive losses, limit "
                f"{self.cfg.max_consecutive_losses} - halted for review")

        if self.orders_today >= self.cfg.max_orders_per_day:
            raise GuardTripped(
                f"{self.orders_today} orders today, limit {self.cfg.max_orders_per_day}")

        gap = monotonic - self.last_order_ts
        if self.last_order_ts and gap < self.cfg.min_seconds_between_orders:
            raise GuardTripped(
                f"only {gap:.1f}s since last order, minimum "
                f"{self.cfg.min_seconds_between_orders}s - throttled")

    def record_order(self, monotonic: float) -> None:
        self.orders_today += 1
        self.last_order_ts = monotonic

    def record_result(self, pnl: float) -> None:
        self.consecutive_losses = self.consecutive_losses + 1 if pnl <= 0 else 0
