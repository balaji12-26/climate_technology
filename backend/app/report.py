"""Plan response assembly (API contract) and binding-constraint detection."""
from __future__ import annotations

import hashlib
import json

from .derive import Derived
from .evaluate import Plan, evaluate, fuel_used_dl, normalize_plan, served_of, validate


def plan_id_of(plan: Plan, sc: dict) -> str:
    key = json.dumps({"plan": plan, "dis": sc.get("applied_disruptions", []),
                      "pw": sc["priority_weights"], "uw": sc["urgency_weights"]}, sort_keys=True)
    return hashlib.sha1(key.encode()).hexdigest()[:10]


def binding_constraints(plan: Plan, d: Derived) -> list[dict]:
    plan = normalize_plan(plan, d)
    y = served_of(plan, d)
    out: list[dict] = []
    for r in d.resources:
        used = sum(plan[z][r] for z in d.zones)
        if d.available[r] > 0 and used == d.available[r]:
            out.append({"type": "resource_exhausted", "resource": r,
                        "detail": f"all {used} {r.replace('_', ' ')} unit(s) assigned"})
    slack_dl = d.fuel_budget_dl - fuel_used_dl(plan, d)
    candidates = [d.fuel_dl[z][r] for z in d.zones for r in d.resources
                  if d.eligible[z][r] and y[z][r] < d.demand[z][r]
                  and sum(plan[zz][r] for zz in d.zones) < d.available[r]]
    if candidates and slack_dl < min(candidates):
        out.append({"type": "fuel_binding",
                    "detail": f"fuel slack {slack_dl / 10:.1f} L is below the cheapest useful unit "
                              f"({min(candidates) / 10:.1f} L)"})
    for z in d.zones:
        for r in d.resources:
            if plan[z][r] > 0 and y[z][r] >= d.demand[z][r]:
                out.append({"type": "demand_cap_reached", "zone": z, "resource": r,
                            "detail": f"{z} {r}: demand {d.demand[z][r]} fully served"})
        if d.deep_water[z] and "medical_team" in d.resources and plan[z]["medical_team"] > 0 \
                and plan[z]["medical_team"] == 2 * plan[z]["rescue_boat"]:
            out.append({"type": "access_coupling_tight", "zone": z,
                        "detail": f"{z}: medical teams = 2 x boats (deep water access rule)"})
    return out


def allocations_list(plan: Plan, d: Derived) -> list[dict]:
    plan = normalize_plan(plan, d)
    y = served_of(plan, d)
    rows = []
    for z in d.zones:
        for r in d.resources:
            rows.append({
                "zone": z, "zone_name": d.zone_name[z], "resource": r,
                "units": plan[z][r], "served": y[z][r], "demand": d.demand[z][r],
                "unmet": d.demand[z][r] - y[z][r],
                "capacity_per_unit": d.capacity[z][r],
                "travel_h": (round(d.travel_h[z][r], 2) if d.reachable[z] else None),
                "fuel_l_per_unit": round(d.fuel_l[z][r], 1),
                "eligible": d.eligible[z][r],
                "urgency": round(d.urgency[z], 1),
            })
    return rows


def zone_summaries(d: Derived) -> list[dict]:
    return [{
        "id": z, "name": d.zone_name[z], "urgency": round(d.urgency[z], 1),
        "reachable": d.reachable[z], "dist_km": d.dist_km.get(z), "route": d.route.get(z, []),
        "deep_water": d.deep_water[z], "critical": d.critical[z],
        "demand": d.demand[z],
    } for z in d.zones]


def build_plan_response(sc: dict, d: Derived, plan: Plan, *, status: str, solve_ms: float,
                        method: str, warnings: list[str] | None = None,
                        diff: list[dict] | None = None, churn: int | None = None) -> dict:
    plan = normalize_plan(plan, d)
    warnings = list(warnings or [])
    violations = validate(plan, sc, d)
    metrics = evaluate(plan, sc, d)
    metrics["solver_status"] = status
    metrics["solve_ms"] = round(solve_ms, 1)
    for z in d.zones:
        if d.critical[z] and sum(plan[z].values()) == 0:
            warnings.append(f"Critical zone {z} ({d.zone_name[z]}) receives no unit (soft minimum violated).")
    if violations:
        warnings.extend("CONSTRAINT VIOLATION: " + v for v in violations)
    return {
        "plan_id": plan_id_of(plan, sc),
        "method": method,
        "status": status,
        "solve_ms": round(solve_ms, 1),
        "allocations": allocations_list(plan, d),
        "plan": plan,
        "metrics": metrics,
        "binding_constraints": binding_constraints(plan, d),
        "unreachable_zones": list(d.unreachable_zones),
        "warnings": warnings,
        "valid": not violations,
        "diff": diff if diff is not None else [],
        "churn": churn,
        "zones": zone_summaries(d),
        "applied_disruptions": list(sc.get("applied_disruptions", [])),
        "weights": {"priority": dict(sc["priority_weights"]), "urgency": dict(sc["urgency_weights"])},
        "fuel_budget_l": sc["fuel_budget_l"],
    }


DELTA_KEYS = ("objective", "weighted_service_pct", "critical_demand_served_pct", "avg_response_h",
              "fuel_used_l", "total_served")


def metric_deltas(before: dict, after: dict) -> dict:
    out: dict = {}
    for k in DELTA_KEYS:
        b, a = before.get(k), after.get(k)
        if isinstance(b, (int, float)) and isinstance(a, (int, float)):
            out[k] = {"before": b, "after": a, "delta": round(a - b, 2)}
        else:
            out[k] = {"before": b, "after": a, "delta": None}
    for r, cov in after.get("coverage", {}).items():
        b = before.get("coverage", {}).get(r, {}).get("pct", 0.0)
        out[f"coverage_{r}_pct"] = {"before": b, "after": cov["pct"], "delta": round(cov["pct"] - b, 1)}
    b_obj, a_obj = before.get("objective", 0), after.get("objective", 0)
    out["objective_pct"] = round(100.0 * (a_obj - b_obj) / abs(b_obj), 2) if b_obj else None
    return out
