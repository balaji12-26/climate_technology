# Demo runbook (5 minutes)

Start: `./run.ps1` (or `./run.sh`), open http://127.0.0.1:8000. Press **Reset scenario** first.

| Time | Action | What to say / point at |
|---|---|---|
| 0:00 | Title | Kerala 2018: 483 deaths (state count, whole monsoon season from 29 May); PDNA ₹26,718 cr damage, ₹31,000 cr recovery need; 4,537 fishermen in 669 boats rescued ≥65,000 people, coordinated ad hoc. Our prototype is decision support on a **simulated** scenario; the optimizer is real. |
| 0:45 | Base plan is already on screen | Status badge OPTIMAL + solve ms. Map: zones coloured by urgency (Z1 70.8, Z2 64.2 critical), route widths = units. Metrics panel: weighted service, critical demand served, coverage per resource, fuel 1986/2000 L → **fuel is binding** (binding-constraints list). |
| 1:30 | Inject **D1** (bridge collapse) | Z3 route 50 → 110 km (closed edge drawn red/dashed). Diff rows highlighted with reason codes (travel time ↑, capacity ↓, fuel re-allocated). Toggle **Showing BEFORE/AFTER**. Briefing tab: template text regenerated from solver JSON. |
| 2:30 | Audit tab | **Explain** Z1 medical: contribution, marginal value of last unit, binding constraints, value lost if one unit is removed and the solver re-optimizes. **Compare**: move 1 medical Z1 → Z2 → "best plan with this change scores X% lower". **What-if** "Lose 2 boats" → metric deltas + re-deployment diff. **Uniqueness** → yes/no. |
| 3:30 | Compare tab | Equal split vs severity greedy vs CP-SAT, same inputs, same `evaluate()`. Assertion shown live: optimizer ≥ both. Point out ties honestly. |
| 4:15 | Close | "Our prototype recalculates resource allocations under changing constraints and exposes the trade-offs behind each decision. We measure it against simpler strategies in a reproducible simulated scenario." |

## Fallbacks (all tested)
- No network: map tiles missing but table + metrics are the proof; rainfall panel shows **cached** data; briefing uses the template.
- No API key: briefing checkbox falls back to the template with a note.
- Solver error: greedy plan shown, badge says GREEDY FALLBACK.

## Policy choices
- Priority weights are policy assumptions, shown and adjustable in the UI. Defaults: boats 100, medical 200, supplies 10.
- **Medical = 200** means one treated patient is weighted at twice one evacuation in the objective (and twenty times one person supplied).
- Measured flip point: with D1+D2 applied and medical = 100, the fuel-bound solver idles 3 of 5 medical teams in favour of an extra boat and truck. From medical = **150** upward all 5 teams deploy and Z4 (the flooded hospital) gets one. **200 was chosen for margin**: the D1+D2 allocation is identical at 150, 200 and 300 (acceptance test 17), so the plan does not sit on a knife edge.

## If asked
- **Why does Pandanad (Z5) get nothing?** Lower urgency (44.8, below the critical line of 60) and a binding fuel budget: every litre spent on a 90 L boat trip to Z5 scores less than the same litre at Z1 or Z2. Show it live: Audit → Compare, force 1 boat to Z5, and read the objective drop and the fuel-driven re-deployment.
- **D5 (Pandanad cut off)** is not used in the live demo on purpose. Z5 already receives nothing under the default weights, so the only visible effect is indirect: Z2's route ran through Z5 (D→J3→Z5→Z2, 101 km) and is rerouted via Kottayam (105 km), which shifts one boat from Z2 to Z3. That is a weak demo moment compared with D1. D5 stays in the suite as the robustness case (zone reported unreachable, status OPTIMAL, no crash), which is acceptance test 8.
- Weights are documented policy assumptions, not validated coefficients; sliders re-run the solver live.
- Single-period static model; no per-vehicle routing; redeployment cost approximated by the anti-churn term; synthetic data; not tested on real incident data.
- Why CP-SAT and not greedy: fuel (C3) and deep-water access (C4) couple resource types, so per-resource greedy is not automatically optimal; the Compare tab measures the gap.
