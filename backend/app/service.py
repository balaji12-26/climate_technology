"""Orchestration: scenario -> derived -> hint -> CP-SAT -> plan response.

Also holds the in-memory session state used by the API (base scenario,
applied disruptions, weight overrides, last plan).
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field

from .baselines import equal_split, severity_greedy
from .derive import Derived, derive
from .diff import diff_plans
from .evaluate import Plan
from .model import SolveResult, solve
from .report import build_plan_response
from .scenario import apply_disruptions, load_base_scenario, with_weights

LAMBDA_ANTI_CHURN = 1


def optimize(sc: dict, d: Derived | None = None, *, prev_plan: Plan | None = None,
             lam: int = 0, prev_derived: Derived | None = None, time_limit_s: float = 3.0) -> dict:
    """Solve and return the API plan response. Falls back to the greedy plan
    (clearly labelled) if the solver errors or returns no plan."""
    d = d or derive(sc)
    hint = severity_greedy(d)
    res: SolveResult = solve(sc, d, prev_plan=prev_plan, lam=lam, hint=hint, time_limit_s=time_limit_s)
    method = "cp_sat"
    warnings = list(res.warnings)
    plan = res.plan
    if res.status not in ("OPTIMAL", "FEASIBLE"):
        method = "greedy_fallback"
        plan = hint
        warnings.append("Showing the severity-greedy plan because the solver returned no plan.")
    diff = None
    if prev_plan is not None:
        diff = diff_plans(prev_plan, plan, prev_derived or d, d)
    resp = build_plan_response(sc, d, plan, status=res.status, solve_ms=res.solve_ms, method=method,
                               warnings=warnings, diff=diff, churn=res.churn)
    resp["solver_objective"] = res.solver_objective
    resp["hint_objective"] = None
    return resp


def baseline_plans(sc: dict, d: Derived | None = None) -> dict[str, dict]:
    d = d or derive(sc)
    out = {}
    for name, fn in (("equal_split", equal_split), ("severity_greedy", severity_greedy)):
        plan = fn(d)
        out[name] = build_plan_response(sc, d, plan, status="HEURISTIC", solve_ms=0.0, method=name)
    return out


@dataclass
class SessionState:
    base: dict = field(default_factory=load_base_scenario)
    applied: list[str] = field(default_factory=list)
    priority_weights: dict = field(default_factory=dict)
    urgency_weights: dict = field(default_factory=dict)
    last_plan: dict | None = None          # last plan response
    last_derived: Derived | None = None
    live_rainfall: bool = False
    rainfall_depth_add: dict = field(default_factory=dict)   # zone -> metres added when live adjustment is on

    def scenario(self) -> dict:
        sc = apply_disruptions(self.base, self.applied)
        sc = with_weights(sc, self.priority_weights or None, self.urgency_weights or None)
        if self.live_rainfall and self.rainfall_depth_add:
            for z in sc["zones"]:
                z["flood_depth_m"] = round(z["flood_depth_m"] + self.rainfall_depth_add.get(z["id"], 0.0), 2)
            sc["live_rainfall_adjustment"] = copy.deepcopy(self.rainfall_depth_add)
        return sc

    def reset(self) -> None:
        self.applied = []
        self.priority_weights = {}
        self.urgency_weights = {}
        self.last_plan = None
        self.last_derived = None
        self.live_rainfall = False

    def run_optimize(self, reoptimize: bool = False) -> dict:
        sc = self.scenario()
        d = derive(sc)
        if reoptimize and self.last_plan is not None:
            resp = optimize(sc, d, prev_plan=self.last_plan["plan"], lam=LAMBDA_ANTI_CHURN,
                            prev_derived=self.last_derived)
        else:
            resp = optimize(sc, d)
        self.last_plan = resp
        self.last_derived = d
        return resp
