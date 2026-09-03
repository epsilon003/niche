"""
Phase 6 — Execution orchestrator.

Reads new TRADE decisions from data/cross_intel_decisions.jsonl (Phase 5),
builds a debit spread per the bias (see strategy.py), runs it through the
IV-rank gate and the max-loss gate, and either submits a paper multi-leg
order or logs a rejection with the specific reason. Every decision this
module makes — trade or reject — is written to data/trade_log.jsonl.
Nothing here trades uncapped risk: only debit spreads, only against the
paper endpoint, and only if EXECUTION_DRY_RUN is explicitly set to false.

IV rank gate default behavior: on a fresh install there's no IV history
yet (see iv_rank.py), so by default (IV_RANK_REQUIRE_HISTORY=false)
missing history does not block a trade — only a *confirmed* elevated IV
rank does. Flip IV_RANK_REQUIRE_HISTORY=true once you have enough history
built up if you'd rather be conservative from day one.

Usage:
    python -m options_execution.execution --once
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone

from config import get_logger, settings
from cross_intelligence.models import CrossIntelDecision, Decision
from . import alpaca_options_client as alpaca
from .iv_rank import compute_iv_rank
from .models import DebitSpread, OptionType, TradeLogEntry, TradeStatus
from .risk_gate import DEFAULT_MAX_LOSS_PCT, size_position
from .strategy import SpreadSelectionError, build_debit_spread

log = get_logger("options_execution.execution")

DECISIONS_LOG_PATH = settings.data_dir / "cross_intel_decisions.jsonl"
TRADE_LOG_PATH = settings.data_dir / "trade_log.jsonl"
SEEN_STORE_PATH = settings.data_dir / "execution_seen.json"

IV_RANK_MAX = float(os.getenv("IV_RANK_MAX", "90"))
IV_RANK_REQUIRE_HISTORY = os.getenv("IV_RANK_REQUIRE_HISTORY", "false").lower() == "true"
MAX_LOSS_PCT = float(os.getenv("MAX_LOSS_PCT", str(DEFAULT_MAX_LOSS_PCT)))
DRY_RUN = os.getenv("EXECUTION_DRY_RUN", "true").lower() != "false"


def _load_decisions() -> list[CrossIntelDecision]:
    if not DECISIONS_LOG_PATH.exists():
        return []
    return [
        CrossIntelDecision.model_validate_json(line)
        for line in DECISIONS_LOG_PATH.read_text().splitlines() if line.strip()
    ]


def _load_seen() -> set[str]:
    if not SEEN_STORE_PATH.exists():
        return set()
    return set(json.loads(SEEN_STORE_PATH.read_text()))


def _save_seen(seen: set[str]) -> None:
    SEEN_STORE_PATH.write_text(json.dumps(sorted(seen)))


def _log_entry(entry: TradeLogEntry) -> TradeLogEntry:
    with TRADE_LOG_PATH.open("a") as f:
        f.write(entry.model_dump_json() + "\n")
    return entry


def _average_iv(spread: DebitSpread) -> float | None:
    ivs = [leg.contract.implied_volatility for leg in (spread.long_leg, spread.short_leg) if leg.contract.implied_volatility]
    return sum(ivs) / len(ivs) if ivs else None


def _reject(decision: CrossIntelDecision, reason: str, *, spread: DebitSpread | None = None,
            iv_rank: float | None = None, contracts: int = 0) -> TradeLogEntry:
    kwargs = dict(
        ticker=decision.ticker, status=TradeStatus.REJECTED, rejection_reason=reason,
        bias=decision.bias.value, dedup_key=decision.dedup_key, contracts=contracts,
        iv_rank=iv_rank, logged_at=datetime.now(timezone.utc),
    )
    if spread is not None:
        kwargs.update(
            spread_description=_describe(spread), expiration=spread.expiration,
            long_strike=spread.long_leg.contract.strike, short_strike=spread.short_leg.contract.strike,
            net_debit_per_contract=spread.net_debit,
        )
    entry = _log_entry(TradeLogEntry(**kwargs))
    log.warning("REJECTED %s: %s", decision.ticker, reason)
    return entry


def _describe(spread: DebitSpread) -> str:
    return (
        f"{spread.ticker} {spread.option_type.value} debit spread {spread.expiration} "
        f"long {spread.long_leg.contract.strike} / short {spread.short_leg.contract.strike}"
    )


def process_decision(decision: CrossIntelDecision) -> TradeLogEntry:
    if decision.decision != Decision.TRADE or decision.bias.value == "NONE":
        return _reject(decision, "not_a_trade_decision")

    option_type = OptionType.CALL if decision.bias.value == "CALL" else OptionType.PUT

    # --- build the spread ---
    try:
        contracts = alpaca.fetch_chain(decision.ticker, option_type)
        if not contracts:
            raise SpreadSelectionError(f"empty option chain for {decision.ticker} {option_type.value}")
        spread = build_debit_spread(decision.ticker, option_type, contracts)
    except SpreadSelectionError as exc:
        return _reject(decision, f"spread_construction: {exc}")
    except Exception as exc:  # noqa: BLE001 — network/API failure from the chain fetch
        return _reject(decision, f"chain_fetch_failed: {exc}")

    # --- IV rank gate ---
    iv_rank_value = None
    avg_iv = _average_iv(spread)
    if avg_iv is not None:
        result = compute_iv_rank(decision.ticker, avg_iv)
        iv_rank_value = result.rank
        if result.available and result.rank is not None and result.rank > IV_RANK_MAX:
            return _reject(
                decision, f"iv_rank_too_high: {result.rank:.1f} > {IV_RANK_MAX:.1f}",
                spread=spread, iv_rank=result.rank,
            )
        if not result.available:
            if IV_RANK_REQUIRE_HISTORY:
                return _reject(decision, f"iv_rank_unavailable: {result.reason}", spread=spread)
            log.info("%s: %s — proceeding (IV_RANK_REQUIRE_HISTORY=false)", decision.ticker, result.reason)

    # --- max-loss gate ---
    try:
        account = alpaca.get_account()
        equity = float(account["equity"])
    except Exception as exc:  # noqa: BLE001
        return _reject(decision, f"account_fetch_failed: {exc}", spread=spread, iv_rank=iv_rank_value)

    sizing = size_position(equity, spread.net_debit, max_loss_pct=MAX_LOSS_PCT)
    if not sizing.approved:
        return _reject(decision, f"max_loss_gate: {sizing.reason}", spread=spread, iv_rank=iv_rank_value)

    total_debit = spread.net_debit * 100 * sizing.max_contracts

    # --- submit (or dry-run) ---
    if DRY_RUN:
        entry = _log_entry(TradeLogEntry(
            ticker=decision.ticker, status=TradeStatus.DRY_RUN, bias=decision.bias.value,
            dedup_key=decision.dedup_key, spread_description=_describe(spread),
            expiration=spread.expiration, long_strike=spread.long_leg.contract.strike,
            short_strike=spread.short_leg.contract.strike, net_debit_per_contract=spread.net_debit,
            contracts=sizing.max_contracts, total_debit=total_debit, iv_rank=iv_rank_value,
            logged_at=datetime.now(timezone.utc),
        ))
        log.info(
            "DRY_RUN %s: would buy %d x %s for $%.2f total debit (EXECUTION_DRY_RUN=true)",
            decision.ticker, sizing.max_contracts, _describe(spread), total_debit,
        )
        return entry

    legs = [
        {"symbol": spread.long_leg.contract.symbol, "side": "buy", "ratio_qty": 1, "position_intent": "buy_to_open"},
        {"symbol": spread.short_leg.contract.symbol, "side": "sell", "ratio_qty": 1, "position_intent": "sell_to_open"},
    ]
    try:
        order = alpaca.place_multi_leg_order(legs, qty=sizing.max_contracts, limit_price=spread.net_debit)
    except Exception as exc:  # noqa: BLE001
        return _reject(decision, f"order_submission_failed: {exc}", spread=spread, iv_rank=iv_rank_value,
                        contracts=sizing.max_contracts)

    entry = _log_entry(TradeLogEntry(
        ticker=decision.ticker, status=TradeStatus.EXECUTED, bias=decision.bias.value,
        dedup_key=decision.dedup_key, spread_description=_describe(spread), expiration=spread.expiration,
        long_strike=spread.long_leg.contract.strike, short_strike=spread.short_leg.contract.strike,
        net_debit_per_contract=spread.net_debit, contracts=sizing.max_contracts, total_debit=total_debit,
        iv_rank=iv_rank_value, order_id=order.get("id", ""), logged_at=datetime.now(timezone.utc),
    ))
    log.info(
        "EXECUTED %s: order %s — %d x %s ($%.2f total debit)",
        decision.ticker, entry.order_id, sizing.max_contracts, _describe(spread), total_debit,
    )
    return entry


def run_once() -> list[TradeLogEntry]:
    decisions = _load_decisions()
    seen = _load_seen()
    todo = [d for d in decisions if d.decision == Decision.TRADE and d.dedup_key not in seen]

    if not todo:
        log.info("No new TRADE decisions to execute.")
        return []

    entries = [process_decision(d) for d in todo]
    seen.update(d.dedup_key for d in todo)
    _save_seen(seen)
    log.info("Processed %d TRADE decisions (%d executed/dry-run, %d rejected).",
              len(entries),
              sum(1 for e in entries if e.status != TradeStatus.REJECTED),
              sum(1 for e in entries if e.status == TradeStatus.REJECTED))
    return entries


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 6 options execution")
    parser.add_argument("--once", action="store_true", help="currently the only mode")
    parser.parse_args()
    run_once()


if __name__ == "__main__":
    main()
