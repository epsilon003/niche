"""
Phase 4 — Neural perception inference.

Loads the trained autoencoder, watches data/spectrograms/<symbol>/ for new
files dropped by Phase 3's pipeline, computes reconstruction error for each,
converts it to a per-symbol z-score via AnomalyScorer, and appends the
result to data/anomaly_scores.jsonl — the file Phase 5 (cross-intelligence
agent) reads to fuse market-microstructure anomaly against the scientific
signal.

Usage (one-shot over whatever's new):
    python -m neural_perception.infer --once

Usage (poll continuously):
    python -m neural_perception.infer
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import torch

from config import get_logger, settings
from sonification.spectrogram import pad_or_trim
from .anomaly_scorer import AnomalyScorer
from .autoencoder import ConvAutoencoder
from .train import DEFAULT_CHECKPOINT

log = get_logger("neural_perception.infer")

SPECTROGRAM_DIR = settings.data_dir / "spectrograms"
SCORES_LOG_PATH = settings.data_dir / "anomaly_scores.jsonl"
PROCESSED_SEEN_PATH = settings.data_dir / "anomaly_processed_seen.json"


def load_model(checkpoint_path: Path = DEFAULT_CHECKPOINT) -> tuple[ConvAutoencoder, int]:
    if not checkpoint_path.exists():
        raise FileNotFoundError(
            f"No checkpoint at {checkpoint_path}. Run `python -m "
            "neural_perception.train` first."
        )
    ckpt = torch.load(checkpoint_path, map_location="cpu")
    model = ConvAutoencoder(base_channels=16, latent_channels=64)
    model.load_state_dict(ckpt["model_state"])
    model.eval()
    return model, ckpt["target_frames"]


def score_file(model: ConvAutoencoder, target_frames: int, path: Path, scorer: AnomalyScorer) -> dict:
    symbol = path.parent.name
    spec = np.load(str(path))
    spec = pad_or_trim(spec, target_frames)
    tensor = torch.from_numpy(spec).unsqueeze(0).unsqueeze(0).float()  # (1,1,n_mels,frames)

    with torch.no_grad():
        raw_error = model.reconstruction_error(tensor, reduction="mean").item()

    result = scorer.score(symbol, raw_error)
    result["source_file"] = str(path)
    result["timestamp"] = path.stem  # pipeline names files by iso-ish timestamp
    return result


def _load_seen() -> set[str]:
    if not PROCESSED_SEEN_PATH.exists():
        return set()
    return set(json.loads(PROCESSED_SEEN_PATH.read_text()))


def _save_seen(seen: set[str]) -> None:
    PROCESSED_SEEN_PATH.write_text(json.dumps(sorted(seen)))


def run_once(checkpoint_path: Path = DEFAULT_CHECKPOINT) -> int:
    model, target_frames = load_model(checkpoint_path)
    scorer = AnomalyScorer()
    seen = _load_seen()

    all_files = sorted(SPECTROGRAM_DIR.rglob("*.npy"))
    todo = [p for p in all_files if str(p) not in seen]
    if not todo:
        log.info("No new spectrograms to score.")
        return 0

    written = 0
    with SCORES_LOG_PATH.open("a") as f:
        for path in todo:
            try:
                result = score_file(model, target_frames, path, scorer)
            except Exception:
                log.exception("Failed to score %s, skipping", path)
                continue
            f.write(json.dumps(result) + "\n")
            seen.add(str(path))
            written += 1
            flag = " ANOMALY" if abs(result["z_score"]) > 3 and result["confidence"] >= 1.0 else ""
            log.info(
                "%-6s raw_err=%.5f z=%+.2f conf=%.2f%s",
                result["symbol"], result["raw_error"], result["z_score"], result["confidence"], flag,
            )

    _save_seen(seen)
    log.info("Scored %d new spectrograms -> %s", written, SCORES_LOG_PATH)
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 4 neural perception inference")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=5.0)
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    args = parser.parse_args()

    if args.once:
        run_once(args.checkpoint)
        return

    log.info("Polling %s every %.1fs. Ctrl+C to stop.", SPECTROGRAM_DIR, args.poll_seconds)
    try:
        while True:
            run_once(args.checkpoint)
            time.sleep(args.poll_seconds)
    except KeyboardInterrupt:
        log.info("Stopped.")


if __name__ == "__main__":
    main()
