import { useEffect, useRef } from 'react'

// Small hand-rolled "inferno-ish" colormap — avoids pulling in a whole
// colormap library for one gradient. Stops chosen to read clearly on a
// dark panel: near-black at 0, through purple/orange, to pale yellow at 1.
const STOPS = [
  [0, [10, 10, 20]],
  [0.25, [63, 22, 84]],
  [0.5, [158, 47, 84]],
  [0.75, [230, 121, 46]],
  [1, [252, 232, 130]],
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
      // row 0 = lowest mel bin; flip vertically so low frequencies sit at the bottom
      const y = height - (row + 1) * cellH
      for (let col = 0; col < nFrames; col++) {
        ctx.fillStyle = colorFor(data[row][col])
        ctx.fillRect(col * cellW, y, cellW + 0.5, cellH + 0.5)
      }
    }
  }, [spectrogram])

  if (!spectrogram) {
    return (
      <div className="flex h-48 items-center justify-center rounded-lg border border-edge bg-panel text-sm text-slate-500">
        No spectrogram yet for {symbol} — run the sonification pipeline against a live stream.
      </div>
    )
  }

  return (
    <div className="rounded-lg border border-edge bg-panel p-3">
      <div className="mb-2 flex items-center justify-between text-xs text-slate-400">
        <span>{symbol} — last 60s tick sonification</span>
        <span>{spectrogram.n_mels} mel bins</span>
      </div>
      <canvas ref={canvasRef} width={800} height={220} className="w-full rounded" />
    </div>
  )
}
