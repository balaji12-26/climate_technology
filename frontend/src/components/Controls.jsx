import { useEffect, useRef, useState } from 'react'
import { RES, REASON } from '../api.js'

// slider ceilings: defaults (boats 100, medical 200, trucks 10) must not sit at an edge
const PRI_MAX = { rescue_boat: 300, medical_team: 500, supply_truck: 100 }

const URG = [
  ['depth', 'Flood depth'], ['infrastructure', 'Infrastructure damage'], ['medical', 'Medical urgency'],
  ['access', 'Access difficulty'], ['vulnerable', 'Vulnerable population'],
]

export default function Controls({ scenario, plan, busy, onOptimize, onDisrupt, onReset, lastEvent }) {
  const [did, setDid] = useState('D1')
  const [urg, setUrg] = useState(null)
  const [pri, setPri] = useState(null)
  const timer = useRef(null)
  const dirty = useRef(false)

  // sync sliders from the server state unless the user is mid-drag
  useEffect(() => {
    if (!scenario || dirty.current) return
    setUrg({ ...scenario.urgency_weights })
    setPri({ ...scenario.priority_weights })
  }, [scenario])

  const schedule = (nextUrg, nextPri) => {
    dirty.current = true
    clearTimeout(timer.current)
    timer.current = setTimeout(async () => {
      await onOptimize({ urgency_weights: nextUrg, priority_weights: nextPri })
      dirty.current = false
    }, 350)
  }

  if (!scenario || !urg || !pri) return <div className="panel">Loading scenario…</div>
  const applied = scenario.applied_disruptions
  const urgSum = Object.values(urg).reduce((a, b) => a + Number(b), 0)

  return (
    <>
      <div className="panel">
        <h3>Disruptions (cumulative)</h3>
        <div className="row">
          <select value={did} onChange={(e) => setDid(e.target.value)} style={{ flex: 1 }}>
            {scenario.disruptions.map((d) => (
              <option key={d.id} value={d.id} disabled={applied.includes(d.id)}>{d.id} — {d.description}{applied.includes(d.id) ? ' ✓' : ''}</option>
            ))}
          </select>
        </div>
        <div className="row" style={{ marginTop: 6 }}>
          <button className="btn primary" disabled={busy || applied.includes(did)} onClick={() => onDisrupt(did)}>Inject {did}</button>
          <button className="btn danger" disabled={busy} onClick={onReset}>Reset scenario</button>
        </div>
        <div className="hint" style={{ marginTop: 6 }}>Applied: {applied.length ? applied.join(' → ') : 'none (base scenario)'}</div>
        {lastEvent && (
          <div className="event">
            <b>{lastEvent.id}: {lastEvent.description}</b>
            {lastEvent.input_changes?.length > 0 && <ul className="list">{lastEvent.input_changes.map((c, i) => <li key={i}>{c}</li>)}</ul>}
            <div style={{ marginTop: 4 }}>
              {lastEvent.diff?.length ? `${lastEvent.diff.length} allocation(s) changed: ` : 'No allocation changed.'}
              {lastEvent.diff?.slice(0, 6).map((d, i) => (
                <span key={i} className="chip">{d.zone} {RES[d.resource].short} {d.before}→{d.after} ({d.reason_codes.map((c) => REASON[c] || c).join(', ')})</span>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="panel">
        <h3><span>Urgency weights</span><span className="hint" style={{ color: Math.abs(urgSum - 1) > 0.005 ? 'var(--warn)' : undefined }}>Σ = {urgSum.toFixed(2)}</span></h3>
        {URG.map(([k, label]) => (
          <div className="slider" key={k}>
            <label><span>{label}</span></label>
            <span className="val">{Number(urg[k]).toFixed(2)}</span>
            <input type="range" min="0" max="0.6" step="0.01" value={urg[k]} style={{ gridColumn: '1 / -1' }}
                   onChange={(e) => { const n = { ...urg, [k]: Number(e.target.value) }; setUrg(n); schedule(n, pri) }} />
          </div>
        ))}
        <div className="hint">Design assumptions, not validated coefficients. Changing a weight re-runs the solver.</div>
      </div>

      <div className="panel">
        <h3><span>Resource priority weights</span><span className="hint">Policy weights (assumptions, adjustable)</span></h3>
        {Object.keys(RES).map((r) => (
          <div className="slider" key={r}>
            <label><span>{RES[r].label}</span></label>
            <span className="val">{pri[r]}</span>
            <input type="range" min="0" max={PRI_MAX[r]} step="5" value={pri[r]} style={{ gridColumn: '1 / -1' }}
                   onChange={(e) => { const n = { ...pri, [r]: Number(e.target.value) }; setPri(n); schedule(urg, n) }} />
          </div>
        ))}
        <div className="hint">Policy weights in the objective Σ urgency × priority × people served (urgency scaled ×10 internally for integer arithmetic; ratios and percentages are unaffected). Fuel budget {scenario.fuel_budget_l} L · window {scenario.planning_window_h} h · max response {scenario.max_response_h} h.</div>
      </div>
    </>
  )
}
