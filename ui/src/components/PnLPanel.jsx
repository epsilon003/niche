import { usePolling } from '../hooks/usePolling'
import { api } from '../api'
import { Panel } from './ui'

function fmt(n) {
  if (n === null || n === undefined) return '—'
  return n.toLocaleString('en-US', { style: 'currency', currency: 'USD' })
}

function fmtDelta(n) {
  if (n === null || n === undefined) return '—'
  const sign = n > 0 ? '+' : ''
  return `${sign}${fmt(n)}`
}

export default function PnLPanel() {
  const { data: account } = usePolling(api.account, 10000)
  const { data: positions } = usePolling(api.positions, 10000)

  const dayPl = account?.connected ? account.equity - account.last_equity : null
  const dayPlTone = dayPl > 0 ? 'text-positive' : dayPl < 0 ? 'text-negative' : 'text-ink2'

  return (
    <Panel title="Paper account">
      {!account?.connected && (
        <div className="rounded-[10px] border border-hairline bg-surface2/50 px-4 py-3 text-[13px] text-ink2">
          {account?.error || 'Not connected to Alpaca.'}
        </div>
      )}

      {account?.connected && (
        <div className="flex flex-wrap items-end justify-between gap-6">
          <div>
            <div className="text-[12px] text-ink3">Equity</div>
            <div className="mt-0.5 text-[32px] font-semibold tabular-nums tracking-[-0.02em] text-ink">
              {fmt(account.equity)}
            </div>
            <div className={`mt-0.5 text-[13px] font-medium tabular-nums ${dayPlTone}`}>
              {fmtDelta(dayPl)} today
            </div>
          </div>
          <div className="flex gap-6">
            <Stat label="Buying power" value={fmt(account.buying_power)} />
            <Stat label="Cash" value={fmt(account.cash)} />
          </div>
        </div>
      )}

      <div className="mt-5 border-t border-hairline pt-4">
        <div className="mb-2 text-[12px] text-ink3">Open positions</div>
        {(!positions?.positions || positions.positions.length === 0) && (
          <p className="text-[13px] text-ink3">No open positions.</p>
        )}
        {positions?.positions?.length > 0 && (
          <table className="w-full border-collapse text-[13px]">
            <thead>
              <tr className="text-left text-[11px] text-ink3">
                <th className="pb-2 font-normal">Symbol</th>
                <th className="pb-2 font-normal">Qty</th>
                <th className="pb-2 font-normal">Avg entry</th>
                <th className="pb-2 font-normal">Current</th>
                <th className="pb-2 text-right font-normal">Unrealized P&amp;L</th>
              </tr>
            </thead>
            <tbody>
              {positions.positions.map((p) => (
                <tr key={p.symbol} className="border-t border-hairline">
                  <td className="py-2 font-medium text-ink">{p.symbol}</td>
                  <td className="py-2 tabular-nums text-ink2">{p.qty}</td>
                  <td className="py-2 tabular-nums text-ink2">{fmt(p.avg_entry_price)}</td>
                  <td className="py-2 tabular-nums text-ink2">{fmt(p.current_price)}</td>
                  <td
                    className={`py-2 text-right tabular-nums ${
                      p.unrealized_pl > 0 ? 'text-positive' : p.unrealized_pl < 0 ? 'text-negative' : 'text-ink2'
                    }`}
                  >
                    {fmtDelta(p.unrealized_pl)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </Panel>
  )
}

function Stat({ label, value }) {
  return (
    <div>
      <div className="text-[12px] text-ink3">{label}</div>
      <div className="mt-0.5 text-[15px] font-medium tabular-nums text-ink">{value}</div>
    </div>
  )
}
