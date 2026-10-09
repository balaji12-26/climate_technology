"""Layer 4 - audit functions: EXPLAIN, COMPARE (forced alternative), WHAT-IF,
UNIQUENESS. These are re-solves with extra constraints, reported honestly.
They are not proofs; they are measured consequences of the stated objective.
"""
from __future__ import annotations

from .baselines import severity_greedy
from .derive import Derived, derive
from .diff import diff_plans, input_changes
from .evaluate import Plan, evaluate, fuel_used_dl, normalize_plan, served_of, service_objective
from .model import solve
from .report import build_plan_response, metric_deltas
from .scenario import apply_effect


def explain(sc: dict, d: Derived, plan: Plan, z: str, r: str) -> dict:
    plan = normalize_plan(plan, d)
    if z not in d.zones or r not in d.resources:
        return {"status": "ERROR", "error": f"unknown zone/resource {z}/{r}"}
    units = plan[z][r]
    y = served_of(plan, d)
    served = y[z][r]
    coef = d.coef(z, r)
    contribution = coef * served
    # marginal value of the LAST unit (holding everything else fixed)
    if units > 0:
        plan_minus = {zz: dict(row) for zz, row in plan.items()}
        plan_minus[z][r] -= 1
        marginal_last = service_objective(plan, d) - service_objective(plan_minus, d)
    else:
        marginal_last = 0
    # value lost if one unit is removed AND the solver re-optimizes the rest
    base_obj = service_objective(plan, d)
    resolved = None
    if units > 0:
        res = solve(sc, d, bounds={(z, r): (0, units - 1)}, hint=plan)
        if res.status in ("OPTIMAL", "FEASIBLE"):
            resolved = {"status": res.status, "objective": res.service_objective,
                        "value_lost": base_obj - res.service_objective,
                        "value_lost_pct": round(100.0 * (base_obj - res.service_objective) / abs(base_obj), 2) if base_obj else None,
                        "plan": res.plan, "diff": diff_plans(plan, res.plan, d, d),
                        "metric_deltas": metric_deltas(evaluate(plan, sc, d), evaluate(res.plan, sc, d))}
        else:
            resolved = {"status": res.status, "warnings": res.warnings}

    # which constraints bind for this pair
    binding = []
    used_r = sum(plan[zz][r] for zz in d.zones)
    if used_r >= d.available[r]:
        binding.append({"type": "resource_exhausted", "detail": f"all {d.available[r]} {r} units are assigned"})
    slack_dl = d.fuel_budget_dl - fuel_used_dl(plan, d)
    if d.eligible[z][r] and slack_dl < d.fuel_dl[z][r]:
        binding.append({"type": "fuel_binding", "detail": f"fuel slack {slack_dl / 10:.1f} L < one more unit here ({d.fuel_l[z][r]:.1f} L)"})
    if served >= d.demand[z][r] and units > 0:
        binding.append({"type": "demand_cap_reached", "detail": f"demand {d.demand[z][r]} fully served"})
    if r == "medical_team" and d.deep_water[z] and units == 2 * plan[z]["rescue_boat"]:
        binding.append({"type": "access_coupling_tight", "detail": "medical teams = 2 x boats (deep-water access rule)"})
    if not d.eligible[z][r]:
        why = ("zone unreachable" if not d.reachable[z] else
               f"travel {d.travel_h[z][r]:.2f} h > {d.T_max:.0f} h" if d.travel_h[z][r] > d.T_max else
               "zero capacity in window" if d.capacity[z][r] == 0 else "no demand / no units")
        binding.append({"type": "ineligible", "detail": why})

    return {
        "status": "OK", "zone": z, "zone_name": d.zone_name[z], "resource": r,
        "urgency": round(d.urgency[z], 1), "priority": d.priority[r],
        "demand": d.demand[z][r], "capacity_per_unit": d.capacity[z][r],
        "units": units, "served": served, "unmet": d.demand[z][r] - served,
        "travel_h": None if not d.reachable[z] else round(d.travel_h[z][r], 2),
        "fuel_l_per_unit": round(d.fuel_l[z][r], 1),
        "objective_coefficient_per_person": coef,
        "objective_contribution": contribution,
        "objective_contribution_pct": round(100.0 * contribution / base_obj, 2) if base_obj else None,
        "marginal_value_last_unit": marginal_last,
        "binding_constraints": binding,
        "remove_one_and_reoptimize": resolved,
        "eligible": d.eligible[z][r],
    }


def _resolve_and_report(sc: dict, d: Derived, base_plan: Plan, label: str, *, bounds=None,
                        sc_new: dict | None = None) -> dict:
    """Shared tail for COMPARE / WHAT-IF: re-solve, then report deltas against base_plan."""
    base_plan = normalize_plan(base_plan, d)
    sc2 = sc_new if sc_new is not None else sc
    d2 = derive(sc2) if sc_new is not None else d
    hint = severity_greedy(d2) if sc_new is not None else base_plan
    res = solve(sc2, d2, bounds=bounds, hint=hint)
    base_metrics = evaluate(base_plan, sc, d)
    out = {"type": label, "status": res.status, "solve_ms": round(res.solve_ms, 1),
           "warnings": list(res.warnings), "base_objective": base_metrics["objective"]}
    if res.status not in ("OPTIMAL", "FEASIBLE"):
        out["message"] = f"No feasible plan satisfies this change (solver: {res.status})."
        return out
    new_metrics = evaluate(res.plan, sc2, d2)
    deltas = metric_deltas(base_metrics, new_metrics)
    out.update({
        "objective": new_metrics["objective"],
        "objective_delta": new_metrics["objective"] - base_metrics["objective"],
        "objective_delta_pct": deltas["objective_pct"],
        "metric_deltas": deltas,
        "diff": diff_plans(base_plan, res.plan, d, d2),
        "plan_response": build_plan_response(sc2, d2, res.plan, status=res.status, solve_ms=res.solve_ms,
                                             method="cp_sat_" + label, warnings=res.warnings),
        "input_changes": input_changes(d, d2) if sc_new is not None else [],
    })
    pct = deltas["objective_pct"]
    if pct is None:
        out["message"] = "Objective comparison unavailable."
    elif pct < 0:
        out["message"] = f"The best plan with this change scores {abs(pct):.2f}% lower on the stated objective."
    elif pct > 0:
        out["message"] = f"The best plan with this change scores {pct:.2f}% higher on the stated objective."
    else:
        out["message"] = "The best plan with this change scores the same on the stated objective."
    return out


def compare_force_move(sc: dict, d: Derived, base_plan: Plan, resource: str,
                       from_zone: str, to_zone: str, units: int = 1) -> dict:
    base_plan = normalize_plan(base_plan, d)
    if resource not in d.resources or from_zone not in d.zones or to_zone not in d.zones:
        return {"type": "force_move", "status": "ERROR", "message": "unknown zone or resource"}
    cur_from, cur_to = base_plan[from_zone][resource], base_plan[to_zone][resource]
    if cur_from < units:
        return {"type": "force_move", "status": "ERROR",
                "message": f"{from_zone} has only {cur_from} {resource} unit(s) to move"}
    bounds = {(from_zone, resource): (0, cur_from - units),
              (to_zone, resource): (cur_to + units, d.available[resource])}
    out = _resolve_and_report(sc, d, base_plan, "force_move", bounds=bounds)
    out["forced"] = {"resource": resource, "from": from_zone, "to": to_zone, "units": units}
    return out


def what_if(sc: dict, d: Derived, base_plan: Plan, effect: dict) -> dict:
    sc2 = apply_effect(sc, effect)
    out = _resolve_and_report(sc, d, base_plan, "param_change", sc_new=sc2)
    out["effect"] = effect
    return out


def remove_zone(sc: dict, d: Derived, base_plan: Plan, zone: str) -> dict:
    if zone not in d.zones:
        return {"type": "remove_zone", "status": "ERROR", "message": "unknown zone"}
    bounds = {(zone, r): (0, 0) for r in d.resources}
    out = _resolve_and_report(sc, d, base_plan, "remove_zone", bounds=bounds)
    out["zone"] = zone
    return out


def uniqueness(sc: dict, d: Derived, base_plan: Plan) -> dict:
    """Re-solve with objective >= optimum and sum|x - x*| >= 1."""
    base_plan = normalize_plan(base_plan, d)
    opt = service_objective(base_plan, d)
    res = solve(sc, d, forbid_plan=base_plan, min_service_objective=opt)
    if res.status in ("OPTIMAL", "FEASIBLE"):
        return {"alternative_optimal_plans_exist": True, "status": res.status,
                "answer": "yes", "objective": opt,
                "alternative_plan": res.plan,
                "diff": diff_plans(base_plan, res.plan, d, d),
                "note": "Another plan reaches the same objective value; the displayed plan is one of several optima."}
    if res.status == "INFEASIBLE":
        return {"alternative_optimal_plans_exist": False, "status": res.status, "answer": "no",
                "objective": opt, "note": "No other plan reaches the optimum: the displayed plan is the unique optimum."}
    return {"alternative_optimal_plans_exist": None, "status": res.status, "answer": "unknown",
            "objective": opt, "note": f"Uniqueness check inconclusive (solver: {res.status})."}
