import { useState } from 'react'
import { api, RES, RESOURCES, REASON, fmt, fmtInt } from '../api.js'

const WHATIFS = [
  { label: 'Lose 2 boats', effect: { resource: 'rescue_boat', count_add: -2 } },
  { label: 'Lose 1 medical team', effect: { resource: 'medical_team', count_add: -1 } },
  { label: 'Fuel −30%', effect: { fuel_budget_multiplier: 0.7 } },
  { label: 'Fuel +30%', effect: { fuel_budget_multiplier: 1.3 } },
  { label: 'Supplies priority ×5', effect: { priority_weights: { supply_truck: 50 } } },
  { label: 'Z5 patients +100', effect: { zone: 'Z5', patients_add: 100 } },
]

export default function AuditPanel({ plan, scenario, selected, setSelected }) {
  const [explain, setExplain] = useState(null)
  const [cf, setCf] = useState(null)
  const [uniq, setUniq] = useState(null)
  const [busy, setBusy] = useState(false)
  const [move, setMove] = useState({ resource: 'medical_team', from_zone: 'Z1', to_zone: 'Z2', units: 1 })
  const zones = scenario?.zones || []

  const wrap = async (fn) => { setBusy(true); const r = await fn(); setBusy(false); return r }
  const doExplain = () => wrap(async () => setExplain(await api.explain(selected.zone, selected.resource)))
  const doMove = () => wrap(async () => setCf(await api.counterfactual({ type: 'force_move', ...move })))
  const doWhatIf = (effect) => wrap(async () => setCf(await api.counterfactual({ type: 'param_change', effect })))
  const doRemove = () => wrap(async () => setCf(await api.counterfactual({ type: 'remove_zone', zone: selected.zone })))
  const doUniq = () => wrap(async () => setUniq(await api.uniqueness()))

  if (!plan) return null
  return (
    <div className="panel" style={{ borderTopLeftRadius: 0 }}>
      <h3>Explain (z, r)</h3>
      <div className="row">
        <select value={selected.zone} onChange={(e) => setSelected({ ...selected, zone: e.target.value })}>
          {zones.map((z) => <option key={z.id} value={z.id}>{z.id} {z.name}</option>)}
        </select>
        <select value={selected.resource} onChange={(e) => setSelected({ ...selected, resource: e.target.value })}>
          {RESOURCES.map((r) => <option key={r} value={r}>{RES[r].label}</option>)}
        </select>
        <button className="btn" disabled={busy} onClick={doExplain}>Explain</button>
      </div>
      {explain && explain.status === 'OK' && <ExplainResult e={explain} />}
      {explain && explain.status !== 'OK' && <div className="result">{explain.error}</div>}

      <h3 style={{ marginTop: 12 }}>Compare: forced alternative</h3>
      <div className="row">
        <span className="hint">move</span>
        <input type="number" min="1" max="30" value={move.units} style={{ width: 52 }} onChange={(e) => setMove({ ...move, units: Number(e.target.value) })} />
        <select value={move.resource} onChange={(e) => setMove({ ...move, resource: e.target.value })}>
          {RESOURCES.map((r) => <option key={r} value={r}>{RES[r].short}</option>)}
        </select>
        <select value={move.from_zone} onChange={(e) => setMove({ ...move, from_zone: e.target.value })}>
          {zones.map((z) => <option key={z.id} value={z.id}>{z.id}</option>)}
        </select>
        <span className="hint">→</span>
        <select value={move.to_zone} onChange={(e) => setMove({ ...move, to_zone: e.target.value })}>
          {zones.map((z) => <option key={z.id} value={z.id}>{z.id}</option>)}
        </select>
        <button className="btn" disabled={busy} onClick={doMove}>Re-solve</button>
      </div>

      <h3 style={{ marginTop: 12 }}>What-if</h3>
      <div className="row">
        {WHATIFS.map((w) => <button key={w.label} className="btn small" disabled={busy} onClick={() => doWhatIf(w.effect)}>{w.label}</button>)}
        <button className="btn small" disabled={busy} onClick={doRemove}>Drop {selected.zone} entirely</button>
      </div>
      {cf && <CfResult cf={cf} />}

      <h3 style={{ marginTop: 12 }}><span>Uniqueness</span><button className="btn small" disabled={busy} onClick={doUniq}>Check</button></h3>
      {uniq && (
        <div className="result">
          <div className="msg">Alternative optimal plans exist: <span style={{ color: uniq.answer === 'yes' ? 'var(--warn)' : 'var(--ok)' }}>{uniq.answer.toUpperCase()}</span></div>
          <div className="hint">{uniq.note}</div>
          {uniq.diff?.length > 0 && <DiffList diff={uniq.diff} label="one alternative differs by" />}
        </div>
      )}
    </div>
  )
}

function ExplainResult({ e }) {
  const r = e.remove_one_and_reoptimize
  return (
    <div className="result">
      <div className="msg">{e.zone} {e.zone_name} · {RES[e.resource].label}</div>
      <div className="kv">
        <span className="k">units / served / unmet</span><span className="v">{e.units} / {fmtInt(e.served)} / {fmtInt(e.unmet)} (demand {fmtInt(e.demand)})</span>
        <span className="k">capacity per unit</span><span className="v">{fmtInt(e.capacity_per_unit)} people · travel {fmt(e.travel_h, 2)} h · fuel {fmt(e.fuel_l_per_unit)} L</span>
        <span className="k">objective coefficient</span><span className="v">urgency {e.urgency} × priority {e.priority} × 10 (integer scaling) = {fmtInt(e.objective_coefficient_per_person)} / person</span>
        <span className="k">contribution</span><span className="v">{fmtInt(e.objective_contribution)} ({fmt(e.objective_contribution_pct)}% of objective)</span>
        <span className="k">marginal value of last unit</span><span className="v">{fmtInt(e.marginal_value_last_unit)}</span>
        {r && r.status && r.value_lost !== undefined && (
          <>
            <span className="k">remove 1 unit + re-optimize</span>
            <span className="v">objective −{fmtInt(r.value_lost)} ({fmt(r.value_lost_pct, 2)}%), solver {r.status}</span>
          </>
        )}
      </div>
      <div style={{ marginTop: 6 }}>
        <span className="k hint">binding: </span>
        {e.binding_constraints.length === 0 ? <span className="hint">none</span> : e.binding_constraints.map((b, i) => <span key={i} className="chip" title={b.detail}>{b.type}</span>)}
      </div>
      {r?.diff?.length > 0 && <DiffList diff={r.diff} label="the solver would then re-deploy" />}
    </div>
  )
}

function CfResult({ cf }) {
  if (cf.status === 'ERROR') return <div className="result"><div className="msg" style={{ color: 'var(--bad)' }}>{cf.message || cf.error}</div></div>
  if (cf.status === 'INFEASIBLE') return <div className="result"><div className="msg" style={{ color: 'var(--bad)' }}>{cf.message}</div></div>
  const md = cf.metric_deltas || {}
  const row = (k, label, d = 1, unit = '') => md[k] && (
    <>
      <span className="k">{label}</span>
      <span className="v">{fmt(md[k].before, d)}{unit} → {fmt(md[k].after, d)}{unit} <span className={`delta ${md[k].delta >= 0 ? 'up' : 'down'}`}>({md[k].delta >= 0 ? '+' : ''}{fmt(md[k].delta, d)})</span></span>
    </>
  )
  return (
    <div className="result">
      <div className="msg" style={{ color: cf.objective_delta < 0 ? 'var(--bad)' : cf.objective_delta > 0 ? 'var(--ok)' : undefined }}>{cf.message}</div>
      {cf.input_changes?.length > 0 && <div className="hint">{cf.input_changes.join(' · ')}</div>}
      <div className="kv">
        <span className="k">objective</span><span className="v">{fmtInt(cf.base_objective)} → {fmtInt(cf.objective)} ({fmt(cf.objective_delta_pct, 2)}%)</span>
        {row('weighted_service_pct', 'weighted service', 1, '%')}
        {row('critical_demand_served_pct', 'critical served', 1, '%')}
        {row('coverage_rescue_boat_pct', 'evacuated', 1, '%')}
        {row('coverage_medical_team_pct', 'treated', 1, '%')}
        {row('coverage_supply_truck_pct', 'supplied', 1, '%')}
        {row('avg_response_h', 'avg response', 2, ' h')}
        {row('fuel_used_l', 'fuel used', 0, ' L')}
      </div>
      {cf.diff?.length > 0 ? <DiffList diff={cf.diff} label="re-solved plan differs by" /> : <div className="hint" style={{ marginTop: 4 }}>Plan unchanged.</div>}
    </div>
  )
}

function DiffList({ diff, label }) {
  return (
    <div style={{ marginTop: 6 }}>
      <div className="hint">{label}:</div>
      {diff.map((d, i) => (
        <span key={i} className="chip">{d.zone} {RES[d.resource].short} {d.before}→{d.after}{d.reason_codes ? ` (${d.reason_codes.map((c) => REASON[c] || c).join(', ')})` : ''}</span>
      ))}
    </div>
  )
}
