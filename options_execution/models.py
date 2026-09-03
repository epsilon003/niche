"""Phase 6 — data model for option contracts, spreads, and the trade log."""
from __future__ import annotations

from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel


class OptionType(str, Enum):
    CALL = "call"
    PUT = "put"


class OptionContract(BaseModel):
    symbol: str  # OCC symbol, e.g. MRNA260320C00120000
    underlying: str
    option_type: OptionType
    strike: float
    expiration: date
    bid: float | None = None
    ask: float | None = None
    last: float | None = None
    implied_volatility: float | None = None
    delta: float | None = None
    open_interest: int | None = None

    @property
    def mid(self) -> float | None:
        if self.bid is not None and self.ask is not None:
            return (self.bid + self.ask) / 2
        return self.last


class SpreadLeg(BaseModel):
    contract: OptionContract
    side: str  # "buy" | "sell"


class DebitSpread(BaseModel):
    ticker: str
    option_type: OptionType
    long_leg: SpreadLeg
    short_leg: SpreadLeg
    expiration: date
    net_debit: float  # per share; per-contract dollar cost is net_debit * 100


class TradeStatus(str, Enum):
    EXECUTED = "EXECUTED"
    REJECTED = "REJECTED"
    DRY_RUN = "DRY_RUN"  # gates passed, order would have been submitted, but EXECUTION_DRY_RUN=true


class TradeLogEntry(BaseModel):
    ticker: str
    status: TradeStatus
    bias: str
    dedup_key: str  # ties back to the CrossIntelDecision, so we never re-trade the same catalyst
    rejection_reason: str = ""
    spread_description: str = ""
    expiration: date | None = None
    long_strike: float | None = None
    short_strike: float | None = None
    net_debit_per_contract: float | None = None
    contracts: int = 0
    total_debit: float | None = None
    iv_rank: float | None = None
    order_id: str = ""
    logged_at: datetime
