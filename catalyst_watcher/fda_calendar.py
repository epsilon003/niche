"""
Phase 1A — FDA schedule source.

Important honesty note: the FDA does not publish a free, forward-looking,
machine-readable feed of PDUFA target action dates. openFDA's `drugsfda`
endpoint gives you the *historical* action log for approved/reviewed
applications (submission types, action dates, approval status) — useful as
a catalyst-confirmation source — but not upcoming target dates for pending
applications. Those are typically disclosed by the sponsor in press
releases/10-Ks, or aggregated by paid trackers.

So this module does two things:
  1. `fetch_recent_actions()` — real, live data from openFDA's drugsfda API
     for a company, turned into FDA_ACTION_LOGGED events (e.g. "FDA logged
     a Type II resubmission action for company X").
  2. `load_curated_pdufa_dates()` — reads a small JSON file you maintain
     yourself (data/pdufa_calendar.json) with known upcoming PDUFA dates,
     turned into PDUFA_DATE events. This keeps the pipeline honest about
     what's live-fetched vs. what's operator-supplied.
"""

from __future__ import annotations

import json
from datetime import date, datetime

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from config import get_logger, settings

from .models import CatalystEvent, CatalystKind, CatalystSource

log = get_logger("catalyst_watcher.fda_calendar")

OPENFDA_DRUGSFDA_URL = "https://api.fda.gov/drug/drugsfda.json"
CURATED_CALENDAR_PATH = settings.data_dir / "pdufa_calendar.json"


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _fetch(params: dict) -> dict:
    if settings.openfda_api_key:
        params = {**params, "api_key": settings.openfda_api_key}

    resp = httpx.get(OPENFDA_DRUGSFDA_URL, params=params, timeout=15.0)

    # openFDA returns 404 when no records match the query.
    # This is expected behavior (not a transient network error), so we return
    # an empty result set directly to avoid triggering tenacity retries.
    if resp.status_code == 404:
        log.debug("openFDA: no records found for query params: %s", params)
        return {"results": []}

    # For any other error (5xx server errors, 429 rate limits),
    # raise_for_status will trigger the tenacity retry mechanism as intended.
    resp.raise_for_status()
    return resp.json()


def fetch_recent_actions(
    company_name: str, ticker: str, limit: int = 20
) -> list[CatalystEvent]:
    """Pull the most recent FDA application actions for a sponsor name."""
    # Tip: If you get empty results for "Moderna", try "ModernaTX" or "Moderna Tx",
    # as that is the official sponsor name registered in FDA databases.
    params = {
        "search": f'sponsor_name:"{company_name}"',
        "limit": limit,
        "sort": "application_number:desc",
    }
    try:
        payload = _fetch(params)
    except httpx.HTTPStatusError as exc:
        log.error(
            "openFDA request failed for %r (HTTP %s): %s",
            company_name,
            exc.response.status_code,
            exc,
        )
        return []
    except httpx.HTTPError as exc:
        log.error(
            "openFDA request failed for %r (Network/Timeout): %s", company_name, exc
        )
        return []
    except Exception as exc:
        # Catches tenacity.RetryError if all retries are exhausted for 5xx errors
        log.error("openFDA request failed for %r after retries: %s", company_name, exc)
        return []

    events: list[CatalystEvent] = []
    for result in payload.get("results", []):
        app_no = result.get("application_number", "unknown")
        products = result.get("products", [{}])
        brand = products[0].get("brand_name", "") if products else ""
        for submission in result.get("submissions", []):
            action_date_raw = submission.get("submission_status_date")
            action_date = _parse_fda_date(action_date_raw)
            sub_type = submission.get("submission_type", "?")
            sub_status = submission.get("submission_status", "?")
            events.append(
                CatalystEvent(
                    ticker=ticker,
                    source=CatalystSource.FDA_CALENDAR,
                    kind=CatalystKind.FDA_ACTION_LOGGED,
                    event_date=action_date,
                    title=f"{brand or app_no} — {sub_type} {sub_status}",
                    detail=json.dumps(submission, default=str),
                    url=f"https://www.accessdata.fda.gov/scripts/cder/daf/index.cfm?event=overview.process&ApplNo={app_no.lstrip('NDABLA')}",
                    external_id=f"{app_no}:{submission.get('submission_number', '?')}",
                    raw=submission,
                )
            )

    log.info(
        "openFDA: %d results -> %d events for %s",
        len(payload.get("results", [])),
        len(events),
        ticker,
    )
    return events


def _parse_fda_date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y%m%d").date()
    except ValueError:
        return None


def load_curated_pdufa_dates() -> list[CatalystEvent]:
    """
    Load operator-maintained PDUFA target dates from
    data/pdufa_calendar.json. Expected schema:

    [
      {"ticker": "SRPT", "drug": "Elevidys sBLA", "pdufa_date": "2026-11-19",
       "url": "https://...", "note": "label expansion"}
    ]

    Missing file is not an error — it just means no curated dates yet.
    """
    if not CURATED_CALENDAR_PATH.exists():
        log.info(
            "No curated PDUFA calendar at %s yet — skipping. "
            "Create it to feed known target action dates into the pipeline.",
            CURATED_CALENDAR_PATH,
        )
        return []

    try:
        entries = json.loads(CURATED_CALENDAR_PATH.read_text())
    except json.JSONDecodeError as exc:
        log.error(
            "Failed to parse curated PDUFA calendar at %s (invalid JSON): %s",
            CURATED_CALENDAR_PATH,
            exc,
        )
        return []

    if not isinstance(entries, list):
        log.error(
            "Curated PDUFA calendar at %s must be a JSON list.", CURATED_CALENDAR_PATH
        )
        return []

    events: list[CatalystEvent] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        try:
            pdufa_date = datetime.strptime(entry["pdufa_date"], "%Y-%m-%d").date()
        except (KeyError, ValueError) as exc:
            log.warning("Skipping malformed curated PDUFA entry %r: %s", entry, exc)
            continue

        ticker = entry.get("ticker", "UNKNOWN").upper()
        events.append(
            CatalystEvent(
                ticker=ticker,
                source=CatalystSource.FDA_CALENDAR,
                kind=CatalystKind.PDUFA_DATE,
                event_date=pdufa_date,
                title=entry.get("drug", "PDUFA date"),
                detail=entry.get("note", ""),
                url=entry.get("url", ""),
                external_id=f"{ticker}:{entry.get('drug', '')}:{entry['pdufa_date']}",
                raw=entry,
            )
        )
    log.info(
        "Loaded %d curated PDUFA events from %s", len(events), CURATED_CALENDAR_PATH
    )
    return events
