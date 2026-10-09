import { useEffect, useState } from 'react'
import { api, RES, fmt, fmtInt } from '../api.js'

const NAMES = { equal_split: 'Equal split', severity_greedy: 'Severity greedy', cp_sat: 'CP-SAT optimizer' }
const ORDER = ['equal_split', 'severity_greedy', 'cp_sat']

export default function ComparePanel({ planId }) {
  const [data, setData] = useState(null)
  useEffect(() => { let on = true; api.compare().then((d) => on && setData(d)); return () => { on = false } }, [planId])
  if (!data) return <div className="panel" style={{ borderTopLeftRadius: 0 }}>Measuring baselines…</div>
  if (data.status === 'ERROR') return <div className="panel">{data.error}</div>
  const m = data.metrics
  const best = (key, dir = 1, sub) => {
    const vals = ORDER.map((n) => (sub ? m[n][key][sub].pct : m[n][key]))
    const b = dir > 0 ? Math.max(...vals.filter((v) => v !== null)) : Math.min(...vals.filter((v) => v !== null))
    return (n) => { const v = sub ? m[n][key][sub].pct : m[n][key]; return v === b ? 'best' : '' }
  }
  const rows = [
    ['Objective', (n) => fmtInt(m[n].objective), best('objective')],
    ['Gap to optimizer', (n) => `${fmt(data.objective_gap_pct[n], 2)}%`, () => ''],
    ['Weighted service %', (n) => fmt(m[n].weighted_service_pct), best('weighted_service_pct')],
    ['Critical demand served %', (n) => fmt(m[n].critical_demand_served_pct), best('critical_demand_served_pct')],
    ...Object.keys(RES).map((r) => [`${RES[r].served} %`, (n) => fmt(m[n].coverage[r].pct), best('coverage', 1, r)]),
    ['People served', (n) => fmtInt(m[n].total_served), best('total_served')],
    ['Avg response h', (n) => fmt(m[n].avg_response_h, 2), best('avg_response_h', -1)],
    ['Fuel used L', (n) => fmt(m[n].fuel_used_l, 0), () => ''],
    ['Zones with zero service', (n) => m[n].zones_zero_service.length, () => ''],
    ['Valid (validate())', (n) => (data.plans[n].valid ? 'yes' : 'NO'), () => ''],
  ]
  return (
    <div className="panel" style={{ borderTopLeftRadius: 0 }}>
      <h3><span>Three methods, identical inputs & constraints</span><span className="hint">scored by the same evaluate()</span></h3>
      <table className="cmp-table">
        <thead><tr><th className="l">Metric</th>{ORDER.map((n) => <th key={n}>{NAMES[n]}</th>)}</tr></thead>
        <tbody>
          {rows.map(([label, f, cls]) => (
            <tr key={label}><td className="l">{label}</td>{ORDER.map((n) => <td key={n} className={cls ? cls(n) : ''}>{f(n)}</td>)}</tr>
          ))}
        </tbody>
      </table>
      <div className="hint" style={{ marginTop: 6 }}>
        Assertion checked live: optimizer objective ≥ both baselines → <b style={{ color: data.optimizer_dominates ? 'var(--ok)' : 'var(--bad)' }}>{data.optimizer_dominates ? 'holds' : 'VIOLATED'}</b>.
        Ties on individual metrics are shown as they are; the optimizer maximizes the stated objective, not every metric.
      </div>
    </div>
  )
}
