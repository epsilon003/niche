"""
Phase 6 — Alpaca options REST client.

Thin wrapper over Alpaca's options endpoints:
  - GET  /v2/options/contracts                (trading API — contract metadata)
  - GET  /v1beta1/options/snapshots            (market data API — quotes + greeks + IV)
  - POST /v2/orders with order_class="mleg"    (trading API — multi-leg orders)

Requires options trading to be enabled on your Alpaca paper account
(Account -> Settings -> Options Trading Level is a separate opt-in from
plain equities paper trading). Field names below match Alpaca's options
API as documented at the time this was written — if a response comes back
missing a field this file expects, that's Alpaca's schema having moved;
this module is the one place to fix the parsing.
"""

from __future__ import annotations

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from config import get_logger, settings

from .models import OptionContract, OptionType

log = get_logger("options_execution.alpaca_options_client")

TRADING_BASE = settings.alpaca_trading_base_url  # e.g. https://paper-api.alpaca.markets
DATA_BASE = "https://data.alpaca.markets"


def _headers() -> dict:
    return {
        "APCA-API-KEY-ID": settings.alpaca_api_key,
        "APCA-API-SECRET-KEY": settings.alpaca_secret_key,
    }


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def get_account() -> dict:
    resp = httpx.get(f"{TRADING_BASE}/v2/account", headers=_headers(), timeout=10.0)
    resp.raise_for_status()
    return resp.json()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def list_option_contracts(
    underlying: str, option_type: OptionType | None = None, limit: int = 500
) -> list[dict]:
    params: dict = {
        "underlying_symbols": underlying,
        "status": "active",
        "limit": limit,
    }
    if option_type is not None:
        params["type"] = option_type.value
    resp = httpx.get(
        f"{TRADING_BASE}/v2/options/contracts",
        headers=_headers(),
        params=params,
        timeout=15.0,
    )
    resp.raise_for_status()
    return resp.json().get("option_contracts", [])


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def get_option_snapshots(symbols: list[str]) -> dict:
    """Batched quote + greeks + IV lookup. Returns {occ_symbol: snapshot_dict}."""
    if not symbols:
        return {}
    params = {"symbols": ",".join(symbols)}
    resp = httpx.get(
        f"{DATA_BASE}/v1beta1/options/snapshots",
        headers=_headers(),
        params=params,
        timeout=15.0,
    )
    resp.raise_for_status()
    return resp.json().get("snapshots", {})


def fetch_chain(underlying: str, option_type: OptionType) -> list[OptionContract]:
    """Contracts + their live quote/greeks/IV, merged into one OptionContract list."""
    raw_contracts = list_option_contracts(underlying, option_type)
    if not raw_contracts:
        return []

    symbols = [c["symbol"] for c in raw_contracts]
    snapshots: dict = {}
    for i in range(
        0, len(symbols), 100
    ):  # batch conservatively — Alpaca caps symbols/request
        snapshots.update(get_option_snapshots(symbols[i : i + 100]))

    out: list[OptionContract] = []
    for raw in raw_contracts:
        symbol = raw["symbol"]
        snap = snapshots.get(symbol, {})
        quote = snap.get("latestQuote", {})
        trade = snap.get("latestTrade", {})
        greeks = snap.get("greeks", {})
        out.append(
            OptionContract(
                symbol=symbol,
                underlying=underlying,
                option_type=option_type,
                strike=float(raw["strike_price"]),
                expiration=raw["expiration_date"],
                bid=quote.get("bp"),
                ask=quote.get("ap"),
                last=trade.get("p"),
                implied_volatility=snap.get("impliedVolatility"),
                delta=greeks.get("delta"),
                open_interest=int(raw["open_interest"])
                if raw.get("open_interest")
                else None,
            )
        )
    return out


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def list_positions() -> list[dict]:
    """All open positions (equities + options) on the account — used by Phase 7's P&L view."""
    resp = httpx.get(f"{TRADING_BASE}/v2/positions", headers=_headers(), timeout=10.0)
    resp.raise_for_status()
    return resp.json()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def list_orders(status: str = "all", limit: int = 50) -> list[dict]:
    """Recent orders — used by Phase 7's P&L/activity view."""
    params = {"status": status, "limit": limit, "direction": "desc"}
    resp = httpx.get(
        f"{TRADING_BASE}/v2/orders", headers=_headers(), params=params, timeout=10.0
    )
    resp.raise_for_status()
    return resp.json()


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def place_multi_leg_order(
    legs: list[dict], qty: int, limit_price: float, time_in_force: str = "day"
) -> dict:
    """
    legs: [{"symbol": occ_symbol, "side": "buy"|"sell", "ratio_qty": 1,
             "position_intent": "buy_to_open"|"sell_to_open"}]
    limit_price: net debit you're willing to pay per spread, positive number.
    """
    payload = {
        "order_class": "mleg",
        "qty": str(qty),
        "type": "limit",
        "limit_price": str(round(limit_price, 2)),
        "time_in_force": time_in_force,
        "legs": legs,
    }
    resp = httpx.post(
        f"{TRADING_BASE}/v2/orders", headers=_headers(), json=payload, timeout=15.0
    )
    resp.raise_for_status()
    return resp.json()
