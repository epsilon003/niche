const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

async function get(path, params = {}) {
  const url = new URL(API_BASE + path)
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null) url.searchParams.set(k, v)
  })
  const res = await fetch(url)
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `${res.status} ${res.statusText}`)
  }
  return res.json()
}

export const api = {
  health: () => get('/api/health'),
  agentLog: (since, limit = 200) => get('/api/agent-log', { since, limit }),
  replay: (start, end) => get('/api/replay', { start, end }),
  symbols: () => get('/api/market/symbols'),
  spectrogram: (symbol) => get('/api/market/spectrogram/latest', { symbol }),
  anomalyScores: (symbol, limit = 200) => get('/api/market/anomaly-scores', { symbol, limit }),
  trades: (status) => get('/api/trades', { status }),
  account: () => get('/api/account'),
  positions: () => get('/api/positions'),
}
