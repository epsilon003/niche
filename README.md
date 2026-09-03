# biosignal-trader — Phases 0–5

Implements setup, both tracks (scientific: catalyst watcher → scientific
agent; market: tick engine → sonification → neural perception), and the
cross-intelligence rule engine where they merge. Phases 6–7 (options
execution, UI) are not built yet.

```
Phase 0 — Setup
├── Phase 1A — Catalyst watcher   (scientific track)
│   └── Phase 2 — Scientific agent
└── Phase 1B — Tick engine        (market track)
    └── Phase 3 — Sonification
        └── Phase 4 — Neural perception
                                    \
                                     Phase 5 — Cross-intelligence agent (rule engine, no LLM)
```

## 0. Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # then fill in your Alpaca paper keys + Featherless key
python -m phase0_setup.check_alpaca_connection
```

The check script confirms REST auth against your Alpaca **paper** account and
does a WebSocket auth handshake against the market-data stream. It refuses
to proceed if `ALPACA_TRADING_BASE_URL` doesn't look like the paper host —
this whole project is paper-trading only.

## 1A + 2 — Scientific track

```bash
python -m catalyst_watcher.watcher --once      # poll CT.gov + FDA sources once
python -m scientific_agent.agent                # classify new readouts POSITIVE/NEGATIVE/UNCERTAIN
```

- `catalyst_watcher/clinicaltrials_client.py` — ClinicalTrials.gov API v2 (no
  key needed): trial status changes, upcoming primary-completion dates, and
  results-posted flags.
- `catalyst_watcher/fda_calendar.py` — two honest sources: **live** openFDA
  `drugsfda` application-action history, and an **operator-curated**
  `data/pdufa_calendar.json` for upcoming target action dates (there is no
  free live feed of forward PDUFA dates — see the module docstring).
- `catalyst_watcher/watcher.py` — polls both, dedupes against
  `data/catalyst_seen.json`, appends new events to
  `data/catalyst_events.jsonl`.
- `scientific_agent/agent.py` — a `smolagents.CodeAgent` on an OpenAI-compatible
  LLM endpoint, with one tool (`fetch_trial_detail`) to pull full
  outcome/adverse-event text before classifying. Provider is config-driven
  via `LLM_PROVIDER` in `.env`:
  - **`openrouter` (default)** — free tier, no card required. Uses
    `qwen/qwen3-next-80b-a3b-instruct:free` by default. Rate-limited (20
    req/min; 50/day, or 1000/day after any one-time $10+ credit purchase)
    and the free-model lineup rotates over time — check
    [openrouter.ai/models?max_price=0](https://openrouter.ai/models?max_price=0)
    if classification starts failing with a model-not-found error.
  - **`featherless`** — paid, flat-rate. What the original spec named;
    kept as an option, switch to it by setting `LLM_PROVIDER=featherless`.
  Writes `data/scientific_classifications.jsonl`.

Ticker → company-name mapping for CT.gov/openFDA search lives in
`TICKER_TO_COMPANY` at the top of `watcher.py` — extend it as you grow the
watchlist.

## 1B + 3 + 4 — Market track

```bash
python -m tick_engine.alpaca_stream          # sanity-check the live tick stream alone
python -m sonification.pipeline               # stream + sonify + spectrogram, continuously
python -m neural_perception.train --epochs 30  # once you've accumulated normal-market spectrograms
python -m neural_perception.infer              # score new spectrograms against the trained model
```

- `tick_engine/rolling_deque.py` — `RollingTickWindow`: a 60-second,
  wall-clock-evicted deque per symbol, plus derived stats (VWAP, tick rate,
  price change %).
- `tick_engine/alpaca_stream.py` — reconnect-with-backoff WebSocket client
  against Alpaca's trade stream, feeding every tick into the rolling window.
- `sonification/tick_to_audio.py` — maps price to pitch (log-frequency,
  zero-order-hold + phase-accumulated sine) and trade size to a percussive
  click layer, producing a fixed-length waveform per 60s window.
- `sonification/spectrogram.py` — log-mel spectrogram of that waveform
  (librosa), normalized to `[0, 1]`. The four STFT/mel constants here are
  the contract with Phase 4 — change them in one place only.
- `sonification/pipeline.py` — ties the stream to periodic (default every
  5s) sonification, writing `data/spectrograms/<symbol>/<ts>.npy`.
- `neural_perception/autoencoder.py` — a 4-layer strided Conv2d
  autoencoder; reconstruction MSE is the raw anomaly signal.
- `neural_perception/anomaly_scorer.py` — turns raw MSE into a per-symbol
  EWMA z-score so anomalies are comparable across tickers with very
  different baseline "chattiness."
- `neural_perception/train.py` / `infer.py` — train on accumulated
  spectrograms, then score new ones into `data/anomaly_scores.jsonl`.

This whole chain (tick window → audio → mel-spectrogram → autoencoder
forward pass → anomaly score) was smoke-tested end-to-end with synthetic
ticks during development: a window with an injected price jump scored
**z ≈ +4.35** against a model trained on quiet synthetic windows, i.e. the
anomaly signal responds to the kind of event it's meant to catch.

## 5 — Cross-intelligence agent

```bash
python -m cross_intelligence.engine --once
```

A deterministic rule engine (explicitly *not* an LLM — this is the one
place in the pipeline where a fixed, auditable decision table beats a
model's judgment call). For each new row in
`data/scientific_classifications.jsonl` it finds the closest-in-time
market anomaly reading (within 10 minutes) for that ticker in
`data/anomaly_scores.jsonl`, loads that spectrogram's sidecar
`*.stats.json` (written by `sonification/pipeline.py`) for **directional**
market data — the anomaly z-score alone tells you the market is reacting,
not which way — and fuses all three into one of:

| Decision | Meaning |
|---|---|
| `TRADE` (bias `CALL`/`PUT`) | Scientific signal and market direction agree, on an active anomaly |
| `MONITOR` | One signal present, the other not confirming yet — wait |
| `SKIP` | Either no usable signal, or scientific and market actively **disagree** |

Full decision table and thresholds (`SCI_CONFIDENCE_MIN`,
`ANOMALY_Z_THRESHOLD`, `ANOMALY_CONFIDENCE_MIN`, `DIRECTION_MIN_PCT`) live
at the top of `cross_intelligence/rules.py`. Output goes to
`data/cross_intel_decisions.jsonl` — what Phase 6 will read.

All 10 branches of the decision table (confirmed positive/negative, both
disagreement cases, both "awaiting confirmation" cases, uncertain-with-
and-without market corroboration, low-confidence-treated-as-uncertain, and
no-market-data-at-all) were exercised directly against `rules.decide()`
during development, and the full join — scientific classification →
matched anomaly → matched stats sidecar → decision, plus dedup on a second
run — was exercised against `cross_intelligence.engine.run_once()` with
realistic fixture files. Both produced the expected decisions.

## What Phase 6 will need from here

- `data/cross_intel_decisions.jsonl` — `{ticker, decision, bias, reason_code, reason, ...}`

Phase 6 (options strategy + execution) filters this stream to `decision ==
TRADE`, picks a call/put spread per `bias`, checks IV rank and the max-loss
gate, and executes against Alpaca's paper options API.

## Honesty notes / known limitations

- **No live PDUFA feed exists for free.** `fda_calendar.py` is explicit
  about which of its output is live-fetched (openFDA action history) vs.
  operator-maintained (`data/pdufa_calendar.json`).
- **CT.gov has no ticker field.** The company-name search in
  `TICKER_TO_COMPANY` is a manually maintained mapping and will need
  periodic upkeep (name changes, subsidiaries, etc.).
- Network access to `alpaca.markets`, `clinicaltrials.gov`, `api.fda.gov`,
  and `featherless.ai` was not available in the sandbox this was built in,
  so the live-network code paths (REST/WebSocket auth, CT.gov/openFDA
  queries, the LLM call) are implemented and reviewed but not
  live-exercised — **run `phase0_setup.check_alpaca_connection` first**
  against your real paper keys before trusting the rest. Everything that
  *could* be tested without external network access (tick window eviction
  logic, tick→audio→spectrogram synthesis, the autoencoder's forward pass,
  a real training loop, and inference producing anomaly z-scores) was
  actually run during development, not just written.
