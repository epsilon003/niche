"""
Phase 1A — Catalyst watcher orchestrator.

Polls ClinicalTrials.gov + the FDA sources for every ticker in the
watchlist, diffs against a small on-disk "seen" store so we only surface
genuinely new/changed catalysts, and writes them to data/catalyst_events.jsonl
for Phase 2 (scientific agent) to consume.

Run once:
    python -m catalyst_watcher.watcher --once

Run on a schedule (default: every 15 min):
    python -m catalyst_watcher.watcher
"""

from __future__ import annotations

import argparse
import json

from apscheduler.schedulers.blocking import BlockingScheduler

from config import get_logger, settings

from . import clinicaltrials_client, fda_calendar
from .models import CatalystEvent

log = get_logger("catalyst_watcher.watcher")

SEEN_STORE_PATH = settings.data_dir / "catalyst_seen.json"
EVENTS_LOG_PATH = settings.data_dir / "catalyst_events.jsonl"

# CT.gov / openFDA index by company name, not ticker. Maintain the mapping
# here (or move it to a config file once the watchlist grows).
TICKER_TO_COMPANY = {
    "MRNA": "Moderna",
    "NVAX": "Novavax",
    "BNTX": "BioNTech",
    "SRPT": "Sarepta Therapeutics",
    "IONS": "Ionis Pharmaceuticals",
}


def _load_seen() -> set[str]:
    if not SEEN_STORE_PATH.exists():
        return set()
    return set(json.loads(SEEN_STORE_PATH.read_text()))


def _save_seen(seen: set[str]) -> None:
    SEEN_STORE_PATH.write_text(json.dumps(sorted(seen)))


def _append_events(events: list[CatalystEvent]):
    # FIX: Use EVENTS_LOG_PATH instead of settings.events_file to match what the agent reads
    with open(EVENTS_LOG_PATH, "a", encoding="utf-8") as f:
        f.writelines(ev.model_dump_json() + "\n" for ev in events)


def poll_once() -> list[CatalystEvent]:
    seen = _load_seen()
    new_events: list[CatalystEvent] = []

    curated = fda_calendar.load_curated_pdufa_dates()
    for ev in curated:
        if ev.dedup_key not in seen:
            new_events.append(ev)
            seen.add(ev.dedup_key)

    tickers = settings.watchlist or list(TICKER_TO_COMPANY.keys())
    for ticker in tickers:
        company = TICKER_TO_COMPANY.get(ticker)
        if not company:
            log.warning(
                "No CT.gov/FDA company mapping for %s — add it to "
                "TICKER_TO_COMPANY in watcher.py, skipping.",
                ticker,
            )
            continue

        for ev in clinicaltrials_client.search_studies(company, ticker):
            if ev.dedup_key not in seen:
                new_events.append(ev)
                seen.add(ev.dedup_key)

        for ev in fda_calendar.fetch_recent_actions(company, ticker):
            if ev.dedup_key not in seen:
                new_events.append(ev)
                seen.add(ev.dedup_key)

    if new_events:
        _append_events(new_events)
        _save_seen(seen)
        log.info(
            "Poll complete: %d NEW catalyst events written to %s",
            len(new_events),
            EVENTS_LOG_PATH,
        )
        for ev in new_events:
            log.info(
                "  [%s] %s — %s (%s)", ev.ticker, ev.kind.value, ev.title, ev.event_date
            )
    else:
        log.info("Poll complete: no new catalyst events.")

    return new_events


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 1A catalyst watcher")
    parser.add_argument(
        "--once", action="store_true", help="poll a single time and exit"
    )
    parser.add_argument(
        "--interval-min", type=int, default=15, help="polling interval in minutes"
    )
    args = parser.parse_args()

    if args.once:
        poll_once()
        return

    log.info(
        "Starting catalyst watcher, polling every %d min. Ctrl+C to stop.",
        args.interval_min,
    )
    scheduler = BlockingScheduler()
    scheduler.add_job(
        poll_once, "interval", minutes=args.interval_min, next_run_time=None
    )
    poll_once()  # run immediately on startup too
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("Catalyst watcher stopped.")


if __name__ == "__main__":
    main()
