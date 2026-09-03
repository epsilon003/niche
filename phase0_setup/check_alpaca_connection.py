"""
Phase 0 — Setup sanity check.

Run this once after filling in .env to confirm:
  1. Your Alpaca paper credentials authenticate against the trading REST API.
  2. You're really pointed at paper-api.alpaca.markets, not live.
  3. The market-data WebSocket accepts your credentials and completes the
     auth handshake (this alone does not consume market data — Phase 1B
     does the actual subscribe/stream loop).

Usage:
    python -m phase0_setup.check_alpaca_connection
"""
from __future__ import annotations

import asyncio
import json
import sys

import httpx
import websockets

from config import get_logger, settings

log = get_logger("phase0.setup_check")


def check_rest_auth() -> bool:
    problems = settings.validate_alpaca()
    if problems:
        for p in problems:
            log.error("Config problem: %s", p)
        return False

    if "paper-api.alpaca.markets" not in settings.alpaca_trading_base_url:
        log.error(
            "ALPACA_TRADING_BASE_URL (%s) does not look like the paper "
            "endpoint. Refusing to proceed.",
            settings.alpaca_trading_base_url,
        )
        return False

    url = f"{settings.alpaca_trading_base_url}/v2/account"
    headers = {
        "APCA-API-KEY-ID": settings.alpaca_api_key,
        "APCA-API-SECRET-KEY": settings.alpaca_secret_key,
    }
    try:
        resp = httpx.get(url, headers=headers, timeout=10.0)
    except httpx.HTTPError as exc:
        log.error("Could not reach Alpaca trading API: %s", exc)
        return False

    if resp.status_code != 200:
        log.error("Auth failed (%s): %s", resp.status_code, resp.text[:300])
        return False

    account = resp.json()
    log.info(
        "REST auth OK — account %s | status=%s | equity=$%s | buying_power=$%s",
        account.get("account_number"),
        account.get("status"),
        account.get("equity"),
        account.get("buying_power"),
    )
    return True


async def check_websocket_handshake() -> bool:
    url = settings.alpaca_data_stream_url
    try:
        async with websockets.connect(url, ping_interval=20, ping_timeout=20) as ws:
            # Server should greet us first.
            greeting = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
            log.info("WS greeting: %s", greeting)

            auth_msg = {
                "action": "auth",
                "key": settings.alpaca_api_key,
                "secret": settings.alpaca_secret_key,
            }
            await ws.send(json.dumps(auth_msg))
            auth_resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
            log.info("WS auth response: %s", auth_resp)

            ok = any(
                item.get("T") == "success" and item.get("msg") == "authenticated"
                for item in auth_resp
                if isinstance(item, dict)
            )
            if ok:
                log.info("WebSocket auth handshake OK.")
            else:
                log.error("WebSocket auth handshake failed: %s", auth_resp)
            return ok
    except Exception as exc:  # noqa: BLE001 — top-level sanity check
        log.error("WebSocket connection failed: %s", exc)
        return False


def main() -> int:
    log.info("=== Phase 0 setup check ===")
    rest_ok = check_rest_auth()
    ws_ok = asyncio.run(check_websocket_handshake()) if rest_ok else False

    log.info("--- summary ---")
    log.info("REST auth:      %s", "OK" if rest_ok else "FAILED")
    log.info("WebSocket auth: %s", "OK" if ws_ok else "FAILED")

    if rest_ok and ws_ok:
        log.info("Phase 0 complete. Safe to move on to Phase 1A/1B.")
        return 0
    log.error("Phase 0 checks did not all pass — fix .env before continuing.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
