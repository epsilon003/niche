"""
Phase 5 — Cross-intelligence agent orchestrator.

Joins Phase 2's output (data/scientific_classifications.jsonl) with Phase
4's output (data/anomaly_scores.jsonl) and Phase 3's per-window stats
sidecars, by ticker and nearest timestamp, then runs the rule engine
(rules.decide) on each pairing. Writes data/cross_intel_decisions.jsonl —
what Phase 6 (options strategy + execution) will read.

A scientific classification with no matching market data yet (e.g. the
sonification pipeline hasn't been running for that ticker) is still
processed — it just falls through the rule engine's "no anomaly gate"
paths (MONITOR or SKIP, never TRADE), so this is safe to run even with a
partial pipeline.

Usage:
    python -m cross_intelligence.engine --once
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path

from config import get_logger, settings
from .models import CrossIntelDecision, MarketAnomaly, MarketStats, ScientificSignal
from .rules import decide

log = get_logger("cross_intelligence.engine")

SCIENTIFIC_LOG_PATH = settings.data_dir / "scientific_classifications.jsonl"
ANOMALY_LOG_PATH = settings.data_dir / "anomaly_scores.jsonl"
DECISIONS_LOG_PATH = settings.data_dir / "cross_intel_decisions.jsonl"
SEEN_STORE_PATH = settings.data_dir / "cross_intel_seen.json"

# How far apart (in either direction) a scientific classification and a
# market anomaly reading are allowed to be and still be considered "the
# same moment" for fusion purposes.
MAX_STALENESS = timedelta(minutes=10)


def _load_scientific_signals() -> list[ScientificSignal]:
    if not SCIENTIFIC_LOG_PATH.exists():
        return []
    out = []
    for line in SCIENTIFIC_LOG_PATH.read_text().splitlines():
        if line.strip():
            out.append(ScientificSignal.model_validate_json(line))
    return out


def _load_anomalies_by_symbol() -> dict[str, list[MarketAnomaly]]:
    by_symbol: dict[str, list[MarketAnomaly]] = {}
    if not ANOMALY_LOG_PATH.exists():
        return by_symbol
    for line in ANOMALY_LOG_PATH.read_text().splitlines():
        if not line.strip():
            continue
        anomaly = MarketAnomaly.model_validate_json(line)
        by_symbol.setdefault(anomaly.symbol, []).append(anomaly)
    for lst in by_symbol.values():
        lst.sort(key=lambda a: a.timestamp)  # "%Y%m%dT%H%M%S" sorts lexically = chronologically
    return by_symbol


def _anomaly_timestamp(anomaly: MarketAnomaly) -> datetime | None:
    try:
        return datetime.strptime(anomaly.timestamp, "%Y%m%dT%H%M%S")
    except ValueError:
        return None


def _find_best_anomaly(
    ticker: str,
    around: datetime,
    anomalies_by_symbol: dict[str, list[MarketAnomaly]],
) -> MarketAnomaly | None:
    candidates = anomalies_by_symbol.get(ticker, [])
    best, best_delta = None, None
    around_naive = around.replace(tzinfo=None)
    for anomaly in candidates:
        ts = _anomaly_timestamp(anomaly)
        if ts is None:
            continue
        delta = abs(ts - around_naive)
        if delta > MAX_STALENESS:
            continue
        if best_delta is None or delta < best_delta:
            best, best_delta = anomaly, delta
    return best


def _load_stats_for_anomaly(anomaly: MarketAnomaly) -> MarketStats | None:
    npy_path = Path(anomaly.source_file)
    stats_path = npy_path.with_suffix("").with_suffix(".stats.json")
    if not stats_path.exists():
        return None
    try:
        return MarketStats.model_validate_json(stats_path.read_text())
    except Exception:  # noqa: BLE001
        log.warning("Malformed stats sidecar at %s, ignoring", stats_path)
        return None


def _load_seen() -> set[str]:
    if not SEEN_STORE_PATH.exists():
        return set()
    return set(json.loads(SEEN_STORE_PATH.read_text()))


def _save_seen(seen: set[str]) -> None:
    SEEN_STORE_PATH.write_text(json.dumps(sorted(seen)))


def run_once() -> list[CrossIntelDecision]:
    signals = _load_scientific_signals()
    seen = _load_seen()
    todo = [s for s in signals if s.dedup_key not in seen]

    if not todo:
        log.info("No new scientific signals to fuse.")
        return []

    anomalies_by_symbol = _load_anomalies_by_symbol()
    decisions: list[CrossIntelDecision] = []

    with DECISIONS_LOG_PATH.open("a") as f:
        for sci in todo:
            anomaly = _find_best_anomaly(sci.ticker, sci.classified_at, anomalies_by_symbol)
            stats = _load_stats_for_anomaly(anomaly) if anomaly else None

            result = decide(sci, anomaly, stats)
            f.write(result.model_dump_json() + "\n")
            seen.add(sci.dedup_key)
            decisions.append(result)

            log.info(
                "[%s] %s (%s) — %s | sci=%s(%.2f) dir=%s z=%s",
                result.ticker, result.decision.value, result.reason_code,
                result.catalyst_title[:60],
                result.scientific_label, result.scientific_confidence,
                result.market_direction.value,
                f"{result.anomaly_z_score:+.2f}" if result.anomaly_z_score is not None else "n/a",
            )

    _save_seen(seen)
    log.info("Wrote %d decisions to %s", len(decisions), DECISIONS_LOG_PATH)
    return decisions


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 5 cross-intelligence agent")
    parser.add_argument("--once", action="store_true", help="currently the only mode")
    parser.parse_args()
    run_once()


if __name__ == "__main__":
    main()
