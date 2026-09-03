"""
Phase 4 — Train the conv autoencoder on "normal" market spectrograms.

Trains on whatever's accumulated under data/spectrograms/<symbol>/*.npy
(written by Phase 3's pipeline during regular, non-halted trading). The
autoencoder learns to reconstruct typical tick-sonification texture; at
inference time (infer.py) a window that reconstructs badly is, by
construction, one that doesn't look like anything the model has seen —
i.e. a candidate market-microstructure anomaly for Phase 5 to weigh
against the scientific-agent signal.

Usage:
    python -m neural_perception.train --epochs 30 --batch-size 16
"""
from __future__ import annotations

import argparse
import random
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, Dataset, random_split

from config import get_logger, settings
from sonification.spectrogram import N_MELS, expected_frames, pad_or_trim
from sonification.tick_to_audio import DEFAULT_DURATION_SECONDS, DEFAULT_SAMPLE_RATE
from .autoencoder import ConvAutoencoder

log = get_logger("neural_perception.train")

MODEL_DIR = settings.data_dir / "models"
DEFAULT_CHECKPOINT = MODEL_DIR / "autoencoder_global.pt"

TARGET_FRAMES = expected_frames(DEFAULT_DURATION_SECONDS, DEFAULT_SAMPLE_RATE)


class SpectrogramDataset(Dataset):
    def __init__(self, spectrogram_dir: Path):
        self.paths = sorted(spectrogram_dir.rglob("*.npy"))
        if not self.paths:
            raise RuntimeError(
                f"No spectrograms found under {spectrogram_dir}. Run "
                "sonification.pipeline against a live/paper stream for a "
                "while first to accumulate training data."
            )

    def __len__(self) -> int:
        return len(self.paths)

    def __getitem__(self, idx: int) -> torch.Tensor:
        spec = np.load(str(self.paths[idx]))
        spec = pad_or_trim(spec, TARGET_FRAMES)
        return torch.from_numpy(spec).unsqueeze(0).float()  # (1, n_mels, frames)


def train(
    spectrogram_dir: Path,
    checkpoint_path: Path = DEFAULT_CHECKPOINT,
    epochs: int = 30,
    batch_size: int = 16,
    lr: float = 1e-3,
    val_fraction: float = 0.1,
    seed: int = 0,
) -> Path:
    random.seed(seed)
    torch.manual_seed(seed)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    log.info("Training on device: %s", device)

    dataset = SpectrogramDataset(spectrogram_dir)
    n_val = max(1, int(len(dataset) * val_fraction)) if len(dataset) > 5 else 0
    n_train = len(dataset) - n_val
    train_set, val_set = random_split(dataset, [n_train, n_val]) if n_val else (dataset, None)

    train_loader = DataLoader(train_set, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_set, batch_size=batch_size) if val_set else None

    model = ConvAutoencoder(base_channels=16, latent_channels=64).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    criterion = nn.MSELoss()

    best_val = float("inf")
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)

    for epoch in range(1, epochs + 1):
        model.train()
        train_loss = 0.0
        for batch in train_loader:
            batch = batch.to(device)
            optimizer.zero_grad()
            recon = model(batch)
            loss = criterion(recon, batch)
            loss.backward()
            optimizer.step()
            train_loss += loss.item() * batch.size(0)
        train_loss /= len(train_set)

        msg = f"epoch {epoch:3d}/{epochs} | train_mse={train_loss:.5f}"

        if val_loader:
            model.eval()
            val_loss = 0.0
            with torch.no_grad():
                for batch in val_loader:
                    batch = batch.to(device)
                    recon = model(batch)
                    val_loss += criterion(recon, batch).item() * batch.size(0)
            val_loss /= len(val_set)
            msg += f" | val_mse={val_loss:.5f}"

            if val_loss < best_val:
                best_val = val_loss
                torch.save(
                    {"model_state": model.state_dict(), "target_frames": TARGET_FRAMES, "n_mels": N_MELS},
                    checkpoint_path,
                )
        log.info(msg)

    if not val_loader:
        torch.save(
            {"model_state": model.state_dict(), "target_frames": TARGET_FRAMES, "n_mels": N_MELS},
            checkpoint_path,
        )

    log.info("Best checkpoint saved to %s", checkpoint_path)
    return checkpoint_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 4 autoencoder trainer")
    parser.add_argument("--spectrogram-dir", type=Path, default=settings.data_dir / "spectrograms")
    parser.add_argument("--checkpoint", type=Path, default=DEFAULT_CHECKPOINT)
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--lr", type=float, default=1e-3)
    args = parser.parse_args()
    train(
        args.spectrogram_dir,
        checkpoint_path=args.checkpoint,
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
    )


if __name__ == "__main__":
    main()
