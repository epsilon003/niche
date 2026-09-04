"""
Central configuration for the whole pipeline (Phase 0).

Every other module imports `settings` from here instead of calling
os.getenv() directly, so there is exactly one place that knows how to
find the .env file and one place to change if the schema changes.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent
load_dotenv(ROOT_DIR / ".env")  # no-op if the file doesn't exist yet


def _split_csv(value: str) -> list[str]:
    return [t.strip().upper() for t in value.split(",") if t.strip()]


@dataclass(frozen=True)
class Settings:
    # Alpaca
    alpaca_api_key: str = os.getenv("ALPACA_API_KEY", "")
    alpaca_secret_key: str = os.getenv("ALPACA_SECRET_KEY", "")
    alpaca_paper: bool = os.getenv("ALPACA_PAPER", "true").lower() == "true"
    alpaca_trading_base_url: str = os.getenv(
        "ALPACA_TRADING_BASE_URL", "https://paper-api.alpaca.markets"
    )
    alpaca_data_stream_url: str = os.getenv(
        "ALPACA_DATA_STREAM_URL", "wss://stream.data.alpaca.markets/v2/iex"
    )

    # LLM provider for the scientific agent (Phase 2) — config-driven so you
    # can swap providers without touching agent.py. Both are OpenAI-compatible
    # endpoints, so smolagents.OpenAIServerModel works unchanged either way.
    #
    #   "openrouter"  — default. Free tier: no card required, includes
    #                   tool-calling-capable Qwen models at $0. Rate-limited
    #                   (20 req/min; 50/day free, 1000/day after any $10+
    #                   lifetime credit purchase) and the specific free
    #                   model lineup rotates over time — check
    #                   https://openrouter.ai/models?max_price=0 if the
    #                   configured model stops being free.
    #   "featherless" — paid, flat-rate. Kept as an option since it's what
    #                   the original spec named.
    llm_provider: str = os.getenv("LLM_PROVIDER", "openrouter")

    openrouter_api_key: str = os.getenv("OPENROUTER_API_KEY", "")
    openrouter_base_url: str = os.getenv(
        "OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"
    )
    openrouter_model: str = os.getenv("OPENROUTER_MODEL", "openrouter/free")

    featherless_api_key: str = os.getenv("FEATHERLESS_API_KEY", "")
    featherless_base_url: str = os.getenv(
        "FEATHERLESS_BASE_URL", "https://api.featherless.ai/v1"
    )
    featherless_model: str = os.getenv("FEATHERLESS_MODEL", "Qwen/Qwen2.5-72B-Instruct")

    # Catalyst sources
    openfda_api_key: str = os.getenv("OPENFDA_API_KEY", "")

    # Universe
    watchlist: list[str] = field(
        default_factory=lambda: _split_csv(os.getenv("WATCHLIST", "MRNA,NVAX,BNTX"))
    )

    # Misc
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    data_dir: Path = Path(os.getenv("DATA_DIR", str(ROOT_DIR / "data")))

    # ADDED: Path to the JSONL file where catalyst events are appended
    events_file: Path = (
        Path(os.getenv("DATA_DIR", str(ROOT_DIR / "data"))) / "events.jsonl"
    )

    def validate_alpaca(self) -> list[str]:
        """Return a list of missing/invalid Alpaca settings, empty if OK."""
        problems = []
        if not self.alpaca_api_key:
            problems.append("ALPACA_API_KEY is not set")
        if not self.alpaca_secret_key:
            problems.append("ALPACA_SECRET_KEY is not set")
        if not self.alpaca_paper:
            problems.append(
                "ALPACA_PAPER is false — this pipeline is built and tested "
                "for paper trading only, refusing to assume live is safe"
            )
        return problems

    def validate_featherless(self) -> list[str]:
        problems = []
        if not self.featherless_api_key:
            problems.append("FEATHERLESS_API_KEY is not set")
        return problems

    def validate_openrouter(self) -> list[str]:
        problems = []
        if not self.openrouter_api_key:
            problems.append(
                "OPENROUTER_API_KEY is not set (sign up free at "
                "https://openrouter.ai/keys — no card required)"
            )
        return problems

    def validate_llm(self) -> list[str]:
        """Dispatches to whichever provider LLM_PROVIDER selects."""
        if self.llm_provider == "openrouter":
            return self.validate_openrouter()
        if self.llm_provider == "featherless":
            return self.validate_featherless()
        return [
            f"Unknown LLM_PROVIDER {self.llm_provider!r} — expected 'openrouter' or 'featherless'"
        ]


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)


def get_logger(name: str) -> logging.Logger:
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    )
    return logging.getLogger(name)
