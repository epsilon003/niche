"""
Phase 1B — 60-second rolling tick window.

Plain, dependency-free deque-based ring buffer keyed by wall-clock age
rather than a fixed count, since trade tick rates vary wildly by symbol
and time of day.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass(frozen=True, slots=True)
class Tick:
    symbol: str
    price: float
    size: int
    timestamp: datetime  # UTC


class RollingTickWindow:
    """Keeps only the ticks from the last `window_seconds` for one symbol."""

    def __init__(self, symbol: str, window_seconds: float = 60.0):
        self.symbol = symbol
        self.window_seconds = window_seconds
        self._ticks: deque[Tick] = deque()

    def add(self, tick: Tick) -> None:
        self._ticks.append(tick)
        self._evict_stale(reference=tick.timestamp)

    def _evict_stale(self, reference: datetime) -> None:
        cutoff = reference - timedelta(seconds=self.window_seconds)
        while self._ticks and self._ticks[0].timestamp < cutoff:
            self._ticks.popleft()

    def snapshot(self) -> list[Tick]:
        """Evict against wall-clock now, then return ticks oldest -> newest."""
        self._evict_stale(reference=datetime.now(timezone.utc))
        return list(self._ticks)

    def is_empty(self) -> bool:
        return len(self.snapshot()) == 0

    # --- derived stats used by Phase 3 sonification & Phase 5 cross-intel ---

    def last_price(self) -> float | None:
        ticks = self.snapshot()
        return ticks[-1].price if ticks else None

    def vwap(self) -> float | None:
        ticks = self.snapshot()
        if not ticks:
            return None
        notional = sum(t.price * t.size for t in ticks)
        volume = sum(t.size for t in ticks)
        return notional / volume if volume else None

    def price_change_pct(self) -> float | None:
        ticks = self.snapshot()
        if len(ticks) < 2:
            return None
        first, last = ticks[0].price, ticks[-1].price
        if first == 0:
            return None
        return (last - first) / first * 100.0

    def tick_rate_per_sec(self) -> float:
        ticks = self.snapshot()
        if not ticks:
            return 0.0
        span = (ticks[-1].timestamp - ticks[0].timestamp).total_seconds()
        return len(ticks) / span if span > 0 else float(len(ticks))

    def volume(self) -> int:
        return sum(t.size for t in self.snapshot())

    def prices(self) -> list[float]:
        return [t.price for t in self.snapshot()]


class TickEngine:
    """Owns one RollingTickWindow per symbol in the watchlist."""

    def __init__(self, symbols: list[str], window_seconds: float = 60.0):
        self.windows: dict[str, RollingTickWindow] = {
            sym: RollingTickWindow(sym, window_seconds) for sym in symbols
        }

    def ingest(self, tick: Tick) -> None:
        window = self.windows.setdefault(
            tick.symbol, RollingTickWindow(tick.symbol)
        )
        window.add(tick)

    def get(self, symbol: str) -> RollingTickWindow | None:
        return self.windows.get(symbol)
