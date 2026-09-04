export function Panel({ title, meta, action, children, className = '' }) {
  return (
    <section className={`rounded-card border border-hairline bg-surface/60 p-5 backdrop-blur-material ${className}`}>
      <div className="mb-4 flex items-baseline justify-between">
        <h2 className="text-[13px] font-medium text-ink2">{title}</h2>
        <div className="flex items-center gap-3">
          {meta && <span className="text-[12px] tabular-nums text-ink3">{meta}</span>}
          {action}
        </div>
      </div>
      {children}
    </section>
  )
}

export function EmptyState({ label, hint }) {
  return (
    <div className="flex h-40 flex-col items-center justify-center gap-1 rounded-[10px] border border-dashed border-hairline text-center">
      <p className="text-[13px] text-ink2">{label}</p>
      {hint && <p className="text-[12px] text-ink3">{hint}</p>}
    </div>
  )
}
