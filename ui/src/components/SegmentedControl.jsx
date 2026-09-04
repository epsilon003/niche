export default function SegmentedControl({ options, value, onChange }) {
  const activeIndex = options.indexOf(value)

  return (
    <div
      className="relative grid rounded-full border border-hairline bg-surface p-1"
      style={{ gridTemplateColumns: `repeat(${options.length}, minmax(0, 1fr))` }}
    >
      <div
        className="absolute inset-y-1 rounded-full bg-surface2 shadow-[0_1px_2px_rgba(0,0,0,0.4)] transition-transform duration-300 ease-out"
        style={{
          width: `calc(${100 / options.length}% - 4px)`,
          transform: `translateX(calc(${activeIndex * 100}% + ${activeIndex * 4}px))`,
        }}
      />
      {options.map((opt) => (
        <button
          key={opt}
          onClick={() => onChange(opt)}
          className={`relative z-10 rounded-full px-4 py-1.5 text-[13px] font-medium transition-colors duration-150 ${
            opt === value ? 'text-ink' : 'text-ink2 hover:text-ink'
          }`}
        >
          {opt}
        </button>
      ))}
    </div>
  )
}
