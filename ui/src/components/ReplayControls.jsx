import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import AgentLog from './AgentLog'

function isoLocal(date) {
  // datetime-local inputs want "YYYY-MM-DDTHH:mm" in local time, no timezone suffix
  const pad = (n) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

const SPEEDS = [1, 2, 5, 10]
const BASE_STEP_MS = 1200 // time between revealed events at 1x

export default function ReplayControls() {
  const now = new Date()
  const dayAgo = new Date(now.getTime() - 24 * 3600 * 1000)

  const [start, setStart] = useState(isoLocal(dayAgo))
  const [end, setEnd] = useState(isoLocal(now))
  const [allEvents, setAllEvents] = useState([])
  const [cursor, setCursor] = useState(0)
  const [playing, setPlaying] = useState(false)
  const [speed, setSpeed] = useState(1)
  const [loadError, setLoadError] = useState(null)
  const timerRef = useRef(null)

  async function loadWindow() {
    setPlaying(false)
    setCursor(0)
    setLoadError(null)
    try {
      const { events } = await api.replay(new Date(start).toISOString(), new Date(end).toISOString())
      setAllEvents(events)
    } catch (err) {
      setLoadError(err.message)
      setAllEvents([])
    }
  }

  useEffect(() => {
    if (!playing) {
      clearInterval(timerRef.current)
      return
    }
    timerRef.current = setInterval(() => {
      setCursor((c) => {
        if (c >= allEvents.length) {
          setPlaying(false)
          return c
        }
        return c + 1
      })
    }, BASE_STEP_MS / speed)
    return () => clearInterval(timerRef.current)
  }, [playing, speed, allEvents.length])

  const visible = [...allEvents.slice(0, cursor)].reverse() // newest-first, matching the live log

  return (
    <div className="rounded-lg border border-edge bg-panel p-3">
      <div className="mb-2 text-xs text-slate-400">Historical replay (Phase 7)</div>

      <div className="flex flex-wrap items-end gap-3 text-xs">
        <label className="flex flex-col gap-1">
          <span className="text-slate-500">Start</span>
          <input
            type="datetime-local"
            value={start}
            onChange={(e) => setStart(e.target.value)}
            className="rounded border border-edge bg-black/30 px-2 py-1 text-slate-200"
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-slate-500">End</span>
          <input
            type="datetime-local"
            value={end}
            onChange={(e) => setEnd(e.target.value)}
            className="rounded border border-edge bg-black/30 px-2 py-1 text-slate-200"
          />
        </label>
        <button
          onClick={loadWindow}
          className="rounded border border-sky-500/40 bg-sky-500/15 px-3 py-1.5 text-sky-300 hover:bg-sky-500/25"
        >
          Load window
        </button>

        {allEvents.length > 0 && (
          <>
            <button
              onClick={() => setPlaying((p) => !p)}
              className="rounded border border-edge bg-black/30 px-3 py-1.5 text-slate-200 hover:bg-black/50"
            >
              {playing ? 'Pause' : cursor >= allEvents.length ? 'Replay' : 'Play'}
            </button>
            <button
              onClick={() => { setCursor(0); setPlaying(false) }}
              className="rounded border border-edge bg-black/30 px-3 py-1.5 text-slate-200 hover:bg-black/50"
            >
              Reset
            </button>
            <label className="flex flex-col gap-1">
              <span className="text-slate-500">Speed</span>
              <select
                value={speed}
                onChange={(e) => setSpeed(Number(e.target.value))}
                className="rounded border border-edge bg-black/30 px-2 py-1 text-slate-200"
              >
                {SPEEDS.map((s) => (
                  <option key={s} value={s}>{s}x</option>
                ))}
              </select>
            </label>
            <span className="text-slate-500">
              {cursor} / {allEvents.length} events
            </span>
          </>
        )}
      </div>

      {loadError && <div className="mt-2 text-xs text-rose-400">{loadError}</div>}

      {allEvents.length === 0 && !loadError && (
        <div className="mt-2 text-xs text-slate-500">Pick a window and load it to replay what the pipeline logged.</div>
      )}

      {allEvents.length > 0 && (
        <div className="mt-3 h-72">
          <AgentLog events={visible} title="" emptyHint="Press Play to start replaying." />
        </div>
      )}
    </div>
  )
}
