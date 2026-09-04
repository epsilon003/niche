"""
Phase 3 — Audio -> mel-spectrogram.

Converts the synthesized tick-audio into a log-mel spectrogram: the
representation Phase 4's convolutional autoencoder is trained on. Kept as a
thin, well-documented wrapper around librosa so the exact STFT/mel params
are visible in one place (and reused identically at train and inference
time in Phase 4 — a mismatch here is the classic silent bug in this kind
of pipeline).
"""

from __future__ import annotations

from pathlib import Path

import librosa
import numpy as np
import soundfile as sf

# These four numbers define the "contract" between Phase 3 and Phase 4.
# Change them in exactly one place; the autoencoder's input shape derives
# from N_MELS x frames, so bumping n_mels means retraining Phase 4.
N_FFT = 1024
HOP_LENGTH = 256
N_MELS = 64
FMIN = 20.0


def audio_to_mel_spectrogram(
    audio: np.ndarray,
    sample_rate: int,
    *,
    n_fft: int = N_FFT,
    hop_length: int = HOP_LENGTH,
    n_mels: int = N_MELS,
) -> np.ndarray:
    """Returns a (n_mels, n_frames) array in log-scaled dB, roughly [-80, 0]."""
    mel = librosa.feature.melspectrogram(
        y=audio,
        sr=sample_rate,
        n_fft=n_fft,
        hop_length=hop_length,
        n_mels=n_mels,
        fmin=FMIN,
    )
    log_mel = librosa.power_to_db(mel, ref=np.max)
    return log_mel.astype(np.float32)


def normalize_for_model(log_mel: np.ndarray) -> np.ndarray:
    """
    Map [-80, 0] dB -> [0, 1] for the autoencoder. Fixed constants (not
    per-sample min/max) so scale is comparable across windows/symbols —
    an anomaly should look anomalous relative to a fixed reference, not
    relative to itself.
    """
    return np.clip((log_mel + 80.0) / 80.0, 0.0, 1.0)


def save_wav(audio: np.ndarray, sample_rate: int, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), audio, sample_rate)


def save_spectrogram(spec: np.ndarray, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.save(str(path), spec)


def load_spectrogram(path: Path) -> np.ndarray:
    return np.load(str(path))


def expected_frames(
    duration_seconds: float, sample_rate: int, hop_length: int = HOP_LENGTH
) -> int:
    """
    Number of STFT frames librosa produces for a signal of this length
    (center=True padding, which is the melspectrogram default). Phase 4
    uses this to pad/trim every spectrogram to one fixed width so they can
    be batched.
    """
    n_samples = int(sample_rate * duration_seconds)
    return 1 + n_samples // hop_length


def pad_or_trim(spec: np.ndarray, target_frames: int) -> np.ndarray:
    """Force a (n_mels, n_frames) array to exactly target_frames wide."""
    n_frames = spec.shape[1]
    if n_frames == target_frames:
        return spec
    if n_frames > target_frames:
        return spec[:, :target_frames]
    pad_width = target_frames - n_frames
    return np.pad(spec, ((0, 0), (0, pad_width)), mode="constant", constant_values=0.0)
