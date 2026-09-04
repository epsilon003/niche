import { usePolling } from '../hooks/usePolling'
import { api } from '../api'

function fmt(n) {
  if (n === null || n === undefined) return '—'
  return n.toLocaleString('en-US', { style: 'currency', currency: 'USD' })
}

export default function PnLPanel() {
  const { data: account } = usePolling(api.account, 10000)
  const { data: positions } = usePolling(api.positions, 10000)

  const dayPl = account && account.connected ? account.equity - account.last_equity : null

  return (
    <div className="rounded-lg border border-edge bg-panel p-3">
      <div className="mb-2 text-xs text-slate-400">Alpaca paper account (Phase 6)</div>

      {!account?.connected && (
        <div className="rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-400">
          Not connected{account?.error ? ` — ${account.error}` : ''}. Check ALPACA_API_KEY / ALPACA_SECRET_KEY.
        </div>
      )}

      {account?.connected && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Stat label="Equity" value={fmt(account.equity)} />
          <Stat label="Buying power" value={fmt(account.buying_power)} />
          <Stat label="Cash" value={fmt(account.cash)} />
          <Stat
            label="Day P&L"
            value={fmt(dayPl)}
            tone={dayPl > 0 ? 'text-emerald-400' : dayPl < 0 ? 'text-rose-400' : undefined}
          />
        </div>
      )}

      <div className="mt-3 border-t border-edge pt-2">
        <div className="mb-1.5 text-xs text-slate-400">Open positions</div>
        {(!positions?.positions || positions.positions.length === 0) && (
          <div className="text-xs text-slate-500">No open positions.</div>
        )}
        {positions?.positions?.length > 0 && (
          <table className="w-full text-xs">
            <thead className="text-slate-500">
              <tr className="text-left">
                <th className="py-1 font-normal">Symbol</th>
                <th className="py-1 font-normal">Qty</th>
                <th className="py-1 font-normal">Avg entry</th>
                <th className="py-1 font-normal">Current</th>
                <th className="py-1 font-normal text-right">Unrealized P&L</th>
              </tr>
            </thead>
            <tbody>
              {positions.positions.map((p) => (
                <tr key={p.symbol} className="border-t border-edge/60">
                  <td className="py-1 text-slate-200">{p.symbol}</td>
                  <td className="py-1">{p.qty}</td>
                  <td className="py-1">{fmt(p.avg_entry_price)}</td>
                  <td className="py-1">{fmt(p.current_price)}</td>
                  <td className={`py-1 text-right ${p.unrealized_pl > 0 ? 'text-emerald-400' : p.unrealized_pl < 0 ? 'text-rose-400' : ''}`}>
                    {fmt(p.unrealized_pl)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

function Stat({ label, value, tone }) {
  return (
    <div>
      <div className="text-[11px] text-slate-500">{label}</div>
      <div className={`text-sm font-medium ${tone || 'text-slate-200'}`}>{value}</div>
    </div>
  )
}
