import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine, ResponsiveContainer } from 'recharts'

const Z_THRESHOLD = 2.5 // matches cross_intelligence/rules.py ANOMALY_Z_THRESHOLD

function formatTimestamp(ts) {
  // Phase 4 timestamps look like "20260903T211524" (spectrogram-filename format)
  if (!ts || ts.length < 15) return ts
  return `${ts.slice(9, 11)}:${ts.slice(11, 13)}:${ts.slice(13, 15)}`
}

export default function AnomalyChart({ scores, symbol }) {
  if (!scores || scores.length === 0) {
    return (
      <div className="flex h-40 items-center justify-center rounded-lg border border-edge bg-panel text-sm text-slate-500">
        No anomaly scores yet for {symbol} — run neural_perception.infer.
      </div>
    )
  }

  const chartData = scores.map((s) => ({
    time: formatTimestamp(s.timestamp),
    z: s.z_score,
    confidence: s.confidence,
  }))

  return (
    <div className="rounded-lg border border-edge bg-panel p-3">
      <div className="mb-2 text-xs text-slate-400">{symbol} — anomaly z-score (Phase 4)</div>
      <ResponsiveContainer width="100%" height={160}>
        <LineChart data={chartData} margin={{ top: 4, right: 12, left: -12, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#232733" />
          <XAxis dataKey="time" stroke="#64748b" fontSize={11} />
          <YAxis stroke="#64748b" fontSize={11} />
          <Tooltip
            contentStyle={{ background: '#12151c', border: '1px solid #232733', fontSize: 12 }}
            labelStyle={{ color: '#94a3b8' }}
          />
          <ReferenceLine y={Z_THRESHOLD} stroke="#f59e0b" strokeDasharray="4 4" />
          <ReferenceLine y={-Z_THRESHOLD} stroke="#f59e0b" strokeDasharray="4 4" />
          <ReferenceLine y={0} stroke="#334155" />
          <Line type="monotone" dataKey="z" stroke="#38bdf8" strokeWidth={2} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
