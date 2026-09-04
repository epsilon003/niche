import { useState } from 'react'
import { api } from './api'
import { usePolling } from './hooks/usePolling'
import { useLiveAgentLog } from './hooks/useLiveAgentLog'
import SpectrogramView from './components/SpectrogramView'
import AnomalyChart from './components/AnomalyChart'
import AgentLog from './components/AgentLog'
import PnLPanel from './components/PnLPanel'
import ReplayControls from './components/ReplayControls'
import SegmentedControl from './components/SegmentedControl'

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
    <div className="min-h-screen bg-base">
      <div className="mx-auto max-w-7xl px-6 py-8">
        <Header tab={tab} setTab={setTab} />

        {tab === 'Live' && (
          <div className="mt-8 grid grid-cols-1 gap-6 lg:grid-cols-[1fr_360px]">
            <div className="flex flex-col gap-6">
              <SymbolPicker symbols={symbols} active={activeSymbol} onSelect={setSymbol} />
              <SpectrogramView spectrogram={spectrogram} symbol={activeSymbol || '—'} />
              <AnomalyChart scores={anomalyData?.scores} symbol={activeSymbol || '—'} />
              <PnLPanel />
            </div>
            <div className="lg:sticky lg:top-8 lg:h-[calc(100vh-8rem)]">
              <AgentLog events={liveEvents} title="Agent log" />
            </div>
          </div>
        )}

        {tab === 'Replay' && (
          <div className="mt-8">
            <ReplayControls />
          </div>
        )}
      </div>
    </div>
  )
}

function Header({ tab, setTab }) {
  return (
    <header className="flex flex-col gap-6 border-b border-hairline pb-6 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h1 className="text-[28px] font-semibold tracking-[-0.02em] text-ink">biosignal-trader</h1>
        <p className="mt-1 text-[15px] text-ink2">
          Live spectrogram, agent reasoning, and paper P&amp;L in one place.
        </p>
      </div>
      <SegmentedControl options={TABS} value={tab} onChange={setTab} />
    </header>
  )
}

function SymbolPicker({ symbols, active, onSelect }) {
  if (symbols.length === 0) {
    return (
      <div className="rounded-card border border-hairline bg-surface px-4 py-3 text-[13px] text-ink3">
        No symbols yet — set WATCHLIST in .env and run the pipeline.
      </div>
    )
  }
  return (
    <div className="flex flex-wrap gap-2">
      {symbols.map((s) => {
        const isActive = s === active
        return (
          <button
            key={s}
            onClick={() => onSelect(s)}
            className={`rounded-full px-3.5 py-1.5 text-[13px] font-medium transition-colors duration-150 ${
              isActive
                ? 'bg-accent text-white'
                : 'border border-hairline bg-surface text-ink2 hover:text-ink'
            }`}
          >
            {s}
          </button>
        )
      })}
    </div>
  )
}
