import { useEffect, useRef } from 'react'
import { Panel, EmptyState } from './ui'

// A muted blue-through-white ramp reads calmer and more instrument-like than
// a hot inferno palette — closer to what a real spectral analyzer shows,
// and it sits quietly against the dark surface instead of competing with it.
const STOPS = [
  [0, [10, 14, 26]],
  [0.35, [16, 60, 120]],
  [0.65, [10, 132, 255]],
  [0.85, [100, 210, 255]],
  [1, [245, 245, 247]],
]

function colorFor(value) {
  const v = Math.max(0, Math.min(1, value))
  for (let i = 0; i < STOPS.length - 1; i++) {
    const [t0, c0] = STOPS[i]
    const [t1, c1] = STOPS[i + 1]
    if (v >= t0 && v <= t1) {
      const t = (v - t0) / (t1 - t0 || 1)
      const r = Math.round(c0[0] + t * (c1[0] - c0[0]))
      const g = Math.round(c0[1] + t * (c1[1] - c0[1]))
      const b = Math.round(c0[2] + t * (c1[2] - c0[2]))
      return `rgb(${r},${g},${b})`
    }
  }
  return 'rgb(0,0,0)'
}

export default function SpectrogramView({ spectrogram, symbol }) {
  const canvasRef = useRef(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas || !spectrogram) return
    const { data, n_mels: nMels, n_frames: nFrames } = spectrogram

    const ctx = canvas.getContext('2d')
    const width = canvas.width
    const height = canvas.height
    const cellW = width / nFrames
    const cellH = height / nMels

    ctx.clearRect(0, 0, width, height)
    for (let row = 0; row < nMels; row++) {
      const y = height - (row + 1) * cellH
      for (let col = 0; col < nFrames; col++) {
        ctx.fillStyle = colorFor(data[row][col])
        ctx.fillRect(col * cellW, y, cellW + 0.5, cellH + 0.5)
      }
    }
  }, [spectrogram])

  return (
    <Panel
      title="Sonification"
      meta={spectrogram ? `${spectrogram.n_mels} mel bins · last 60s` : null}
    >
      {!spectrogram ? (
        <EmptyState label={`No spectrogram yet for ${symbol}`} hint="Run the sonification pipeline against a live stream." />
      ) : (
        <canvas ref={canvasRef} width={800} height={200} className="w-full rounded-[10px]" />
      )}
    </Panel>
  )
}
