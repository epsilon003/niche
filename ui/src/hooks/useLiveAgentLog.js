import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api'

/** Polls /api/agent-log, only asking for events newer than the last one we have. */
export function useLiveAgentLog(intervalMs = 4000) {
  const [events, setEvents] = useState([])
  const [error, setError] = useState(null)
  const lastTimestampRef = useRef(null)

  const poll = useCallback(async () => {
    try {
      const { events: newEvents } = await api.agentLog(lastTimestampRef.current)
      if (newEvents.length > 0) {
        lastTimestampRef.current = newEvents[newEvents.length - 1].timestamp
        setEvents((prev) => [...newEvents, ...prev].slice(0, 500))
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
