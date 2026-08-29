"""Data loading and validation.

Loud refusal beats quiet corruption. Every loader validates before it
returns, and raises on anything that would silently poison a backtest.
"""
from __future__ import annotations

import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

OHLC = ["open", "high", "low", "close"]


class DataError(ValueError):
    """Raised when input data is unfit to backtest on."""


def validate(df: pd.DataFrame, *, max_gap_factor: float = 50.0) -> dict:
    """Check a bar frame. Raises DataError on anything fatal; returns a report."""
    if df.empty:
        raise DataError("frame is empty")
    missing = set(OHLC) - set(df.columns)
    if missing:
        raise DataError(f"missing columns: {sorted(missing)}")
    if not isinstance(df.index, pd.DatetimeIndex):
        raise DataError(f"index must be DatetimeIndex, got {type(df.index).__name__}")
    if not df.index.is_monotonic_increasing:
        raise DataError("index is not sorted ascending")

    n_dupes = int(df.index.duplicated().sum())
    if n_dupes:
        raise DataError(f"{n_dupes} duplicate timestamps")

    nans = int(df[OHLC].isna().sum().sum())
    if nans:
        raise DataError(f"{nans} NaN values in OHLC")

    if (df[OHLC] <= 0).to_numpy().any():
        raise DataError("non-positive prices present")

    bad_hl = int((df["high"] < df["low"]).sum())
    if bad_hl:
        raise DataError(f"{bad_hl} bars where high < low")

    bad_range = int(
        ((df["high"] < df[["open", "close"]].max(axis=1))
         | (df["low"] > df[["open", "close"]].min(axis=1))).sum()
    )
    if bad_range:
        raise DataError(f"{bad_range} bars where open/close sit outside high/low")

    deltas = df.index.to_series().diff().dropna()
    median_dt = deltas.median()
    big_gaps = deltas[deltas > median_dt * max_gap_factor]

    return {
        "rows": len(df),
        "start": str(df.index[0]),
        "end": str(df.index[-1]),
        "median_bar": str(median_dt),
        "large_gaps": len(big_gaps),
        "largest_gap": str(big_gaps.max()) if len(big_gaps) else "none",
        "span_days": (df.index[-1] - df.index[0]).days,
    }


def load_histdata(path: str | Path, tz_source: str = "Etc/GMT+5") -> pd.DataFrame:
    """Load HistData.com ASCII M1 files (.csv or .zip, single or many).

    Format: `YYYYMMDD HHMMSS;open;high;low;close;volume`, semicolon
    separated, no header, timestamps in EST with no DST shift.
    """
    path = Path(path)
    files: list[tuple[str, bytes]] = []

    def collect(p: Path):
        if p.suffix.lower() == ".zip":
            with zipfile.ZipFile(p) as z:
                for name in z.namelist():
                    if name.lower().endswith(".csv"):
                        files.append((name, z.read(name)))
        elif p.suffix.lower() == ".csv":
            files.append((p.name, p.read_bytes()))

    if path.is_dir():
        for p in sorted(path.iterdir()):
            collect(p)
    else:
        collect(path)

    if not files:
        raise DataError(f"no .csv or .zip data found at {path}")

    frames = []
    for name, raw in files:
        import io
        head = raw[:200].decode("ascii", "replace").splitlines()[0] if raw else ""
        if ";" in head:
            # ASCII format: YYYYMMDD HHMMSS;o;h;l;c;v
            df = pd.read_csv(
                io.BytesIO(raw), sep=";", header=None,
                names=["ts", "open", "high", "low", "close", "volume"],
                dtype={"ts": str},
            )
            df["ts"] = pd.to_datetime(df["ts"], format="%Y%m%d %H%M%S")
        else:
            # MT format: YYYY.MM.DD,HH:MM,o,h,l,c,v
            df = pd.read_csv(
                io.BytesIO(raw), sep=",", header=None,
                names=["d", "t", "open", "high", "low", "close", "volume"],
                dtype={"d": str, "t": str},
            )
            df["ts"] = pd.to_datetime(df["d"] + " " + df["t"], format="%Y.%m.%d %H:%M")
            df = df.drop(columns=["d", "t"])
        frames.append(df)

    out = pd.concat(frames, ignore_index=True)
    out = out.drop_duplicates(subset="ts").sort_values("ts").set_index("ts")
    out.index = out.index.tz_localize(tz_source).tz_convert("UTC")
    out.index.name = "timestamp"
    return out[OHLC + ["volume"]]


def load_csv(path: str | Path, ts_col: str = "timestamp", tz: str | None = "UTC") -> pd.DataFrame:
    """Load a generic OHLCV csv with a header row."""
    df = pd.read_csv(path)
    df.columns = [c.strip().lower() for c in df.columns]
    ts_col = ts_col.lower()
    if ts_col not in df.columns:
        for cand in ("timestamp", "date", "datetime", "time", "open_time"):
            if cand in df.columns:
                ts_col = cand
                break
        else:
            raise DataError(f"no timestamp column found in {list(df.columns)}")
    df[ts_col] = pd.to_datetime(df[ts_col], utc=(tz == "UTC"), format="mixed")
    df = df.drop_duplicates(subset=ts_col).sort_values(ts_col).set_index(ts_col)
    df.index.name = "timestamp"
    keep = OHLC + (["volume"] if "volume" in df.columns else [])
    return df[keep]


def resample(df: pd.DataFrame, rule: str = "1h") -> pd.DataFrame:
    """Aggregate to a coarser timeframe. Drops empty periods (weekends)."""
    agg = {"open": "first", "high": "max", "low": "min", "close": "last"}
    if "volume" in df.columns:
        agg["volume"] = "sum"
    out = df.resample(rule, label="left", closed="left").agg(agg).dropna(subset=OHLC)
    return out
