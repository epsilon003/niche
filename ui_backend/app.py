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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import get_logger
from .routers import agent_log, market, trades

log = get_logger("ui_backend.app")

app = FastAPI(title="biosignal-trader UI backend", version="0.7.0")

# Vite's default dev server port. Add your deployed frontend origin here too
# if you build/serve this somewhere other than localhost.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(agent_log.router)
app.include_router(market.router)
app.include_router(trades.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("ui_backend.app:app", host="0.0.0.0", port=8000, reload=True)
