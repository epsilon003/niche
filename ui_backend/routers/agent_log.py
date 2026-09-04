"""
Phase 7 — Agent log + replay endpoints.

/api/agent-log powers the live feed: the frontend polls it every few
seconds with `since` set to the timestamp of the last event it already
has, so each poll only returns what's new.

/api/replay serves a fixed historical window for the replay mode — the
frontend fetches once for a chosen date range, then steps through the
returned list client-side at whatever speed the user picks.
"""
from __future__ import annotations

from fastapi import APIRouter, Query

from .. import data_access

router = APIRouter(prefix="/api", tags=["agent-log"])


@router.get("/agent-log")
def get_agent_log(
    since: str | None = Query(default=None, description="ISO timestamp; only events after this"),
    limit: int = Query(default=200, ge=1, le=2000),
):
    since_dt = data_access.parse_iso_datetime(since)
    events = data_access.merge_agent_log_events(since=since_dt)
    events = events[-limit:]
    return {"events": events, "count": len(events)}


@router.get("/replay")
def get_replay_window(
    start: str = Query(..., description="ISO timestamp — window start"),
    end: str = Query(..., description="ISO timestamp — window end"),
):
    start_dt, end_dt = data_access.parse_iso_datetime(start), data_access.parse_iso_datetime(end)
    if start_dt is None or end_dt is None:
        return {"error": "start and end must be valid ISO timestamps", "events": []}
    events = data_access.merge_agent_log_events(since=start_dt, until=end_dt)
    return {"events": events, "count": len(events), "start": start, "end": end}
