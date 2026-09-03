"""
Phase 1A — ClinicalTrials.gov client.

Uses the public ClinicalTrials.gov API v2 (no key required):
https://clinicaltrials.gov/data-api/api

We query by sponsor/company name (CT.gov has no ticker field), pull back
status + key dates + results-posted flag, and turn each study into a
CatalystEvent. The watcher (watcher.py) is responsible for diffing against
previously-seen state to decide what's actually "new."
"""
from __future__ import annotations

from datetime import date, datetime

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from config import get_logger
from .models import CatalystEvent, CatalystKind, CatalystSource

log = get_logger("catalyst_watcher.clinicaltrials")

BASE_URL = "https://clinicaltrials.gov/api/v2/studies"

FIELDS = [
    "protocolSection.identificationModule.nctId",
    "protocolSection.identificationModule.briefTitle",
    "protocolSection.identificationModule.organization",
    "protocolSection.statusModule.overallStatus",
    "protocolSection.statusModule.primaryCompletionDateStruct",
    "protocolSection.statusModule.lastUpdatePostDateStruct",
    "hasResults",
]


def _parse_ct_date(struct: dict | None) -> date | None:
    if not struct or "date" not in struct:
        return None
    raw = struct["date"]
    for fmt in ("%Y-%m-%d", "%Y-%m"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def _fetch_page(query_term: str, page_token: str | None, page_size: int) -> dict:
    params = {
        "query.term": query_term,
        "fields": ",".join(FIELDS),
        "pageSize": page_size,
        "format": "json",
    }
    if page_token:
        params["pageToken"] = page_token
    resp = httpx.get(BASE_URL, params=params, timeout=15.0)
    resp.raise_for_status()
    return resp.json()


def search_studies(
    company_or_intervention: str,
    ticker: str,
    max_studies: int = 50,
) -> list[CatalystEvent]:
    """
    Search CT.gov for studies matching a sponsor/company/intervention term
    and turn each into one or more CatalystEvents.

    `company_or_intervention` should be a free-text search term — usually the
    company name (e.g. "Moderna") since CT.gov indexes sponsor names, not
    tickers. Pass the most distinctive name you have.
    """
    events: list[CatalystEvent] = []
    page_token = None
    fetched = 0

    while fetched < max_studies:
        page_size = min(50, max_studies - fetched)
        try:
            page = _fetch_page(company_or_intervention, page_token, page_size)
        except httpx.HTTPError as exc:
            log.error("CT.gov request failed for %r: %s", company_or_intervention, exc)
            break

        studies = page.get("studies", [])
        if not studies:
            break

        for study in studies:
            events.extend(_study_to_events(study, ticker))

        fetched += len(studies)
        page_token = page.get("nextPageToken")
        if not page_token:
            break

    log.info(
        "CT.gov: %d studies -> %d catalyst events for %s (%s)",
        fetched, len(events), ticker, company_or_intervention,
    )
    return events


DETAIL_FIELDS = [
    "protocolSection.identificationModule.nctId",
    "protocolSection.identificationModule.briefTitle",
    "protocolSection.descriptionModule.briefSummary",
    "protocolSection.statusModule.overallStatus",
    "protocolSection.outcomesModule",
    "resultsSection.outcomeMeasuresModule",
    "resultsSection.adverseEventsModule.description",
    "hasResults",
]


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def fetch_study_detail(nct_id: str) -> dict:
    """
    Fetch a single study by NCT id with results-section fields included.
    Used by Phase 2's scientific agent to read primary/secondary outcome
    measures and adverse-event summaries when classifying a trial readout.
    """
    url = f"{BASE_URL}/{nct_id}"
    params = {"fields": ",".join(DETAIL_FIELDS), "format": "json"}
    resp = httpx.get(url, params=params, timeout=15.0)
    resp.raise_for_status()
    return resp.json()


def _study_to_events(study: dict, ticker: str) -> list[CatalystEvent]:
    proto = study.get("protocolSection", {})
    ident = proto.get("identificationModule", {})
    status = proto.get("statusModule", {})

    nct_id = ident.get("nctId", "unknown")
    title = ident.get("briefTitle", "(no title)")
    overall_status = status.get("overallStatus", "UNKNOWN")
    url = f"https://clinicaltrials.gov/study/{nct_id}"

    out: list[CatalystEvent] = []

    # 1. Current status snapshot -> a trial_status_change candidate.
    #    The watcher decides whether this status differs from last time we saw it.
    out.append(
        CatalystEvent(
            ticker=ticker,
            source=CatalystSource.CLINICAL_TRIALS,
            kind=CatalystKind.TRIAL_STATUS_CHANGE,
            event_date=_parse_ct_date(status.get("lastUpdatePostDateStruct")),
            title=title,
            detail=f"overallStatus={overall_status}",
            url=url,
            external_id=nct_id,
            raw=study,
        )
    )

    # 2. Upcoming primary completion date -> a readout-window catalyst.
    completion_date = _parse_ct_date(status.get("primaryCompletionDateStruct"))
    if completion_date:
        out.append(
            CatalystEvent(
                ticker=ticker,
                source=CatalystSource.CLINICAL_TRIALS,
                kind=CatalystKind.PRIMARY_COMPLETION_DUE,
                event_date=completion_date,
                title=title,
                detail=f"primary completion ~{completion_date.isoformat()}",
                url=url,
                external_id=f"{nct_id}:primary_completion",
                raw=study,
            )
        )

    # 3. Results posted -> the big one for the scientific agent to read/classify.
    if study.get("hasResults"):
        out.append(
            CatalystEvent(
                ticker=ticker,
                source=CatalystSource.CLINICAL_TRIALS,
                kind=CatalystKind.RESULTS_POSTED,
                event_date=_parse_ct_date(status.get("lastUpdatePostDateStruct")),
                title=title,
                detail="hasResults=true",
                url=url,
                external_id=f"{nct_id}:results",
                raw=study,
            )
        )

    return out
