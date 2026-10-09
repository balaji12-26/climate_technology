// Thin fetch wrapper for the frozen API contract. Every call returns parsed JSON;
// HTTP errors are surfaced as {status: "ERROR", error}.
async function call(method, path, body) {
  try {
    const res = await fetch(path, {
      method,
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    })
    const data = await res.json().catch(() => ({}))
    if (!res.ok && !data.status) return { status: 'ERROR', error: `HTTP ${res.status}` }
    return data
  } catch (e) {
    return { status: 'ERROR', error: String(e) }
  }
}

export const api = {
  scenario: () => call('GET', '/api/scenario'),
  optimize: (body = {}) => call('POST', '/api/optimize', body),
  disrupt: (id) => call('POST', '/api/disrupt', { id }),
  reset: () => call('POST', '/api/reset'),
  compare: () => call('GET', '/api/compare'),
  explain: (zone, resource) => call('POST', '/api/explain', { zone, resource }),
  counterfactual: (body) => call('POST', '/api/counterfactual', body),
  uniqueness: () => call('GET', '/api/uniqueness'),
  rainfall: (live = true) => call('GET', `/api/rainfall?live=${live}`),
  rainfallToggle: (enabled) => call('POST', '/api/rainfall/toggle', { enabled }),
  briefing: (use_llm = false) => call('POST', '/api/briefing', { use_llm }),
}

export const RES = {
  rescue_boat: { label: 'Rescue boats', short: 'Boats', served: 'evacuated', demand: 'stranded' },
  medical_team: { label: 'Medical teams', short: 'Medical', served: 'treated', demand: 'patients' },
  supply_truck: { label: 'Supply trucks', short: 'Trucks', served: 'supplied', demand: 'displaced' },
}
export const RESOURCES = Object.keys(RES)

export const REASON = {
  travel_time_increased: 'travel time ↑',
  demand_changed: 'demand changed',
  urgency_changed: 'urgency changed',
  capacity_reduced: 'capacity ↓',
  resource_lost: 'resource lost',
  fuel_reallocated: 'fuel re-allocated',
  zone_unreachable: 'unreachable',
}

export function urgencyColor(u) {
  // 0 -> green, 50 -> amber, 100 -> red
  const t = Math.max(0, Math.min(100, u)) / 100
  const h = (1 - t) * 120
  return `hsl(${h.toFixed(0)} 85% 48%)`
}

export const fmt = (v, d = 1) => (v === null || v === undefined ? '—' : Number(v).toFixed(d))
export const fmtInt = (v) => (v === null || v === undefined ? '—' : Number(v).toLocaleString())
