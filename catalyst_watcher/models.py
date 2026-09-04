"""Shared data model for Phase 1A -> Phase 2."""
from __future__ import annotations

from datetime import date, datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class CatalystSource(str, Enum):
    CLINICAL_TRIALS = "clinicaltrials.gov"
    FDA_CALENDAR = "fda_calendar"


class CatalystKind(str, Enum):
    TRIAL_STATUS_CHANGE = "trial_status_change"     # e.g. RECRUITING -> COMPLETED
    RESULTS_POSTED = "results_posted"                 # CT.gov results section populated
    PRIMARY_COMPLETION_DUE = "primary_completion_due"  # upcoming readout window
    PDUFA_DATE = "pdufa_date"                         # FDA target action date
    FDA_ACTION_LOGGED = "fda_action_logged"           # openFDA drugsfda action recorded


class CatalystEvent(BaseModel):
    ticker: str
    source: CatalystSource
    kind: CatalystKind
    event_date: date | None = None
    title: str
    detail: str = ""
    url: str = ""
    external_id: str = Field(..., description="NCT id, application number, etc.")
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    raw: dict = Field(default_factory=dict, repr=False)

    @property
    def dedup_key(self) -> str:
        """Stable key used to detect 'is this a new catalyst or one we've seen'."""
        return f"{self.source}:{self.external_id}:{self.kind}"
