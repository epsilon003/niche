"""
Phase 6 — Options execution orchestrator.

Reads new TRADE decisions from data/cross_intel_decisions.jsonl (Phase 5),
builds a debit spread per the bias (see strategy.py), runs it through the
IV-rank gate and the max-loss gate, and either submits a paper multi-leg
order or logs a rejection with the specific reason. Every decision this
module makes — trade or reject — is written to data/trade_log.jsonl.
Nothing here trades uncapped risk: only debit spreads, only against the
paper endpoint, and only if EXECUTION_DRY_RUN is explicitly set to false.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone

from rich.console import Console
from rich.table import Table

from config import get_logger, settings
from cross_intelligence.models import CrossIntelDecision, Decision

from . import alpaca_options_client as alpaca
from .iv_rank import IV_RANK_MAX, IV_RANK_REQUIRE_HISTORY, compute_iv_rank
from .models import OptionSpread, OptionType, TradeLogEntry, TradeStatus
from .risk_gate import MAX_LOSS_PCT, size_position
from .strategy import SpreadSelectionError, build_debit_spread

log = get_logger("options_execution.execution")
console = Console()

TRADE_LOG_PATH = settings.data_dir / "trade_log.jsonl"
DRY_RUN = settings.alpaca_paper or getattr(settings, "execution_dry_run", True)


def _describe(spread: OptionSpread) -> str:
    return f"{spread.long_leg.contract.strike}/{spread.short_leg.contract.strike} {spread.expiration} {spread.option_type.value} Debit Spread"


def _log_entry(entry: TradeLogEntry) -> TradeLogEntry:
    with TRADE_LOG_PATH.open("a") as f:
        f.write(entry.model_dump_json() + "\n")
    return entry


def _average_iv(spread: OptionSpread) -> float | None:
    ivs = [
        leg.contract.implied_volatility
        for leg in (spread.long_leg, spread.short_leg)
        if leg.contract.implied_volatility is not None
    ]
    return sum(ivs) / len(ivs) if ivs else None


def _reject(
    decision: CrossIntelDecision,
    reason: str,
    spread: OptionSpread | None = None,
    iv_rank: float | None = None,
    contracts: int = 0,
) -> TradeLogEntry:
    entry = _log_entry(
        TradeLogEntry(
            ticker=decision.ticker,
            status=TradeStatus.REJECTED,
            bias=decision.bias.value if decision.bias else "NONE",
            dedup_key=decision.dedup_key,
            spread_description=_describe(spread) if spread else "N/A",
            expiration=spread.expiration if spread else None,
            long_strike=spread.long_leg.contract.strike if spread else None,
            short_strike=spread.short_leg.contract.strike if spread else None,
            net_debit_per_contract=spread.net_debit if spread else None,
            contracts=contracts,
            total_debit=0.0,
            iv_rank=iv_rank,
            rejection_reason=reason,
            logged_at=datetime.now(timezone.utc),
        )
    )
    log.warning("REJECTED %s: %s", decision.ticker, reason)

    # ENHANCEMENT: Rich table for clean demo output
    table = Table(title=f"⛔ REJECTED: Options Execution ({decision.ticker})")
    table.add_column("Parameter", style="cyan")
    table.add_column("Value", style="red")
    table.add_row("Reason", reason)
    table.add_row("Bias", decision.bias.value if decision.bias else "NONE")
    if spread:
        table.add_row("Strategy", _describe(spread))
    console.print(table)

    return entry


def process_decision(decision: CrossIntelDecision) -> TradeLogEntry:
    if decision.decision != Decision.TRADE or decision.bias.value == "NONE":
        return _reject(decision, "not_a_trade_decision")

    option_type = OptionType.CALL if decision.bias.value == "CALL" else OptionType.PUT

    # --- build the spread ---
    try:
        contracts = alpaca.fetch_chain(decision.ticker, option_type)
        if not contracts:
            raise SpreadSelectionError(
                f"empty option chain for {decision.ticker} {option_type.value}"
            )
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
                decision,
                f"iv_rank_too_high: {result.rank:.1f} > {IV_RANK_MAX:.1f}",
                spread=spread,
                iv_rank=result.rank,
            )
        if not result.available:
            if IV_RANK_REQUIRE_HISTORY:
                return _reject(
                    decision, f"iv_rank_unavailable: {result.reason}", spread=spread
                )
            log.info(
                "%s: %s — proceeding (IV_RANK_REQUIRE_HISTORY=false)",
                decision.ticker,
                result.reason,
            )

    # --- max-loss gate ---
    try:
        account = alpaca.get_account()
        equity = float(account["equity"])
    except Exception as exc:  # noqa: BLE001
        return _reject(
            decision,
            f"account_fetch_failed: {exc}",
            spread=spread,
            iv_rank=iv_rank_value,
        )

    sizing = size_position(equity, spread.net_debit, max_loss_pct=MAX_LOSS_PCT)
    if not sizing.approved:
        return _reject(
            decision,
            f"max_loss_gate: {sizing.reason}",
            spread=spread,
            iv_rank=iv_rank_value,
        )

    total_debit = spread.net_debit * 100 * sizing.max_contracts

    # --- submit (or dry-run) ---
    if DRY_RUN:
        entry = _log_entry(
            TradeLogEntry(
                ticker=decision.ticker,
                status=TradeStatus.DRY_RUN,
                bias=decision.bias.value,
                dedup_key=decision.dedup_key,
                spread_description=_describe(spread),
                expiration=spread.expiration,
                long_strike=spread.long_leg.contract.strike,
                short_strike=spread.short_leg.contract.strike,
                net_debit_per_contract=spread.net_debit,
                contracts=sizing.max_contracts,
                total_debit=total_debit,
                iv_rank=iv_rank_value,
                logged_at=datetime.now(timezone.utc),
            )
        )
        log.info(
            "DRY_RUN %s: would buy %d x %s for $%.2f total debit (EXECUTION_DRY_RUN=true)",
            decision.ticker,
            sizing.max_contracts,
            _describe(spread),
            total_debit,
        )

        # ENHANCEMENT: Rich table for clean demo output
        table = Table(title=f"🚀 DRY RUN: Options Execution ({decision.ticker})")
        table.add_column("Parameter", style="cyan")
        table.add_column("Value", style="green")
        table.add_row("Bias", decision.bias.value)
        table.add_row("Strategy", _describe(spread))
        table.add_row("Contracts", str(sizing.max_contracts))
        table.add_row("Net Debit/Contract", f"${spread.net_debit:.2f}")
        table.add_row("Total Debit", f"${total_debit:.2f}")
        table.add_row(
            "IV Rank", f"{iv_rank_value:.1f}" if iv_rank_value is not None else "N/A"
        )
        console.print(table)

        return entry

    legs = [
        {
            "symbol": spread.long_leg.contract.symbol,
            "side": "buy",
            "ratio_qty": 1,
            "position_intent": "buy_to_open",
        },
        {
            "symbol": spread.short_leg.contract.symbol,
            "side": "sell",
            "ratio_qty": 1,
            "position_intent": "sell_to_open",
        },
    ]
    try:
        order = alpaca.place_multi_leg_order(
            legs, qty=sizing.max_contracts, limit_price=spread.net_debit
        )
    except Exception as exc:  # noqa: BLE001
        return _reject(
            decision,
            f"order_submission_failed: {exc}",
            spread=spread,
            iv_rank=iv_rank_value,
            contracts=sizing.max_contracts,
        )

    entry = _log_entry(
        TradeLogEntry(
            ticker=decision.ticker,
            status=TradeStatus.EXECUTED,
            bias=decision.bias.value,
            dedup_key=decision.dedup_key,
            spread_description=_describe(spread),
            expiration=spread.expiration,
            long_strike=spread.long_leg.contract.strike,
            short_strike=spread.short_leg.contract.strike,
            net_debit_per_contract=spread.net_debit,
            contracts=sizing.max_contracts,
            total_debit=total_debit,
            iv_rank=iv_rank_value,
            order_id=order.get("id", ""),
            logged_at=datetime.now(timezone.utc),
        )
    )
    log.info(
        "EXECUTED %s: order %s — %d x %s ($%.2f total debit)",
        decision.ticker,
        entry.order_id,
        sizing.max_contracts,
        _describe(spread),
        total_debit,
    )

    # ENHANCEMENT: Rich table for clean demo output
    table = Table(title=f"✅ EXECUTED: Options Order ({decision.ticker})")
    table.add_column("Parameter", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Order ID", entry.order_id or "N/A")
    table.add_row("Bias", decision.bias.value)
    table.add_row("Strategy", _describe(spread))
    table.add_row("Contracts", str(sizing.max_contracts))
    table.add_row("Total Debit", f"${total_debit:.2f}")
    table.add_row(
        "IV Rank", f"{iv_rank_value:.1f}" if iv_rank_value is not None else "N/A"
    )
    console.print(table)

    return entry


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 6 options execution")
    parser.add_argument(
        "--once", action="store_true", help="process pending decisions once and exit"
    )
    args = parser.parse_args()

    if args.once:
        # Simple implementation: read last unprocessed decision
        if not (settings.data_dir / "cross_intel_decisions.jsonl").exists():
            log.info("No cross_intel_decisions.jsonl found.")
            return

        with open(settings.data_dir / "cross_intel_decisions.jsonl", "r") as f:
            lines = f.read().splitlines()

        if not lines:
            log.info("No decisions to process.")
            return

        # Process the most recent decision for demo purposes
        latest_decision = CrossIntelDecision.model_validate_json(lines[-1])
        log.info(
            "Processing decision: %s %s",
            latest_decision.ticker,
            latest_decision.decision.value,
        )
        process_decision(latest_decision)
    else:
        log.info("Use --once to process pending decisions.")


if __name__ == "__main__":
    main()
