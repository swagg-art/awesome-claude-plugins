"""Backtester for the RSI strategy.

The point of this file is to answer one question honestly: does the thing the
bot actually trades make money on history?

To make that answer meaningful it imports `compute_rsi` and `detect_signal`
from main.py rather than reimplementing them. If the signal changes, this
changes with it. A backtester with its own copy of the logic measures a
strategy you are not running.

    python backtest.py --csv data/BTCUSD_M15.csv
    python backtest.py --mt5 --bars 20000          # pull history from MT5
    python backtest.py --csv data.csv --walk-forward

Assumptions are listed by --explain, and every one of them is pessimistic where
there is a choice.
"""

import argparse
import csv
import sys
from dataclasses import dataclass, field

import pandas as pd

from config import Config
from main import compute_rsi, detect_signal
from strategy import (
    arm_setup,
    average_true_range,
    confirms,
    levels_from_structure,
)

ASSUMPTIONS = """
How this backtest fills orders, and why each choice is the pessimistic one:

  Entry price      The open of the bar AFTER the signal bar. You cannot trade a
                   close you have only just seen; the bot places its order on
                   the next tick, which is the next bar's open.

  Spread           Charged once per round trip, as a fixed price distance. A buy
                   enters at open + spread; a sell exits at level + spread. Real
                   spreads widen at exactly the wrong moments, so treat the
                   result as a ceiling.

  Stop and target  Checked against each bar's high and low from the entry bar
                   onward. If a bar's range contains BOTH the stop and the
                   target, the STOP is taken. Without tick data there is no way
                   to know which came first, and assuming the win is how
                   backtests lie.

  Gaps             If a bar opens beyond the stop, the fill is the open, not the
                   stop. That models slippage through the level.

  Position size    Fixed LOT_SIZE, as the live bot does. P/L is
                   price_delta x volume x contract_size.

  One at a time    At most MAX_OPEN_POSITIONS, matching the live bot.

  Not modelled     Swap/financing on positions held overnight, commission,
                   requotes, weekend gaps in FX, and the possibility that your
                   broker's feed differs from the data you tested on.
"""


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------


def load_csv(path):
    """Read OHLC from a CSV.

    Accepts a plain time,open,high,low,close header and MetaTrader's own export
    (tab separated, <DATE> <TIME> <OPEN> ... angle-bracketed headers).
    """

    with open(path, newline="", encoding="utf-8-sig") as fh:
        sample = fh.read(4096)
        fh.seek(0)
        delimiter = "\t" if "\t" in sample.splitlines()[0] else ","
        rows = list(csv.DictReader(fh, delimiter=delimiter))

    if not rows:
        raise SystemExit(f"{path} has no data rows")

    def pick(row, *names):
        for name in names:
            for key in row:
                if key.strip().strip("<>").upper() == name:
                    return row[key]
        raise SystemExit(
            f"{path} has no {names[0]} column. Found: {', '.join(rows[0].keys())}"
        )

    records = []
    for row in rows:
        try:
            date = pick(row, "DATE", "TIME", "TIMESTAMP")
            try:
                clock = pick(row, "TIME")
            except SystemExit:
                clock = ""
            stamp = f"{date} {clock}".strip() if clock and clock != date else date
            records.append(
                {
                    "time": stamp,
                    "open": float(pick(row, "OPEN")),
                    "high": float(pick(row, "HIGH")),
                    "low": float(pick(row, "LOW")),
                    "close": float(pick(row, "CLOSE")),
                }
            )
        except (ValueError, TypeError):
            continue  # header repeats and blank lines

    df = pd.DataFrame(records)
    if len(df) < Config.RSI_PERIOD * 3:
        raise SystemExit(
            f"only {len(df)} usable bars in {path}; need at least "
            f"{Config.RSI_PERIOD * 3} for RSI({Config.RSI_PERIOD})"
        )
    return df


def load_mt5(bars):
    """Pull history straight from the terminal. Windows only."""

    try:
        import MetaTrader5 as mt5
    except ImportError:
        raise SystemExit(
            "the MetaTrader5 package is not installed (Windows only). Export a "
            "CSV from the terminal instead and use --csv."
        ) from None

    from main import TIMEFRAMES

    if not mt5.initialize():
        raise SystemExit(f"MT5 initialization failed: {mt5.last_error()}")
    if Config.LOGIN and Config.PASSWORD and Config.SERVER:
        if not mt5.login(Config.LOGIN, password=Config.PASSWORD, server=Config.SERVER):
            raise SystemExit(f"MT5 login failed: {mt5.last_error()}")

    timeframe = getattr(mt5, TIMEFRAMES[Config.TIMEFRAME])
    rates = mt5.copy_rates_from_pos(Config.SYMBOL, timeframe, 0, bars)
    info = mt5.symbol_info(Config.SYMBOL)
    spread_price = (info.spread * info.point) if info else 0.0
    contract = info.trade_contract_size if info else 1.0
    mt5.shutdown()

    if rates is None or len(rates) == 0:
        raise SystemExit(f"no history returned for {Config.SYMBOL}")

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    point = info.point if info else 0.0
    return df[["time", "open", "high", "low", "close"]], spread_price, contract, point


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


@dataclass
class Trade:
    side: str
    entry_index: int
    entry_time: object
    entry_price: float
    exit_index: int = 0
    exit_time: object = None
    exit_price: float = 0.0
    exit_reason: str = ""
    pnl: float = 0.0

    @property
    def bars_held(self):
        return self.exit_index - self.entry_index


@dataclass
class Result:
    trades: list = field(default_factory=list)
    equity: list = field(default_factory=list)
    bars: int = 0
    bars_in_market: int = 0
    blocked_by_daily_limit: int = 0
    first_time: object = None
    last_time: object = None
    buy_hold_pnl: float = 0.0


def run_backtest(
    df,
    *,
    spread=0.0,
    contract_size=1.0,
    point=0.0,
    starting_equity=10_000.0,
    apply_daily_limit=True,
    rsi_period=None,
    oversold=None,
    overbought=None,
):
    """Replay the strategy bar by bar. Returns a Result."""

    rsi_period = rsi_period or Config.RSI_PERIOD
    oversold = oversold if oversold is not None else Config.RSI_OVERSOLD
    overbought = overbought if overbought is not None else Config.RSI_OVERBOUGHT

    # detect_signal reads thresholds off Config; set them for this run so the
    # sweep can vary them without a second copy of the comparison logic.
    saved = (Config.RSI_OVERSOLD, Config.RSI_OVERBOUGHT)
    Config.RSI_OVERSOLD, Config.RSI_OVERBOUGHT = oversold, overbought
    try:
        if Config.SL_MODE == "points" and point <= 0:
            raise SystemExit(
                "SL_MODE=points needs the symbol's point size. Pass --point "
                "(0.01 for a 2-digit symbol like BTCUSD, 0.00001 for 5-digit FX), "
                "or use SL_MODE=percent."
            )
        return _run(
            df, spread, contract_size, point, starting_equity,
            apply_daily_limit, rsi_period,
        )
    finally:
        Config.RSI_OVERSOLD, Config.RSI_OVERBOUGHT = saved


def _run(df, spread, contract_size, point, starting_equity, apply_daily_limit,
         rsi_period):
    """The plain strategy: RSI crossing back through a fixed threshold."""

    rsi = compute_rsi(df["close"], rsi_period).to_numpy()

    def decide(i):
        return detect_signal(rsi[i - 2], rsi[i - 1]) if i >= 2 else None

    def levels(side, entry, _i):
        stop, target, _ = Config.stop_levels(side, entry, point, 8)
        return stop, target

    return _simulate(df, decide, levels, spread, contract_size, starting_equity,
                     apply_daily_limit)


class ConfirmedStrategy:
    """Divergence and candlestick confirmation, with structure-derived stops.

    Stateful across bars, because that is what "wait for confirmation" means:
    a setup is armed on one bar and either confirmed on a later one or allowed
    to expire. Only data up to the current bar is ever read.
    """

    def __init__(self, df, rsi, atr, *, oversold, overbought, confirm_within=5,
                 reward_multiple=2.0, atr_buffer=0.5, require_pattern=True,
                 require_break=True, require_rsi_turn=True, divergence_only=False):
        self.df, self.rsi, self.atr = df, rsi, atr
        self.oversold, self.overbought = oversold, overbought
        self.confirm_within = confirm_within
        self.reward_multiple, self.atr_buffer = reward_multiple, atr_buffer
        self.require_pattern = require_pattern
        self.require_break = require_break
        self.require_rsi_turn = require_rsi_turn
        self.divergence_only = divergence_only

        self.setup = None
        self._fired = None
        self.armed_count = 0
        self.expired_count = 0
        self.confirmed_count = 0
        self.last_reasons = []

    def decide(self, i):
        """Called on bar i when flat. A fill, if any, happens at bar i's open.

        The confirmation therefore has to have happened on bar i-1, whose close
        is the last thing knowable before that open.
        """
        signal_bar = i - 1
        if signal_bar < 3 or self.atr[signal_bar] is None:
            return None

        if self.setup is not None and self.setup.expired(signal_bar, self.confirm_within):
            self.setup = None
            self.expired_count += 1

        if self.setup is None:
            candidate = arm_setup(
                self.df, self.rsi, signal_bar,
                oversold=self.oversold, overbought=self.overbought,
            )
            if candidate is not None:
                if self.divergence_only and candidate.divergence is None:
                    return None
                self.setup = candidate
                self.armed_count += 1
            return None

        reasons = confirms(
            self.df, self.rsi, signal_bar, self.setup,
            require_pattern=self.require_pattern,
            require_break=self.require_break,
            require_rsi_turn=self.require_rsi_turn,
        )
        if reasons is None:
            return None

        self._fired = self.setup
        self.last_reasons = self.setup.reasons + reasons
        self.confirmed_count += 1
        side = self.setup.side
        self.setup = None
        return side

    def levels(self, side, entry, i):
        atr_value = self.atr[i - 1] or self.atr[i]
        computed = levels_from_structure(
            self._fired, entry, atr_value,
            atr_buffer=self.atr_buffer, reward_multiple=self.reward_multiple,
        )
        if computed is None:
            return None
        stop, target, _ = computed
        return stop, target


def run_confirmed_backtest(df, *, spread=0.0, contract_size=1.0,
                           starting_equity=10_000.0, apply_daily_limit=True,
                           rsi_period=None, oversold=None, overbought=None,
                           **strategy_kwargs):
    """Backtest the confirmed strategy. Returns (Result, ConfirmedStrategy)."""

    rsi_period = rsi_period or Config.RSI_PERIOD
    oversold = oversold if oversold is not None else Config.RSI_OVERSOLD
    overbought = overbought if overbought is not None else Config.RSI_OVERBOUGHT

    rsi = compute_rsi(df["close"], rsi_period).to_numpy()
    atr = average_true_range(df, rsi_period)

    strategy = ConfirmedStrategy(
        df, rsi, atr, oversold=oversold, overbought=overbought, **strategy_kwargs
    )
    result = _simulate(df, strategy.decide, strategy.levels, spread, contract_size,
                       starting_equity, apply_daily_limit)
    return result, strategy


def _simulate(df, decide, levels, spread, contract_size, starting_equity,
              apply_daily_limit):
    """Bar-by-bar fill engine, shared by both strategies.

    `decide(i)` returns "BUY", "SELL" or None for a fill at bar i's open.
    `levels(side, entry, i)` returns the stop and target for that fill.

    Keeping this in one place means the fill mechanics verified in
    test_backtest.py are the mechanics both strategies are measured with.
    """

    opens = df["open"].to_numpy()
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    times = df["time"].tolist()

    volume = Config.LOT_SIZE
    result = Result(bars=len(df), first_time=times[0], last_time=times[-1])

    equity = starting_equity
    open_trade = None
    stop = target = 0.0
    day = None
    day_open_equity = equity
    halted = False

    for i in range(1, len(df)):
        # --- daily loss limit, replaying what the live bot does -----------
        if apply_daily_limit:
            today = str(times[i])[:10]
            if today != day:
                day, day_open_equity, halted = today, equity, False
            if not halted and day_open_equity > 0:
                drop = 100 * (equity - day_open_equity) / day_open_equity
                halted = drop <= -Config.MAX_DAILY_LOSS_PERCENT

        # --- manage an open position --------------------------------------
        if open_trade is not None:
            result.bars_in_market += 1
            long = open_trade.side == "BUY"
            hit_stop = lows[i] <= stop if long else highs[i] >= stop
            hit_target = highs[i] >= target if long else lows[i] <= target

            exit_price = exit_reason = None
            if hit_stop:
                # Pessimistic: when a bar spans both levels, take the stop.
                # A gap through the level fills at the open, not the level.
                exit_price = min(opens[i], stop) if long else max(opens[i], stop)
                exit_reason = "stop"
            elif hit_target:
                exit_price = max(opens[i], target) if long else min(opens[i], target)
                exit_reason = "target"

            if exit_price is not None:
                # A short buys back at the ask, so it pays the spread on exit.
                fill = exit_price if long else exit_price + spread
                delta = (fill - open_trade.entry_price) * (1 if long else -1)
                open_trade.pnl = delta * volume * contract_size
                open_trade.exit_index = i
                open_trade.exit_time = times[i]
                open_trade.exit_price = fill
                open_trade.exit_reason = exit_reason
                equity += open_trade.pnl
                result.trades.append(open_trade)
                open_trade = None

        # --- look for an entry --------------------------------------------
        if open_trade is None:
            action = decide(i)
            if action:
                if apply_daily_limit and halted:
                    result.blocked_by_daily_limit += 1
                else:
                    # A long enters at the ask.
                    entry = opens[i] + spread if action == "BUY" else opens[i]
                    computed = levels(action, entry, i)
                    if computed is not None:
                        stop, target = computed
                        open_trade = Trade(side=action, entry_index=i,
                                           entry_time=times[i], entry_price=entry)

        result.equity.append(equity)

    # Buy and hold over the same window, for comparison.
    result.buy_hold_pnl = (
        (df["close"].iloc[-1] - df["open"].iloc[0]) * volume * contract_size
    )
    return result



# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def summarise(result, starting_equity=10_000.0):
    trades = result.trades
    pnls = [t.pnl for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    gross_loss = abs(sum(losses))

    peak = starting_equity
    max_dd = 0.0
    for value in result.equity:
        peak = max(peak, value)
        max_dd = max(max_dd, peak - value)

    streak = worst_streak = 0
    for pnl in pnls:
        streak = streak + 1 if pnl < 0 else 0
        worst_streak = max(worst_streak, streak)

    net = sum(pnls)
    return {
        "bars": result.bars,
        "from": result.first_time,
        "to": result.last_time,
        "trades": len(trades),
        "net_pnl": net,
        "return_pct": 100 * net / starting_equity,
        "buy_hold_pnl": result.buy_hold_pnl,
        "win_rate_pct": (100 * len(wins) / len(trades)) if trades else None,
        "profit_factor": (sum(wins) / gross_loss) if gross_loss else None,
        "expectancy": (net / len(trades)) if trades else None,
        "average_win": (sum(wins) / len(wins)) if wins else None,
        "average_loss": (sum(losses) / len(losses)) if losses else None,
        "largest_win": max(pnls) if pnls else None,
        "largest_loss": min(pnls) if pnls else None,
        "max_drawdown": max_dd,
        "max_drawdown_pct": 100 * max_dd / starting_equity,
        "worst_losing_streak": worst_streak,
        "stops_hit": sum(1 for t in trades if t.exit_reason == "stop"),
        "targets_hit": sum(1 for t in trades if t.exit_reason == "target"),
        "avg_bars_held": (sum(t.bars_held for t in trades) / len(trades)) if trades else None,
        "time_in_market_pct": 100 * result.bars_in_market / result.bars if result.bars else 0,
        "blocked_by_daily_limit": result.blocked_by_daily_limit,
    }


def fmt(value, spec=".2f"):
    return "n/a" if value is None else format(value, spec)


def print_report(stats, title="BACKTEST"):
    print()
    print("=" * 62)
    print(f" {title}")
    print("=" * 62)
    if "confirmed" in title:
        print(f" {Config.SYMBOL} {Config.TIMEFRAME} | RSI({Config.RSI_PERIOD}) "
              f"{Config.RSI_OVERSOLD:g}/{Config.RSI_OVERBOUGHT:g} | {Config.LOT_SIZE} lots"
              f" | stop from swing structure + ATR buffer")
    else:
        print(f" {Config.describe()}")
    print(f" {stats['bars']} bars, {stats['from']} → {stats['to']}")
    print("-" * 62)
    print(f" Trades                {stats['trades']}")
    print(f"   closed at stop      {stats['stops_hit']}")
    print(f"   closed at target    {stats['targets_hit']}")
    print(f" Net P/L               {fmt(stats['net_pnl'])}  "
          f"({fmt(stats['return_pct'])}% of starting equity)")
    print(f" Buy and hold          {fmt(stats['buy_hold_pnl'])}   <- same window, same size")
    print("-" * 62)
    print(f" Win rate              {fmt(stats['win_rate_pct'])}%")
    print(f" Profit factor         {fmt(stats['profit_factor'], '.3f')}")
    print(f" Expectancy per trade  {fmt(stats['expectancy'])}")
    print(f" Average win / loss    {fmt(stats['average_win'])} / {fmt(stats['average_loss'])}")
    print(f" Largest win / loss    {fmt(stats['largest_win'])} / {fmt(stats['largest_loss'])}")
    print("-" * 62)
    print(f" Max drawdown          {fmt(stats['max_drawdown'])} "
          f"({fmt(stats['max_drawdown_pct'])}%)")
    print(f" Worst losing streak   {stats['worst_losing_streak']} trades")
    print(f" Avg bars held         {fmt(stats['avg_bars_held'], '.1f')}")
    print(f" Time in market        {fmt(stats['time_in_market_pct'], '.1f')}%")
    if stats["blocked_by_daily_limit"]:
        print(f" Signals skipped by the daily loss limit: "
              f"{stats['blocked_by_daily_limit']}")
    print("=" * 62)

    verdict(stats)


def verdict(stats):
    """Say plainly whether this is worth trading. Err toward no."""

    print()
    if stats["trades"] < 30:
        print(" VERDICT: not enough trades to conclude anything. Fewer than 30")
        print(" closed trades is noise, whatever the profit factor says.")
        return

    pf = stats["profit_factor"]
    if pf is None or stats["net_pnl"] <= 0:
        print(" VERDICT: loses money on this data. Do not trade it.")
    elif pf < 1.2:
        print(f" VERDICT: profit factor {pf:.2f} is inside the range that costs,")
        print(" slippage and a different broker feed can erase. Not tradable.")
    elif stats["max_drawdown_pct"] > 25:
        print(f" VERDICT: profitable but the {stats['max_drawdown_pct']:.0f}% drawdown")
        print(" would end most accounts, and every prop-firm account, before the")
        print(" edge arrived.")
    else:
        print(f" VERDICT: profitable in sample (PF {pf:.2f}, max DD")
        print(f" {stats['max_drawdown_pct']:.1f}%). That is necessary, not sufficient.")
        print(" Confirm with --walk-forward before believing it.")
    print()
    print(" One backtest on one symbol is not evidence of an edge. Costs are")
    print(" modelled optimistically and swap is not modelled at all.")


# ---------------------------------------------------------------------------
# Walk forward
# ---------------------------------------------------------------------------


def walk_forward(df, spread, contract, point, starting_equity):
    """Tune on the first 70%, then report the winner on the untouched 30%.

    A parameter sweep on all the data finds the settings that best fit the past
    and tells you nothing. The out-of-sample column is the only one worth
    reading, and it is usually much worse. That gap is the point.
    """

    split = int(len(df) * 0.7)
    in_sample, out_sample = df.iloc[:split], df.iloc[split:].reset_index(drop=True)

    grid = [
        (period, os_, 100 - os_)
        for period in (7, 14, 21)
        for os_ in (20, 25, 30, 35)
    ]

    print(f"\nTuning on bars 0–{split} ({len(grid)} combinations), "
          f"testing on {len(out_sample)} held-out bars.\n")

    scored = []
    for period, os_, ob in grid:
        res = run_backtest(
            in_sample, spread=spread, contract_size=contract, point=point,
            starting_equity=starting_equity, rsi_period=period,
            oversold=os_, overbought=ob,
        )
        stats = summarise(res, starting_equity)
        scored.append(((period, os_, ob), stats))

    scored.sort(key=lambda row: row[1]["net_pnl"], reverse=True)

    print(f"{'RSI':>4} {'OS':>4} {'OB':>4} | {'in-sample P/L':>14} {'trades':>7} "
          f"| {'out-of-sample P/L':>18} {'trades':>7}")
    print("-" * 74)
    for (period, os_, ob), in_stats in scored[:8]:
        out_stats = summarise(
            run_backtest(
                out_sample, spread=spread, contract_size=contract, point=point,
                starting_equity=starting_equity, rsi_period=period,
                oversold=os_, overbought=ob,
            ),
            starting_equity,
        )
        print(f"{period:>4} {os_:>4} {ob:>4} | {in_stats['net_pnl']:>14.2f} "
              f"{in_stats['trades']:>7} | {out_stats['net_pnl']:>18.2f} "
              f"{out_stats['trades']:>7}")

    best_params, best_in = scored[0]
    best_out = summarise(
        run_backtest(
            out_sample, spread=spread, contract_size=contract,
            starting_equity=starting_equity, rsi_period=best_params[0],
            oversold=best_params[1], overbought=best_params[2],
        ),
        starting_equity,
    )
    print()
    print(f"Best in sample: RSI({best_params[0]}) {best_params[1]}/{best_params[2]} "
          f"made {best_in['net_pnl']:.2f}")
    print(f"The same settings out of sample made {best_out['net_pnl']:.2f}")
    if best_out["net_pnl"] <= 0 < best_in["net_pnl"]:
        print()
        print("That is the whole lesson: the settings that fit the past best lost")
        print("money on data they had not seen. Do not trade the tuned parameters.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Backtest the RSI strategy.")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--csv", help="OHLC CSV, or a MetaTrader history export")
    source.add_argument("--mt5", action="store_true", help="pull history from the terminal")
    parser.add_argument("--bars", type=int, default=20000, help="bars to pull with --mt5")
    parser.add_argument("--spread", type=float, default=None,
                        help="spread in price units (default: from MT5, else 0)")
    parser.add_argument("--point", type=float, default=0.0,
                        help="symbol point size, needed only for SL_MODE=points")
    parser.add_argument("--contract-size", type=float, default=1.0,
                        help="1 for crypto/index CFDs, 100000 for standard FX")
    parser.add_argument("--equity", type=float, default=10_000.0)
    parser.add_argument("--no-daily-limit", action="store_true",
                        help="ignore MAX_DAILY_LOSS_PERCENT (measures the raw strategy)")
    parser.add_argument("--walk-forward", action="store_true",
                        help="tune on the first 70%%, report on the held-out 30%%")
    parser.add_argument("--strategy", choices=("simple", "confirmed"),
                        default="confirmed",
                        help="simple: RSI threshold cross with fixed-percent stops. "
                             "confirmed: divergence + candlestick confirmation with "
                             "structure-derived stops (default)")
    parser.add_argument("--divergence-only", action="store_true",
                        help="confirmed strategy: ignore plain oversold/overbought, "
                             "arm only on divergence")
    parser.add_argument("--reward", type=float, default=2.0,
                        help="target as a multiple of the stop distance")
    parser.add_argument("--confirm-within", type=int, default=5,
                        help="bars a setup waits for confirmation before expiring")
    parser.add_argument("--trades", action="store_true", help="list every trade")
    parser.add_argument("--explain", action="store_true", help="print the fill assumptions")
    args = parser.parse_args()

    if args.explain:
        print(ASSUMPTIONS)
        return 0

    spread, contract, point = args.spread or 0.0, args.contract_size, args.point
    if args.mt5:
        df, mt5_spread, mt5_contract, mt5_point = load_mt5(args.bars)
        if args.spread is None:
            spread = mt5_spread
        if args.contract_size == 1.0:
            contract = mt5_contract
        if args.point == 0.0:
            point = mt5_point
    elif args.csv:
        df = load_csv(args.csv)
    else:
        parser.error("give --csv PATH or --mt5 (or --explain)")

    if spread == 0.0:
        print("NOTE: spread is 0, so these results are better than anything you\n"
              "      could trade. Pass --spread with your broker's real spread.",
              file=sys.stderr)

    if args.walk_forward:
        walk_forward(df, spread, contract, point, args.equity)
        return 0

    if args.strategy == "confirmed":
        result, strategy = run_confirmed_backtest(
            df, spread=spread, contract_size=contract,
            starting_equity=args.equity, apply_daily_limit=not args.no_daily_limit,
            reward_multiple=args.reward, confirm_within=args.confirm_within,
            divergence_only=args.divergence_only,
        )
        print_report(summarise(result, args.equity), title="BACKTEST — confirmed")
        print(f" Setups armed          {strategy.armed_count}")
        print(f"   confirmed           {strategy.confirmed_count}")
        print(f"   expired unfilled    {strategy.expired_count}")
        if strategy.armed_count:
            rate = 100 * strategy.confirmed_count / strategy.armed_count
            print(f"   confirmation rate   {rate:.1f}%")
    else:
        result = run_backtest(
            df, spread=spread, contract_size=contract, point=point,
            starting_equity=args.equity, apply_daily_limit=not args.no_daily_limit,
        )
        print_report(summarise(result, args.equity), title="BACKTEST — simple")

    if args.trades:
        print(f"\n{'#':>4} {'side':<5} {'entry':>12} {'exit':>12} {'reason':<7} {'P/L':>10}")
        for n, t in enumerate(result.trades, 1):
            print(f"{n:>4} {t.side:<5} {t.entry_price:>12.5f} {t.exit_price:>12.5f} "
                  f"{t.exit_reason:<7} {t.pnl:>10.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
