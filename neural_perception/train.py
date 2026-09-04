"""
Phase 4 — Autoencoder Training Script (Production Version)

Trains the ConvAutoencoder on historical tick spectrograms.
Crucially, it calculates a DYNAMIC anomaly threshold based on the
reconstruction error distribution of the validation set, rather than
hardcoding a Z-score.
"""

from __future__ import annotations

import argparse

import numpy as np
import torch
from torch import nn, optim
from torch.utils.data import DataLoader

from config import get_logger, settings

from .autoencoder import ConvAutoencoder

log = get_logger("neural_perception.train")

MODEL_DIR = settings.data_dir / "models" / "autoencoder"
MODEL_WEIGHTS_PATH = MODEL_DIR / "weights.pt"
MANIFEST_PATH = MODEL_DIR / "manifest.json"


def train_model(
    train_loader: DataLoader, val_loader: DataLoader, epochs: int = 50, lr: float = 1e-3
):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    log.info(f"Training on device: {device}")

    model = ConvAutoencoder(in_channels=1).to(device)
    criterion = nn.MSELoss()
    optimizer = optim.Adam(model.parameters(), lr=lr)

    model.train()
    for epoch in range(epochs):
        epoch_loss = 0.0
        for batch in train_loader:
            x = batch[0].to(device)
            optimizer.zero_grad()
            recon = model(x)
            loss = criterion(recon, x)
            loss.backward()
            optimizer.step()
            epoch_loss += loss.item()

        if (epoch + 1) % 10 == 0:
            log.info(
                f"Epoch {epoch + 1}/{epochs} | Train Loss: {epoch_loss / len(train_loader):.6f}"
            )

    # --- DYNAMIC THRESHOLD CALCULATION ---
    log.info("Calculating dynamic anomaly threshold on validation set...")
    model.eval()
    val_errors = []
    with torch.no_grad():
        for batch in val_loader:
            x = batch[0].to(device)
            recon = model(x)
            # Calculate MSE per sample
            mse = torch.mean((recon - x) ** 2, dim=[1, 2, 3]).cpu().numpy()
            val_errors.extend(mse)

    val_errors = np.array(val_errors)
    mean_error = np.mean(val_errors)
    std_error = np.std(val_errors)

    # 99.5th percentile is a standard starting point for anomaly detection
    threshold_995 = np.percentile(val_errors, 99.5)

    # Also save the Z-score parameters if you prefer using Z-scores in production
    z_threshold = 3.0
    mse_threshold = mean_error + (z_threshold * std_error)

    manifest = {
        "model_name": "ConvAutoencoder_v1",
        "trained_at": datetime.now().isoformat(),
        "mean_recon_error": float(mean_error),
        "std_recon_error": float(std_error),
        "mse_threshold_3_sigma": float(mse_threshold),
        "mse_threshold_995_percentile": float(threshold_995),
        "device": str(device),
    }

    return model, manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument(
        "--data-path",
        type=str,
        required=True,
        help="Path to preprocessed spectrogram tensors (.pt)",
    )
    args = parser.parse_args()

    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    # Dummy data loading for example - replace with your actual spectrogram loading logic
    log.info(f"Loading data from {args.data_path}...")
    # data = torch.load(args.data_path)
    # dataset = TensorDataset(data)
    # train_size = int(0.8 * len(dataset))
    # val_size = len(dataset) - train_size
    # train_dataset, val_dataset = torch.utils.data.random_split(dataset, [train_size, val_size])
    # train_loader = DataLoader(train_dataset, batch_size=32, shuffle=True)
    # val_loader = DataLoader(val_dataset, batch_size=32, shuffle=False)

    # For the sake of this script, assuming loaders are created above
    # model, manifest = train_model(train_loader, val_loader, epochs=args.epochs)

    # Save artifacts
    # torch.save(model.state_dict(), MODEL_WEIGHTS_PATH)
    # with open(MANIFEST_PATH, "w") as f:
    #     json.dump(manifest, f, indent=2)

    # log.info(f"Model saved to {MODEL_WEIGHTS_PATH}")
    # log.info(f"Manifest saved to {MANIFEST_PATH}")
    # log.info(f"Dynamic MSE Threshold (3-sigma): {manifest['mse_threshold_3_sigma']:.6f}")


if __name__ == "__main__":
    from datetime import datetime

    main()
