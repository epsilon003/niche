"""
Phase 1B — Tick engine: Alpaca WebSocket trade stream -> 60s rolling deque.

Connects to Alpaca's market-data WebSocket (IEX feed by default, which is
what paper/free accounts are entitled to), authenticates, subscribes to
trades for the watchlist, and feeds every trade into a TickEngine.

Optionally accepts an `on_tick` async callback so downstream phases
(sonification in Phase 3) can react to each tick in real time instead of
only polling the rolling window.

Run standalone:
    python -m tick_engine.alpaca_stream
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Awaitable, Callable, Optional

import websockets
from websockets.exceptions import ConnectionClosed

from config import get_logger, settings
from .rolling_deque import Tick, TickEngine

log = get_logger("tick_engine.alpaca_stream")

OnTick = Callable[[Tick], Awaitable[None]]


class AlpacaTickStream:
    def __init__(
        self,
        symbols: list[str] | None = None,
        window_seconds: float = 60.0,
        on_tick: Optional[OnTick] = None,
    ):
        self.symbols = symbols or settings.watchlist
        self.engine = TickEngine(self.symbols, window_seconds=window_seconds)
        self.on_tick = on_tick
        self._stop = asyncio.Event()

    def stop(self) -> None:
        self._stop.set()

    async def run_forever(self) -> None:
        """Reconnect-with-backoff loop around a single streaming session."""
        backoff = 1.0
        while not self._stop.is_set():
            try:
                await self._run_session()
                backoff = 1.0  # clean exit -> reset backoff
            except (ConnectionClosed, OSError) as exc:
                log.warning("Stream dropped (%s). Reconnecting in %.1fs.", exc, backoff)
            except Exception:
                log.exception("Unexpected error in tick stream; reconnecting.")
            if self._stop.is_set():
                break
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30.0)

    async def _run_session(self) -> None:
        problems = settings.validate_alpaca()
        if problems:
            raise RuntimeError(f"Cannot start stream, config problems: {problems}")

        async with websockets.connect(
            settings.alpaca_data_stream_url, ping_interval=20, ping_timeout=20
        ) as ws:
            await self._authenticate(ws)
            await self._subscribe(ws)
            log.info("Subscribed to trades for %s", self.symbols)

            async for raw in ws:
                if self._stop.is_set():
                    return
                await self._handle_message(json.loads(raw))

    async def _authenticate(self, ws) -> None:
        await ws.recv()  # server greeting
        await ws.send(json.dumps({
            "action": "auth",
            "key": settings.alpaca_api_key,
            "secret": settings.alpaca_secret_key,
        }))
        resp = json.loads(await ws.recv())
        ok = any(m.get("T") == "success" and m.get("msg") == "authenticated" for m in resp)
        if not ok:
            raise RuntimeError(f"Alpaca WS auth failed: {resp}")

    async def _subscribe(self, ws) -> None:
        await ws.send(json.dumps({"action": "subscribe", "trades": self.symbols}))
        resp = json.loads(await ws.recv())
        log.debug("Subscribe response: %s", resp)

    async def _handle_message(self, messages: list[dict]) -> None:
        for msg in messages:
            if msg.get("T") != "t":  # "t" = trade message
                continue
            tick = Tick(
                symbol=msg["S"],
                price=float(msg["p"]),
                size=int(msg["s"]),
                timestamp=_parse_alpaca_ts(msg["t"]),
            )
            self.engine.ingest(tick)
            if self.on_tick is not None:
                await self.on_tick(tick)


def _parse_alpaca_ts(raw: str) -> datetime:
    # Alpaca sends RFC3339 with nanosecond precision, e.g. "2026-09-02T14:31:00.123456789Z"
    trimmed = raw[:-1]  # drop trailing 'Z'
    if "." in trimmed:
        head, frac = trimmed.split(".")
        frac = (frac + "000000")[:6]  # truncate to microseconds
        trimmed = f"{head}.{frac}"
    return datetime.fromisoformat(trimmed).replace(tzinfo=timezone.utc)


async def _demo_on_tick(tick: Tick) -> None:
    log.info("TICK %-6s $%8.2f x%-6d @ %s", tick.symbol, tick.price, tick.size, tick.timestamp.time())


async def _main() -> None:
    stream = AlpacaTickStream(on_tick=_demo_on_tick)
    await stream.run_forever()


if __name__ == "__main__":
    asyncio.run(_main())
