"""
Phase 6 — IV rank.

IV rank = where today's implied volatility sits within its own trailing
history: (iv_today - iv_min) / (iv_max - iv_min) * 100. It's only
meaningful relative to a real history, so this module persists one IV
sample per (ticker, date) to data/iv_history/<ticker>.jsonl on every call,
and reports "unavailable" rather than a misleading number until there's
at least MIN_HISTORY_DAYS of samples behind it.

Practical consequence, stated plainly: on a fresh install, IV rank will
be unavailable for every ticker for the first ~20 trading days this
pipeline runs, since there's no history yet. `options_execution.execution`
treats that as non-blocking by default (IV_RANK_REQUIRE_HISTORY=false) —
see its module docstring for the reasoning.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from config import settings

IV_HISTORY_DIR = settings.data_dir / "iv_history"
MIN_HISTORY_DAYS = 20  # ~1 trading month; below this a rank isn't statistically meaningful


@dataclass(frozen=True)
class IvRankResult:
    available: bool
    rank: float | None  # 0-100
    n_days: int
    iv_min: float | None
    iv_max: float | None
    iv_today: float
    reason: str


def _history_path(ticker: str) -> Path:
    return IV_HISTORY_DIR / f"{ticker.upper()}.jsonl"


def _load_history(ticker: str) -> list[dict]:
    path = _history_path(ticker)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def record_iv_sample(ticker: str, iv: float, as_of: date | None = None) -> None:
    as_of = as_of or datetime.now(timezone.utc).date()
    path = _history_path(ticker)
    path.parent.mkdir(parents=True, exist_ok=True)

    existing = _load_history(ticker)
    existing = [row for row in existing if row["date"] != as_of.isoformat()]  # one sample/day
    existing.append({"date": as_of.isoformat(), "iv": iv})
    existing.sort(key=lambda r: r["date"])

    with path.open("w") as f:
        for row in existing:
            f.write(json.dumps(row) + "\n")


def compute_iv_rank(ticker: str, current_iv: float, lookback_days: int = 252) -> IvRankResult:
    """Records `current_iv` as today's sample, then ranks it against trailing history."""
    record_iv_sample(ticker, current_iv)
    history = _load_history(ticker)[-lookback_days:]

    if len(history) < MIN_HISTORY_DAYS:
        return IvRankResult(
            False, None, len(history), None, None, current_iv,
            f"only {len(history)} day(s) of IV history for {ticker} — need at least "
            f"{MIN_HISTORY_DAYS} to compute a meaningful rank",
        )

    ivs = [row["iv"] for row in history]
    iv_min, iv_max = min(ivs), max(ivs)
    rank = 50.0 if iv_max == iv_min else (current_iv - iv_min) / (iv_max - iv_min) * 100.0
    return IvRankResult(True, rank, len(history), iv_min, iv_max, current_iv, "ok")
