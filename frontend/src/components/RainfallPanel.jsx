import { useEffect, useState } from 'react'
import { api, fmt } from '../api.js'

export default function RainfallPanel({ scenario, onToggle, busy }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const enabled = scenario?.live_rainfall || false

  const load = async (live) => { setLoading(true); setData(await api.rainfall(live)); setLoading(false) }
  useEffect(() => { load(true) }, [])

  return (
    <div className="panel">
      <h3><span>Live rainfall (Open-Meteo)</span>
        <button className="btn small" disabled={loading} onClick={() => load(true)}>{loading ? '…' : 'refresh'}</button>
      </h3>
      {data && data.status !== 'ERROR' && (
        <>
          <div className="hint">
            source: <b style={{ color: data.source === 'live' ? 'var(--ok)' : 'var(--warn)' }}>{data.source}</b>
            {data.fetched_at ? ` · ${new Date(data.fetched_at).toLocaleString()}` : ''}{data.error ? ` · ${data.error}` : ''}
          </div>
          <table style={{ marginTop: 4 }}>
            <thead><tr><th className="l">Zone</th><th>24 h rain mm</th><th>+depth m</th></tr></thead>
            <tbody>
              {data.zones.map((z) => (
                <tr key={z.zone}><td className="l">{z.zone} {z.name}</td><td>{fmt(z.rain_mm_24h)}</td><td>{fmt(z.depth_add_m, 2)}</td></tr>
              ))}
            </tbody>
          </table>
          <label className="toggle" style={{ marginTop: 8 }}>
            <input type="checkbox" checked={enabled} disabled={busy} onChange={(e) => onToggle(e.target.checked)} />
            <span>Live rainfall adjustment {enabled ? 'ON' : 'OFF'} (default OFF for reproducibility)</span>
          </label>
          <div className="hint">Rule: {data.rule}. Applied to flood depth before the urgency score; re-optimizes with the anti-churn term.</div>
        </>
      )}
      {data && data.status === 'ERROR' && <div className="hint">{data.error}</div>}
    </div>
  )
}
