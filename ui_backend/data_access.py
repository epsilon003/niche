"""
Phase 7 — Shared data access for the UI backend.

Every endpoint reads directly from the same data/*.jsonl files the
pipeline phases already write — there's no separate database. This module
is the one place that knows those file layouts, so routers stay thin.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from config import settings

CATALYST_EVENTS_PATH = settings.data_dir / "catalyst_events.jsonl"
SCIENTIFIC_LOG_PATH = settings.data_dir / "scientific_classifications.jsonl"
DECISIONS_LOG_PATH = settings.data_dir / "cross_intel_decisions.jsonl"
TRADE_LOG_PATH = settings.data_dir / "trade_log.jsonl"
ANOMALY_LOG_PATH = settings.data_dir / "anomaly_scores.jsonl"
SPECTROGRAM_DIR = settings.data_dir / "spectrograms"


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # tolerate a partially-written last line from a concurrent writer
    return out


def _parse_ts(value: Any) -> datetime | None:
    """
    Parses an ISO timestamp and always returns a timezone-aware UTC
    datetime, treating any naive input as UTC. Every current writer stamps
    timezone-aware UTC times, but rows written by an older version of the
    catalyst watcher (pre-fix) may be naive — mixing naive and aware
    datetimes in a sort() raises TypeError, so this normalizes regardless
    of what's actually on disk rather than assuming the fix alone is enough.
    """
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def parse_iso_datetime(value: Any) -> datetime | None:
    """Public wrapper — also used by routers to normalize query params the same way."""
    return _parse_ts(value)


# --- per-source event -> unified agent-log-event shape ---

def _catalyst_events() -> list[dict]:
    events = []
    for row in _read_jsonl(CATALYST_EVENTS_PATH):
        events.append({
            "phase": "catalyst_watcher",
            "ticker": row.get("ticker"),
            "timestamp": row.get("fetched_at"),
            "title": f"{row.get('ticker')} — {row.get('kind')}",
            "detail": row.get("title", "") + (f" ({row['detail']})" if row.get("detail") else ""),
            "url": row.get("url", ""),
            "raw": row,
        })
    return events


def _scientific_events() -> list[dict]:
    events = []
    for row in _read_jsonl(SCIENTIFIC_LOG_PATH):
        conf = row.get("confidence")
        conf_str = f"{conf:.0%}" if isinstance(conf, (int, float)) else "?"
        events.append({
            "phase": "scientific_agent",
            "ticker": row.get("ticker"),
            "timestamp": row.get("classified_at"),
            "title": f"{row.get('ticker')} — {row.get('label')} ({conf_str} confidence)",
            "detail": row.get("rationale", ""),
            "url": row.get("catalyst_url", ""),
            "raw": row,
        })
    return events


def _cross_intel_events() -> list[dict]:
    events = []
    for row in _read_jsonl(DECISIONS_LOG_PATH):
        events.append({
            "phase": "cross_intelligence",
            "ticker": row.get("ticker"),
            "timestamp": row.get("decided_at"),
            "title": f"{row.get('ticker')} — {row.get('decision')} ({row.get('bias')})",
            "detail": row.get("reason", ""),
            "url": row.get("catalyst_url", ""),
            "raw": row,
        })
    return events


def _trade_events() -> list[dict]:
    events = []
    for row in _read_jsonl(TRADE_LOG_PATH):
        detail = row.get("spread_description") or row.get("rejection_reason") or ""
        events.append({
            "phase": "options_execution",
            "ticker": row.get("ticker"),
            "timestamp": row.get("logged_at"),
            "title": f"{row.get('ticker')} — {row.get('status')}",
            "detail": detail,
            "url": "",
            "raw": row,
        })
    return events


def merge_agent_log_events(
    since: datetime | None = None,
    until: datetime | None = None,
) -> list[dict]:
    """All four phases' events, unified, sorted ascending by timestamp."""
    all_events: Iterable[dict] = (
        _catalyst_events() + _scientific_events() + _cross_intel_events() + _trade_events()
    )
    out = []
    for ev in all_events:
        ts = _parse_ts(ev["timestamp"])
        if ts is None:
            continue
        if since is not None and ts <= since:
            continue
        if until is not None and ts > until:
            continue
        ev["_ts_parsed"] = ts
        out.append(ev)
    out.sort(key=lambda e: e["_ts_parsed"])
    for ev in out:
        del ev["_ts_parsed"]
    return out


# --- market data ---

def list_known_symbols() -> list[str]:
    symbols = set(settings.watchlist)
    if SPECTROGRAM_DIR.exists():
        symbols.update(p.name for p in SPECTROGRAM_DIR.iterdir() if p.is_dir())
    return sorted(symbols)


def latest_spectrogram(symbol: str, target_frames: int = 200) -> dict | None:
    """
    Loads the most recent spectrogram for `symbol` and block-mean-pools it
    down to (n_mels, target_frames) — the raw array (64 x ~5000+ floats)
    is far more resolution than a browser chart needs and too large to
    poll every few seconds; ~64 x 200 renders identically at chart size
    and is roughly 25x smaller on the wire.
    """
    symbol_dir = SPECTROGRAM_DIR / symbol.upper()
    if not symbol_dir.exists():
        return None
    files = sorted(symbol_dir.glob("*.npy"))
    if not files:
        return None
    latest = files[-1]
    spec = np.load(str(latest))

    n_mels, n_frames = spec.shape
    if n_frames > target_frames:
        # block-mean pool along the time axis
        trimmed = spec[:, : n_frames - (n_frames % target_frames)] if n_frames % target_frames else spec
        pooled = trimmed.reshape(n_mels, target_frames, -1).mean(axis=2)
    else:
        pooled = spec

    return {
        "symbol": symbol.upper(),
        "timestamp": latest.stem,
        "n_mels": int(pooled.shape[0]),
        "n_frames": int(pooled.shape[1]),
        "data": pooled.round(3).tolist(),
    }


def anomaly_history(symbol: str, limit: int = 200) -> list[dict]:
    rows = [r for r in _read_jsonl(ANOMALY_LOG_PATH) if r.get("symbol", "").upper() == symbol.upper()]
    rows.sort(key=lambda r: r.get("timestamp", ""))
    return rows[-limit:]


def trade_log(status: str | None = None, limit: int = 200) -> list[dict]:
    rows = _read_jsonl(TRADE_LOG_PATH)
    if status:
        rows = [r for r in rows if r.get("status") == status.upper()]
    rows.sort(key=lambda r: r.get("logged_at", ""), reverse=True)
    return rows[:limit]
