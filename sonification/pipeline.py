"""
Phase 3 — Sonification pipeline.

Runs alongside the Phase 1B tick stream: every `hop_seconds`, take the
current 60s RollingTickWindow snapshot for each symbol, synthesize audio,
compute its mel-spectrogram, and drop it to disk under
data/spectrograms/<symbol>/<iso-timestamp>.npy for Phase 4 to pick up.

Run standalone against a live Alpaca stream:
    python -m sonification.pipeline
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path

from config import get_logger, settings
from tick_engine.alpaca_stream import AlpacaTickStream
from tick_engine.rolling_deque import TickEngine

from .spectrogram import (
    audio_to_mel_spectrogram,
    normalize_for_model,
    save_spectrogram,
    save_wav,
)
from .tick_to_audio import DEFAULT_SAMPLE_RATE, ticks_to_audio

log = get_logger("sonification.pipeline")

SPECTROGRAM_DIR = settings.data_dir / "spectrograms"
DEBUG_WAV_DIR = settings.data_dir / "debug_wav"


def sonify_symbol(
    engine: TickEngine,
    symbol: str,
    *,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    write_wav: bool = False,
) -> Path | None:
    window = engine.get(symbol)
    if window is None or window.is_empty():
        return None

    ticks = window.snapshot()
    audio = ticks_to_audio(ticks, sample_rate=sample_rate)
    log_mel = audio_to_mel_spectrogram(audio, sample_rate)
    model_input = normalize_for_model(log_mel)

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    out_path = SPECTROGRAM_DIR / symbol / f"{ts}.npy"
    save_spectrogram(model_input, out_path)

    if write_wav:
        save_wav(audio, sample_rate, DEBUG_WAV_DIR / symbol / f"{ts}.wav")

    return out_path


class SonificationPipeline:
    def __init__(self, symbols: list[str] | None = None, hop_seconds: float = 5.0):
        self.symbols = symbols or settings.watchlist
        self.hop_seconds = hop_seconds
        self.stream = AlpacaTickStream(symbols=self.symbols)
        self._stop = asyncio.Event()

    async def run(self, write_wav: bool = False) -> None:
        stream_task = asyncio.create_task(self.stream.run_forever())
        try:
            while not self._stop.is_set():
                await asyncio.sleep(self.hop_seconds)
                for symbol in self.symbols:
                    path = sonify_symbol(
                        self.stream.engine, symbol, write_wav=write_wav
                    )
                    if path:
                        log.info("Wrote spectrogram: %s", path)
        finally:
            self.stream.stop()
            await stream_task

    def stop(self) -> None:
        self._stop.set()


async def _main() -> None:
    pipeline = SonificationPipeline()
    await pipeline.run(write_wav=False)


if __name__ == "__main__":
    asyncio.run(_main())
