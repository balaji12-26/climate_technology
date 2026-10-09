"""Layer 2 - CP-SAT allocation model (Google OR-Tools).

Deterministic: num_workers = 1, random_seed = 42, max_time_in_seconds = 3.
Never crashes on any solver status; every result carries `status`.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from ortools.sat.python import cp_model

from .derive import Derived, derive
from .evaluate import Plan, empty_plan, normalize_plan, service_objective

STATUS_NAME = {
    cp_model.OPTIMAL: "OPTIMAL",
    cp_model.FEASIBLE: "FEASIBLE",
    cp_model.INFEASIBLE: "INFEASIBLE",
    cp_model.MODEL_INVALID: "ERROR",
    cp_model.UNKNOWN: "UNKNOWN",
}

TIME_LIMIT_S = 3.0
RANDOM_SEED = 42
NUM_WORKERS = 1


@dataclass
class SolveResult:
    status: str
    solve_ms: float
    plan: Plan
    solver_objective: int | None       # objective as seen by CP-SAT (may include anti-churn term)
    service_objective: int | None      # the stated objective (evaluate() definition)
    warnings: list[str] = field(default_factory=list)
    churn: int | None = None           # sum |x - x_prev| if a previous plan was given


def solve(sc: dict, d: Derived | None = None, *,
          prev_plan: Plan | None = None, lam: int = 0,
          hint: Plan | None = None,
          bounds: dict[tuple[str, str], tuple[int, int]] | None = None,
          forbid_plan: Plan | None = None,
          min_service_objective: int | None = None,
          time_limit_s: float = TIME_LIMIT_S) -> SolveResult:
    """Build and solve the CP-SAT model.

    prev_plan + lam   : anti-churn term  - lam x sum|x - x_prev|  (re-optimization)
    hint              : solution hint (e.g. the greedy plan)
    bounds            : {(z, r): (lo, hi)} forced bounds on x (audit: explain/compare/remove_zone)
    forbid_plan       : require sum|x - forbid_plan| >= 1 (uniqueness check)
    min_service_objective : require stated objective >= value (uniqueness check)
    """
    d = d or derive(sc)
    t0 = time.perf_counter()
    try:
        m = cp_model.CpModel()
        x: dict[tuple[str, str], cp_model.IntVar] = {}
        y: dict[tuple[str, str], cp_model.IntVar] = {}
        s: dict[str, cp_model.IntVar] = {}
        for z in d.zones:
            for r in d.resources:
                hi_elig = d.available[r] if d.eligible[z][r] else 0
                x[(z, r)] = m.NewIntVar(0, hi_elig, f"x_{z}_{r}")
                if bounds and (z, r) in bounds:
                    blo, bhi = bounds[(z, r)]
                    m.Add(x[(z, r)] >= int(blo))   # contradictory bounds -> INFEASIBLE (reported, never crashes)
                    m.Add(x[(z, r)] <= int(bhi))
                y[(z, r)] = m.NewIntVar(0, d.demand[z][r] if d.eligible[z][r] else 0, f"y_{z}_{r}")
                m.Add(y[(z, r)] <= d.capacity[z][r] * x[(z, r)])                     # C2
            s[z] = m.NewBoolVar(f"s_{z}")
            if d.critical[z]:                                                     # C5 soft minimum
                m.Add(sum(x[(z, r)] for r in d.resources) + s[z] >= 1)
            else:
                m.Add(s[z] == 0)
            if d.deep_water[z] and "medical_team" in d.resources and "rescue_boat" in d.resources:
                m.Add(x[(z, "medical_team")] <= 2 * x[(z, "rescue_boat")])          # C4 access
        for r in d.resources:                                                     # C1 capacity
            m.Add(sum(x[(z, r)] for z in d.zones) <= d.available[r])
        m.Add(sum(d.fuel_dl[z][r] * x[(z, r)] for z in d.zones for r in d.resources) <= d.fuel_budget_dl)  # C3

        service = sum(d.coef(z, r) * y[(z, r)] for z in d.zones for r in d.resources) \
            - d.slack_penalty * sum(s[z] for z in d.zones)
        objective = service

        churn_terms = []
        if prev_plan is not None and lam > 0:
            prev = normalize_plan(prev_plan, d)
            for z in d.zones:
                for r in d.resources:
                    dev = m.NewIntVar(0, max(d.available[r], prev[z][r]), f"dev_{z}_{r}")
                    m.Add(dev >= x[(z, r)] - prev[z][r])
                    m.Add(dev >= prev[z][r] - x[(z, r)])
                    churn_terms.append(dev)
            objective = service - lam * sum(churn_terms)

        if forbid_plan is not None:
            fp = normalize_plan(forbid_plan, d)
            devs = []
            for z in d.zones:
                for r in d.resources:
                    dev = m.NewIntVar(0, max(d.available[r], fp[z][r]), f"fdev_{z}_{r}")
                    m.Add(dev >= x[(z, r)] - fp[z][r])
                    m.Add(dev >= fp[z][r] - x[(z, r)])
                    devs.append(dev)
            m.Add(sum(devs) >= 1)
        if min_service_objective is not None:
            m.Add(service >= int(min_service_objective))

        m.Maximize(objective)

        if hint is not None:
            h = normalize_plan(hint, d)
            for z in d.zones:
                for r in d.resources:
                    if (z, r) in x:
                        m.AddHint(x[(z, r)], min(h[z][r], d.available[r]) if d.eligible[z][r] else 0)

        solver = cp_model.CpSolver()
        solver.parameters.num_workers = NUM_WORKERS
        solver.parameters.random_seed = RANDOM_SEED
        solver.parameters.max_time_in_seconds = time_limit_s
        status_code = solver.Solve(m)
        status = STATUS_NAME.get(status_code, "UNKNOWN")
        ms = (time.perf_counter() - t0) * 1000.0

        if status in ("OPTIMAL", "FEASIBLE"):
            plan = {z: {r: int(solver.Value(x[(z, r)])) for r in d.resources} for z in d.zones}
            churn = sum(int(solver.Value(v)) for v in churn_terms) if churn_terms else None
            warnings = []
            if status == "FEASIBLE":
                warnings.append("Solver hit the 3 s time limit; plan is best-so-far, not proven optimal.")
            return SolveResult(status, ms, plan, int(round(solver.ObjectiveValue())),
                               service_objective(plan, d), warnings, churn)
        return SolveResult(status, ms, empty_plan(d), None, None,
                           [f"Solver returned {status}; no plan available from this model."])
    except Exception as exc:  # never crash
        ms = (time.perf_counter() - t0) * 1000.0
        return SolveResult("ERROR", ms, empty_plan(d), None, None, [f"Solver error: {exc!r}"])
