import { useEffect, useRef, useState } from 'react'

/**
 * Calls `fn` immediately, then again every `intervalMs` while `enabled`.
 * Exposes {data, error, loading} — callers don't need to manage timers.
 */
export function usePolling(fn, intervalMs, deps = [], enabled = true) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const fnRef = useRef(fn)
  fnRef.current = fn

  useEffect(() => {
    if (!enabled) return
    let cancelled = false

    async function tick() {
      try {
        const result = await fnRef.current()
        if (!cancelled) {
          setData(result)
          setError(null)
        }
      } catch (err) {
        if (!cancelled) setError(err)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    tick()
    const id = setInterval(tick, intervalMs)
    return () => {
      cancelled = true
      clearInterval(id)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [intervalMs, enabled, ...deps])

  return { data, error, loading }
}
