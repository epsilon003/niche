"""
Phase 4 — Inference Engine.

Loads the trained autoencoder and its dynamic threshold manifest to score
incoming tick spectrograms. Outputs an anomaly score and a boolean flag
indicating if the threshold was breached.
"""

from __future__ import annotations

import json

import torch

from config import get_logger, settings

from .autoencoder import ConvAutoencoder

log = get_logger("neural_perception.infer")

MODEL_DIR = settings.data_dir / "models" / "autoencoder"
WEIGHTS_PATH = MODEL_DIR / "weights.pt"
MANIFEST_PATH = MODEL_DIR / "manifest.json"


class AnomalyInferencer:
    def __init__(self):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model = self._load_model()
        self.manifest = self._load_manifest()
        self.threshold = self.manifest.get(
            "mse_threshold_995_percentile", 0.05
        )  # Fallback
        log.info(f"Inferencer loaded. Active MSE Threshold: {self.threshold:.6f}")

    def _load_model(self) -> ConvAutoencoder:
        if not WEIGHTS_PATH.exists():
            raise FileNotFoundError(
                f"No model weights found at {WEIGHTS_PATH}. Run train.py first."
            )

        model = ConvAutoencoder(in_channels=1).to(self.device)
        model.load_state_dict(torch.load(WEIGHTS_PATH, map_location=self.device))
        model.eval()
        return model

    def _load_manifest(self) -> dict:
        if not MANIFEST_PATH.exists():
            log.warning("Manifest not found. Using default threshold.")
            return {"mse_threshold_995_percentile": 0.05}
        with open(MANIFEST_PATH, "r") as f:
            return json.load(f)

    @torch.no_grad()
    def score(self, spectrogram_tensor: torch.Tensor) -> dict:
        """
        Takes a (1, N_MELS, T_FRAMES) tensor and returns anomaly metrics.
        """
        x = spectrogram_tensor.unsqueeze(0).to(self.device)  # Add batch dim
        recon = self.model(x)

        # Calculate Mean Squared Error for this specific sample
        mse = torch.mean((recon - x) ** 2).item()

        # Calculate Z-score relative to training distribution
        mean_err = self.manifest.get("mean_recon_error", 0)
        std_err = self.manifest.get("std_recon_error", 1)
        z_score = (mse - mean_err) / std_err if std_err > 0 else 0

        is_anomaly = mse > self.threshold

        return {
            "mse": mse,
            "z_score": z_score,
            "is_anomaly": is_anomaly,
            "threshold": self.threshold,
        }
