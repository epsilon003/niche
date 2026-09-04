"""
Phase 3 — Tick -> audio synthesis.

Turns a window of trade ticks into an audible signal so market
microstructure becomes something a neural net (Phase 4) — or a human ear —
can pick anomalies out of. Two layers, mixed together:

  1. Pitch layer: price is mapped log-frequency (theremin-style). Rising
     price -> rising pitch. Held with zero-order-hold + light smoothing
     between ticks so silence between trades doesn't sound like silence
     between musical notes.
  2. Percussion layer: every actual trade fires a short exponentially-decaying
     click, amplitude scaled by trade size. Bursts of clicks = bursts of
     volume = audibly "busier" market, independent of price direction.

Output is a mono float32 waveform in [-1, 1] at `sample_rate`, exactly
`duration_seconds` long, regardless of how many/few ticks were in the
window (silence-padded if the window was thin).
"""

from __future__ import annotations

import numpy as np

from tick_engine.rolling_deque import Tick

DEFAULT_SAMPLE_RATE = 22_050
DEFAULT_DURATION_SECONDS = 60.0
DEFAULT_FREQ_LOW = 220.0  # A3 — mapped to the window's lowest price
DEFAULT_FREQ_HIGH = 880.0  # A5 — mapped to the window's highest price


def ticks_to_audio(
    ticks: list[Tick],
    *,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    duration_seconds: float = DEFAULT_DURATION_SECONDS,
    freq_low: float = DEFAULT_FREQ_LOW,
    freq_high: float = DEFAULT_FREQ_HIGH,
    click_decay_seconds: float = 0.05,
) -> np.ndarray:
    n_samples = int(sample_rate * duration_seconds)
    if not ticks:
        return np.zeros(n_samples, dtype=np.float32)

    t0 = ticks[0].timestamp
    # Anchor tick offsets to the END of the window so the most recent tick
    # always lands at duration_seconds, and older ticks fall earlier —
    # this matches how RollingTickWindow reports "last window_seconds."
    t_last = ticks[-1].timestamp
    offsets = np.array(
        [duration_seconds - (t_last - t.timestamp).total_seconds() for t in ticks]
    )
    offsets = np.clip(offsets, 0.0, duration_seconds)

    prices = np.array([t.price for t in ticks], dtype=np.float64)
    sizes = np.array([t.size for t in ticks], dtype=np.float64)

    audio = np.zeros(n_samples, dtype=np.float64)

    # --- layer 1: pitch envelope from price, via phase accumulation ---
    freq_track = _price_to_freq_track(
        prices, offsets, n_samples, sample_rate, freq_low, freq_high
    )
    phase = 2 * np.pi * np.cumsum(freq_track) / sample_rate
    pitch_layer = 0.35 * np.sin(phase)
    # gentle fade in/out to avoid clicks at buffer edges
    pitch_layer *= _edge_fade(n_samples, sample_rate, fade_seconds=0.05)
    audio += pitch_layer

    # --- layer 2: percussive click per trade, amplitude ~ log(size) ---
    if sizes.max() > 0:
        log_sizes = np.log1p(sizes)
        norm_sizes = log_sizes / log_sizes.max()
    else:
        norm_sizes = np.zeros_like(sizes)

    decay_samples = max(1, int(click_decay_seconds * sample_rate))
    click_kernel = np.exp(-np.linspace(0, 6, decay_samples))  # exp decay envelope
    click_freq = 1200.0  # short percussive tone, distinct from the pitch layer
    click_wave = np.sin(2 * np.pi * click_freq * np.arange(decay_samples) / sample_rate)
    click_shape = click_kernel * click_wave

    sample_idx = np.clip((offsets * sample_rate).astype(int), 0, n_samples - 1)
    for idx, amp in zip(sample_idx, norm_sizes):
        end = min(n_samples, idx + decay_samples)
        length = end - idx
        audio[idx:end] += 0.25 * amp * click_shape[:length]

    # normalize to avoid clipping, leave headroom
    peak = np.max(np.abs(audio))
    if peak > 0:
        audio = audio / peak * 0.9

    return audio.astype(np.float32)


def _price_to_freq_track(
    prices: np.ndarray,
    offsets: np.ndarray,
    n_samples: int,
    sample_rate: int,
    freq_low: float,
    freq_high: float,
) -> np.ndarray:
    """Interpolate price at every audio sample, then log-map to frequency."""
    p_min, p_max = prices.min(), prices.max()
    if p_max == p_min:
        norm = np.full_like(prices, 0.5)
    else:
        norm = (prices - p_min) / (p_max - p_min)

    sample_times = np.arange(n_samples) / sample_rate
    # np.interp needs strictly increasing x; ticks can share a timestamp —
    # nudge duplicates apart by a negligible epsilon.
    offsets_unique = np.maximum.accumulate(offsets + np.arange(len(offsets)) * 1e-9)
    norm_at_sample = np.interp(
        sample_times, offsets_unique, norm, left=norm[0], right=norm[-1]
    )

    # log-frequency mapping (musically even steps, avoids high end sounding cramped)
    log_low, log_high = np.log(freq_low), np.log(freq_high)
    freq_track = np.exp(log_low + norm_at_sample * (log_high - log_low))
    return freq_track


def _edge_fade(n_samples: int, sample_rate: int, fade_seconds: float) -> np.ndarray:
    fade_samples = min(n_samples // 2, int(fade_seconds * sample_rate))
    envelope = np.ones(n_samples)
    if fade_samples > 0:
        ramp = np.linspace(0, 1, fade_samples)
        envelope[:fade_samples] *= ramp
        envelope[-fade_samples:] *= ramp[::-1]
    return envelope
