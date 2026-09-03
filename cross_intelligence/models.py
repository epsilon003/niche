"""Phase 5 — data model shared between the rule engine and its inputs/outputs."""
from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class Decision(str, Enum):
    TRADE = "TRADE"      # confirm — scientific + market agree, act
    MONITOR = "MONITOR"  # wait — one signal present, the other not confirming yet
    SKIP = "SKIP"        # disagree, or no usable signal at all — don't act


class MarketDirection(str, Enum):
    UP = "UP"
    DOWN = "DOWN"
    FLAT = "FLAT"


class Bias(str, Enum):
    CALL = "CALL"
    PUT = "PUT"
    NONE = "NONE"


class ScientificSignal(BaseModel):
    """One row from data/scientific_classifications.jsonl."""
    ticker: str
    label: str  # POSITIVE | NEGATIVE | UNCERTAIN
    confidence: float
    rationale: str
    catalyst_kind: str
    catalyst_title: str
    catalyst_url: str = ""
    dedup_key: str
    classified_at: datetime


class MarketAnomaly(BaseModel):
    """One row from data/anomaly_scores.jsonl."""
    symbol: str
    raw_error: float
    running_mean: float
    running_std: float
    z_score: float
    n_observations: int
    confidence: float
    source_file: str
    timestamp: str


class MarketStats(BaseModel):
    """One sidecar *.stats.json written by sonification/pipeline.py."""
    symbol: str
    captured_at: datetime
    last_price: float | None
    vwap: float | None
    price_change_pct: float | None
    tick_rate_per_sec: float
    volume: int
    n_ticks: int


class CrossIntelDecision(BaseModel):
    ticker: str
    decision: Decision
    bias: Bias
    reason_code: str
    reason: str
    scientific_label: str
    scientific_confidence: float
    market_direction: MarketDirection
    price_change_pct: float | None
    anomaly_z_score: float | None
    anomaly_confidence: float | None
    catalyst_title: str
    catalyst_url: str
    dedup_key: str
    decided_at: datetime
