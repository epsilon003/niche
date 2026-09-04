"""Phase 7 — Market/neural-perception endpoints: symbols, spectrogram, anomaly scores."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from .. import data_access

router = APIRouter(prefix="/api/market", tags=["market"])


@router.get("/symbols")
def get_symbols():
    return {"symbols": data_access.list_known_symbols()}


@router.get("/spectrogram/latest")
def get_latest_spectrogram(symbol: str = Query(...)):
    result = data_access.latest_spectrogram(symbol)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No spectrograms yet for {symbol.upper()}")
    return result


@router.get("/anomaly-scores")
def get_anomaly_scores(symbol: str = Query(...), limit: int = Query(default=200, ge=1, le=2000)):
    return {"symbol": symbol.upper(), "scores": data_access.anomaly_history(symbol, limit=limit)}
