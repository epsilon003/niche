import { useState } from 'react'
import { api } from './api'
import { usePolling } from './hooks/usePolling'
import { useLiveAgentLog } from './hooks/useLiveAgentLog'
import SpectrogramView from './components/SpectrogramView'
import AnomalyChart from './components/AnomalyChart'
import AgentLog from './components/AgentLog'
import PnLPanel from './components/PnLPanel'
import ReplayControls from './components/ReplayControls'

const TABS = ['Live', 'Replay']

export default function App() {
  const [tab, setTab] = useState('Live')
  const [symbol, setSymbol] = useState(null)

  const { data: symbolsData } = usePolling(api.symbols, 30000)
  const symbols = symbolsData?.symbols || []
  const activeSymbol = symbol || symbols[0]

  const { data: spectrogram } = usePolling(
    () => (activeSymbol ? api.spectrogram(activeSymbol) : Promise.resolve(null)),
    5000,
    [activeSymbol],
    !!activeSymbol,
  )
  const { data: anomalyData } = usePolling(
    () => (activeSymbol ? api.anomalyScores(activeSymbol) : Promise.resolve(null)),
    5000,
    [activeSymbol],
    !!activeSymbol,
  )

  const { events: liveEvents } = useLiveAgentLog(4000)

  return (
    <div className="mx-auto flex min-h-screen max-w-7xl flex-col gap-4 p-4">
      <Header tab={tab} setTab={setTab} />

      {tab === 'Live' && (
        <div className="grid flex-1 grid-cols-1 gap-4 lg:grid-cols-3">
          <div className="flex flex-col gap-4 lg:col-span-2">
            <SymbolPicker symbols={symbols} active={activeSymbol} onSelect={setSymbol} />
            <SpectrogramView spectrogram={spectrogram} symbol={activeSymbol || '—'} />
            <AnomalyChart scores={anomalyData?.scores} symbol={activeSymbol || '—'} />
            <PnLPanel />
          </div>
          <div className="h-[70vh] lg:h-auto">
            <AgentLog events={liveEvents} title="Live agent log — all phases" />
          </div>
        </div>
      )}

      {tab === 'Replay' && <ReplayControls />}
    </div>
  )
}

function Header({ tab, setTab }) {
  return (
    <header className="flex items-center justify-between border-b border-edge pb-3">
      <div>
        <h1 className="text-lg font-semibold text-slate-100">biosignal-trader</h1>
        <p className="text-xs text-slate-500">Phase 7 — live spectrogram · agent log · Alpaca P&amp;L · historical replay</p>
      </div>
      <nav className="flex gap-1 rounded-lg border border-edge bg-panel p-1">
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`rounded-md px-3 py-1.5 text-sm transition ${
              tab === t ? 'bg-sky-500/20 text-sky-300' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            {t}
          </button>
        ))}
      </nav>
    </header>
  )
}

function SymbolPicker({ symbols, active, onSelect }) {
  if (symbols.length === 0) {
    return (
      <div className="rounded-lg border border-edge bg-panel px-3 py-2 text-xs text-slate-500">
        No symbols found yet — set WATCHLIST in .env and run the pipeline.
      </div>
    )
  }
  return (
    <div className="flex flex-wrap gap-1.5">
      {symbols.map((s) => (
        <button
          key={s}
          onClick={() => onSelect(s)}
          className={`rounded-md border px-3 py-1 text-sm transition ${
            s === active
              ? 'border-sky-500/40 bg-sky-500/20 text-sky-300'
              : 'border-edge bg-panel text-slate-400 hover:text-slate-200'
          }`}
        >
          {s}
        </button>
      ))}
    </div>
  )
}
