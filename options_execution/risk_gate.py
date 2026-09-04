"""
Phase 6 — Max-loss risk gate.

For a defined-risk debit spread, max loss per contract equals the net
debit paid (times the 100-share multiplier) — the spread structurally
cannot lose more than what you paid for it, before slippage/fees. This
gate refuses to let a trade risk more than `max_loss_pct` of current
account equity, sized down to whole contracts (never rounds up), and
rejects outright (0 contracts) if even a single contract would breach the
cap — it never partially violates the gate to force a trade through.
"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_MAX_LOSS_PCT = (
    2.0  # percent of account equity — per the diagram's "max loss 2% gate"
)
CONTRACTS_MULTIPLIER = 100  # standard equity option contract multiplier


@dataclass(frozen=True)
class RiskGateResult:
    approved: bool
    max_contracts: int
    max_loss_budget: float  # dollars available under the cap
    equity: float
    reason: str


def size_position(
    equity: float,
    net_debit_per_contract: float,
    *,
    max_loss_pct: float = DEFAULT_MAX_LOSS_PCT,
    contracts_multiplier: int = CONTRACTS_MULTIPLIER,
    max_contracts_cap: int = 20,
) -> RiskGateResult:
    if net_debit_per_contract <= 0:
        return RiskGateResult(
            False, 0, 0.0, equity, "net_debit_per_contract must be positive"
        )
    if equity <= 0:
        return RiskGateResult(False, 0, 0.0, equity, "non-positive account equity")

    max_loss_budget = equity * (max_loss_pct / 100.0)
    per_contract_risk = net_debit_per_contract * contracts_multiplier
    affordable = int(max_loss_budget // per_contract_risk)
    affordable = min(affordable, max_contracts_cap)

    if affordable < 1:
        return RiskGateResult(
            False,
            0,
            max_loss_budget,
            equity,
            f"even 1 contract (${per_contract_risk:.2f} max loss) exceeds the "
            f"{max_loss_pct:.1f}% equity cap (${max_loss_budget:.2f} on ${equity:.2f} equity)",
        )
    return RiskGateResult(True, affordable, max_loss_budget, equity, "ok")
