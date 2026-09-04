"""
Phase 7 — UI backend app.

Serves the React frontend's data needs by reading straight from the
data/*.jsonl files the earlier phases already write, plus a thin proxy to
Alpaca for live account/position P&L. No database — the jsonl files are
the source of truth, same as every other phase in this pipeline.

Run:
    uvicorn ui_backend.app:app --reload --port 8000
or:
    python -m ui_backend.app
"""

from __future__ import annotations

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="biosignal-trader UI backend", version="0.7.0")

# Allow Vercel preview + production URLs
allowed_origins = [
    "http://localhost:5173",
    "http://localhost:3000",
    os.getenv("VERCEL_URL", "").replace("^", "https://").replace(".vercel.app", ".vercel.app"),
    # Add your actual Vercel URL:
    "https://niche-xyz.vercel.app",  # REPLACE THIS
]

# Filter out empty strings
allowed_origins = [o for o in allowed_origins if o]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("ui_backend.app:app", host="0.0.0.0", port=8000, reload=True)
