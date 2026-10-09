import { RES, fmt, fmtInt } from '../api.js'

export default function MetricsPanel({ plan }) {
  if (!plan) return <div className="panel">Loading metrics…</div>
  const m = plan.metrics
  const fuelFull = m.fuel_pct >= 99
  return (
    <div className="panel">
      <h3><span>Metrics (live from evaluate())</span><span className="hint">plan {plan.plan_id}</span></h3>
      <div className="metrics">
        <Metric k="Weighted service" v={`${fmt(m.weighted_service_pct)}%`} s="Σ u·p·y / Σ u·p·demand" pct={m.weighted_service_pct} />
        <Metric k="Critical demand served" v={`${fmt(m.critical_demand_served_pct)}%`} s="zones with urgency ≥ 60" pct={m.critical_demand_served_pct} />
        {Object.entries(m.coverage).map(([r, c]) => (
          <Metric key={r} k={`${RES[r].served[0].toUpperCase() + RES[r].served.slice(1)}`} v={`${fmt(c.pct)}%`}
                  s={`${fmtInt(c.served)} / ${fmtInt(c.demand)} ${RES[r].demand}`} pct={c.pct} />
        ))}
        <Metric k="Avg response time" v={m.avg_response_h === null ? '—' : `${fmt(m.avg_response_h, 2)} h`} s="service-weighted travel time" />
        <Metric k="Fuel used" v={`${fmt(m.fuel_used_l, 0)} L`} s={`of ${fmt(m.fuel_budget_l, 0)} L (${fmt(m.fuel_pct)}%)`} pct={m.fuel_pct} full={fuelFull} />
        <Metric k="People served" v={fmtInt(m.total_served)} s={`units: ${Object.entries(m.units_used).map(([r, u]) => `${u}/${m.units_available[r]} ${RES[r].short.toLowerCase()}`).join(' · ')}`} />
      </div>
      <h4>Binding constraints</h4>
      {plan.binding_constraints.length === 0 ? <div className="hint">none detected</div> : (
        <ul className="list">{plan.binding_constraints.map((b, i) => <li key={i}><b>{b.type}</b>: {b.detail}</li>)}</ul>
      )}
      {(m.zones_zero_service.length > 0 || plan.unreachable_zones.length > 0) && (
        <div className="hint" style={{ marginTop: 6 }}>
          {m.zones_zero_service.length > 0 && <div>Zones with zero service: {m.zones_zero_service.join(', ')}</div>}
          {plan.unreachable_zones.length > 0 && <div style={{ color: 'var(--bad)' }}>Unreachable: {plan.unreachable_zones.join(', ')}</div>}
        </div>
      )}
      <div className="hint" style={{ marginTop: 6 }}>Objective (×10 integer scaling): <span style={{ fontFamily: 'var(--mono)' }}>{fmtInt(m.objective)}</span> · solver {m.solver_status} in {m.solve_ms} ms{plan.churn !== null && plan.churn !== undefined ? ` · churn ${plan.churn} unit-moves` : ''}</div>
    </div>
  )
}

function Metric({ k, v, s, pct, full }) {
  return (
    <div className="metric">
      <div className="k">{k}</div>
      <div className="v">{v}</div>
      {s && <div className="s">{s}</div>}
      {pct !== undefined && <div className={`bar ${full ? 'full' : ''}`}><i style={{ width: `${Math.min(100, pct)}%` }} /></div>}
    </div>
  )
}
