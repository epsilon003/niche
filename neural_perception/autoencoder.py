"""
Phase 4 — Convolutional autoencoder over mel-spectrograms.

Input:  (batch, 1, N_MELS, T_FRAMES) normalized to [0, 1] (see
         sonification.spectrogram.normalize_for_model / pad_or_trim).
Output: same shape, sigmoid-activated reconstruction.

Five stride-2 conv layers downsample both axes; the decoder mirrors it with
transposed convs. Depth/width are deliberately modest — this is meant to
learn "what normal 60s tick-sonification looks like" for a handful of
watchlist tickers, not to be a large generative model. Reconstruction error
is the anomaly signal Phase 5 consumes.
"""

from __future__ import annotations

import torch
from torch import nn


class ConvAutoencoder(nn.Module):
    def __init__(
        self, in_channels: int = 1, base_channels: int = 16, latent_channels: int = 64
    ):
        super().__init__()

        c1, c2, c3 = base_channels, base_channels * 2, base_channels * 4

        self.encoder = nn.Sequential(
            nn.Conv2d(in_channels, c1, kernel_size=3, stride=2, padding=1),
            nn.BatchNorm2d(c1),
            nn.ReLU(inplace=True),
            nn.Conv2d(c1, c2, kernel_size=3, stride=2, padding=1),
            nn.BatchNorm2d(c2),
            nn.ReLU(inplace=True),
            nn.Conv2d(c2, c3, kernel_size=3, stride=2, padding=1),
            nn.BatchNorm2d(c3),
            nn.ReLU(inplace=True),
            nn.Conv2d(c3, latent_channels, kernel_size=3, stride=2, padding=1),
            nn.BatchNorm2d(latent_channels),
            nn.ReLU(inplace=True),
        )

        self.decoder = nn.Sequential(
            nn.ConvTranspose2d(latent_channels, c3, kernel_size=4, stride=2, padding=1),
            nn.BatchNorm2d(c3),
            nn.ReLU(inplace=True),
            nn.ConvTranspose2d(c3, c2, kernel_size=4, stride=2, padding=1),
            nn.BatchNorm2d(c2),
            nn.ReLU(inplace=True),
            nn.ConvTranspose2d(c2, c1, kernel_size=4, stride=2, padding=1),
            nn.BatchNorm2d(c1),
            nn.ReLU(inplace=True),
            nn.ConvTranspose2d(c1, in_channels, kernel_size=4, stride=2, padding=1),
            nn.Sigmoid(),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        latent = self.encoder(x)
        recon = self.decoder(latent)
        # Stride-2 x4 down/up-sampling can round dimensions off by a pixel or
        # two depending on input size; crop/pad back to the exact input shape
        # so the reconstruction-error loss always aligns element-wise.
        recon = _match_shape(recon, x.shape[-2:])
        return recon

    def reconstruction_error(
        self, x: torch.Tensor, reduction: str = "mean"
    ) -> torch.Tensor:
        """Per-sample MSE reconstruction error — the raw anomaly signal."""
        recon = self.forward(x)
        err = (recon - x) ** 2
        err = err.flatten(start_dim=1)
        if reduction == "mean":
            return err.mean(dim=1)
        if reduction == "max":
            return err.max(dim=1).values
        raise ValueError(f"Unknown reduction {reduction!r}")


def _match_shape(tensor: torch.Tensor, target_hw: tuple[int, int]) -> torch.Tensor:
    target_h, target_w = target_hw
    h, w = tensor.shape[-2], tensor.shape[-1]

    if h > target_h:
        tensor = tensor[..., :target_h, :]
    elif h < target_h:
        tensor = nn.functional.pad(tensor, (0, 0, 0, target_h - h))

    if w > target_w:
        tensor = tensor[..., :target_w]
    elif w < target_w:
        tensor = nn.functional.pad(tensor, (0, target_w - w))

    return tensor
