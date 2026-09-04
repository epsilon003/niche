const PHASE_STYLE = {
  catalyst_watcher: { label: '1A · Catalyst', color: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30' },
  scientific_agent: { label: '2 · Scientific', color: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30' },
  cross_intelligence: { label: '5 · Cross-Intel', color: 'bg-amber-500/15 text-amber-400 border-amber-500/30' },
  options_execution: { label: '6 · Execution', color: 'bg-sky-500/15 text-sky-400 border-sky-500/30' },
}

function formatTime(iso) {
  try {
    return new Date(iso).toLocaleTimeString()
  } catch {
    return iso
  }
}

export default function AgentLog({ events, title = 'Live agent log', emptyHint }) {
  return (
    <div className="flex h-full flex-col rounded-lg border border-edge bg-panel">
      <div className="border-b border-edge px-3 py-2 text-xs font-medium text-slate-400">{title}</div>
      <div className="flex-1 overflow-y-auto p-2">
        {events.length === 0 && (
          <div className="p-4 text-center text-sm text-slate-500">
            {emptyHint || 'No events yet — the pipeline hasn\u2019t produced any log entries.'}
          </div>
        )}
        <ul className="space-y-1.5">
          {events.map((ev, i) => {
            const style = PHASE_STYLE[ev.phase] || { label: ev.phase, color: 'bg-slate-500/15 text-slate-400 border-slate-500/30' }
            return (
              <li key={`${ev.timestamp}-${i}`} className="rounded-md border border-edge/60 bg-black/20 px-2.5 py-2 text-sm">
                <div className="flex items-center justify-between gap-2">
                  <span className={`rounded border px-1.5 py-0.5 text-[10px] font-medium ${style.color}`}>
                    {style.label}
                  </span>
                  <span className="text-[11px] text-slate-500">{formatTime(ev.timestamp)}</span>
                </div>
                <div className="mt-1 font-medium text-slate-200">{ev.title}</div>
                {ev.detail && <div className="mt-0.5 text-xs text-slate-400">{ev.detail}</div>}
              </li>
            )
          })}
        </ul>
      </div>
    </div>
  )
}
