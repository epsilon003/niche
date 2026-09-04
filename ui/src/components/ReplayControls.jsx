import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import AgentLog from './AgentLog'
import { Panel } from './ui'

function isoLocal(date) {
  const pad = (n) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

const SPEEDS = [1, 2, 5, 10]
const BASE_STEP_MS = 1200

const inputClass =
  'rounded-control border border-hairline bg-white/[0.04] px-2.5 py-1.5 text-[13px] text-ink outline-none focus:border-accent'
const primaryBtn =
  'rounded-control bg-accent px-3.5 py-1.5 text-[13px] font-medium text-white transition-opacity duration-150 hover:opacity-85'
const secondaryBtn =
  'rounded-control border border-hairline bg-white/[0.04] px-3.5 py-1.5 text-[13px] font-medium text-ink transition-colors duration-150 hover:bg-white/[0.08]'

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

  const visible = [...allEvents.slice(0, cursor)].reverse()

  return (
    <Panel title="Historical replay">
      <div className="flex flex-wrap items-end gap-4">
        <Field label="Start">
          <input type="datetime-local" value={start} onChange={(e) => setStart(e.target.value)} className={inputClass} />
        </Field>
        <Field label="End">
          <input type="datetime-local" value={end} onChange={(e) => setEnd(e.target.value)} className={inputClass} />
        </Field>
        <button onClick={loadWindow} className={primaryBtn}>
          Load window
        </button>

        {allEvents.length > 0 && (
          <>
            <button onClick={() => setPlaying((p) => !p)} className={secondaryBtn}>
              {playing ? 'Pause' : cursor >= allEvents.length ? 'Replay' : 'Play'}
            </button>
            <button onClick={() => { setCursor(0); setPlaying(false) }} className={secondaryBtn}>
              Reset
            </button>
            <Field label="Speed">
              <select value={speed} onChange={(e) => setSpeed(Number(e.target.value))} className={inputClass}>
                {SPEEDS.map((s) => (
                  <option key={s} value={s}>{s}×</option>
                ))}
              </select>
            </Field>
            <span className="pb-1.5 text-[12px] tabular-nums text-ink3">
              {cursor} / {allEvents.length}
            </span>
          </>
        )}
      </div>

      {loadError && <p className="mt-3 text-[13px] text-negative">{loadError}</p>}

      {allEvents.length === 0 && !loadError && (
        <p className="mt-3 text-[13px] text-ink3">Pick a window and load it to replay what the pipeline logged.</p>
      )}

      {allEvents.length > 0 && (
        <div className="mt-4 h-80">
          <AgentLog events={visible} title="" emptyHint="Press Play to start replaying." />
        </div>
      )}
    </Panel>
  )
}

function Field({ label, children }) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-[11px] text-ink3">{label}</span>
      {children}
    </label>
  )
}
