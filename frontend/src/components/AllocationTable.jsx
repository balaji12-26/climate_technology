import { RES, RESOURCES, REASON, urgencyColor, fmt, fmtInt } from '../api.js'

export default function AllocationTable({ plan, diff, selected, onSelect }) {
  if (!plan) return <div className="panel">Loading plan…</div>
  const diffMap = {}
  ;(diff || []).forEach((d) => { diffMap[`${d.zone}|${d.resource}`] = d })
  const byZone = {}
  plan.allocations.forEach((a) => { (byZone[a.zone] ||= []).push(a) })
  const zones = plan.zones

  return (
    <div className="panel">
      <h3>
        <span>Allocation plan {plan.method === 'greedy_fallback' ? '(GREEDY FALLBACK)' : ''}</span>
        <span className="hint">{(diff || []).length ? `${diff.length} change(s) vs previous plan` : 'click a row to audit it'}</span>
      </h3>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th className="l">Zone / resource</th><th>Units</th><th>Δ</th><th>Served</th><th>Demand</th><th>Unmet</th><th>Cap/unit</th><th>Travel h</th><th>Fuel/unit L</th><th className="l">Reason</th>
            </tr>
          </thead>
          <tbody>
            {zones.map((z) => (
              <ZoneRows key={z.id} z={z} rows={byZone[z.id] || []} diffMap={diffMap} selected={selected} onSelect={onSelect} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function ZoneRows({ z, rows, diffMap, selected, onSelect }) {
  return (
    <>
      <tr className="zone-head">
        <td colSpan={10}>
          <span className="urg" style={{ background: z.reachable ? urgencyColor(z.urgency) : '#5b6673' }}>{fmt(z.urgency, 1)}</span>
          &nbsp;{z.id} {z.name}
          {z.critical && <span className="chip crit">critical</span>}
          {z.deep_water && <span className="chip deep">deep water</span>}
          {!z.reachable && <span className="chip crit">UNREACHABLE</span>}
          {z.reachable && <span className="chip">{fmt(z.dist_km, 0)} km via {z.route.join('→')}</span>}
        </td>
      </tr>
      {RESOURCES.map((r) => {
        const a = rows.find((x) => x.resource === r)
        if (!a) return null
        const d = diffMap[`${z.id}|${r}`]
        const cls = [
          d ? (d.delta > 0 ? 'diff-up' : 'diff-down') : '',
          selected?.zone === z.id && selected?.resource === r ? 'sel' : '',
          a.eligible ? '' : 'ineligible',
          'clickable',
        ].join(' ')
        return (
          <tr key={r} className={cls} onClick={() => onSelect({ zone: z.id, resource: r })}>
            <td className="l">&nbsp;&nbsp;{RES[r].label}</td>
            <td><b>{a.units}</b>{d && <span className="hint"> (was {d.before})</span>}</td>
            <td>{d ? <span className={`delta ${d.delta > 0 ? 'up' : 'down'}`}>{d.delta > 0 ? '+' : ''}{d.delta}</span> : ''}</td>
            <td>{fmtInt(a.served)}</td>
            <td>{fmtInt(a.demand)}</td>
            <td style={{ color: a.unmet > 0 ? 'var(--warn)' : 'var(--ok)' }}>{fmtInt(a.unmet)}</td>
            <td>{a.eligible ? fmtInt(a.capacity_per_unit) : <span className="hint">ineligible</span>}</td>
            <td>{fmt(a.travel_h, 2)}</td>
            <td>{fmt(a.fuel_l_per_unit, 1)}</td>
            <td className="l">{d ? d.reason_codes.map((c) => <span key={c} className="chip">{REASON[c] || c}</span>) : ''}</td>
          </tr>
        )
      })}
    </>
  )
}
