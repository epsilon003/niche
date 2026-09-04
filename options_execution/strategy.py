"""
Phase 6 — Spread construction.

Binary biotech catalysts (trial readouts, FDA actions) are directional,
one-shot events. A debit spread caps both the cost and the max loss to
the premium paid — the right shape for "I have a directional view and a
known event window," unlike a naked long option (full theta/IV-crush
exposure with nothing offsetting it) or a credit spread (risk sized well
past the premium collected, the wrong side of a binary bet).

  - bias CALL -> bull call debit spread: buy a near-the-money call, sell
    a further-OTM call against it.
  - bias PUT  -> bear put debit spread: buy a near-the-money put, sell a
    further-OTM put against it.

Expiration: nearest available expiration at least MIN_DAYS_TO_EXPIRY out
(gives the catalyst room to actually happen and be reflected in price
before the position expires) and at most MAX_DAYS_TO_EXPIRY out (keeps
the trade tied to the event rather than becoming an unrelated multi-month
theta bet).

Strikes are delta-targeted rather than dollar-targeted, since delta is a
much better analog for "moneyness" across tickers with very different
share prices.
"""

from __future__ import annotations

from datetime import date, datetime

from .models import DebitSpread, OptionContract, OptionType, SpreadLeg

MIN_DAYS_TO_EXPIRY = 5
MAX_DAYS_TO_EXPIRY = 45

LONG_LEG_TARGET_DELTA = (
    0.60  # near-the-money — high probability of being ITM if the view is right
)
SHORT_LEG_TARGET_DELTA = 0.30  # further OTM — caps upside but funds the spread


class SpreadSelectionError(Exception):
    """Raised whenever the available chain can't support a clean debit spread."""


def pick_expiration(contracts: list[OptionContract], as_of: date | None = None) -> date:
    as_of = as_of or datetime.now().date()
    candidates = sorted({c.expiration for c in contracts})
    in_window = [
        d
        for d in candidates
        if MIN_DAYS_TO_EXPIRY <= (d - as_of).days <= MAX_DAYS_TO_EXPIRY
    ]
    if not in_window:
        raise SpreadSelectionError(
            f"no expiration between {MIN_DAYS_TO_EXPIRY} and {MAX_DAYS_TO_EXPIRY} days out "
            f"in the available chain (candidates: {candidates})"
        )
    return in_window[0]  # nearest expiration inside the acceptable window


def _closest_by_delta(
    contracts: list[OptionContract], target_delta: float
) -> OptionContract:
    with_delta = [c for c in contracts if c.delta is not None]
    if not with_delta:
        raise SpreadSelectionError("no contracts in chain have delta/greeks data")
    return min(with_delta, key=lambda c: abs(abs(c.delta) - target_delta))


def build_debit_spread(
    ticker: str,
    option_type: OptionType,
    contracts: list[OptionContract],
    as_of: date | None = None,
) -> DebitSpread:
    expiration = pick_expiration(contracts, as_of)
    same_expiry = [
        c
        for c in contracts
        if c.expiration == expiration and c.option_type == option_type
    ]
    if len(same_expiry) < 2:
        raise SpreadSelectionError(
            f"fewer than 2 {option_type.value} contracts at {expiration} for {ticker}"
        )

    long_contract = _closest_by_delta(same_expiry, LONG_LEG_TARGET_DELTA)

    if option_type == OptionType.CALL:
        short_candidates = [c for c in same_expiry if c.strike > long_contract.strike]
    else:
        short_candidates = [c for c in same_expiry if c.strike < long_contract.strike]
    if not short_candidates:
        raise SpreadSelectionError(
            f"no further-OTM {option_type.value} strike available to sell against "
            f"the {long_contract.strike} long leg for {ticker} {expiration}"
        )
    short_contract = _closest_by_delta(short_candidates, SHORT_LEG_TARGET_DELTA)

    long_mid, short_mid = long_contract.mid, short_contract.mid
    if long_mid is None or short_mid is None:
        raise SpreadSelectionError(
            "missing bid/ask/last on one or both legs — can't price the spread"
        )

    net_debit = long_mid - short_mid
    if net_debit <= 0:
        raise SpreadSelectionError(
            f"computed non-positive net debit ({net_debit:.2f}) — stale/crossed quotes, refusing to trade"
        )

    return DebitSpread(
        ticker=ticker,
        option_type=option_type,
        long_leg=SpreadLeg(contract=long_contract, side="buy"),
        short_leg=SpreadLeg(contract=short_contract, side="sell"),
        expiration=expiration,
        net_debit=net_debit,
    )
