"""
Phase 4 — Anomaly scorer.

Raw autoencoder reconstruction-error (MSE) isn't directly comparable across
tickers or across a training run's convergence state — a chatty, high-volume
stock will naturally reconstruct slightly worse than a quiet one even when
both are behaving "normally." So we track a per-symbol running mean/std of
recent reconstruction error (EWMA) and report a z-score: "how many standard
deviations off this ticker's own recent normal is this window."

Persisted to disk so the running stats survive process restarts.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from config import get_logger, settings

log = get_logger("neural_perception.anomaly_scorer")

STATE_PATH = settings.data_dir / "anomaly_ewma_state.json"


@dataclass
class EwmaState:
    mean: float
    var: float
    n: int = 0

    @classmethod
    def fresh(cls) -> EwmaState:
        return cls(mean=0.0, var=1e-6, n=0)


class AnomalyScorer:
    """One EWMA mean/variance tracker per symbol, alpha-smoothed."""

    def __init__(self, alpha: float = 0.05):
        self.alpha = alpha
        self._state: dict[str, EwmaState] = {}
        self._load()

    def _load(self) -> None:
        if STATE_PATH.exists():
            raw = json.loads(STATE_PATH.read_text())
            self._state = {sym: EwmaState(**s) for sym, s in raw.items()}

    def _save(self) -> None:
        STATE_PATH.write_text(
            json.dumps({sym: asdict(s) for sym, s in self._state.items()})
        )

    def score(self, symbol: str, raw_error: float) -> dict:
        """
        Update running stats with this observation and return both the raw
        error and a z-score. First ~20 observations for a symbol are
        reported with low confidence since the running stats haven't
        stabilized yet.
        """
        state = self._state.setdefault(symbol, EwmaState.fresh())

        if state.n == 0:
            state.mean = raw_error
            state.var = 1e-6
        else:
            delta = raw_error - state.mean
            state.mean += self.alpha * delta
            state.var = (1 - self.alpha) * (state.var + self.alpha * delta**2)
        state.n += 1

        std = max(state.var**0.5, 1e-6)
        z = (raw_error - state.mean) / std

        self._save()

        return {
            "symbol": symbol,
            "raw_error": raw_error,
            "running_mean": state.mean,
            "running_std": std,
            "z_score": z,
            "n_observations": state.n,
            "confidence": min(1.0, state.n / 20.0),
        }
