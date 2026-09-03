"""
Phase 2 — Scientific agent.

Wraps a smolagents CodeAgent, backed by Qwen-72B served through Featherless's
OpenAI-compatible endpoint, with one tool (fetch_trial_detail) so the model
can pull full outcome/adverse-event text instead of classifying off a title.

Consumes catalyst_watcher's output (data/catalyst_events.jsonl) and produces
data/scientific_classifications.jsonl for Phase 5 (cross-intelligence agent)
to fuse with market microstructure.

Run once over whatever's new in the catalyst log:
    python -m scientific_agent.agent --once
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ValidationError
from smolagents import CodeAgent, OpenAIServerModel, Tool

from catalyst_watcher import clinicaltrials_client
from catalyst_watcher.models import CatalystEvent, CatalystKind
from config import get_logger, settings
from .prompts import SYSTEM_PROMPT, TASK_TEMPLATE

log = get_logger("scientific_agent.agent")

EVENTS_LOG_PATH = settings.data_dir / "catalyst_events.jsonl"
CLASSIFICATIONS_LOG_PATH = settings.data_dir / "scientific_classifications.jsonl"
CLASSIFIED_SEEN_PATH = settings.data_dir / "scientific_classified_seen.json"

# Only these catalyst kinds carry actual outcome data worth classifying.
# PRIMARY_COMPLETION_DUE / PDUFA_DATE / plain status changes are calendar
# markers, not readouts — the agent has nothing to read yet for those.
CLASSIFIABLE_KINDS = {
    CatalystKind.RESULTS_POSTED,
    CatalystKind.FDA_ACTION_LOGGED,
}


class ClassificationResult(BaseModel):
    label: str  # POSITIVE | NEGATIVE | UNCERTAIN
    confidence: float
    rationale: str


class FetchTrialDetailTool(Tool):
    name = "fetch_trial_detail"
    description = (
        "Fetch full outcome-measure, results, and adverse-event text for a "
        "ClinicalTrials.gov study by NCT id. Returns a JSON string."
    )
    inputs = {
        "nct_id": {
            "type": "string",
            "description": "ClinicalTrials.gov identifier, e.g. NCT01234567",
        }
    }
    output_type = "string"

    def forward(self, nct_id: str) -> str:
        try:
            detail = clinicaltrials_client.fetch_study_detail(nct_id)
        except Exception as exc:  # noqa: BLE001
            return json.dumps({"error": str(exc)})
        # Keep the tool result bounded so it doesn't blow the context window.
        return json.dumps(detail)[:8000]


def build_model() -> OpenAIServerModel:
    problems = settings.validate_llm()
    if problems:
        raise RuntimeError(f"Cannot build scientific agent model: {problems}")

    if settings.llm_provider == "openrouter":
        return OpenAIServerModel(
            model_id=settings.openrouter_model,
            api_base=settings.openrouter_base_url,
            api_key=settings.openrouter_api_key,
        )
    if settings.llm_provider == "featherless":
        return OpenAIServerModel(
            model_id=settings.featherless_model,
            api_base=settings.featherless_base_url,
            api_key=settings.featherless_api_key,
        )
    raise RuntimeError(f"Unknown LLM_PROVIDER {settings.llm_provider!r}")


class ScientificAgent:
    def __init__(self):
        self.model = build_model()
        self.agent = CodeAgent(
            tools=[FetchTrialDetailTool()],
            model=self.model,
            max_steps=6,
        )

    def classify(self, event: CatalystEvent) -> ClassificationResult:
        task = SYSTEM_PROMPT + "\n\n" + TASK_TEMPLATE.format(
            ticker=event.ticker,
            kind=event.kind.value,
            title=event.title,
            detail=event.detail,
            external_id=event.external_id.split(":")[0],  # strip our own suffixes
        )
        raw_output = self.agent.run(task)
        return _parse_classification(raw_output)


def _parse_classification(raw_output) -> ClassificationResult:
    """
    smolagents' final_answer can come back as a str, dict, or other object
    depending on version/config — normalize all of those to JSON text first.
    """
    if isinstance(raw_output, dict):
        text = json.dumps(raw_output)
    else:
        text = str(raw_output)

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        log.warning("Could not find JSON in agent output, defaulting to UNCERTAIN: %r", text[:300])
        return ClassificationResult(label="UNCERTAIN", confidence=0.0, rationale="Unparseable agent output.")

    try:
        parsed = json.loads(match.group(0))
        result = ClassificationResult(**parsed)
    except (json.JSONDecodeError, ValidationError) as exc:
        log.warning("Bad classification JSON (%s), defaulting to UNCERTAIN: %r", exc, text[:300])
        return ClassificationResult(label="UNCERTAIN", confidence=0.0, rationale="Malformed agent output.")

    if result.label not in {"POSITIVE", "NEGATIVE", "UNCERTAIN"}:
        log.warning("Unexpected label %r, coercing to UNCERTAIN", result.label)
        result.label = "UNCERTAIN"
    return result


def _load_events() -> list[CatalystEvent]:
    if not EVENTS_LOG_PATH.exists():
        return []
    events = []
    for line in EVENTS_LOG_PATH.read_text().splitlines():
        if line.strip():
            events.append(CatalystEvent.model_validate_json(line))
    return events


def _load_seen() -> set[str]:
    if not CLASSIFIED_SEEN_PATH.exists():
        return set()
    return set(json.loads(CLASSIFIED_SEEN_PATH.read_text()))


def _save_seen(seen: set[str]) -> None:
    CLASSIFIED_SEEN_PATH.write_text(json.dumps(sorted(seen)))


def run_once() -> int:
    events = _load_events()
    seen = _load_seen()
    todo = [e for e in events if e.kind in CLASSIFIABLE_KINDS and e.dedup_key not in seen]

    if not todo:
        log.info("No new classifiable catalyst events.")
        return 0

    agent = ScientificAgent()
    written = 0
    with CLASSIFICATIONS_LOG_PATH.open("a") as f:
        for event in todo:
            log.info("Classifying %s :: %s", event.ticker, event.title)
            try:
                result = agent.classify(event)
            except Exception:
                log.exception("Classification failed for %s, skipping", event.dedup_key)
                continue
            record = {
                "ticker": event.ticker,
                "catalyst_kind": event.kind.value,
                "catalyst_title": event.title,
                "catalyst_url": event.url,
                "dedup_key": event.dedup_key,
                "classified_at": datetime.now(timezone.utc).isoformat(),
                **result.model_dump(),
            }
            f.write(json.dumps(record) + "\n")
            seen.add(event.dedup_key)
            written += 1
            log.info("  -> %s (confidence=%.2f): %s", result.label, result.confidence, result.rationale)

    _save_seen(seen)
    log.info("Wrote %d classifications to %s", written, CLASSIFICATIONS_LOG_PATH)
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 2 scientific agent")
    parser.add_argument("--once", action="store_true", help="classify whatever's new and exit")
    args = parser.parse_args()
    if args.once or True:  # currently the only mode; flag kept for future --watch
        run_once()


if __name__ == "__main__":
    main()
