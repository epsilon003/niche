import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine, ResponsiveContainer } from 'recharts'
import { Panel, EmptyState } from './ui'

const Z_THRESHOLD = 2.5 // matches cross_intelligence/rules.py ANOMALY_Z_THRESHOLD

function formatTimestamp(ts) {
  if (!ts || ts.length < 15) return ts
  return `${ts.slice(9, 11)}:${ts.slice(11, 13)}:${ts.slice(13, 15)}`
}

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-[10px] border border-hairline2 bg-surface2/95 px-3 py-2 text-[12px] shadow-lg backdrop-blur-material">
      <div className="text-ink3">{label}</div>
      <div className="mt-0.5 font-medium tabular-nums text-ink">z = {payload[0].value.toFixed(2)}</div>
    </div>
  )
}

export default function AnomalyChart({ scores, symbol }) {
  if (!scores || scores.length === 0) {
    return (
      <Panel title="Anomaly score">
        <EmptyState label={`No anomaly scores yet for ${symbol}`} hint="Run neural_perception.infer." />
      </Panel>
    )
  }

  const chartData = scores.map((s) => ({
    time: formatTimestamp(s.timestamp),
    z: s.z_score,
  }))
  const latest = chartData[chartData.length - 1]
  const isAlert = Math.abs(latest.z) >= Z_THRESHOLD

  return (
    <Panel
      title="Anomaly score"
      meta={
        <span className={`tabular-nums ${isAlert ? 'text-caution' : 'text-ink3'}`}>
          z = {latest.z.toFixed(2)}
        </span>
      }
    >
      <ResponsiveContainer width="100%" height={160}>
        <LineChart data={chartData} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" vertical={false} />
          <XAxis dataKey="time" stroke="rgba(235,235,245,0.3)" fontSize={11} tickLine={false} axisLine={false} />
          <YAxis stroke="rgba(235,235,245,0.3)" fontSize={11} tickLine={false} axisLine={false} />
          <Tooltip content={<CustomTooltip />} cursor={{ stroke: 'rgba(255,255,255,0.12)' }} />
          <ReferenceLine y={Z_THRESHOLD} stroke="#ff9f0a" strokeDasharray="4 4" strokeOpacity={0.6} />
          <ReferenceLine y={-Z_THRESHOLD} stroke="#ff9f0a" strokeDasharray="4 4" strokeOpacity={0.6} />
          <ReferenceLine y={0} stroke="rgba(255,255,255,0.14)" />
          <Line type="monotone" dataKey="z" stroke="#0a84ff" strokeWidth={2} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </Panel>
  )
}
