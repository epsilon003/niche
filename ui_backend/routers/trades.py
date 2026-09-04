"""
Phase 7 — Trades and P&L endpoints.

/api/trades reads straight from data/trade_log.jsonl — always available,
no network dependency.

/api/account and /api/positions proxy live to Alpaca's paper API for P&L.
Both fail soft: if Alpaca isn't reachable/configured (e.g. this demo is
being run without real keys), they return {"connected": false, "error":
...} with a 200 rather than a 500, so the frontend can show a clear
"not connected" state instead of an error boundary.
"""
from __future__ import annotations

from fastapi import APIRouter, Query

from options_execution import alpaca_options_client as alpaca
from .. import data_access

router = APIRouter(prefix="/api", tags=["trades"])


@router.get("/trades")
def get_trades(status: str | None = Query(default=None), limit: int = Query(default=200, ge=1, le=2000)):
    return {"trades": data_access.trade_log(status=status, limit=limit)}


@router.get("/account")
def get_account():
    try:
        account = alpaca.get_account()
    except Exception as exc:  # noqa: BLE001 — network/auth failure, not a bug
        return {"connected": False, "error": str(exc)}
    return {
        "connected": True,
        "equity": float(account.get("equity", 0)),
        "last_equity": float(account.get("last_equity", 0)),
        "buying_power": float(account.get("buying_power", 0)),
        "cash": float(account.get("cash", 0)),
        "status": account.get("status"),
        "account_number": account.get("account_number"),
    }


@router.get("/positions")
def get_positions():
    try:
        positions = alpaca.list_positions()
    except Exception as exc:  # noqa: BLE001
        return {"connected": False, "error": str(exc), "positions": []}
    return {
        "connected": True,
        "positions": [
            {
                "symbol": p.get("symbol"),
                "qty": float(p.get("qty", 0)),
                "avg_entry_price": float(p.get("avg_entry_price", 0)),
                "current_price": float(p.get("current_price", 0)) if p.get("current_price") else None,
                "market_value": float(p.get("market_value", 0)) if p.get("market_value") else None,
                "unrealized_pl": float(p.get("unrealized_pl", 0)) if p.get("unrealized_pl") else None,
                "unrealized_plpc": float(p.get("unrealized_plpc", 0)) if p.get("unrealized_plpc") else None,
            }
            for p in positions
        ],
    }
