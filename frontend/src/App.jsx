import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from './api.js'
import MapView from './components/MapView.jsx'
import AllocationTable from './components/AllocationTable.jsx'
import MetricsPanel from './components/MetricsPanel.jsx'
import Controls from './components/Controls.jsx'
import AuditPanel from './components/AuditPanel.jsx'
import ComparePanel from './components/ComparePanel.jsx'
import BriefingPanel from './components/BriefingPanel.jsx'
import RainfallPanel from './components/RainfallPanel.jsx'

export default function App() {
  const [scenario, setScenario] = useState(null)
  const [plan, setPlan] = useState(null)        // current plan response
  const [prevPlan, setPrevPlan] = useState(null) // plan before the last disruption (before/after toggle)
  const [showBefore, setShowBefore] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [tab, setTab] = useState('audit')
  const [selected, setSelected] = useState({ zone: 'Z1', resource: 'medical_team' })
  const [lastEvent, setLastEvent] = useState(null)
  const seq = useRef(0)

  const refreshScenario = useCallback(async () => {
    const s = await api.scenario()
    if (s.status !== 'ERROR') setScenario(s)
    return s
  }, [])

  const run = useCallback(async (fn, { keepPrev = false } = {}) => {
    const my = ++seq.current
    setBusy(true); setError(null)
    const p = await fn()
    if (my !== seq.current) return p
    if (p.status === 'ERROR' && !p.allocations) {
      setError(p.error || 'request failed')
    } else {
      setPlan((old) => { if (keepPrev && old) setPrevPlan(old); return p })
      if (!keepPrev) { setPrevPlan(null); setShowBefore(false) }
    }
    await refreshScenario()
    setBusy(false)
    return p
  }, [refreshScenario])

  useEffect(() => { run(() => api.optimize({})) }, [run])

  const onOptimize = (weights) => run(() => api.optimize({ ...weights, reoptimize: false }))
  const onDisrupt = async (id) => {
    const p = await run(() => api.disrupt(id), { keepPrev: true })
    if (p && p.disruption) setLastEvent({ kind: 'disruption', ...p.disruption, diff: p.diff, input_changes: p.input_changes })
  }
  const onReset = async () => { setLastEvent(null); await run(() => api.reset()) }
  const onRainfallToggle = (enabled) => run(() => api.rainfallToggle(enabled), { keepPrev: true })

  const shown = showBefore && prevPlan ? prevPlan : plan
  const status = plan?.status || 'LOADING'

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand-title">Climate Disaster Response Optimizer</span>
          <span className="brand-sub">Decision support · SIMULATED Kerala-inspired flood scenario · CP-SAT allocation</span>
        </div>
        <div className="status-group">
          {busy && <span className="spinner" aria-label="solving" />}
          <StatusBadge status={status} method={plan?.method} ms={plan?.solve_ms} valid={plan?.valid} />
          {prevPlan && (
            <button className={`btn small ${showBefore ? 'active' : ''}`} onClick={() => setShowBefore((v) => !v)}>
              {showBefore ? 'Showing BEFORE' : 'Showing AFTER'} ⇄
            </button>
          )}
        </div>
      </header>

      {error && <div className="banner error">Backend error: {error}. Is the API running on :8000?</div>}
      {plan?.warnings?.length > 0 && (
        <div className="banner warn">{plan.warnings.map((w, i) => <div key={i}>⚠ {w}</div>)}</div>
      )}

      <div className="layout">
        <aside className="left">
          <Controls scenario={scenario} plan={plan} busy={busy}
                    onOptimize={onOptimize} onDisrupt={onDisrupt} onReset={onReset} lastEvent={lastEvent} />
          <RainfallPanel scenario={scenario} onToggle={onRainfallToggle} busy={busy} />
        </aside>

        <main className="center">
          <MapView scenario={scenario} plan={shown} selected={selected} onSelectZone={(z) => setSelected((s) => ({ ...s, zone: z }))} />
          <AllocationTable plan={shown} diff={showBefore ? [] : plan?.diff} selected={selected} onSelect={setSelected} />
        </main>

        <aside className="right">
          <MetricsPanel plan={shown} />
          <nav className="tabs">
            {['audit', 'compare', 'briefing'].map((t) => (
              <button key={t} className={`tab ${tab === t ? 'active' : ''}`} onClick={() => setTab(t)}>{t}</button>
            ))}
          </nav>
          {tab === 'audit' && <AuditPanel plan={plan} scenario={scenario} selected={selected} setSelected={setSelected} />}
          {tab === 'compare' && <ComparePanel planId={plan?.plan_id} />}
          {tab === 'briefing' && <BriefingPanel planId={plan?.plan_id} />}
        </aside>
      </div>

      <footer className="foot">
        All zone figures are synthetic ("Kerala-inspired"). Every number shown is computed live by evaluate() on solver output.
        Weights are documented policy assumptions, not validated coefficients. Single-period static model; no per-vehicle routing.
      </footer>
    </div>
  )
}

function StatusBadge({ status, method, ms, valid }) {
  const cls = { OPTIMAL: 'ok', FEASIBLE: 'warn', INFEASIBLE: 'bad', ERROR: 'bad', UNKNOWN: 'warn', LOADING: 'muted' }[status] || 'muted'
  return (
    <div className={`badge ${cls}`} title={method ? `method: ${method}` : ''}>
      <span className="dot" />
      {status}{ms !== undefined && ms !== null ? ` · ${ms} ms` : ''}
      {method === 'greedy_fallback' && ' · GREEDY FALLBACK'}
      {valid === false && ' · INVALID'}
    </div>
  )
}
