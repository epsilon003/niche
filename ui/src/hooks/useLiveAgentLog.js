import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api'

// Events have no server-assigned id, so a stable dedup key is built from
// the fields that make an event unique. Needed because React 18's
// StrictMode intentionally double-invokes effects in development — both
// invocations can fire the initial since=null fetch before either updates
// lastTimestampRef, which without this dedup produced visibly duplicated
// rows (caught via a Playwright DOM assertion, not just a screenshot).
function eventKey(ev) {
  return `${ev.phase}:${ev.timestamp}:${ev.title}`
}

/** Polls /api/agent-log, only asking for events newer than the last one we have. */
export function useLiveAgentLog(intervalMs = 4000) {
  const [events, setEvents] = useState([])
  const [error, setError] = useState(null)
  const lastTimestampRef = useRef(null)
  const seenRef = useRef(new Set())

  const poll = useCallback(async () => {
    try {
      const { events: newEvents } = await api.agentLog(lastTimestampRef.current)
      if (newEvents.length > 0) {
        lastTimestampRef.current = newEvents[newEvents.length - 1].timestamp
        const fresh = newEvents.filter((ev) => !seenRef.current.has(eventKey(ev)))
        fresh.forEach((ev) => seenRef.current.add(eventKey(ev)))
        if (fresh.length > 0) {
          // API returns ascending (oldest first); reverse so the newest
          // event lands at the top, matching ReplayControls' ordering.
          setEvents((prev) => [...fresh].reverse().concat(prev).slice(0, 500))
        }
      }
      setError(null)
    } catch (err) {
      setError(err)
    }
  }, [])

  useEffect(() => {
    poll()
    const id = setInterval(poll, intervalMs)
    return () => clearInterval(id)
  }, [poll, intervalMs])

  return { events, error }
}
