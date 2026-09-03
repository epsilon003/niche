"""
Phase 5 — Rule engine.

Deliberately not an LLM: this is the one decision point in the pipeline
where we want a fixed, auditable, backtestable set of rules rather than a
model's judgment call. Everything upstream of this (the scientific agent's
POSITIVE/NEGATIVE/UNCERTAIN read, the autoencoder's anomaly z-score) is
allowed to be probabilistic; the fusion step is not.

Inputs:
  - ScientificSignal: what the trial/FDA data means (direction + confidence)
  - MarketAnomaly:    how unusual the last 60s of trading looks (magnitude only)
  - MarketStats:      which way price actually moved in that window (direction)

The anomaly z-score alone can't tell you if the market agrees or
disagrees with the science — a big z-score just means "unusual," not
"unusual in the direction I expected." So direction comes from
price_change_pct, and the anomaly score is used as a *gate*: it tells you
whether the market is actually reacting to something right now, separate
from which way it's reacting.

Decision table (see `decide()` for the exact logic):

  scientific         market direction      anomaly gate       -> decision   bias
  ----------------   -------------------   ----------------   -----------   ----
  POSITIVE (conf)     UP                    open (z >= thr)    TRADE         CALL
  POSITIVE (conf)     FLAT / no anomaly     n/a                MONITOR       NONE
  POSITIVE (conf)     DOWN                  open (z >= thr)    SKIP          NONE  (disagree)
  NEGATIVE (conf)     DOWN                  open (z >= thr)    TRADE         PUT
  NEGATIVE (conf)     FLAT / no anomaly     n/a                MONITOR       NONE
  NEGATIVE (conf)     UP                    open (z >= thr)    SKIP          NONE  (disagree)
  UNCERTAIN / low-conf anything             open (z >= thr)    MONITOR       NONE  (something's happening, watch)
  UNCERTAIN / low-conf anything             closed             SKIP          NONE  (nothing to act on)
"""
from __future__ import annotations

from datetime import datetime, timezone

from .models import (
    Bias,
    CrossIntelDecision,
    Decision,
    MarketAnomaly,
    MarketDirection,
    MarketStats,
    ScientificSignal,
)

# --- tunable thresholds, all in one place ---
SCI_CONFIDENCE_MIN = 0.55        # below this, treat the label as UNCERTAIN
ANOMALY_Z_THRESHOLD = 2.5        # |z| at/above this counts as "market is reacting"
ANOMALY_CONFIDENCE_MIN = 0.5     # EWMA stats need this many observations behind them
DIRECTION_MIN_PCT = 0.3          # price move smaller than this (either way) counts as FLAT


def classify_direction(price_change_pct: float | None) -> MarketDirection:
    if price_change_pct is None:
        return MarketDirection.FLAT
    if price_change_pct >= DIRECTION_MIN_PCT:
        return MarketDirection.UP
    if price_change_pct <= -DIRECTION_MIN_PCT:
        return MarketDirection.DOWN
    return MarketDirection.FLAT


def _anomaly_gate_open(anomaly: MarketAnomaly | None) -> bool:
    if anomaly is None:
        return False
    return abs(anomaly.z_score) >= ANOMALY_Z_THRESHOLD and anomaly.confidence >= ANOMALY_CONFIDENCE_MIN


def decide(
    sci: ScientificSignal,
    anomaly: MarketAnomaly | None,
    stats: MarketStats | None,
) -> CrossIntelDecision:
    direction = classify_direction(stats.price_change_pct if stats else None)
    gate_open = _anomaly_gate_open(anomaly)

    effective_label = sci.label if sci.confidence >= SCI_CONFIDENCE_MIN else "UNCERTAIN"

    decision, bias, reason_code, reason = _apply_rules(effective_label, direction, gate_open, sci)

    return CrossIntelDecision(
        ticker=sci.ticker,
        decision=decision,
        bias=bias,
        reason_code=reason_code,
        reason=reason,
        scientific_label=sci.label,
        scientific_confidence=sci.confidence,
        market_direction=direction,
        price_change_pct=stats.price_change_pct if stats else None,
        anomaly_z_score=anomaly.z_score if anomaly else None,
        anomaly_confidence=anomaly.confidence if anomaly else None,
        catalyst_title=sci.catalyst_title,
        catalyst_url=sci.catalyst_url,
        dedup_key=sci.dedup_key,
        decided_at=datetime.now(timezone.utc),
    )


def _apply_rules(
    effective_label: str,
    direction: MarketDirection,
    gate_open: bool,
    sci: ScientificSignal,
) -> tuple[Decision, Bias, str, str]:
    if effective_label == "UNCERTAIN":
        if gate_open:
            return (
                Decision.MONITOR, Bias.NONE, "uncertain_but_market_moving",
                "Scientific read is uncertain (or low-confidence), but the market "
                "is showing an unusual move right now — watch, don't act yet.",
            )
        return (
            Decision.SKIP, Bias.NONE, "no_signal",
            "Scientific read is uncertain and the market shows nothing unusual. "
            "Nothing to act on.",
        )

    if effective_label == "POSITIVE":
        if direction == MarketDirection.UP and gate_open:
            return (
                Decision.TRADE, Bias.CALL, "confirmed_positive",
                f"Scientific agent read POSITIVE ({sci.confidence:.2f} confidence) and "
                "the market is moving up on unusual volume/volatility — confirmed.",
            )
        if direction == MarketDirection.DOWN and gate_open:
            return (
                Decision.SKIP, Bias.NONE, "disagree_positive_but_market_down",
                "Scientific agent read POSITIVE but the market is moving down on an "
                "unusual, high-confidence anomaly — the market may be pricing in "
                "something the agent didn't see. Disagreement — skip.",
            )
        return (
            Decision.MONITOR, Bias.NONE, "positive_awaiting_confirmation",
            "Scientific agent read POSITIVE but the market hasn't reacted yet "
            "(flat, or no confirmed anomaly) — wait for price action to confirm.",
        )

    if effective_label == "NEGATIVE":
        if direction == MarketDirection.DOWN and gate_open:
            return (
                Decision.TRADE, Bias.PUT, "confirmed_negative",
                f"Scientific agent read NEGATIVE ({sci.confidence:.2f} confidence) and "
                "the market is moving down on unusual volume/volatility — confirmed.",
            )
        if direction == MarketDirection.UP and gate_open:
            return (
                Decision.SKIP, Bias.NONE, "disagree_negative_but_market_up",
                "Scientific agent read NEGATIVE but the market is moving up on an "
                "unusual, high-confidence anomaly — disagreement — skip.",
            )
        return (
            Decision.MONITOR, Bias.NONE, "negative_awaiting_confirmation",
            "Scientific agent read NEGATIVE but the market hasn't reacted yet "
            "— wait for price action to confirm.",
        )

    # Defensive fallback — should be unreachable given the label validation
    # upstream in scientific_agent, but never silently trade on a signal we
    # don't recognize.
    return (
        Decision.SKIP, Bias.NONE, "unrecognized_label",
        f"Unrecognized scientific label {effective_label!r} — refusing to act.",
    )
