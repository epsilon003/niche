const PHASE = {
  catalyst_watcher: { label: 'Catalyst', dot: '#30d158' },
  scientific_agent: { label: 'Scientific', dot: '#30d158' },
  cross_intelligence: { label: 'Cross-intel', dot: '#ff9f0a' },
  options_execution: { label: 'Execution', dot: '#0a84ff' },
}

function formatTime(iso) {
  try {
    return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  } catch {
    return iso
  }
}

export default function AgentLog({ events, title = 'Agent log', emptyHint }) {
  return (
    <div className="flex h-full flex-col rounded-card border border-hairline bg-surface/60 backdrop-blur-material">
      {title && (
        <div className="border-b border-hairline px-5 py-4">
          <h2 className="text-[13px] font-medium text-ink2">{title}</h2>
        </div>
      )}
      <div className="flex-1 overflow-y-auto px-2 py-2">
        {events.length === 0 && (
          <EmptyRow text={emptyHint || 'No events yet.'} />
        )}
        <ul>
          {events.map((ev, i) => {
            const meta = PHASE[ev.phase] || { label: ev.phase, dot: '#8e8e93' }
            return (
              <li
                key={`${ev.timestamp}-${i}`}
                className="group flex gap-3 rounded-[10px] px-3 py-2.5 transition-colors duration-150 hover:bg-white/[0.03]"
              >
                <span
                  className="mt-1.5 h-1.5 w-1.5 flex-none rounded-full"
                  style={{ backgroundColor: meta.dot }}
                />
                <div className="min-w-0 flex-1">
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="truncate text-[13.5px] font-medium text-ink">{ev.title}</span>
                    <span className="flex-none text-[11px] tabular-nums text-ink3">{formatTime(ev.timestamp)}</span>
                  </div>
                  {ev.detail && (
                    <p className="mt-0.5 line-clamp-2 text-[12.5px] leading-snug text-ink2">{ev.detail}</p>
                  )}
                  <span className="mt-1 inline-block text-[11px] text-ink3">{meta.label}</span>
                </div>
              </li>
            )
          })}
        </ul>
      </div>
    </div>
  )
}

function EmptyRow({ text }) {
  return (
    <div className="flex h-32 items-center justify-center px-4 text-center text-[13px] text-ink3">
      {text}
    </div>
  )
}
