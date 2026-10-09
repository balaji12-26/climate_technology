# Climate Disaster Response Optimizer

Decision support on a **simulated**, Kerala-inspired flood scenario. The scenario is synthetic;
the optimizer is real: Google OR-Tools **CP-SAT** allocates rescue boats, medical teams and supply
trucks to flooded zones under fuel, access and resource constraints, re-optimizes under injected
disruptions, and exposes the trade-offs behind each decision (explain / compare / what-if /
uniqueness). Two baselines (equal split, severity greedy) are scored by the **same** `evaluate()`.

## Run

```bash
# backend (Python 3.11+; venv already created at .venv)
.venv/Scripts/python -m pip install -r backend/requirements.txt
.venv/Scripts/python -m uvicorn app.main:app --app-dir backend --port 8000
```

```bash
# frontend (dev server with API proxy)  — or just open http://127.0.0.1:8000 after `npm run build`
cd frontend && npm install && npm run dev
```

The backend serves `frontend/dist` at `/` when it exists, so after `npm run build` the whole demo
is one process on http://127.0.0.1:8000.

Optional: set `ANTHROPIC_API_KEY` to enable Claude formatting of the briefing. Without it (or
offline) the deterministic template is used. The LLM only formats verified solver JSON; its output
is rejected if it contains any number not present in that JSON.

## Tests

```bash
cd backend && ../.venv/Scripts/python -m pytest
```

33 tests: the 15 acceptance tests from the frozen master prompt plus API-contract tests.

## Layout

| Path | What |
|---|---|
| `backend/data/scenario.json` | Synthetic scenario (zones, road graph, resources, weights, disruptions) |
| `backend/app/scenario.py` | Loader, cumulative disruption application |
| `backend/app/routing.py` | Explicit road graph + Dijkstra; closed roads are removed |
| `backend/app/derive.py` | Urgency (Layer 1), demand/capacity/fuel/eligibility (1b), routing (1c) |
| `backend/app/model.py` | CP-SAT model (Layer 2): C1–C5, anti-churn, forced bounds, uniqueness |
| `backend/app/evaluate.py` | THE `evaluate()` and `validate()` used for every plan |
| `backend/app/baselines.py` | Equal split and severity greedy |
| `backend/app/diff.py` | Plan diff with deterministic reason codes (Layer 3) |
| `backend/app/audit.py` | Explain / compare / what-if / uniqueness (Layer 4) |
| `backend/app/briefing.py` | Template briefing + optional Claude formatting with number guard (Layer 5) |
| `backend/app/rainfall.py` | Open-Meteo last-24h rainfall with cached fallback (Layer 5) |
| `backend/app/main.py` | FastAPI – the frozen API contract |
| `frontend/` | React + Vite + Leaflet UI |

## Model summary

- `urgency(z) = 100 × (0.25·depth_norm + 0.20·infra + 0.25·medical + 0.15·access + 0.15·vulnerable)`,
  per person, population enters only through demand counts.
- Per-unit capacities and fuel from travel time (boats towed by road, trucks do round trips).
- CP-SAT maximizes `Σ urgency·priority·served − P·Σ slack − λ·Σ|x − x_prev|` subject to
  resource counts, fuel budget (2000 L), deep-water access coupling (medical ≤ 2 × boats when
  depth ≥ 2.5 m) and a soft minimum for critical zones. Deterministic: 1 worker, seed 42, 3 s cap.
- All coefficients are integers (urgency ×10, fuel in deciliters).

## Known limitations

Single-period static model; no per-vehicle routing or scheduling; units already in transit are
approximated by a redeployment penalty; synthetic scenario data; weights are policy assumptions
not validated with responders; not tested on real incident data.
